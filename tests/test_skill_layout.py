"""Standard package migration and writable session copies without shared mutations."""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from umeko.config import ModelConfig, Settings
from umeko.server.app import create_app
from umeko.server.admin import create_admin_app
from umeko.skill_layout import entry_path, member_path, migrate_library

BODY = "---\nname: sample\ndescription: Synthetic skill\n---\n# Instructions\nRead the reference.\n"
SCRIPT = '''import json
SKILL_SCRIPT = {"description":"Fixture","usage":"No arguments","input_schema":{"type":"object","properties":{}},"outputs":["fixture"],"example_args":{}}
print(json.dumps({"ok":True,"result":"SESSION_SCRIPT_MARKER","files":[]}))
'''


def app_for(tmp_path, prefix="", admin_prefix=""):
    return create_app(Settings(ModelConfig("fixture", "fixture-key", "https://unused.invalid"), base_path=prefix,
                               admin_base_path=admin_prefix), data_root=tmp_path / "data", workspace_root=tmp_path / "output")


def test_legacy_files_move_once_and_conflicts_and_deletions_are_preserved(tmp_path):
    library = tmp_path / "library"
    (library / "sample").mkdir(parents=True)
    (library / "sample.md").write_text(BODY, encoding="utf-8")
    (library / "sample/checks.md").write_text("Custom reference", encoding="utf-8")
    (library / "sample/run.py").write_text(SCRIPT, encoding="utf-8")
    (library / "sample/config.json").write_text("{}", encoding="utf-8")
    migrate_library(library)
    assert not (library / "sample.md").exists()
    assert entry_path(library, "sample").read_text(encoding="utf-8") == BODY
    assert member_path(library, "sample", "checks.md").relative_to(library).as_posix() == "sample/references/checks.md"
    assert member_path(library, "sample", "run.py").read_text(encoding="utf-8") == SCRIPT
    (library / "sample/checks.md").write_text("Conflicting legacy reference", encoding="utf-8")
    migrate_library(library)
    assert member_path(library, "sample", "checks.md").read_text(encoding="utf-8") == "Custom reference"
    assert (library / "sample/checks.md").read_text(encoding="utf-8") == "Conflicting legacy reference"
    (library / "sample/assets/config.json").unlink()
    migrate_library(library)
    assert not (library / "sample/assets/config.json").exists()


def test_model_edits_and_executes_only_its_dispatched_copy_and_restore_preserves_changes(tmp_path):
    app = app_for(tmp_path)
    service = app.state.agent_service
    owner = service.store.create_user("copy-owner", "fixture-pass")
    definition = service.agent_registry.by_slug("flowchart-correction")
    snapshot = service.agent_registry.snapshot(definition)
    first = service.create_session(user_id=owner["id"], agent_snapshot=snapshot)
    second = service.create_session(user_id=owner["id"], agent_snapshot=snapshot)
    relative = "client/skills/drawio-correction/scripts/prepare_correction.py"
    original = (second.root / relative).read_bytes()
    tools = first.agent._skills
    assert "文件已写入" in tools["write_file"].handler(path=relative, content=SCRIPT)
    assert "SESSION_SCRIPT_MARKER" in tools["read_document"].handler(path=relative)
    assert "SESSION_SCRIPT_MARKER" in tools["run_skill_script"].handler(pack="drawio-correction", script="prepare_correction.py", args="{}")
    catalogue = tools["list_skill_script"].handler(pack="drawio-correction", script="prepare_correction.py")
    assert json.loads(catalogue)["scripts"][0]["description"] == "Fixture"
    assert "未配置" in tools["read_pack_file"].handler(pack="drawio-flowchart", member="style.md")
    assert "错误" in tools["write_file"].handler(path=str(second.root / relative), content="forbidden")
    style = "client/skills/drawio-correction/references/style.md"
    assert "文件已写入" in tools["write_file"].handler(path=style, content="Custom session style")
    assert "Custom session style" in tools["read_pack_file"].handler(pack="drawio-correction", member="style.md")
    assert (second.root / relative).read_bytes() == original
    assert member_path(service._skills_library_dir(), "drawio-correction", "prepare_correction.py").read_bytes() == original
    first_id = first.id
    service.evict_session(first_id)
    restored = service.get_session(first_id)
    assert (restored.root / relative).read_text(encoding="utf-8") == SCRIPT
    assert (restored.root / style).read_text(encoding="utf-8") == "Custom session style"
    service.evict_session(restored.id)
    service.evict_session(second.id)
    service.run_manager.shutdown()


@pytest.mark.parametrize("prefix,admin_prefix", [("", ""), ("/teams/diagrams/work", "/operations/console")])
def test_skill_tree_and_member_preview_save_use_independent_prefixes_and_auth(tmp_path, prefix, admin_prefix):
    app = app_for(tmp_path, prefix, admin_prefix)
    service, store = app.state.agent_service, app.state.store
    owner = store.create_user("tree-owner", "fixture-pass", "admin")
    state = service.create_session(user_id=owner["id"])
    admin_app = create_admin_app(service.settings, service, store)
    with TestClient(app) as client, TestClient(admin_app) as admin:
        assert client.post(prefix + "/v1/auth/login", json={"username": owner["username"], "password": "fixture-pass"}).status_code == 200
        base = prefix + "/v1/sessions/" + state.id
        resources = client.get(base + "/client/skills").json()
        correction = next(item for item in resources if item["name"] == "drawio-correction.md")
        assert {"SKILL.md", "references/style.md", "scripts/prepare_correction.py", "assets/config.json"} <= {item["path"] for item in correction["files"]}
        url = base + "/skill-files/drawio-correction/references/style.md"
        assert client.get(url).status_code == 200
        with state.lock:
            assert client.put(url, json={"content": "Do not race the active run"}).status_code == 409
        assert client.put(url, json={"content": "# Session style"}).status_code == 200
        assert client.get(url).json()["content"] == "# Session style"
        assert client.get(base + "/skill-files/drawio-correction/references/../../../../outside").status_code in {400, 404}
        assert admin.post(admin_prefix + "/admin/login", json={"username": owner["username"], "password": "fixture-pass"}).status_code == 200
        packs = admin.get(admin_prefix + "/admin/v1/skill-library").json()["packs"]
        assert any(p["name"] == "drawio-correction" and p["files"] for p in packs)
        admin_url = admin_prefix + "/admin/v1/skill-scripts/drawio-correction/references/style.md"
        assert "# Session style" not in admin.get(admin_url).json()["content"]
        assert admin.put(admin_prefix + "/admin/v1/skill-members/drawio-correction/references/style.md", json={"content": "# Library style"}).status_code == 201
        assert client.get(url).json()["content"] == "# Session style"
        assert admin.post(admin_prefix + "/admin/logout").status_code == 204
        assert admin.get(admin_url).status_code == 401
        assert admin.put(admin_prefix + "/admin/v1/skill-members/drawio-correction/references/style.md", json={"content": "forbidden"}).status_code == 401
        assert client.post(prefix + "/v1/auth/logout").status_code == 204
        assert client.get(url).status_code == 401
        assert client.put(url, json={"content": "forbidden"}).status_code == 401
