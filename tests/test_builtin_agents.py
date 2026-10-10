from __future__ import annotations

import json
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import zipfile

import pytest
from fastapi.testclient import TestClient

from umeko.config import ModelConfig, Settings
from umeko.host.agents import AgentRegistry
from umeko.host.builtin_agents import ASSETS, INSTALL_KEY, install_builtin_agents
from umeko.host.storage import Store
from umeko.server.app import create_app
from umeko.skills.pack_reader import read_pack_file
from umeko.skills.script_runner import run_skill_script


def app_for(tmp_path, prefix=""):
    return create_app(
        Settings(ModelConfig("fixture", "fixture-key", "http://unused.invalid"), base_path=prefix),
        data_root=tmp_path / "data", workspace_root=tmp_path / "output",
    )


@pytest.mark.parametrize("prefix", ["", "/doc-master/consistency/image-text"])
def test_builtin_bootstrap_card_and_task_skill_selection(tmp_path, prefix):
    app = app_for(tmp_path, prefix)
    service, store = app.state.agent_service, app.state.store
    definition = service.agent_registry.by_slug("image-qc")
    assert definition["name"] == "图像质检"
    assert definition["skill_names"] == ["doc-image-qc.md"]
    assert definition["default_model_id"] is None
    assert definition["default_vision_model_id"] is None
    assert store.config()[INSTALL_KEY] == "1"
    with TestClient(app) as client:
        base = prefix + "/agent/image-qc"
        card = client.get(base + "/.well-known/agent-card.json")
        assert card.status_code == 200
        assert card.json()["name"] == "图像质检"
        assert [s["id"] for s in card.json()["skills"]] == ["doc-image-qc.md"]
        assert "阶段 0" not in card.text and definition["system_prompt"] not in card.text
        assert card.json()["supportedInterfaces"][0]["url"].endswith(base + "/a2a")
        assert client.get(base + "/").json()["mcp"].endswith(base + "/mcp")
        snapshot = service.agent_registry.snapshot(definition)
        vision = ModelConfig("fixture-vision", "fixture-key", "http://unused.invalid")
        owner = store.create_user("builtin-reader", "fixture-pass")
        session = service.create_session(
            user_id=owner["id"], agent_snapshot=snapshot,
            settings=Settings(service.settings.text_model, vision_model=vision),
        )
        try:
            assert (session.root / "client/skills/doc-image-qc.md").is_file()
            assert "doc-image-qc" in session.session.skill_catalog_prompt()
            assert "阶段 0" not in session.session.skill_catalog_prompt()
            assert "image_reasoning" in session.agent._skills
            assert "阶段 0" in session.session.use_skill("doc-image-qc")
            assert "C1" in session.session.call_skill_pack("doc-image-qc", read_pack_file, member="checks.md")
        finally:
            service.evict_session(session.id)


def test_restart_preserves_edits_and_does_not_restore_deleted_defaults(tmp_path):
    app = app_for(tmp_path)
    service, store = app.state.agent_service, app.state.store
    original = service.agent_registry.by_slug("image-qc")
    edited = service.agent_registry.save({**original, "name": "My QC", "enabled": False}, original["id"])
    store.set_default_skill_enabled("doc-image-qc.md", False)
    library = service._skills_library_dir()
    checks = library / "doc-image-qc/checks.md"
    checks.write_text("Custom checks", encoding="utf-8")
    restarted = app_for(tmp_path).state.agent_service
    assert restarted.agent_registry.get(original["id"]) == edited
    assert checks.read_text(encoding="utf-8") == "Custom checks"
    assert not restarted.store.default_skills()[0]["enabled"]
    restarted.agent_registry.delete(original["id"])
    restarted.store.delete_default_skill("doc-image-qc.md")
    checks.unlink()
    final = app_for(tmp_path).state.agent_service
    assert final.agent_registry.list() == []
    assert final.store.default_skills() == []
    assert not checks.exists()


