import bz2
import gzip
import io
import lzma
import os
from pathlib import Path
import stat
import subprocess
import tarfile
import zipfile

import pytest
from fastapi.testclient import TestClient

from umeko import archives
from umeko.cancellation import OperationCancelled
from umeko.config import ModelConfig, Settings
from umeko.server.app import create_app
from umeko.skills.file_tools import archive_tool


@pytest.fixture(autouse=True)
def require_native_backend(request):
    if request.node.name not in {"test_tool_relative_paths_use_session_boundary", "test_seven_zip_discovery_respects_explicit_config_and_path", "test_missing_seven_zip_has_actionable_error"}:
        native_binary()


@pytest.mark.parametrize("suffix", [".zip", ".tar", ".tar.gz", ".tar.bz2", ".tar.xz", ".tgz", ".tbz2", ".txz", ".gz", ".bz2", ".xz"])
def test_all_formats_use_native_seven_zip(tmp_path, suffix):
    source = tmp_path / ("bundle" + suffix)
    payload = "图文 content\nsecond line".encode()
    if suffix == ".zip":
        with zipfile.ZipFile(source, "w") as opened:
            opened.writestr("包裹/notes.txt", payload)
    elif suffix.startswith(".tar") or suffix in {".tgz", ".tbz2", ".txz"}:
        mode = {".tar": "w", ".tar.gz": "w:gz", ".tgz": "w:gz", ".tar.bz2": "w:bz2", ".tbz2": "w:bz2", ".tar.xz": "w:xz", ".txz": "w:xz"}[suffix]
        with tarfile.open(source, mode) as opened:
            entry = tarfile.TarInfo("包裹/notes.txt")
            entry.size = len(payload)
            opened.addfile(entry, io.BytesIO(payload))
    else:
        with {".gz": gzip.open, ".bz2": bz2.open, ".xz": lzma.open}[suffix](source, "wb") as opened:
            opened.write(payload)
    assert archives.archive_members(source)
    target = archives.extract_archive(source)
    assert next(entry for entry in target.rglob("*") if entry.is_file()).read_bytes() == payload
    again = archives.extract_archive(source)
    assert again != target and target.is_dir() and again.is_dir()


@pytest.mark.parametrize("name", ["../outside.txt", "/outside.txt", "C:/outside.txt", "..\\outside.txt", "safe/../../outside.txt"])
@pytest.mark.parametrize("kind", ["zip", "tar"])
def test_archive_paths_are_rejected_before_writes(tmp_path, name, kind):
    source = tmp_path / ("unsafe." + kind)
    if kind == "zip":
        with zipfile.ZipFile(source, "w") as opened:
            opened.writestr("valid.txt", "inside")
            opened.writestr(name, "bad")
    else:
        with tarfile.open(source, "w") as opened:
            for path in ("valid.txt", name):
                entry = tarfile.TarInfo(path)
                entry.size = 3
                opened.addfile(entry, io.BytesIO(b"bad"))
    with pytest.raises(ValueError, match="路径"):
        archives.extract_archive(source)
    assert not (tmp_path / "unsafe").exists()
    assert not (tmp_path / "outside.txt").exists()


@pytest.mark.parametrize("kind", ["zip", "tar-symlink", "tar-hardlink"])
def test_archive_links_are_rejected(tmp_path, kind):
    source = tmp_path / ("links.zip" if kind == "zip" else "links.tar")
    if kind == "zip":
        with zipfile.ZipFile(source, "w") as opened:
            entry = zipfile.ZipInfo("link")
            entry.create_system = 3
            entry.external_attr = (stat.S_IFLNK | 0o777) << 16
            opened.writestr(entry, "../outside")
    else:
        with tarfile.open(source, "w") as opened:
            entry = tarfile.TarInfo("link")
            entry.type = tarfile.SYMTYPE if kind == "tar-symlink" else tarfile.LNKTYPE
            entry.linkname = "../outside"
            opened.addfile(entry)
    with pytest.raises(ValueError, match="链接"):
        archives.extract_archive(source)
    assert not (tmp_path / "links").exists()


