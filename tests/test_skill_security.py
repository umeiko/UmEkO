"""Skill integrity gates use isolated administrator libraries and session copies."""
import io
import json
import os
from pathlib import Path
import shutil
import tarfile
import zipfile

import pytest
from fastapi.testclient import TestClient

from umeko import archives
from umeko.config import ModelConfig, Settings
from umeko.file_operations import operate_files
from umeko.server.app import create_app
from umeko.skill_security import ScriptTrust, SkillSecurityError, guard_skill_write
from umeko.skills import script_runner


SCRIPT = '''import json
from pathlib import Path
from helper import VALUE
base = Path(__file__).parents[1]
style = (base / "references/style.md").read_text(encoding="utf-8")
config = json.loads((base / "assets/config.json").read_text())
print(json.dumps({"ok": True, "result": VALUE + style + config["value"], "files": []}))
'''


@pytest.fixture
def issued(tmp_path):
    library = tmp_path / "library"
    package = library / "sample"
    for name in ("scripts", "references", "assets"):
        (package / name).mkdir(parents=True)
    (package / "SKILL.md").write_text("# Fixture")
    (package / "scripts/run.py").write_text(SCRIPT, encoding="utf-8")
    (package / "scripts/helper.py").write_text('VALUE = "approved: "')
    (package / "references/style.md").write_text("original")
    (package / "assets/config.json").write_text('{"value": " config"}')
    root = tmp_path / "session"
    skills = root / "client/skills"
    skills.mkdir(parents=True)
    shutil.copytree(package, skills / "sample")
    (root / "generate").mkdir()
    (root / "workspace").mkdir()
    trust = ScriptTrust(skills, tmp_path / "private-records")
    trust.issue("sample", library)
    return root, skills, library, trust


def execute(issued, **kwargs):
    root, skills, _, trust = issued
    return script_runner.run_skill_script("sample", "run.py", workdir=root / "generate",
                                         session_root=root, directory=skills, trust=trust, **kwargs)


def test_approved_snapshot_imports_helpers_and_preserves_editable_prose(issued):
    _, skills, _, trust = issued
    (skills / "sample/references/style.md").write_text("session style")
    assert execute(issued) == "approved: session style config"
    assert not list(trust.records.glob("execution-*"))
    assert not list(skills.rglob("*.pyc"))


def test_isolated_subprocess_preserves_utf8_stdin_stdout_and_stderr(issued, monkeypatch):
    root, skills, library, trust = issued
    source = ('import json,sys\n'
              'payload=json.load(sys.stdin)\n'
              'print("进度", file=sys.stderr)\n'
              'print(json.dumps({"ok":True,"result":"收到参数："+payload["args"]["text"]}, ensure_ascii=False))\n')
    (library / "sample/scripts/run.py").write_text(source, encoding="utf-8")
    (skills / "sample/scripts/run.py").write_text(source, encoding="utf-8")
    trust = ScriptTrust(skills, trust.records.parent / "new-approval")
    trust.issue("sample", library)
    progress = []
    assert execute((root, skills, library, trust), args='{"text":"你好世界"}', on_progress=progress.append) == "收到参数：你好世界"
    assert progress == ["进度"]


@pytest.mark.parametrize("relative", ["scripts/run.py", "scripts/helper.py", "assets/config.json"])
def test_modified_code_helpers_or_config_fail_md5_before_launch(issued, monkeypatch, relative):
    _, skills, library, trust = issued
    (skills / "sample" / relative).write_text("tampered")
    # Restoring a session must never approve its current bytes again.
    trust.issue("sample", library)
    monkeypatch.setattr(script_runner.subprocess, "Popen", lambda *a, **kw: pytest.fail("tampered code launched"))
    result = execute(issued)
    assert "SCRIPT_TRUST_REJECTED" in result and "MD5" in result and relative in result


@pytest.mark.parametrize("relative", ["scripts/new.py", "scripts/shadow.pyd", "assets/CONFIG.JSON"])
def test_unissued_protected_file_fails_before_launch(issued, monkeypatch, relative):
    _, skills, _, _ = issued
    path = skills / "sample" / relative
    # CONFIG.JSON aliases the original on Windows; delete it to test an extra path on every OS.
    if relative.endswith("CONFIG.JSON"):
        (skills / "sample/assets/config.json").unlink()
    path.write_text("injected")
    monkeypatch.setattr(script_runner.subprocess, "Popen", lambda *a, **kw: pytest.fail("unissued code launched"))
    assert "SCRIPT_TRUST_REJECTED" in execute(issued)


