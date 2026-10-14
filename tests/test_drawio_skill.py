from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import re
import runpy
import subprocess
import sys
from types import SimpleNamespace
import xml.etree.ElementTree as ET
import zipfile

from fastapi.testclient import TestClient
from openai.types.chat import ChatCompletionMessage
import pytest

from umeko.config import ModelConfig, Settings
from umeko.host.builtin_agents import INSTALL_KEY
from umeko.host.builtin_skills import ASSETS, installation_key, install_builtin_skills
from umeko.host.storage import Store
from umeko.server.admin import create_admin_app
from umeko.server.app import create_app

PACK = ASSETS / "drawio-flowchart"
FLOWCHART_SKILL = "drawio-flowchart.md"
EXAMPLES = re.findall(r"```xml\n(.*?)```", (PACK / "flowchart.md").read_text(encoding="utf-8"), re.S)
FLOW = next(xml for xml in EXAMPLES if any("rhombus" in c.get("style", "") for c in ET.fromstring(xml).iter("mxCell")))
ARCH = re.search(r"```xml\n(.*?)```", (PACK / "architecture.md").read_text(encoding="utf-8"), re.S).group(1)


def app_for(tmp_path, user_prefix="", admin_prefix=""):
    settings = Settings(ModelConfig("fixture", "fixture-key", "http://unused.invalid"),
                        base_path=user_prefix, admin_base_path=admin_prefix)
    return create_app(settings, data_root=tmp_path / "data", workspace_root=tmp_path / "output")


def run_script(tmp_path, args, pack=PACK, script="generate_drawio.py"):
    root = tmp_path / "session"
    workdir = root / "generate"
    workdir.mkdir(parents=True, exist_ok=True)
    result = subprocess.run([sys.executable, str(pack / script)],
                            input=json.dumps({"args": args, "workdir": str(workdir), "session_root": str(root)}),
                            text=True, encoding="utf-8", capture_output=True, timeout=20,
                            env={**os.environ, "PYTHONIOENCODING": "utf-8",
                                 "UMEKO_DRAWIO_PATH": str(tmp_path / "not-installed")})
    body = json.loads(result.stdout)
    assert result.returncode == (0 if body["ok"] else 1), result.stderr
    return body, root


