"""Global dispatch, personal grants, both Agent roles, persistence and machine submissions."""
import json
import time
from types import SimpleNamespace

from fastapi.testclient import TestClient
from openai.types.chat import ChatCompletionMessage
import pytest

from umeko.agent import UmekoAgent
from umeko.config import ModelConfig, Settings
from umeko.host.storage import Store
from umeko.llm import LLMClient
from umeko.server.admin import create_admin_app
from umeko.server.app import create_app
from umeko.skills import build_file_tools
from umeko.tool_catalog import CONFIGURABLE_TOOLS, REQUIRED_TOOLS

REAL_CHAT = UmekoAgent.chat


@pytest.fixture(params=["", "/teams/docs/umeko"])
def access(tmp_path, request):
    settings = Settings(ModelConfig("fixture", "fixture-only", "http://unused.invalid"),
                        base_path=request.param, admin_base_path="/operations/console")
    app = create_app(settings, data_root=tmp_path / "data", workspace_root=tmp_path / "output")
    service, store = app.state.agent_service, app.state.store
    owner = store.create_user("tool-user", "fixture-password")
    manager = store.create_user("tool-admin", "fixture-password", "admin")
    other = store.create_user("other-user", "fixture-password")
    admin_app = create_admin_app(settings, service, store)
    with TestClient(app) as user, TestClient(admin_app) as admin:
        admin.post("/operations/console/admin/login", json={"username": manager["username"], "password": "fixture-password"}).raise_for_status()
        yield SimpleNamespace(user=user, admin=admin, app=app, service=service, store=store, owner=owner, other=other,
                              api="/operations/console/admin/v1", prefix=request.param)


def test_global_dispatch_personal_grants_and_roles(access):
    e = access
    tools = e.admin.get(e.api + "/tools").json()["tools"]
    assert {t["name"] for t in tools} == CONFIGURABLE_TOOLS | REQUIRED_TOOLS
    assert all(t["enabled"] for t in tools)
    state = e.service.create_session(user_id=e.owner["id"])
    assert "write_file" in state.agent._skills and "download_url" in state.agent._subagent._skills
    e.admin.put(e.api + "/tools/write_file", json={"enabled": False}).raise_for_status()
    args = json.dumps({"path": "blocked.txt", "content": "must not write"})
    assert "权限" in state.agent._execute("write_file", args)
    assert "权限" in state.agent._subagent._execute("write_file", args)
    assert not (state.root / "generate/blocked.txt").exists()
    fresh = e.service.create_session(user_id=e.owner["id"])
    assert "write_file" not in fresh.agent._skills and "write_file" not in fresh.agent._subagent._skills
    url = e.api + f"/users/{e.owner['id']}/tool-access"
    assert e.admin.get(url).json()["allowed_tool_names"] is None
    e.admin.put(url, json={"allowed_tool_names": ["write_file", "download_url"]}).raise_for_status()
    granted = e.service.create_session(user_id=e.owner["id"])
    assert set(granted.agent._skills) == set(granted.agent._subagent._skills) == {"write_file", "download_url"}
    ordinary = e.service.create_session(user_id=e.other["id"])
    assert "write_file" not in ordinary.agent._skills
    e.admin.put(url, json={"allowed_tool_names": []}).raise_for_status()
    denied = e.service.create_session(user_id=e.owner["id"])
    assert not denied.agent._skills and not denied.agent._subagent._skills
    e.admin.put(url, json={"allowed_tool_names": None}).raise_for_status()
    assert "download_url" in e.store.effective_tool_names(e.owner["id"])
    assert "write_file" not in e.store.effective_tool_names(e.owner["id"])