def test_missing_code_and_sha256_are_checked_after_the_whitelist(issued, monkeypatch):
    _, skills, _, trust = issued
    monkeypatch.setattr(script_runner.subprocess, "Popen", lambda *a, **kw: pytest.fail("invalid integrity launched"))
    record = trust.records / "sample.json"
    manifest = json.loads(record.read_text())
    expected_sha = manifest["files"]["scripts/run.py"]["sha256"]
    manifest["files"]["scripts/run.py"]["sha256"] = "0" * 64
    record.write_text(json.dumps(manifest))
    assert "SHA-256" in execute(issued)
    (skills / "sample/scripts/helper.py").unlink()
    manifest["files"]["scripts/run.py"]["sha256"] = expected_sha
    record.write_text(json.dumps(manifest))
    assert "缺失" in execute(issued)


def test_only_external_administrator_record_can_authorize_execution(issued, monkeypatch):
    root, skills, _, trust = issued
    record = trust.records / "sample.json"
    (skills / "sample/approval.json").write_bytes(record.read_bytes())
    record.unlink()
    monkeypatch.setattr(script_runner.subprocess, "Popen", lambda *a, **kw: pytest.fail("unapproved code launched"))
    assert "白名单" in execute(issued)
    unbound = script_runner.run_skill_script("sample", "run.py", directory=skills, session_root=root)
    assert "SCRIPT_TRUST_REJECTED" in unbound
    with pytest.raises(SkillSecurityError):
        ScriptTrust(skills, skills / "fake-approval")


@pytest.mark.parametrize("script", ["../run.py", "scripts/../scripts/run.py", "scripts\\run.py", "scripts//run.py", "scripts/run.py:stream", "references/run.py"])
def test_noncanonical_script_paths_are_rejected(issued, monkeypatch, script):
    root, skills, _, trust = issued
    monkeypatch.setattr(script_runner.subprocess, "Popen", lambda *a, **kw: pytest.fail("invalid path launched"))
    result = script_runner.run_skill_script("sample", script, directory=skills, trust=trust, session_root=root)
    assert "SCRIPT_PATH_INVALID" in result


def test_approval_to_execution_race_cannot_replace_verified_bytes(issued, monkeypatch):
    _, skills, _, trust = issued
    native = script_runner.subprocess.Popen
    def launch(command, **kwargs):
        (skills / "sample/scripts/helper.py").write_text('VALUE = "injected: "')
        staged = Path(command[-1])
        assert staged.is_relative_to(trust.records)
        assert not staged.is_relative_to(skills)
        assert (staged.parent / "helper.py").read_text() == 'VALUE = "approved: "'
        return native(command, **kwargs)
    monkeypatch.setattr(script_runner.subprocess, "Popen", launch)
    assert execute(issued) == "approved: original config"


def test_pythonpath_injection_and_old_bytecode_do_not_enter_snapshot(issued, monkeypatch, tmp_path):
    _, skills, _, _ = issued
    injection = tmp_path / "injection"
    injection.mkdir()
    sentinel = tmp_path / "injection-ran"
    (injection / "sitecustomize.py").write_text(f'open({str(sentinel)!r}, "w").close()')
    monkeypatch.setenv("PYTHONPATH", str(injection))
    cache = skills / "sample/scripts/__pycache__"
    cache.mkdir()
    (cache / "helper.cpython-311.pyc").write_bytes(b"not trusted bytecode")
    assert execute(issued) == "approved: original config"
    assert not sentinel.exists()


def test_hardlinked_code_is_not_executable(issued):
    _, skills, _, _ = issued
    source = skills / "sample/scripts/run.py"
    try:
        os.link(source, skills / "sample/scripts/alias.txt")
    except OSError:
        pytest.skip("Hard links unavailable on test filesystem")
    assert "SCRIPT_TRUST_REJECTED" in execute(issued)