def test_limits_cancellation_corruption_and_cleanup(tmp_path, monkeypatch):
    source = tmp_path / "compressed.gz"
    with gzip.open(source, "wb") as opened:
        opened.write(b"large" * 100)
    monkeypatch.setattr(archives, "MAX_ARCHIVE_BYTES", 100)
    with pytest.raises(ValueError, match="预算"):
        archives.extract_archive(source)
    assert not (tmp_path / "compressed").exists()
    with pytest.raises(OperationCancelled):
        archives.extract_archive(source, lambda: True)
    broken = tmp_path / "broken.zip"
    broken.write_bytes(b"bad zip")
    with pytest.raises(ValueError, match="损坏"):
        archives.extract_archive(broken)


def test_bulk_extraction_uses_one_native_process_and_cleans_cancelled_output(tmp_path, monkeypatch):
    source = tmp_path / "many.zip"
    with zipfile.ZipFile(source, "w") as opened:
        for number in range(120):
            opened.writestr(f"folder/file-{number}.txt", "content")
    commands = []
    original = archives.subprocess.Popen

    def launch(command, **kwargs):
        commands.append(command)
        return original(command, **kwargs)

    monkeypatch.setattr(archives.subprocess, "Popen", launch)
    target = archives.extract_archive(source)
    assert len(list(target.rglob("*.txt"))) == 120
    assert [command[1] for command in commands] == ["l", "x"]
    with pytest.raises(OperationCancelled):
        archives.extract_archive(source, lambda: (tmp_path / "many_1").exists())
    assert not (tmp_path / "many_1").exists()
    assert (target / "file-0.txt").read_text() == "content"


def test_unknown_stream_size_is_checked_after_native_extraction(tmp_path, monkeypatch):
    source = tmp_path / "large.bz2"
    with bz2.open(source, "wb") as opened:
        opened.write(b"large" * 100)
    monkeypatch.setattr(archives, "MAX_ARCHIVE_BYTES", 100)
    with pytest.raises(ValueError, match="预算"):
        archives.extract_archive(source)
    assert not (tmp_path / "large").exists()


def test_native_tar_special_files_are_rejected_before_writes(tmp_path):
    source = tmp_path / "special.tar"
    with tarfile.open(source, "w") as opened:
        entry = tarfile.TarInfo("pipe")
        entry.type = tarfile.FIFOTYPE
        opened.addfile(entry)
    with pytest.raises(ValueError, match="特殊"):
        archives.extract_archive(source)
    assert not (tmp_path / "special").exists()


def test_zip_create_preserves_files_and_rejects_links_and_self_inclusion(tmp_path):
    source = tmp_path / "input"
    source.mkdir()
    (source / "empty").mkdir()
    (source / "图.txt").write_text("hello", encoding="utf-8")
    destination = archives.create_zip(source, tmp_path / "out")
    with zipfile.ZipFile(destination) as opened:
        assert opened.read("input/图.txt") == b"hello"
        assert "input/empty/" in opened.namelist()
    with pytest.raises(ValueError, match="内部"):
        archives.create_zip(source, source)


def test_zip_create_does_not_interpret_filename_as_a_list_file(tmp_path):
    source = tmp_path / "@files.txt"
    source.write_text("../private.txt")
    (tmp_path.parent / "private.txt").write_text("private")
    destination = archives.create_zip(source, tmp_path / "out")
    with zipfile.ZipFile(destination) as opened:
        assert opened.namelist() == [source.name]
        assert opened.read(source.name) == b"../private.txt"


def test_tool_relative_paths_use_session_boundary(tmp_path):
    root = tmp_path / "session"
    roots = tuple(root / name for name in ("workspace", "attachments", "generate"))
    for directory in roots:
        directory.mkdir(parents=True)
    outside = tmp_path / "outside.zip"
    with zipfile.ZipFile(outside, "w") as opened:
        opened.writestr("private.txt", "private")
    for operation in ("list", "extract", "create"):
        result = archive_tool(operation, "../outside.zip", root=root, readable_roots=roots, display_root=root, output_dir=roots[2])
        assert result.startswith("错误：") and "private" not in result
    assert not (tmp_path / "outside").exists()


def test_seven_zip_discovery_respects_explicit_config_and_path(monkeypatch):
    monkeypatch.setenv("SEVENZIP_PATH", "custom-tool")
    monkeypatch.setattr(archives.shutil, "which", lambda name: "/opt/custom-tool" if name == "custom-tool" else None)
    assert archives.seven_zip_binary() == "/opt/custom-tool"
    monkeypatch.setenv("SEVENZIP_PATH", "broken")
    with pytest.raises(ValueError, match="SEVENZIP_PATH"):
        archives.seven_zip_binary()
    monkeypatch.delenv("SEVENZIP_PATH")
    monkeypatch.setattr(archives.shutil, "which", lambda name: "/usr/bin/7zz" if name == "7zz" else None)
    assert archives.seven_zip_binary() == "/usr/bin/7zz"


