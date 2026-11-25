from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess
import sys
import xml.etree.ElementTree as ET

import pytest

from umeko.config import ModelConfig, Settings
from umeko.host.builtin_skills import installation_key
from umeko.server.app import create_app


PACK = Path(__file__).resolve().parents[1] / "umeko/builtin_skills/drawio-design-principle"
NAME = PACK.name
ENTRY = NAME + ".md"
SCRIPT = "generate_principle.py"


def example_model():
    reference = (PACK / "references/mechanism.md").read_text(encoding="utf-8")
    return json.loads(re.search(r"```json\n(.*?)\n```", reference, re.S).group(1))


def run_script(tmp_path, model):
    source = tmp_path / "workspace/model.json"
    source.parent.mkdir()
    source.write_text(json.dumps(model, ensure_ascii=False), encoding="utf-8")
    payload = {"args": {"model_path": "workspace/model.json"},
               "session_root": str(tmp_path), "workdir": str(tmp_path / "generate")}
    result = subprocess.run(
        [sys.executable, str(PACK / "scripts" / SCRIPT)], input=json.dumps(payload),
        text=True, encoding="utf-8", capture_output=True, timeout=15,
    )
    return result.returncode, json.loads(result.stdout)


def test_editable_nodes_icons_feedback_and_assumption(tmp_path):
    model = example_model()
    model["nodes"][1]["assumed"] = True
    code, result = run_script(tmp_path, model)
    assert code == 0 and result["files"] == ["generate/principle.drawio"]
    graph = ET.parse(tmp_path / result["files"][0])
    node = graph.find(".//mxCell[@id='node-control']")
    icon = graph.find(".//mxCell[@id='icon-control']")
    feedback = graph.find(".//mxCell[@id='edge-3']")
    assert "待验证" in node.get("value")
    assert icon.get("parent") == "node-control" and icon.get("style").startswith("rhombus;")
    assert (feedback.get("source"), feedback.get("target")) == ("node-observe", "node-control")
    assert len(feedback.findall("./mxGeometry/Array/mxPoint")) == 2
    assert "exitY=1;entryX=0.25;entryY=1;" in feedback.get("style")


@pytest.mark.parametrize("invalid", ["slot", "edge", "icon"])
def test_invalid_model_produces_no_files(tmp_path, invalid):
    model = example_model()
    if invalid == "slot":
        model["layout"]["worker"] = model["layout"]["control"]
    elif invalid == "edge":
        model["relations"][0]["target"] = "unknown"
    else:
        model["nodes"][0]["icon"] = "unlisted-shape"
    code, result = run_script(tmp_path, model)
    assert code == 1 and result["status"] == "failed" and result["files"] == []
    assert not (tmp_path / "generate").exists()


def test_discovered_and_executed_as_approved_skill(tmp_path, approve_skill_files):
    settings = Settings(ModelConfig("fixture", "fixture-key", "http://unused.invalid"))
    app = create_app(settings, data_root=tmp_path / "data", workspace_root=tmp_path / "output")
    service, store = app.state.agent_service, app.state.store
    assert store.config()[installation_key(ENTRY)] == "1"
    assert not next(skill for skill in store.default_skills() if skill["name"] == ENTRY)["enabled"]

    approve_skill_files(service, NAME)
    store.set_default_skill_enabled(ENTRY, True)
    user = store.create_user("diagram-fixture", "fixture-pass")
    session = service.create_session(user_id=user["id"])
    try:
        service.update_client_resource(session.id, "skills", ENTRY, mounted=True)
        tools = session.agent._skills
        assert "离线" in tools["read_pack_file"].handler(pack=NAME, member="references/icons.md")
        source = session.root / "generate/model.json"
        source.write_text(json.dumps(example_model(), ensure_ascii=False), encoding="utf-8")
        result = tools["run_skill_script"].handler(
            pack=NAME, script=SCRIPT, args=json.dumps({"model_path": "generate/model.json"}),
        )
        assert "generate/principle.drawio" in result
        assert ET.parse(session.root / "generate/principle.drawio").getroot().tag == "mxfile"
    finally:
        service.evict_session(session.id)


def test_export_failure_preserves_principle_and_reports_requested_formats(tmp_path, monkeypatch, approve_skill_files):
    monkeypatch.setenv("UMEKO_DRAWIO_PATH", str(tmp_path / "missing-drawio"))
    settings = Settings(ModelConfig("fixture", "fixture-key", "http://unused.invalid"))
    app = create_app(settings, data_root=tmp_path / "data", workspace_root=tmp_path / "output")
    service, store = app.state.agent_service, app.state.store
    approve_skill_files(service, NAME)
    store.set_default_skill_enabled(ENTRY, True)
    user = store.create_user("diagram-fixture", "fixture-pass")
    session = service.create_session(user_id=user["id"])
    try:
        service.update_client_resource(session.id, "skills", ENTRY, mounted=True)
        workdir = session.root / "generate"
        (workdir / "model.json").write_text(json.dumps(example_model()), encoding="utf-8")
        (workdir / "principle.png").write_bytes(b"old preview")
        result = session.agent._skills["run_skill_script"].handler(
            pack=NAME, script=SCRIPT,
            args=json.dumps({"model_path": "generate/model.json", "formats": ["png", "svg"]}),
        )
        assert "renderer_unavailable" in result and "png 未导出" in result and "svg 未导出" in result
        assert ET.parse(workdir / "principle.drawio").getroot().tag == "mxfile"
        assert not (workdir / "principle.png").exists() and not (workdir / "principle.svg").exists()
    finally:
        service.evict_session(session.id)