def test_helper_links_are_rejected_before_execution(issued):
    _, skills, library, _ = issued
    helper = skills / "sample/scripts/helper.py"
    helper.unlink()
    try:
        helper.symlink_to(library / "sample/scripts/helper.py")
    except OSError:
        pytest.skip("Symlink creation requires privileges on this host")
    assert "SCRIPT_TRUST_REJECTED" in execute(issued)


@pytest.mark.parametrize("name", ["new.py", "NEW.PY", "config.json", "CONFIG.JSON", "new.py ", "new.py.", "new.py:stream", "__pycache__/cache.txt"])
def test_protected_names_and_windows_aliases_cannot_be_written(issued, name):
    _, skills, _, _ = issued
    with pytest.raises(ValueError):
        guard_skill_write(skills / "sample/assets" / name)


def test_all_transfer_operations_preflight_contents_and_both_paths(issued):
    root, skills, _, _ = issued
    roots = (root / "workspace", root / "generate", skills)
    (root / "workspace/input.txt").write_text("input")
    (root / "workspace/injected").mkdir()
    (root / "workspace/injected/payload.py").write_text("bad")
    operations = [
        ("cp", "workspace/input.txt", "client/skills/sample/scripts/new.py"),
        ("mv", "workspace/input.txt", "client/skills/sample/assets/config.json"),
        ("cp", "workspace/injected", "client/skills/sample/assets/copied"),
        ("mv", "client/skills/sample/scripts", "workspace/moved"),
        ("rm", "client/skills/sample/scripts", ""),
        ("rm", "client/skills/sample/assets/config.json", ""),
        ("mkdir", "client/skills/sample/new.py", ""),
    ]
    for operation, source, target in operations:
        with pytest.raises(ValueError):
            operate_files(operation, source, target, root=root, allowed_roots=roots, recursive=True)
    assert (root / "workspace/input.txt").read_text() == "input"
    assert not (skills / "sample/assets/copied").exists()
    assert (skills / "sample/scripts/run.py").is_file()
    # Read/copy out is allowed; an ordinary output .py is never an approved skill.
    operate_files("cp", "client/skills/sample/scripts/run.py", "workspace/copy.py", root=root, allowed_roots=roots)
    operate_files("cp", "workspace/input.txt", "client/skills/sample/references/notes.md", root=root, allowed_roots=roots)


@pytest.mark.parametrize("suffix", [".zip", ".tar.gz"])
@pytest.mark.parametrize("member", ["nested/run.py", "nested/CONFIG.JSON"])
def test_native_archive_rejects_protected_members_before_publishing(issued, suffix, member):
    root, skills, _, _ = issued
    try:
        archives.seven_zip_binary()
    except ValueError:
        pytest.skip("Native 7-Zip not installed")
    archive = skills / "sample/assets" / ("upload" + suffix)
    if suffix == ".zip":
        with zipfile.ZipFile(archive, "w") as stream:
            stream.writestr("notes.txt", "safe")
            stream.writestr(member, "bad")
    else:
        with tarfile.open(archive, "w:gz") as stream:
            entry = tarfile.TarInfo(member)
            entry.size = 3
            stream.addfile(entry, io.BytesIO(b"bad"))
    before = set((skills / "sample/assets").iterdir())
    with pytest.raises(SkillSecurityError):
        archives.extract_archive(archive)
    assert set((skills / "sample/assets").iterdir()) == before
    outside = root / "workspace" / archive.name
    shutil.copyfile(archive, outside)
    assert any(path.name == Path(member).name for path in archives.extract_archive(outside).rglob("*"))


