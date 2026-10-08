import asyncio
from dataclasses import replace
import json
import time

import httpx
import httpx2
import pytest
from a2a import types as a2a
from a2a.client import ClientConfig, ClientFactory
from fastapi.testclient import TestClient
from mcp.client import Client
from mcp.client.streamable_http import streamable_http_client

from umeko.agent import UmekoAgent
from umeko.host.tasks import TaskService
from umeko.server.admin import create_admin_app
from umeko.server.app import create_app


def seed(app):
    service, store = app.state.agent_service, app.state.store
    for name in ("alpha", "beta"):
        store.upsert_default_skill(name + ".md", f"---\nname: {name}\ndescription: {name} public description\n---\nPRIVATE {name} instructions")
    first = service.agent_registry.save({"slug": "alpha", "name": "Alpha Agent", "description": "Alpha service",
                                        "skill_names": ["alpha.md"], "system_prompt": "PRIVATE ALPHA ROLE"})
    second = service.agent_registry.save({"slug": "beta", "name": "Beta Agent", "description": "Beta service",
                                         "skill_names": ["beta.md"], "system_prompt": "PRIVATE BETA ROLE"})
    return first, second


def wait(client, path):
    for _ in range(200):
        response = client.get(path)
        assert response.status_code == 200, response.text
        record = response.json()
        if record["status"] in {"completed", "failed", "cancelled"}:
            return record
        time.sleep(.02)
    raise AssertionError("Task did not finish")


@pytest.mark.parametrize("machine_app", ["", "/doc-master/consistency/image-text"], indirect=True)
def test_agent_routes_cards_and_task_ownership(machine_client):
    client, app, _, _ = machine_client
    a, b = seed(app)
    app.state.identity_store.set_auth_mode("anonymous")
    prefix = app.state.agent_service.settings.base_path
    bases = [prefix + "/agent/alpha", prefix + "/agent/beta"]
    for definition, base in zip((a, b), bases):
        response = client.get(base + "/.well-known/agent-card.json")
        assert response.status_code == 200, response.text
        card = response.json()
        assert card["name"] == definition["name"]
        assert [s["id"] for s in card["skills"]] == definition["skill_names"]
        assert card["supportedInterfaces"][0]["url"] == "http://127.0.0.1" + base + "/a2a"
        assert "PRIVATE" not in response.text
        assert client.get(base + "/").json()["mcp"] == "http://127.0.0.1" + base + "/mcp"
        assert client.get(base + "/v1/sessions").status_code == 404
    assert len(client.get(prefix + "/agent").json()["agents"]) == 3
    assert client.get(prefix + "/.well-known/agent-card.json").status_code == 404
    tasks = []
    for base in bases:
        result = client.post(base + "/v1/tasks", json={"prompt": "two-agent check"}, headers={"Idempotency-Key": "same-key"})
        assert result.status_code == 202, result.text
        tasks.append(result.json())
    assert tasks[0]["id"] != tasks[1]["id"]
    assert tasks[0]["agent_id"] == a["id"] and tasks[1]["agent_id"] == b["id"]
    again = client.post(bases[0] + "/v1/tasks", json={"prompt": "two-agent check"}, headers={"Idempotency-Key": "same-key"})
    assert again.json()["id"] == tasks[0]["id"]
    final = wait(client, bases[0] + "/v1/tasks/" + tasks[0]["id"])
    assert final["status"] == "completed", final
    artifact = final["artifacts"][0]
    assert artifact["download_url"].startswith("http://127.0.0.1" + bases[0] + "/v1/tasks/")
    assert client.get(artifact["download_url"]).status_code == 200
    for foreign in (bases[1], prefix):
        task_path = foreign + "/v1/tasks/" + tasks[0]["id"]
        assert client.get(task_path).status_code == 404
        assert client.get(task_path + "/events").status_code == 404
        assert client.post(task_path + "/cancel").status_code == 404
        assert client.get(task_path + "/artifacts/" + artifact["id"] + "/content").status_code == 404
    for base, task in zip(bases, tasks):
        assert [item["id"] for item in client.get(base + "/v1/tasks").json()["tasks"]] == [task["id"]]
    app.state.agent_service.agent_registry.save({**a, "enabled": False}, a["id"])
    assert client.get(bases[0] + "/.well-known/agent-card.json").status_code == 404
    assert client.post(bases[0] + "/v1/tasks", json={"prompt": "hi"}).status_code == 404
    assert len(client.get(prefix + "/agent").json()["agents"]) == 2