def test_next_run_rebuilds_existing_session_after_permissions_change(access, monkeypatch):
    e = access
    state = e.service.create_session(user_id=e.owner["id"])
    seen = []
    def chat(agent, prompt, images=None):
        seen.append(set(agent._skills))
        return "controlled reply"
    monkeypatch.setattr(UmekoAgent, "chat", chat)
    e.store.set_user_tool_access(e.owner["id"], ["list_dir"])
    run = e.service.create_run(state.id, "continue", [])
    for _ in range(200):
        if run.finished:
            break
        time.sleep(.01)
    assert run.status == "completed" and seen == [{"list_dir"}]
    e.service.evict_session(state.id)
    restored = e.service.get_session(state.id)
    assert set(restored.agent._skills) == {"list_dir"}
    assert set(restored.agent._subagent._skills) == {"list_dir"}


def test_management_auth_validation_and_persistence(access):
    e = access
    url = e.api + f"/users/{e.owner['id']}/tool-access"
    with TestClient(e.admin.app) as anonymous:
        assert anonymous.get(e.api + "/tools").status_code == 401
        assert anonymous.put(url, json={"allowed_tool_names": []}).status_code == 401
    assert e.user.get(e.prefix + "/admin/v1/tools").status_code == 404
    assert e.admin.put(e.api + "/tools/unknown", json={"enabled": False}).status_code == 404
    assert e.admin.put(e.api + "/tools/submit_results", json={"enabled": False}).status_code == 400
    assert e.admin.put(e.api + "/tools/list_dir", json={"enabled": "false"}).status_code == 422
    assert e.admin.put(url, json={"allowed_tool_names": ["unknown"]}).status_code == 400
    assert e.admin.put(url, json={"allowed_tool_names": ["submit_results"]}).status_code == 400
    assert e.admin.put(url, json={}).status_code == 422
    e.admin.put(e.api + "/tools/download_url", json={"enabled": False}).raise_for_status()
    e.admin.put(url, json={"allowed_tool_names": ["download_url"]}).raise_for_status()
    store = Store(e.store.path)
    assert store.effective_tool_names(e.owner["id"]) == {"download_url", "submit_results"}
    assert "download_url" not in store.effective_tool_names(e.other["id"])


def test_catalog_matches_native_tool_implementations(access):
    state = access.service.create_session(user_id=access.owner["id"])
    tools = build_file_tools(state.session, SimpleNamespace(add=lambda p: ""), vision_llm=object(),
                             command_runner=SimpleNamespace(run=lambda command: ""))
    assert {tool.name for tool in tools} | {"delegate_task", "submit_results"} == CONFIGURABLE_TOOLS | REQUIRED_TOOLS


@pytest.mark.parametrize("machine_app", ["", "/teams/docs/umeko"], indirect=True)
def test_machine_submission_survives_all_optional_tools_disabled(machine_client, monkeypatch):
    client, app, account, _ = machine_client
    for name in CONFIGURABLE_TOOLS:
        app.state.store.set_tool_dispatch(name, False)
    def llm_chat(llm, messages, tools, **kwargs):
        assert {t["function"]["name"] for t in tools} == {"submit_results"}
        return ChatCompletionMessage(role="assistant", tool_calls=[{"id": "submit", "type": "function", "function": {
            "name": "submit_results", "arguments": json.dumps({"text": "No optional tools needed", "files": []})}}])
    monkeypatch.setattr(UmekoAgent, "chat", REAL_CHAT)
    monkeypatch.setattr(LLMClient, "chat_with_tools_stream", llm_chat)
    base = app.state.agent_service.settings.base_path + "/agent/fixture/v1/tasks"
    headers = {"Authorization": "Bearer " + account["token"]}
    tid = client.post(base, headers=headers, json={"prompt": "answer"}).json()["id"]
    for _ in range(200):
        task = client.get(base + "/" + tid, headers=headers).json()
        if task["status"] in {"completed", "failed"}:
            break
        time.sleep(.01)
    assert task["status"] == "completed", task
    results = client.get(base + f"/{tid}/results", headers=headers).json()
    assert results["text"] == "No optional tools needed" and results["files"] == []