@pytest.mark.parametrize("existing_agent", [False, True])
def test_upgrade_reuses_custom_skill_and_preserves_existing_agent(tmp_path, existing_agent):
    store = Store(tmp_path / "db.sqlite")
    registry = AgentRegistry(store)
    library = Path(os.environ["UMEKO_SKILL_DIR"])
    library.mkdir()
    content = "---\nname: doc-image-qc\ndescription: Customized image checks\n---\nPRIVATE CUSTOM STEPS"
    store.upsert_default_skill("doc-image-qc.md", content)
    store.set_default_skill_enabled("doc-image-qc.md", False)
    (library / "doc-image-qc.md").write_text(content, encoding="utf-8")
    (library / "doc-image-qc").mkdir()
    script = library / "doc-image-qc/render_report.py"
    script.write_text("# Custom report script", encoding="utf-8")
    if existing_agent:
        before = registry.save({"slug": "image-qc", "name": "Custom Agent", "description": "Custom service", "skill_names": []})
    assert install_builtin_agents(registry, library)
    definition = registry.list()[0]
    if existing_agent:
        assert definition == before
    else:
        assert not definition["enabled"]  # Do not reactivate a skill deliberately disabled before upgrade.
    assert store.default_skill("doc-image-qc.md") == content
    assert script.read_text(encoding="utf-8") == "# Custom report script"
    assert (library / "doc-image-qc/checks.md").is_file()
    assert not install_builtin_agents(registry, library)


@pytest.mark.parametrize("initialized", [False, True])
@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_upgrade_replaces_only_recognized_stock_report(tmp_path, monkeypatch, initialized, newline):
    from umeko.host import builtin_agents

    store = Store(tmp_path / "db.sqlite")
    registry = AgentRegistry(store)
    library = Path(os.environ["UMEKO_SKILL_DIR"])
    script = library / "doc-image-qc/render_report.py"
    script.parent.mkdir(parents=True)
    # Register a controlled old stock version; real stock digests are fixed in the installer.
    stock = "# Stock report v1\nprint('old report')\n"
    script.write_bytes(stock.replace("\n", newline).encode("utf-8"))
    monkeypatch.setattr(builtin_agents, "_STOCK_REPORT_DIGESTS", {hashlib.sha256(stock.encode()).hexdigest()})
    checks = script.with_name("checks.md")
    checks.write_text("Custom checklist", encoding="utf-8")
    if initialized:
        store.set_config({INSTALL_KEY: "1"})
    assert install_builtin_agents(registry, library)
    assert script.read_bytes() == (ASSETS / "doc-image-qc/render_report.py").read_bytes()
    assert checks.read_text(encoding="utf-8") == "Custom checklist"
    assert not install_builtin_agents(registry, library)
    script.write_text("# Customized report", encoding="utf-8")
    assert not install_builtin_agents(registry, library)
    assert script.read_text(encoding="utf-8") == "# Customized report"
    script.unlink()
    assert not install_builtin_agents(registry, library)
    assert not script.exists()


def test_stock_skill_upgrade_preserves_customizations_and_disabling(tmp_path, monkeypatch):
    from umeko.host import builtin_agents

    store = Store(tmp_path / "db.sqlite")
    registry = AgentRegistry(store)
    library = Path(os.environ["UMEKO_SKILL_DIR"])
    library.mkdir()
    source = library / "doc-image-qc.md"
    stock = "---\nname: doc-image-qc\ndescription: Old stock QC\n---\nOLD STOCK STEPS"
    monkeypatch.setattr(builtin_agents, "_STOCK_SKILL_DIGESTS", {hashlib.sha256(stock.encode()).hexdigest()})
    source.write_text(stock, encoding="utf-8")
    store.upsert_default_skill("doc-image-qc.md", stock)
    store.set_default_skill_enabled("doc-image-qc.md", False)
    store.set_config({INSTALL_KEY: "1"})
    assert install_builtin_agents(registry, library)
    latest = (ASSETS / "doc-image-qc.md").read_text(encoding="utf-8")
    assert source.read_text(encoding="utf-8") == store.default_skill("doc-image-qc.md") == latest
    assert not store.default_skills()[0]["enabled"]
    assert not install_builtin_agents(registry, library)
    store.upsert_default_skill("doc-image-qc.md", "Custom DB skill")
    assert not install_builtin_agents(registry, library)
    assert store.default_skill("doc-image-qc.md") == "Custom DB skill"
    source.write_text("Custom library skill", encoding="utf-8")
    store.upsert_default_skill("doc-image-qc.md", stock)
    assert not install_builtin_agents(registry, library)
    assert source.read_text(encoding="utf-8") == "Custom library skill"
    assert store.default_skill("doc-image-qc.md") == stock
    source.unlink()
    store.delete_default_skill("doc-image-qc.md")
    assert not install_builtin_agents(registry, library)
    assert not source.exists() and store.default_skill("doc-image-qc.md") is None