def test_admin_definitions_and_public_base_url(machine_app, tmp_path):
    _, _, _, settings = machine_app
    settings = replace(settings, public_url="https://company.internal/doc-master/consistency/image-text", base_path="/doc-master/consistency/image-text")
    app = create_app(settings, data_root=tmp_path / "other", workspace_root=tmp_path / "out")
    service, store = app.state.agent_service, app.state.store
    a, _ = seed(app)
    user = store.create_user("agent-admin", "fixture-pass", "admin")
    admin_app = create_admin_app(settings, service, store)
    with TestClient(admin_app) as admin, TestClient(app) as client:
        assert admin.get("/admin/v1/agents").status_code == 401
        assert admin.post("/admin/v1/agents", json=a).status_code == 401
        admin.cookies.set("umeko_admin", store.issue_token(user["id"]))
        listed = admin.get("/admin/v1/agents").json()
        assert len(listed["agents"]) == 2
        assert {s["filename"] for s in listed["skills"]} == {"alpha.md", "beta.md"}
        value = {"slug": "new-agent", "name": "New", "description": "New delivery", "skill_names": ["alpha.md"]}
        created = admin.post("/admin/v1/agents", json=value)
        assert created.status_code == 201, created.text
        data = created.json()
        card = admin.get("/admin/v1/agents/" + data["id"] + "/card").json()["card"]
        published = client.get(settings.base_path + "/agent/new-agent/.well-known/agent-card.json").json()
        assert card == published
        assert card["supportedInterfaces"][0]["url"] == settings.public_url + "/agent/new-agent/a2a"
        assert admin.post("/admin/v1/agents", json=value).status_code == 400
        for bad in [{**value, "slug": "../wrong"}, {**value, "slug": "unseen", "skill_names": ["missing.md"]},
                    {**value, "slug": "unseen", "default_model_id": "unknown"},
                    {**value, "slug": "unseen", "provider": {"organization": "Team", "url": "https://company.internal", "unsupported": True}},
                    {**value, "slug": "unseen", "provider": {"organization": "Missing URL"}}]:
            assert admin.post("/admin/v1/agents", json=bad).status_code == 400
        assert admin.put("/admin/v1/agents/"+data["id"], json={**value, "slug": "changed"}).status_code == 400
        assert admin.put("/admin/v1/agents/"+data["id"], json={**value, "description": "Updated"}).status_code == 200
        assert client.get(settings.base_path + "/agent/new-agent/.well-known/agent-card.json").json()["description"] == "Updated"
        assert admin.get("/admin/v1/agents/"+data["id"]).json()["name"] == "New"
        assert admin.delete("/admin/v1/agents/"+data["id"]).status_code == 204
        assert client.get(settings.base_path + "/agent/new-agent/.well-known/agent-card.json").status_code == 404


def test_legacy_task_migration_preserves_retries_and_allows_agent_key_reuse(machine_app):
    app, account, _, settings = machine_app
    service, store = app.state.agent_service, app.state.store
    principal = app.state.identity_store.authenticate(account["token"])
    payload = {"prompt": "retained legacy task"}
    original = app.state.task_service.submit(principal, payload, idempotency_key="existing-key")
    # Recreate the pre-agent layout, with the historical unique key still populated.
    with store.connect() as db:
        db.execute("UPDATE service_tasks SET idempotency_key=request_key")
        db.execute("DROP INDEX idx_task_request_key")
        db.execute("ALTER TABLE service_tasks DROP COLUMN request_key")
        db.execute("ALTER TABLE service_tasks DROP COLUMN agent_id")
    migrated = TaskService(service, settings)
    restored = migrated.get(principal, original["id"])
    assert restored["agent_id"] == "" and restored["status"] == "queued"
    assert migrated.submit(principal, payload, idempotency_key="existing-key")["id"] == original["id"]
    a, _ = seed(app)
    scoped = {**principal, "agent_id": a["id"], "agent_definition": a}
    new = migrated.submit(scoped, payload, idempotency_key="existing-key")
    assert new["id"] != original["id"] and new["agent_id"] == a["id"]
    assert migrated.get(principal, original["id"])["id"] == original["id"]
    assert migrated.list(principal)["total"] == 1 and migrated.list(scoped)["total"] == 1
    # Initialization is repeatable without losing old keys or Agent attribution.
    repeated = TaskService(service, settings)
    assert repeated.submit(scoped, payload, idempotency_key="existing-key")["id"] == new["id"]