@pytest.mark.parametrize("prefix", ["", "/teams/example/work"])
def test_user_api_and_model_tools_enforce_readonly_code_and_config(tmp_path, prefix):
    app = create_app(Settings(ModelConfig("fixture", "unused", "https://unused.invalid"), base_path=prefix),
                     data_root=tmp_path / "data", workspace_root=tmp_path / "output")
    service = app.state.agent_service
    with TestClient(app) as client:
        client.post(prefix + "/v1/auth/register", json={"username": "readonly-fixture", "password": "fixture-pass"}).raise_for_status()
        sid = client.post(prefix + "/v1/sessions", json={}).json()["id"]
        state = service.get_session(sid)
        tools = state.agent._skills
        base = prefix + f"/v1/sessions/{sid}"
        package = "client/skills/drawio-correction"
        resources = client.get(base + "/client/skills").json()
        files = next(p["files"] for p in resources if p["name"] == "drawio-correction.md")
        for member in ["scripts/prepare_correction.py", "assets/config.json"]:
            path = package + "/" + member
            url = base + "/skill-files/drawio-correction/" + member
            original = (state.root / path).read_bytes()
            assert client.get(url).json()["readonly"] is True
            assert next(f for f in files if f["path"] == member)["readonly"] is True
            assert client.put(url, json={"content": "forbidden"}).status_code == 400
            assert client.delete(base + "/workspace/entries", params={"path": path}).status_code == 400
            assert client.post(base + "/workspace/files", params={"path": str(Path(path).parent).replace("\\", "/"), "filename": Path(path).name}, content=b"forbidden").status_code == 400
            assert "只读" in tools["write_file"].handler(path=path, content="forbidden")
            assert "只读" in tools["replace_in_file"].handler(path=path, old_text="{", new_text="injected")
            assert not tools["read_document"].handler(path=path).startswith("错误")
            assert (state.root / path).read_bytes() == original
        for name in ["new.py", "CONFIG.JSON"]:
            target = package + "/assets/" + name
            assert client.post(base + "/workspace/entries", json={"path": target, "type": "file"}).status_code == 400
            assert client.post(base + "/workspace/files", params={"path": package + "/assets", "filename": name}, content=b"bad").status_code == 400
        assert client.post(base + "/workspace/entries", json={"path": "workspace/input.txt", "type": "file"}).status_code == 201
        for operation, source, target in [("copy", "workspace/input.txt", package + "/scripts/new.py"),
                                           ("move", package + "/scripts", "workspace/scripts")]:
            assert client.post(base + "/workspace/transfer", json={"operation": operation, "source": source, "target": target}).status_code == 400
        prose = base + "/skill-files/drawio-correction/references/style.md"
        assert client.put(prose, json={"content": "# Editable session style"}).status_code == 200
        assert client.get(prose).json()["readonly"] is False
        record = service.data_root / "skill_trust" / sid
        assert record.is_dir()
        assert client.delete(prefix + "/v1/sessions/" + sid).status_code == 204
        assert not record.exists()


def test_restore_never_reapproves_tampered_config_and_clone_keeps_issued_version(tmp_path, monkeypatch):
    app = create_app(Settings(ModelConfig("fixture", "unused", "https://unused.invalid")),
                     data_root=tmp_path / "data", workspace_root=tmp_path / "output")
    service = app.state.agent_service
    owner = service.store.create_user("trust-lifecycle", "fixture-pass")
    library = service._skills_library_dir()
    script = library / "drawio-correction/scripts/prepare_correction.py"
    source = 'import json\nprint(json.dumps({"ok":True,"result":"issued version"}))'
    script.write_text(source, encoding="utf-8")
    def run(state):
        return state.agent._skills["run_skill_script"].handler(pack="drawio-correction", script="prepare_correction.py", args="{}")
    try:
        first = service.create_session(user_id=owner["id"])
        second = service.create_session(user_id=owner["id"])
        record = first.session.script_trust.records / "drawio-correction.json"
        baseline = record.read_bytes()
        (first.root / "client/skills/drawio-correction/assets/config.json").write_text("tampered")
        service.evict_session(first.id)
        restored = service.get_session(first.id)
        assert record.read_bytes() == baseline
        with monkeypatch.context() as patch:
            patch.setattr(script_runner.subprocess, "Popen", lambda *a, **kw: pytest.fail("restore approved tampering"))
            assert "MD5" in run(restored)
        script.write_text(source.replace("issued version", "new version"), encoding="utf-8")
        cloned = service.clone_session(second.id, owner["id"])
        assert run(cloned) == run(second) == "issued version"
        fresh = service.create_session(user_id=owner["id"])
        assert run(fresh) == "new version"
        cloned_records = cloned.session.script_trust.records
        service.delete_session_admin(cloned.id)
        assert not cloned_records.exists()
        records = [state.session.script_trust.records for state in [restored, second, fresh]]
        service.delete_user_admin(owner["id"])
        assert not any(path.exists() for path in records)
    finally:
        service.run_manager.shutdown()