@pytest.mark.parametrize("user_prefix,admin_prefix", [("", ""), ("/teams/docs/workbench", "/operations/umeko/admin")])
def test_admin_dispatch_session_generation_and_download(tmp_path, user_prefix, admin_prefix):
    app = app_for(tmp_path, user_prefix, admin_prefix)
    service, store = app.state.agent_service, app.state.store
    admin_app = create_admin_app(service.settings, service, store)
    account = store.create_user("skill-admin", "fixture-pass", role="admin")
    sessions = []
    try:
        assert store.config()[installation_key(FLOWCHART_SKILL)] == "1"
        assert {a["slug"] for a in service.agent_registry.list()} == {
            "image-qc", "flow-chart-agent", "image-resioning-agent"}
        with TestClient(admin_app) as admin, TestClient(app) as user:
            api = admin_prefix + "/admin/v1/"
            assert admin.get(api + "skill-library").status_code == 401
            assert admin.post(admin_prefix + "/admin/login", json={"username": account["username"], "password": "fixture-pass"}).status_code == 200
            listing = admin.get(api + "skill-library").json()["packs"]
            pack = next(p for p in listing if p["name"] == "drawio-flowchart")
            assert pack["imported"] and pack["enabled"]
            assert admin.post(api + f"default-skills/{FLOWCHART_SKILL}/toggle").json()["enabled"] is False
            assert "generate_drawio.py" in {s["name"] for s in pack["scripts"]}
            assert {"flowchart.md", "architecture.md", "config.json"} <= {s["name"] for s in pack["members"]}
            old = service.create_session(user_id=account["id"])
            sessions.append(old)
            assert not (old.root / "client/skills" / FLOWCHART_SKILL).exists()
            assert admin.post(api + f"default-skills/{FLOWCHART_SKILL}/toggle").json()["enabled"]
            session = service.create_session(user_id=account["id"])
            sessions.append(session)
            assert (session.root / "client/skills" / FLOWCHART_SKILL).is_file()
            service.update_client_resource(session.id, "skills", FLOWCHART_SKILL, mounted=True)
            assert "drawio-flowchart" in session.session.skill_catalog_prompt()
            assert "image_reasoning" not in session.agent._skills
            tools = session.agent._skills
            assert "操作指引" in tools["use_skill"].handler(name="drawio-flowchart")
            assert "流程图 XML" in tools["read_pack_file"].handler(pack="drawio-flowchart", member="flowchart.md")
            (session.root / "generate/source.xml").write_text(FLOW, encoding="utf-8")
            output = tools["run_skill_script"].handler(pack="drawio-flowchart", script="generate_drawio.py",
                                                      args=json.dumps({"source_path": "generate/source.xml", "formats": []}))
            assert "结构校验与布局完成" in output and "未执行图像复检" in output
            assert "generate/flowchart.drawio" in output
            assert user.post(user_prefix + "/v1/auth/login", json={"username": account["username"], "password": "fixture-pass"}).status_code == 200
            download = user.get(user_prefix + f"/v1/sessions/{session.id}/workspace/files/download", params={"path": "generate/flowchart.drawio"})
            assert download.status_code == 200 and ET.fromstring(download.content).tag == "mxfile"
            definition = service.agent_registry.save({"slug": "diagram", "name": "Diagram", "description": "fixture",
                                                      "skill_names": [FLOWCHART_SKILL]})
            card = user.get(user_prefix + "/agent/diagram/.well-known/agent-card.json").json()
            assert [s["id"] for s in card["skills"]] == [FLOWCHART_SKILL]
            assert card["supportedInterfaces"][0]["url"].endswith(user_prefix + "/agent/diagram/a2a")
            assert "生成与修改" not in json.dumps(card, ensure_ascii=False)
            assert admin.post(api + f"default-skills/{FLOWCHART_SKILL}/toggle").json()["enabled"] is False
            newer = service.create_session(user_id=account["id"])
            sessions.append(newer)
            assert not (newer.root / "client/skills" / FLOWCHART_SKILL).exists()
            assert (session.root / "client/skills" / FLOWCHART_SKILL).exists()
            assert service.agent_registry.snapshot(definition)["dispatched_skills"] == []
            assert admin.post(admin_prefix + "/admin/logout").status_code == 204
            assert admin.get(api + "skill-library").status_code == 401
    finally:
        for session in sessions:
            service.evict_session(session.id)


def test_upgrade_and_restart_preserve_admin_choices(tmp_path):
    store = Store(tmp_path / "data/umeko.db")
    store.set_config({INSTALL_KEY: "1"})  # Existing installation, before this skill existed.
    app = app_for(tmp_path)
    service = app.state.agent_service
    store = service.store
    assert store.default_skill(FLOWCHART_SKILL)
    library = service._skills_library_dir()
    custom = "---\nname: drawio-flowchart\ndescription: Custom diagram skill\n---\nCustom instructions"
    (library / FLOWCHART_SKILL).write_text(custom, encoding="utf-8")
    config = library / "drawio-flowchart/config.json"
    config.write_text('{"drawio_path":"/custom/tool"}', encoding="utf-8")
    store.upsert_default_skill(FLOWCHART_SKILL, custom)
    store.set_default_skill_enabled(FLOWCHART_SKILL, True)
    restarted = app_for(tmp_path).state.store
    assert restarted.default_skill(FLOWCHART_SKILL) == custom
    assert next(s for s in restarted.default_skills() if s["name"] == FLOWCHART_SKILL)["enabled"]
    assert json.loads(config.read_text())["drawio_path"] == "/custom/tool"
    restarted.set_default_skill_enabled(FLOWCHART_SKILL, False)
    assert not install_builtin_skills(restarted, library)
    assert not next(s for s in restarted.default_skills() if s["name"] == FLOWCHART_SKILL)["enabled"]
    restarted.delete_default_skill(FLOWCHART_SKILL)
    config.unlink()
    (library / FLOWCHART_SKILL).unlink()
    final = app_for(tmp_path).state.store
    assert final.default_skill(FLOWCHART_SKILL) is None and not config.exists()