def test_missing_seven_zip_has_actionable_error(tmp_path, monkeypatch):
    monkeypatch.setenv("SEVENZIP_PATH", "missing-binary")
    source = tmp_path / "bundle.zip"
    with zipfile.ZipFile(source, "w") as opened:
        opened.writestr("file.txt", "hello")
    with pytest.raises(ValueError, match="SEVENZIP_PATH"):
        archives.extract_archive(source)
    assert not (tmp_path / "bundle").exists()
    assert "SEVENZIP_PATH" in archive_tool("list", str(source))


def native_binary():
    try:
        return archives.seven_zip_binary()
    except ValueError:
        if os.environ.get("UMEKO_TEST_REQUIRE_7ZIP"):
            pytest.fail("7-Zip must be installed for this test job")
        pytest.skip("Native 7-Zip is not installed on this host")


def test_native_seven_zip_list_and_extract(tmp_path, monkeypatch):
    binary = native_binary()
    source = tmp_path / "输入文件.txt"
    source.write_bytes(b"native 7zip")
    archive = tmp_path / "native.7z"
    subprocess.run([binary, "a", "-t7z", "--", str(archive), source.name], cwd=tmp_path, check=True, capture_output=True)
    assert [entry.name for entry in archives.archive_members(archive)] == [source.name]
    target = archives.extract_archive(archive)
    assert (target / source.name).read_bytes() == b"native 7zip"


def test_native_absolute_members_are_rejected(tmp_path, monkeypatch):
    binary = native_binary()
    source = tmp_path / "private.txt"
    source.write_text("private")
    archive = tmp_path / "absolute.7z"
    subprocess.run([binary, "a", "-spf", "--", str(archive), str(source)], check=True, capture_output=True)
    with pytest.raises(ValueError, match="路径"):
        archives.extract_archive(archive)
    assert not (tmp_path / "absolute").exists()


@pytest.mark.parametrize("prefix", ["", "/doc-master/consistency/image-text"])
def test_workspace_and_agent_extract_use_same_native_backend(tmp_path, monkeypatch, prefix):
    app = create_app(Settings(ModelConfig("fixture", "unused-key", "http://unused.invalid"), base_path=prefix),
                     data_root=tmp_path / "data", workspace_root=tmp_path / "output")
    with TestClient(app) as client:
        client.post(prefix + "/v1/auth/register", json={"username": "archive-owner", "password": "fixture-pass"}).raise_for_status()
        sid = client.post(prefix + "/v1/sessions", json={}).json()["id"]
        base = prefix + f"/v1/sessions/{sid}"
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as opened:
            opened.writestr("wrapper/readme.md", "# hello")
        client.post(base + "/files?filename=bundle.zip", content=buffer.getvalue()).raise_for_status()
        response = client.post(base + "/workspace/extract", json={"path": "attachments/bundle.zip"})
        assert response.status_code == 200, response.text
        assert response.json()["path"] == "attachments/bundle"
        assert client.get(base + "/workspace/files/raw/attachments/bundle/readme.md").text == "# hello"
        state = app.state.agent_service.get_session(sid)
        tool = state.agent._skills["archive_tool"]
        assert "readme.md" in tool.handler(operation="list", path="attachments/bundle.zip")
        assert "attachments/bundle_1" in tool.handler(operation="extract", path="attachments/bundle.zip")
        assert "已压缩" in tool.handler(operation="create", path="attachments/bundle")
        downloaded = client.get(base + "/workspace/files/download?path=attachments/bundle")
        assert downloaded.status_code == 200, downloaded.text
        with zipfile.ZipFile(io.BytesIO(downloaded.content)) as opened:
            assert opened.read("bundle/readme.md") == b"# hello"
        client.post(base + "/files?filename=broken.zip", content=b"bad zip").raise_for_status()
        assert client.post(base + "/workspace/extract", json={"path": "attachments/broken.zip"}).status_code == 400
        monkeypatch.setenv("SEVENZIP_PATH", "missing-binary")
        missing = client.post(base + "/workspace/extract", json={"path": "attachments/bundle.zip"})
        assert missing.status_code == 400 and "SEVENZIP_PATH" in missing.text