def test_queued_tasks_keep_definition_and_skill_snapshot(machine_client, monkeypatch):
    client, app, _, _ = machine_client
    service, tasks = app.state.agent_service, app.state.task_service
    a, _ = seed(app)
    app.state.identity_store.set_auth_mode("anonymous")
    observed = []
    def chat(agent, prompt, images=None):
        session = agent._session
        observed.append({"instructions": agent._messages[0]["content"], "skills": session.list_skill_packs()})
        assert "未配置" in agent._skills["read_pack_file"].handler(pack="beta", member="anything.md")
        assert "未配置" in agent._skills["run_skill_script"].handler(pack="beta", script="anything.py")
        assert "read_pack_file" not in agent._subagent._skills
        return "Snapshot executed"
    monkeypatch.setattr(UmekoAgent, "chat", chat)
    tasks.stop()
    response = client.post("/agent/alpha/v1/tasks", json={"prompt": "snapshot check"})
    assert response.status_code == 202, response.text
    task_id = response.json()["id"]
    service.agent_registry.save({**a, "system_prompt": "CHANGED ROLE", "skill_names": ["beta.md"]}, a["id"])
    service.store.upsert_default_skill("alpha.md", "---\nname: alpha\ndescription: CHANGED description\n---\nCHANGED instructions")
    tasks.start()
    task = wait(client, "/agent/alpha/v1/tasks/"+task_id)
    assert task["status"] == "completed", task["error"]
    assert "PRIVATE ALPHA ROLE" in observed[0]["instructions"] and "CHANGED ROLE" not in observed[0]["instructions"]
    assert "alpha public description" in observed[0]["skills"] and "CHANGED" not in observed[0]["skills"]
    with pytest.raises(ValueError, match="保留任务"):
        service.agent_registry.delete(a["id"])


def test_agent_default_model_and_explicit_request_override(machine_client, monkeypatch):
    client, app, _, _ = machine_client
    service, store = app.state.agent_service, app.state.store
    a, _ = seed(app)
    provider = store.create_provider("fixture-agent", "http://unused.invalid", "fixture-key")
    first = store.add_model(provider["id"], "first")
    second = store.add_model(provider["id"], "second")
    service.agent_registry.save({**a, "default_model_id": first["id"]}, a["id"])
    app.state.identity_store.set_auth_mode("anonymous")
    observed = []
    def chat(agent, prompt, images=None):
        observed.append((agent.settings.text_model.model_id, agent._session.allowed_skill_packs, agent._messages[0]["content"]))
        return "Chosen model"
    monkeypatch.setattr(UmekoAgent, "chat", chat)
    for override, expected in [(None, first["id"]), (second["id"], second["id"])]:
        response = client.post("/agent/alpha/v1/tasks", json={"prompt": "model check", "model_id": override})
        assert response.status_code == 202, response.text
        task = wait(client, "/agent/alpha/v1/tasks/" + response.json()["id"])
        assert task["status"] == "completed", task["error"]
        assert observed[-1][0] == expected
        assert observed[-1][1] == {"alpha"}
        assert "PRIVATE ALPHA ROLE" in observed[-1][2]