def test_default_installer_discovers_other_packages_without_domain_rules(tmp_path, monkeypatch):
    from umeko.host import builtin_skills

    assets = tmp_path / "bundled"
    assets.mkdir()
    (assets / "table-summary.md").write_text('---\nname: table-summary\ndescription: Summarize a table\n---\nInstructions', encoding="utf-8")
    (assets / "table-summary").mkdir()
    (assets / "table-summary/settings.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(builtin_skills, "ASSETS", assets)
    store = Store(tmp_path / "generic.sqlite")
    library = tmp_path / "library"
    assert install_builtin_skills(store, library)
    assert {s["name"] for s in store.default_skills()} == {"table-summary.md"}
    assert not store.default_skills()[0]["enabled"]
    assert (library / "table-summary/settings.json").is_file()
    assert not install_builtin_skills(store, library)


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_stock_upgrade_preserves_configuration_custom_edits_and_deletions(tmp_path, monkeypatch, newline):
    import hashlib
    from umeko.host import builtin_skills

    assets, library = tmp_path / "bundled", tmp_path / "library"
    (assets / "fixture").mkdir(parents=True)
    (library / "fixture").mkdir(parents=True)
    entry = "fixture.md"
    old_entry = "---\nname: fixture\ndescription: Old stock\n---\nOld instructions\n"
    new_entry = old_entry.replace("Old", "New")
    old_script, new_script = "print('old')\n", "print('new')\n"
    (assets / entry).write_text(new_entry, encoding="utf-8")
    (assets / "fixture/run.py").write_text(new_script, encoding="utf-8")
    (assets / "stock-upgrades.json").write_text(json.dumps({
        entry: [hashlib.sha256(old_entry.encode()).hexdigest()],
        "fixture/run.py": [hashlib.sha256(old_script.encode()).hexdigest()],
    }), encoding="utf-8")
    monkeypatch.setattr(builtin_skills, "ASSETS", assets)
    script, config = library / "fixture/run.py", library / "fixture/config.json"
    (library / entry).write_bytes(old_entry.replace("\n", newline).encode())
    script.write_bytes(old_script.replace("\n", newline).encode())
    config.write_text('{"custom":"retain"}', encoding="utf-8")
    store = Store(tmp_path / "fixture.sqlite")
    store.upsert_default_skill(entry, old_entry.replace("\n", newline))
    store.set_default_skill_enabled(entry, False)
    store.set_config({installation_key(entry): "1"})
    assert install_builtin_skills(store, library)
    assert script.read_bytes() == (assets / "fixture/run.py").read_bytes()
    assert (library / entry).read_text(encoding="utf-8") == store.default_skill(entry) == new_entry
    assert not store.default_skills()[0]["enabled"]
    assert config.read_text() == '{"custom":"retain"}'
    assert not install_builtin_skills(store, library)
    store.upsert_default_skill(entry, "Custom admin instructions")
    (library / entry).write_text(old_entry, encoding="utf-8")
    assert install_builtin_skills(store, library)
    assert store.default_skill(entry) == "Custom admin instructions"
    assert not store.default_skills()[0]["enabled"]
    script.write_text("# Custom implementation", encoding="utf-8")
    (library / entry).write_text("Custom library instructions", encoding="utf-8")
    store.upsert_default_skill(entry, "Custom admin instructions")
    assert not install_builtin_skills(store, library)
    assert script.read_text() == "# Custom implementation"
    assert store.default_skill(entry) == "Custom admin instructions"
    assert (library / entry).read_text() == "Custom library instructions"
    script.unlink()
    (library / entry).unlink()
    store.delete_default_skill(entry)
    assert not install_builtin_skills(store, library)
    assert not script.exists() and not (library / entry).exists() and store.default_skill(entry) is None


def test_standalone_flow_layout_and_optional_renderer(tmp_path):
    result, root = run_script(tmp_path, {"xml": FLOW, "layout": {"node_width": 172, "gap_y": 28}})
    assert not result["ok"] and result["status"] == "partial" and result["files"] == ["generate/flowchart.drawio"]
    assert result["visual_review_performed"] is False and result["warnings"]
    assert {e["format"] for e in result["errors"]} == {"png", "svg"}
    assert all(e["code"] == "renderer_unavailable" for e in result["errors"])
    xml = ET.parse(root / result["files"][0])
    nodes = xml.findall('.//mxCell[@vertex="1"]')
    assert len(nodes) == 4
    assert all(float(n.find("mxGeometry").get("width")) == 172 for n in nodes)
    end = next(n for n in nodes if n.get("id") == "end")
    assert float(end.find("mxGeometry").get("y")) == max(float(n.find("mxGeometry").get("y")) for n in nodes)
    assert all("orthogonalEdgeStyle" in e.get("style") for e in xml.findall('.//mxCell[@edge="1"]'))


def test_business_terminal_labels_and_original_visual_defaults(tmp_path):
    xml = FLOW.replace('value="开始"', 'value="开始：顾客到店"').replace('value="结束"', 'value="结束：接待完成"')
    result, root = run_script(tmp_path, {"xml": xml, "formats": []})
    assert result["ok"], result["result"]  # Exactly one attempt, no XML revision.
    tree = ET.parse(root / result["files"][0])
    nodes = tree.findall('.//mxCell[@vertex="1"]')
    assert all(n.find("mxGeometry").get("width") == "172" for n in nodes)
    assert all(n.find("mxGeometry").get("height") == "28" for n in nodes if n.get("id") != "check")
    assert all("fontFamily=方正兰亭黑简体;" in c.get("style", "") and "fontSize=10.5;" in c.get("style", "")
               for c in tree.findall('.//mxCell') if c.get("vertex") == "1" or c.get("edge") == "1")
    override, root = run_script(tmp_path, {"xml": xml, "formats": [], "layout": {"node_width": 200}})
    nodes = ET.parse(root / override["files"][0]).findall('.//mxCell[@vertex="1"]')
    assert all(n.find("mxGeometry").get("width") == "200" for n in nodes)
    assert next(n for n in nodes if n.get("id") == "start").find("mxGeometry").get("height") == "28"


def test_style_file_selection_and_deterministic_visual_options(tmp_path):
    root = tmp_path / "session"
    (root / "attachments").mkdir(parents=True)
    (root / "attachments/style.md").write_text('''---
name: custom
background: "#112233"
font_family: "Arial"
font_size: "9"
edge_color: "#AABBCC"
edge_width: "2"
layout: node_width=200,gap_y=42
---
GENERIC_STYLE
## [drawio:flowchart] Flow
FLOW_STYLE
## [drawio:architecture] Architecture
ARCH_STYLE
## [legacy:flowchart] Other
OTHER_ENGINE_STYLE
## [legacy:architecture] Other diagram
LEGACY_STYLE
''', encoding="utf-8")
    prepared, root = run_script(tmp_path, {"style_path": "attachments/style.md"}, script="prepare_drawio.py")
    assert prepared["ok"]
    rules = (root / "generate/flowchart-rules.md").read_text(encoding="utf-8")
    assert "GENERIC_STYLE" in rules and "FLOW_STYLE" in rules
    assert all(marker not in rules for marker in ("ARCH_STYLE", "OTHER_ENGINE_STYLE", "LEGACY_STYLE"))
    assert "FLOW_STYLE" not in prepared["result"]  # Style body stays out of the main context.
    result, root = run_script(tmp_path, {"xml": FLOW, "style_path": "attachments/style.md", "formats": []})
    assert result["ok"], result["result"]
    tree = ET.parse(root / result["files"][0])
    assert tree.find("diagram/mxGraphModel").get("background") == "#112233"
    nodes = tree.findall('.//mxCell[@vertex="1"]')
    assert all(n.find("mxGeometry").get("width") == "200" for n in nodes)
    assert all("fontFamily=Arial;" in n.get("style") and "fontSize=9;" in n.get("style") for n in nodes)
    assert all("strokeColor=#AABBCC;" in e.get("style") and "strokeWidth=2;" in e.get("style")
               and "edgeStyle=orthogonalEdgeStyle;" in e.get("style") for e in tree.findall('.//mxCell[@edge="1"]'))
    prepared, root = run_script(tmp_path, {"style_path": "attachments/style.md", "diagram_type": "architecture"}, script="prepare_drawio.py")
    rules = (root / "generate/flowchart-rules.md").read_text(encoding="utf-8")
    assert prepared["ok"] and "ARCH_STYLE" in rules and "FLOW_STYLE" not in rules


def test_plain_style_preserves_custom_edge_visuals_after_routing(tmp_path):
    root = tmp_path / "session"
    (root / "workspace").mkdir(parents=True)
    (root / "workspace/style.md").write_text("节点浅色，连线紫色虚线。", encoding="utf-8")
    graph = ET.fromstring(FLOW)
    graph.find('.//mxCell[@id="e1"]').set("style", "strokeColor=#8844AA;strokeWidth=2;dashed=1;endArrow=block;exitX=0;")
    result, root = run_script(tmp_path, {"xml": ET.tostring(graph, encoding="unicode"), "style_path": "workspace/style.md", "formats": []})
    assert result["ok"]
    edge = ET.parse(root / result["files"][0]).find('.//mxCell[@id="e1"]')
    assert all(p in edge.get("style") for p in ("strokeColor=#8844AA;", "strokeWidth=2;", "dashed=1;", "endArrow=block;", "orthogonalEdgeStyle"))
    assert edge.find("mxGeometry") is not None


def test_style_only_change_preserves_graph_and_rejects_content_edits(tmp_path):
    root = tmp_path / "session"
    (root / "generate").mkdir(parents=True)
    (root / "generate/reference.drawio").write_text(FLOW, encoding="utf-8")
    graph = ET.fromstring(FLOW)
    graph.find('.//mxCell[@id="process"]').set("style", "rounded=1;fillColor=#FFCC88;")
    args = {"xml": ET.tostring(graph, encoding="unicode"), "restyle_reference_path": "generate/reference.drawio", "formats": []}
    result, root = run_script(tmp_path, args)
    assert result["ok"]
    graph.find('.//mxCell[@id="process"]').set("value", "Changed business step")
    failed, _ = run_script(tmp_path, {**args, "xml": ET.tostring(graph, encoding="unicode")})
    assert not failed["ok"] and "仅换风格" in failed["result"] and failed["files"] == []


@pytest.mark.parametrize("style_path", ["attachments/missing.md", "attachments/../../outside.md"])
def test_style_file_errors_are_explicit(tmp_path, style_path):
    result, root = run_script(tmp_path, {"xml": FLOW, "style_path": style_path, "formats": []})
    assert not result["ok"] and not result["files"] and not list((root / "generate").iterdir())


@pytest.mark.parametrize("diagram_type", ["flowchart", "architecture"])
def test_delegated_reading_and_xml_do_not_enter_main_context(tmp_path, diagram_type):
    from copy import deepcopy

    app = app_for(tmp_path)
    service = app.state.agent_service
    service.store.set_default_skill_enabled(FLOWCHART_SKILL, True)
    owner = service.store.create_user("diagram-writer", "fixture-pass")
    state = service.create_session(user_id=owner["id"])
    secret_document = "PRIVATE_REQUIREMENT_SENTINEL: 示例需求细节\n" * 1000
    (state.root / "attachments/requirements.md").write_text(secret_document, encoding="utf-8")
    agent = state.agent
    graph = FLOW if diagram_type == "flowchart" else ARCH
    rules_path = "generate/flowchart-rules.md" if diagram_type == "flowchart" else "generate/flowchart-architecture-rules.md"

    def call(name, arguments, cid):
        return {"id": cid, "type": "function", "function": {"name": name, "arguments": json.dumps(arguments)}}

    def reply(*calls, content=None):
        return ChatCompletionMessage(role="assistant", content=content, tool_calls=list(calls) or None)

    class FixtureLLM:
        last_usage = None

        def __init__(self, replies):
            self.replies, self.requests = list(replies), []

        def chat_with_tools_stream(self, messages, tools, **kwargs):
            self.requests.append(deepcopy(messages))
            return self.replies.pop(0)

        def close(self):
            pass

    main = FixtureLLM([
        reply(call("use_skill", {"name": "drawio-flowchart"}, "load")),
        reply(call("run_skill_script", {"pack": "drawio-flowchart", "script": "prepare_drawio.py", "args": json.dumps({
            "document_paths": ["attachments/requirements.md"], "request": "提炼简要流程", "output_name": "flowchart"})}, "prepare")),
        reply(call("delegate_task", {"task": "读取 generate/flowchart-task.md，按指引读需求与规则，写清单和 XML；只回报路径与短摘要。"}, "delegate")),
        reply(call("run_skill_script", {"pack": "drawio-flowchart", "script": "generate_drawio.py", "args": json.dumps({
            "source_path": "generate/flowchart-source.xml", "formats": []})}, "render")),
        reply(content="已完成：generate/flowchart.drawio"),
    ])
    child = FixtureLLM([
        reply(call("read_document", {"path": "generate/flowchart-task.md"}, "task")),
        reply(call("read_document", {"path": rules_path}, "rules"),
              call("read_document", {"path": "attachments/requirements.md", "force_read": True}, "document")),
        reply(call("write_file", {"path": "generate/flowchart-outline.md", "content": "输入有效时处理输入，否则直接结束。"}, "outline"),
              call("write_file", {"path": "generate/flowchart-source.xml", "content": graph}, "xml")),
        reply(content=f"{diagram_type}；generate/flowchart-outline.md、generate/flowchart-source.xml。已按本次图型保存。"),
    ])
    agent._llm, agent._subagent._llm = main, child
    try:
        assert "run_skill_script" not in agent._subagent._skills and "read_pack_file" not in agent._subagent._skills
        answer = agent.chat("根据 attachments/requirements.md 绘制流程图")
        assert "generate/flowchart.drawio" in answer
        assert (state.root / "generate/flowchart.drawio").is_file()
        if diagram_type == "architecture":
            rendered = ET.parse(state.root / "generate/flowchart.drawio")
            assert rendered.find('.//mxCell[@id="n1"]/mxGeometry').get("width") == "180"
        parent_context = json.dumps(main.requests, ensure_ascii=False)
        child_context = json.dumps(child.requests, ensure_ascii=False)
        assert "PRIVATE_REQUIREMENT_SENTINEL" not in parent_context
        assert "<mxfile" not in parent_context
        assert "PRIVATE_REQUIREMENT_SENTINEL" in child_context and "<mxfile" in child_context
        prepare_result = next(m["content"] for request in main.requests for m in request
                              if m.get("role") == "tool" and m.get("tool_call_id") == "prepare")
        assert len(prepare_result) < 1000
        assert "首次运行前逐项核对" not in parent_context  # Detailed rules only live in the child.
    finally:
        service.evict_session(state.id)
        service.run_manager.shutdown()


@pytest.mark.parametrize("args", [
    {"xml": FLOW.replace('target="check"', 'target="missing"')},
    {"xml": FLOW.replace('id="process"', 'id="start"')},
    {"xml": FLOW.replace('value="否" edge=', 'edge=')},
    {"xml": FLOW, "output_name": "../escape"},
    {"source_path": "attachments/../../outside.xml"},
])
def test_invalid_structure_and_paths_leave_no_output(tmp_path, args):
    result, root = run_script(tmp_path, args)
    assert not result["ok"] and result["files"] == []
    assert list((root / "generate").iterdir()) == []


@pytest.mark.parametrize("renderer_failure", [False, True])
def test_export_diagnosis_enters_agents_next_model_request(tmp_path, monkeypatch, renderer_failure):
    from copy import deepcopy

    app = app_for(tmp_path)
    service = app.state.agent_service
    service.store.set_default_skill_enabled(FLOWCHART_SKILL, True)
    owner = service.store.create_user("diagram-errors", "fixture-pass")
    state = service.create_session(user_id=owner["id"])
    # Existing Python is intentionally not a renderer; its --export rejection is a real subprocess failure.
    renderer = sys.executable if renderer_failure else str(tmp_path / "missing-drawio")
    monkeypatch.setenv("UMEKO_DRAWIO_PATH", renderer)
    (state.root / "generate/source.xml").write_text(FLOW, encoding="utf-8")

    class FixtureLLM:
        last_usage = None

        def __init__(self):
            self.requests = []

        def chat_with_tools_stream(self, messages, tools, **kwargs):
            self.requests.append(deepcopy(messages))
            if len(self.requests) == 1:
                return ChatCompletionMessage(role="assistant", content=None, tool_calls=[{
                    "id": "export", "type": "function", "function": {"name": "run_skill_script", "arguments": json.dumps({
                        "pack": "drawio-flowchart", "script": "generate_drawio.py", "args": json.dumps({
                            "source_path": "generate/source.xml", "formats": ["png"]})})}}])
            return ChatCompletionMessage(role="assistant", content="导出失败，草稿已保留。")

        def close(self):
            pass

    model = FixtureLLM()
    state.agent._llm = model
    try:
        state.agent.chat("生成 PNG")
        response = next(m["content"] for m in model.requests[1] if m.get("role") == "tool" and m.get("tool_call_id") == "export")
        assert response.startswith("错误：脚本部分失败")
        assert "generate/flowchart.drawio" in response and "图片导出未完成" in response
        assert not (state.root / "generate/flowchart.png").exists()
        if renderer_failure:
            assert "退出码 2" in response and "--export" in response and "export_failed" in response
        else:
            assert "renderer_unavailable" in response and "UMEKO_DRAWIO_PATH" in response
    finally:
        service.evict_session(state.id)
        service.run_manager.shutdown()


def test_architecture_layout(tmp_path):
    result, root = run_script(tmp_path, {"xml": ARCH, "diagram_type": "architecture", "formats": []})
    assert result["ok"]
    assert len(ET.parse(root / result["files"][0]).findall('.//mxCell[@vertex="1"]/mxGeometry')) == 6


@pytest.mark.parametrize("connect", [False, True])
def test_architecture_auto_nested_groups_grid_and_explicit_dependencies(tmp_path, connect):
    graph = ET.fromstring(ARCH)
    cells = graph.find("diagram/mxGraphModel/root")
    for parent, names in (("L1", ("a2", "a3", "a4", "a5")), ("S1", ("b3", "b4", "b5"))):
        for name in names:
            ET.SubElement(cells, "mxCell", {"id": name, "value": name, "vertex": "1", "parent": parent,
                                          "style": "rounded=0;whiteSpace=wrap;html=1;fillColor=#F5F8FF;strokeColor=none;"})
    if connect:
        ET.SubElement(cells, "mxCell", {"id": "dependency", "edge": "1", "parent": "1", "source": "n1", "target": "n2",
                                      "style": "strokeColor=#666666;endArrow=block;endFill=1;"})
    result, root = run_script(tmp_path, {"xml": ET.tostring(graph, encoding="unicode"), "formats": []})
    assert result["ok"] and result["diagram_type"] == "architecture"
    tree = ET.parse(root / result["files"][0])
    layers = [tree.find(f'.//mxCell[@id="{name}"]/mxGeometry') for name in ("L1", "L2")]
    assert layers[0].get("width") == layers[1].get("width") == "860"
    assert layers[0].get("x") == layers[1].get("x") == "40"
    components = {name: tree.find(f'.//mxCell[@id="{name}"]/mxGeometry') for name in ("n1", "n2", "n3", "a2", "a3", "a4", "a5", "b3", "b4", "b5")}
    assert all(g.get("width") == "180" and g.get("height") == "60" for g in components.values())
    assert components["a5"].get("y") == components["b5"].get("y") == "130"
    assert components["a5"].get("x") == "340" and components["b5"].get("x") == "320"
    assert tree.find('.//mxCell[@id="n2"]').get("parent") == "S1"
    edges = tree.findall('.//mxCell[@edge="1"]')
    assert len(edges) == int(connect)
    if connect:
        assert edges[0].find("mxGeometry").get("relative") == "1"
        assert "edgeStyle=orthogonalEdgeStyle;" in edges[0].get("style")
        assert edges[0].get("source") == "n1" and edges[0].get("target") == "n2"


def test_export_returns_fresh_files_and_drops_failed_stale_preview(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("drawio_skill_test", PACK / "generate_drawio.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "_renderer", lambda config: ("fixture-drawio", None))
    root = tmp_path / "session"
    workdir = root / "generate"
    workdir.mkdir(parents=True)

    def export(command, **kwargs):
        fmt = command[command.index("--format") + 1]
        output = Path(command[command.index("--output") + 1])
        assert ET.parse(command[-1]).getroot().tag == "mxfile"
        assert kwargs["timeout"] <= 45
        if fmt == "svg":
            return SimpleNamespace(returncode=1, stdout="", stderr=f"libasound.so.2 missing: fixture-drawio {command[-1]}")
        output.write_bytes(b"fixture rendered image")
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(module.subprocess, "run", export)
    (workdir / "flowchart.svg").write_text("old preview", encoding="utf-8")
    result = module.generate({"args": {"xml": FLOW}, "workdir": str(workdir), "session_root": str(root)})
    assert result["files"] == ["generate/flowchart.drawio", "generate/flowchart.png"]
    assert not result["ok"] and result["status"] == "partial"
    assert "svg 导出失败" in result["result"] and not (workdir / "flowchart.svg").exists()
    assert "libasound.so.2 missing" in result["result"]
    assert str(root) not in result["result"] and "fixture-drawio" not in result["result"]
    assert not list(workdir.glob("*.export.*"))


def test_export_timeout_retains_renderer_diagnosis_and_draft(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("drawio_timeout_test", PACK / "generate_drawio.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "_renderer", lambda config: ("fixture-drawio", None))
    root = tmp_path / "session"
    workdir = root / "generate"

    def timeout(command, **kwargs):
        raise subprocess.TimeoutExpired(command, kwargs["timeout"], stderr=b"Renderer process gone: fixture-drawio")

    monkeypatch.setattr(module.subprocess, "run", timeout)
    result = module.generate({"args": {"xml": FLOW, "formats": ["png"]}, "workdir": str(workdir), "session_root": str(root)})
    assert not result["ok"] and result["status"] == "partial"
    assert result["errors"][0]["code"] == "export_timeout" and "Renderer process gone" in result["result"]
    assert "fixture-drawio" not in result["result"] and result["files"] == ["generate/flowchart.drawio"]
    assert (root / result["files"][0]).is_file() and not list(workdir.glob("*.export.*"))


def test_packaged_skill_is_self_contained(tmp_path):
    package = runpy.run_path(str(Path(__file__).resolve().parents[1] / "scripts/package_drawio_skill.py"))["package_skill"]
    first, second = package(tmp_path / "one.zip"), package(tmp_path / "two.zip")
    assert first.read_bytes() == second.read_bytes()
    with zipfile.ZipFile(first) as archive:
        assert archive.testzip() is None
        assert FLOWCHART_SKILL in archive.namelist()
        assert {"drawio-flowchart/linux-deployment.md", "drawio-flowchart/drawio_headless.sh",
                "drawio-flowchart/Dockerfile.linux.txt", "drawio-flowchart/linux_smoke.py"} <= set(archive.namelist())
        assert not any("mermaid" in name.lower() or "__pycache__" in name for name in archive.namelist())
        # Docker Compose legitimately uses `init: true`; prohibit diagram directives.
        forbidden = ("mermaid", "mmdc", "```mmd", "%%{init")
        assert not any(word in archive.read(name).decode("utf-8").lower() for name in archive.namelist() for word in forbidden)
        # All input is our own package, not an untrusted user upload.
        for name in archive.namelist():
            target = tmp_path / "unpacked" / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.read(name))
    result, root = run_script(tmp_path, {"xml": FLOW, "formats": []}, tmp_path / "unpacked/drawio-flowchart")
    assert result["ok"] and (root / result["files"][0]).is_file()