@pytest.mark.parametrize("doc_dir", ["", "workspace/docs"])
@pytest.mark.parametrize("frozen", [False, True])
def test_bundled_report_renders_and_packages_images(tmp_path, doc_dir, frozen, monkeypatch):
    app = app_for(tmp_path)
    service = app.state.agent_service
    root = tmp_path / "session"
    generate = root / "generate"
    generate.mkdir(parents=True)
    relative_image = "attachments/sample.png" if not doc_dir else "sample.png"
    image = root / doc_dir / relative_image
    image.parent.mkdir(parents=True, exist_ok=True)
    image.write_bytes(b"image fixture bytes")
    report = {"document": "image-inspection", "items": [{
        "image": relative_image, "status": "WARN", "loc": "Uploaded image",
        "checks": [{"id": "C1", "name": "Consistency", "status": "NA", "note": "No reference document"}],
    }]}
    (generate / "qc-report.json").write_text(json.dumps(report), encoding="utf-8")
    if frozen:
        from umeko.skills import script_runner

        native_popen = subprocess.Popen
        entry = Path(__file__).resolve().parents[1] / "run_server.py"

        def frozen_child(command, **kwargs):
            assert command[1:] == ["--run-skill-script", "doc-image-qc", "render_report.py"]
            # Exercise the executable's actual worker entry with a Python interpreter.
            return native_popen([command[0], str(entry), *command[1:]], **kwargs)

        monkeypatch.setattr(sys, "frozen", True, raising=False)
        monkeypatch.setattr(script_runner.subprocess, "Popen", frozen_child)
    result = run_skill_script("doc-image-qc", "render_report.py", json.dumps({
        "data_path": "generate/qc-report.json", "doc_dir": doc_dir,
    }), workdir=generate, session_root=root)
    assert "HTML 报告已生成" in result
    html = (generate / "qc-report-image-inspection.html").read_text(encoding="utf-8")
    expected_src = "../" + (doc_dir + "/" if doc_dir else "") + relative_image
    assert f'src="{expected_src}"' in html
    assert '<span class="check-name">Consistency</span>' in html
    assert "图片内容与文中临近描述是否一致" in html
    with zipfile.ZipFile(generate / "qc-report-image-inspection.zip") as archive:
        archive_image = (Path(doc_dir) / relative_image).as_posix()
        assert archive.read(archive_image) == b"image fixture bytes"
        assert "No reference document" in archive.read("qc-report.html").decode()
        assert "检查项说明" in archive.read("qc-report.html").decode()
    assert not (image.parent / "qc-report.html").exists()
    assert service._skills_library_dir().joinpath("doc-image-qc/render_report.py").is_file()


@pytest.mark.parametrize("field,path", [("data_path", "../outside.json"), ("doc_dir", "../outside"), ("doc_dir", "client")])
def test_bundled_report_rejects_paths_outside_session_files(tmp_path, field, path):
    root = tmp_path / "session"
    (root / "generate").mkdir(parents=True)
    (root / "generate/qc-report.json").write_text('{"items":[]}', encoding="utf-8")
    payload = {"workdir": str(root / "generate"), "session_root": str(root),
               "args": {"data_path": "generate/qc-report.json", "doc_dir": "", field: path}}
    completed = subprocess.run([sys.executable, str(ASSETS / "doc-image-qc/render_report.py")],
                               input=json.dumps(payload), text=True, encoding="utf-8", capture_output=True, check=True)
    result = json.loads(completed.stdout)
    assert not result["ok"] and result["files"] == []
    assert not list((root / "generate").glob("*.zip"))
