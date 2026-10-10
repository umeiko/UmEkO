import pytest
from fastapi.testclient import TestClient

from umeko.cancellation import OperationCancelled
from umeko.config import ModelConfig, Settings
from umeko.file_operations import operate_files
from umeko.server.app import create_app
from umeko.session import Session
from umeko.skills.file_tools import file_operate, build_file_tools


@pytest.fixture
def sandbox(tmp_path):
    root = tmp_path / "session"
    allowed = tuple(root / name for name in ("workspace", "attachments", "generate"))
    for directory in allowed:
        directory.mkdir(parents=True)
    (tmp_path / "outside.txt").write_text("private", encoding="utf-8")
    return root, allowed


def test_file_and_directory_operations(sandbox):
    root, allowed = sandbox
    operate = lambda op, path, target="", **kwargs: operate_files(op, path, target, root=root, allowed_roots=allowed, **kwargs)
    original = root / "attachments/文档.txt"
    original.write_text("original", encoding="utf-8")
    operate("mkdir", "workspace/nested/reports", recursive=True)
    copied = operate("cp", "attachments/文档.txt", "workspace/nested/reports/copied.txt")
    assert original.read_text(encoding="utf-8") == copied.read_text() == "original"
    with pytest.raises(ValueError, match="已存在"):
        operate("cp", "attachments/文档.txt", "workspace/nested/reports/copied.txt")
    original.write_text("new", encoding="utf-8")
    operate("cp", "attachments/文档.txt", "workspace/nested/reports/copied.txt", overwrite=True)
    assert copied.read_text() == "new"
    with pytest.raises(ValueError, match="recursive"):
        operate("cp", "workspace/nested", "generate/archive")
    operate("cp", "workspace/nested", "generate/archive", recursive=True)
    moved = operate("mv", "generate/archive", "generate/renamed")
    assert not (root / "generate/archive").exists() and (moved / "reports/copied.txt").is_file()
    with pytest.raises(OSError):
        operate("rm", "generate/renamed")
    operate("rm", "generate/renamed", recursive=True)
    assert not moved.exists()
    operate("rm", "attachments/文档.txt")
    assert not original.exists()


@pytest.mark.parametrize("path", ["../outside.txt", "client/skills/private.md", ".", "workspace", "attachments", "generate"])
@pytest.mark.parametrize("operation", ["cp", "mv", "rm", "mkdir"])
def test_operations_cannot_escape_or_change_protected_roots(sandbox, path, operation):
    root, allowed = sandbox
    with pytest.raises((ValueError, FileNotFoundError)):
        operate_files(operation, path, "generate/copy.txt" if operation in {"cp", "mv"} else "", root=root, allowed_roots=allowed, recursive=True)
    assert (root.parent / "outside.txt").read_text() == "private"
    assert all(directory.is_dir() for directory in allowed)


def test_targets_and_recursive_links_are_checked_before_mutation(sandbox):
    root, allowed = sandbox
    source = root / "workspace/folder"
    source.mkdir()
    (source / "file.txt").write_text("inside")
    for target in ("../copy", "client/copy", "workspace/folder/inside"):
        with pytest.raises(ValueError):
            operate_files("cp", "workspace/folder", target, root=root, allowed_roots=allowed, recursive=True)
    try:
        (source / "linked").symlink_to(root.parent / "outside.txt")
    except OSError:
        pytest.skip("Symlink creation requires privileges on this Windows host")
    for operation in ("cp", "mv", "rm"):
        with pytest.raises(ValueError, match="链接"):
            operate_files(operation, "workspace/folder", "generate/copied" if operation != "rm" else "", root=root, allowed_roots=allowed, recursive=True)
    assert not (root / "generate/copied").exists()
    assert (source / "file.txt").read_text() == "inside"


def test_cancellation_and_cli_boundary(sandbox):
    root, _ = sandbox
    with pytest.raises(OperationCancelled):
        operate_files("mkdir", "generate/new", root=root, should_cancel=lambda: True)
    output = root / "generate"
    (output / "a.txt").write_text("hello")
    assert "已复制" in file_operate("cp", "a.txt", "b.txt", root=output)
    assert "错误" in file_operate("rm", "../attachments", root=output, recursive=True)
    assert (output / "b.txt").read_text() == "hello"


def test_tool_arguments_cannot_replace_security_boundaries(sandbox):
    root, allowed = sandbox
    session = Session(Settings(ModelConfig("fixture", "unused-key", "http://unused.invalid")), root / "generate", skill_dir=root / "client/skills")
    tools = {tool.name: tool for tool in build_file_tools(session, None, readable_root=root, readable_roots=allowed)}
    for name, operation in (("file_operate", "rm"), ("archive_tool", "extract")):
        with pytest.raises(TypeError):
            tools[name].handler(operation=operation, path="../outside.txt", root=None)
    with pytest.raises(ValueError, match="布尔"):
        operate_files("rm", "workspace", root=root, recursive="false")
    assert (root.parent / "outside.txt").read_text() == "private"


@pytest.mark.parametrize("prefix", ["", "/doc-master/consistency/image-text"])
def test_agent_and_workspace_share_operations_and_persistent_attachment_ids(tmp_path, prefix):
    app = create_app(Settings(ModelConfig("fixture", "unused-key", "http://unused.invalid"), base_path=prefix),
                     data_root=tmp_path / "data", workspace_root=tmp_path / "output")
    with TestClient(app) as client:
        client.post(prefix + "/v1/auth/register", json={"username": "file-operator", "password": "fixture-pass"}).raise_for_status()
        sid = client.post(prefix + "/v1/sessions", json={}).json()["id"]
        base = prefix + f"/v1/sessions/{sid}"
        uploaded = client.post(base + "/files?filename=original.txt", content=b"content").json()
        service = app.state.agent_service
        state = service.get_session(sid)
        tool = state.agent._skills["file_operate"]
        assert "file_operate" in state.agent._subagent._skills
        assert "已移动" in tool.handler(operation="mv", path="attachments/original.txt", target="workspace/moved.txt")
        expected = state.root / "workspace/moved.txt"
        assert state.files[uploaded["id"]] == expected
        assert service.store.session_files(sid)[uploaded["id"]] == expected
        response = client.post(base + "/workspace/transfer", json={"source": "workspace/moved.txt", "target": "generate/copy.txt", "operation": "copy"})
        assert response.status_code == 200 and response.json()["path"] == "generate/copy.txt"
        state.agent.close()
        service.sessions.pop(sid)
        restored = service.get_session(sid)
        assert restored.files[uploaded["id"]] == expected
        client.delete(base + "/workspace/entries?path=workspace/moved.txt").raise_for_status()
        assert uploaded["id"] not in restored.files
        # Recreating the same path must not resurrect a deleted attachment ID.
        expected.write_text("replacement")
        assert uploaded["id"] not in service.store.session_files(sid)
        assert client.get(base + "/workspace/files/raw/generate/copy.txt").content == b"content"