@pytest.mark.parametrize("machine_app", ["", "/doc-master/consistency/image-text"], indirect=True)
@pytest.mark.parametrize("auth_mode", ["required", "anonymous"])
def test_multiple_agents_official_protocol_clients(machine_server, auth_mode):
    base, app, account, _ = machine_server
    base = base.removesuffix("/agent/fixture")
    a, b = seed(app)
    app.state.identity_store.set_auth_mode(auth_mode)
    headers = {"Authorization": "Bearer "+account["token"]} if auth_mode == "required" else {}
    async def check():
        for definition in (a,b):
            endpoint = base + "/agent/" + definition["slug"]
            async with httpx.AsyncClient(headers={**headers, "A2A-Version": "1.0"},trust_env=False,timeout=15) as http:
                client = await ClientFactory(ClientConfig(httpx_client=http, streaming=True)).create_from_url(endpoint)
                request = a2a.SendMessageRequest(message=a2a.Message(message_id="shared-message", role=a2a.Role.ROLE_USER, parts=[a2a.Part(text="A2A multi-agent")]))
                events = [event async for event in client.send_message(request)]
                task_id = next(e.task.id for e in events if e.HasField("task"))
                task = await client.get_task(a2a.GetTaskRequest(id=task_id))
                assert task.status.state == a2a.TaskState.TASK_STATE_COMPLETED
            async with httpx2.AsyncClient(headers=headers, trust_env=False) as http:
                async with Client(streamable_http_client(endpoint+"/mcp", http_client=http), cache=None) as client:
                    info = await client.call_tool("get_agent_info", {})
                    assert not info.is_error, info
                    assert info.structured_content["name"] == definition["name"]
                    result = await client.call_tool("submit_task", {"prompt": "MCP multi-agent"})
                    assert not result.is_error, result
                    assert result.structured_content["agent_id"] == definition["id"]
                    for _ in range(100):
                        result = await client.call_tool("get_task", {"task_id": result.structured_content["id"]})
                        if result.structured_content["status"] in {"completed", "failed", "cancelled"}:
                            break
                        await asyncio.sleep(.03)
                    assert result.structured_content["status"] == "completed", result
    asyncio.run(check())


def test_agent_oauth_audience_and_context_isolation(machine_client):
    client, app, account, _ = machine_client
    a, b = seed(app)
    resource = "http://127.0.0.1/agent/alpha/v1/tasks"
    token = client.post("/agent/alpha/oauth/token", data={"grant_type": "client_credentials", "client_id": account["id"],
                       "client_secret": account["token"], "resource": resource})
    assert token.status_code == 200, token.text
    headers = {"Authorization": "Bearer " + token.json()["access_token"]}
    response = client.post("/agent/alpha/v1/tasks", json={"prompt": "oauth agent check"}, headers=headers)
    assert response.status_code == 202, response.text
    assert client.get("/agent/beta/v1/tasks", headers=headers).status_code == 401
    assert client.get("/v1/tasks", headers=headers).status_code == 404
    context = response.json()["context_id"]
    principal = {**app.state.identity_store.authenticate(account["token"]), "agent_id": b["id"], "agent_definition": b}
    with pytest.raises(KeyError, match="Context"):
        app.state.task_service.submit(principal, {"prompt": "wrong context"}, context_id=context)


@pytest.mark.parametrize("machine_app", ["", "/doc-master/consistency/image-text"], indirect=True)
def test_global_machine_endpoints_are_removed_and_schema_matches_public_paths(machine_client):
    client, app, account, _ = machine_client
    prefix = app.state.agent_service.settings.base_path
    for mode in ["required", "anonymous"]:
        app.state.identity_store.set_auth_mode(mode)
        for path in ["/mcp", "/a2a", "/v1/tasks", "/oauth/token", "/.well-known/agent-card.json",
                     "/.well-known/oauth-authorization-server", "/.well-known/oauth-protected-resource/mcp",
                     "/agents/fixture/mcp"]:
            assert client.get(prefix + path).status_code == 404
            assert client.post(prefix + path, json={}, headers={"Authorization": "Bearer " + account["token"]}).status_code == 404
    schema = client.get(prefix + "/openapi.json").json()["paths"]
    assert not any(path in schema for path in ["/v1/tasks", "/oauth/token", "/.well-known/agent-card.json"])
    for path in ["/agent/{agent_name}/v1/tasks", "/agent/{agent_name}/oauth/token", "/agent/{agent_name}/.well-known/agent-card.json"]:
        assert path in schema
        for op in schema[path].values():
            assert next(p for p in op["parameters"] if p["name"] == "agent_name")["required"]
    assert client.get(prefix + "/health").status_code == 200
