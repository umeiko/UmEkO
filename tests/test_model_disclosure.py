import asyncio
import json
import time

import httpx
import httpx2
from a2a import types as a2a
from a2a.client import ClientConfig, ClientFactory
from mcp.client import Client
from mcp.client.streamable_http import streamable_http_client
import pytest
from fastapi.testclient import TestClient

from umeko.server.admin import create_admin_app


def setup_models(app, selection="selected", explicit=True):
    store, registry = app.state.store, app.state.agent_service.agent_registry
    provider = store.create_provider("VisibleProvider", "https://unused.invalid", "fixture-only")
    default = store.add_model(provider["id"], "default-main")
    extra = store.add_model(provider["id"], "optional-main")
    private = store.create_provider("PrivateProvider", "https://hidden.invalid", "secret-fixture")
    hidden = store.add_model(private["id"], "hidden-vision", True)
    store.set_active_model(default["id"])
    ids = [extra["id"]] if selection == "selected" else [] if selection == "default" else None
    definition = registry.save({**app.state.fixture_agent, "default_model_id": default["id"] if explicit else None,
                               "default_vision_model_id": hidden["id"], "disclosed_model_ids": ids}, app.state.fixture_agent["id"])
    app.state.fixture_agent = definition
    return definition, default, extra, hidden


@pytest.mark.parametrize("machine_app", ["", "/dept/doc-master/consistency"], indirect=True)
def test_external_models_are_hidden_and_overrides_rejected_all_protocols(machine_server):
    base, app, account, _ = machine_server
    definition, default, extra, hidden = setup_models(app)
    async def check():
        headers = {"Authorization": "Bearer " + account["token"]}
        async with httpx2.AsyncClient(headers=headers, trust_env=False) as http:
            async with Client(streamable_http_client(base + "/mcp", http_client=http), cache=None) as client:
                tools = (await client.list_tools()).tools
                assert not {"list_models", "list_tasks"} & {tool.name for tool in tools}
                submit = next(tool for tool in tools if tool.name == "submit_task")
                assert "model_id" not in submit.input_schema["properties"]
                assert "PrivateProvider" not in json.dumps(submit.model_dump())
                blocked = await client.call_tool("submit_task", {"prompt": "hidden", "model_id": hidden["id"]})
                assert blocked.is_error
                allowed = await client.call_tool("submit_task", {"prompt": "default model"})
                assert not allowed.is_error
        async with httpx.AsyncClient(headers=headers, trust_env=False) as http:
            blocked = await http.post(base + "/v1/tasks", json={"prompt": "hidden", "model_id": hidden["id"]})
            assert blocked.status_code == 422
            for _ in range(100):
                task = (await http.get(base + "/v1/tasks/" + allowed.structured_content["id"])).json()
                if task["status"] in {"completed", "failed", "cancelled"}:
                    break
                await asyncio.sleep(.05)
            assert task["status"] == "completed", task
            assert task["workspace_url"].startswith(base.rsplit("/agent/", 1)[0] + "/TMP/")
        async with httpx.AsyncClient(headers={**headers, "A2A-Version": "1.0"}, trust_env=False) as http:
            client = await ClientFactory(ClientConfig(httpx_client=http, streaming=False)).create_from_url(base)
            blocked = a2a.SendMessageRequest(message=a2a.Message(message_id="hidden-model",
                role=a2a.Role.ROLE_USER, parts=[a2a.Part(text="hidden")]), metadata={"umeko": {"model_id": hidden["id"]}})
            with pytest.raises(Exception, match="model_id"):
                _ = [event async for event in client.send_message(blocked)]
            accepted = a2a.SendMessageRequest(message=a2a.Message(message_id="default-model",
                role=a2a.Role.ROLE_USER, parts=[a2a.Part(text="default")]))
            events = [event async for event in client.send_message(accepted)]
            assert next(e.task for e in events if e.HasField("task")).status.state == a2a.TaskState.TASK_STATE_COMPLETED
    asyncio.run(check())


@pytest.mark.parametrize("selection", ["selected", "default", "all"])
@pytest.mark.parametrize("explicit", [True, False])
def test_default_is_always_disclosed_and_platform_default_can_change(machine_app, selection, explicit):
    app, _, _, _ = machine_app
    definition, default, extra, hidden = setup_models(app, selection, explicit)
    registry = app.state.agent_service.agent_registry
    catalog = registry.disclosed_models(definition)
    expected = {default["id"], extra["id"]} if selection == "selected" else {default["id"]} if selection == "default" else {default["id"], extra["id"], hidden["id"]}
    assert {m["id"] for m in catalog["models"]} == expected
    assert catalog["default_vision_model_id"] == (hidden["id"] if selection == "all" else None)
    app.state.store.set_active_model(extra["id"])
    assert registry.disclosed_models(definition)["default_model_id"] == (default["id"] if explicit else extra["id"])


def test_admin_validation_persistence_and_legacy_compatibility(machine_app):
    app, _, _, settings = machine_app
    definition, default, extra, hidden = setup_models(app)
    store, service = app.state.store, app.state.agent_service
    user = store.create_user("disclosure-admin", "fixture-only", "admin")
    with TestClient(create_admin_app(settings, service, store)) as admin:
        assert admin.get("/admin/v1/agents").status_code == 401
        admin.cookies.set("umeko_admin", store.issue_token(user["id"]))
        endpoint = "/admin/v1/agents/" + definition["id"]
        payload = {k: definition[k] for k in ("slug", "name", "description", "default_model_id", "default_vision_model_id", "skill_names")}
        for invalid in [["unknown"], [extra["id"], extra["id"]]]:
            assert admin.put(endpoint, json={**payload, "disclosed_model_ids": invalid}).status_code == 400
        result = admin.put(endpoint, json={**payload, "disclosed_model_ids": []})
        assert result.status_code == 200 and result.json()["disclosed_model_ids"] == []
        assert admin.get(endpoint).json()["disclosed_model_ids"] == []
        listed = admin.get("/admin/v1/agents").json()
        assert listed["active_model_id"] == default["id"]
        assert admin.put(endpoint, json={**payload, "disclosed_model_ids": None}).json()["disclosed_model_ids"] is None
        assert service.agent_registry.allows_model(service.agent_registry.get(definition["id"]), hidden["id"])
    with store.connect() as db:
        row = db.execute("SELECT definition_json FROM agent_definitions WHERE id=?", (definition["id"],)).fetchone()
        raw = json.loads(row[0])
        raw.pop("disclosed_model_ids", None)
        db.execute("UPDATE agent_definitions SET definition_json=? WHERE id=?", (json.dumps(raw), definition["id"]))
    legacy = service.agent_registry.get(definition["id"])
    assert legacy["disclosed_model_ids"] is None
    assert len(service.agent_registry.disclosed_models(legacy)["models"]) == 3


def test_accepted_task_keeps_configured_model_after_default_changes(machine_client):
    client, app, account, _ = machine_client
    definition, default, extra, _ = setup_models(app)
    tasks, registry = app.state.task_service, app.state.agent_service.agent_registry
    tasks.stop()
    headers = {"Authorization": "Bearer " + account["token"], "Idempotency-Key": "accepted-model-selection"}
    response = client.post("/agent/fixture/v1/tasks", headers=headers, json={"prompt": "queued"})
    assert response.status_code == 202
    registry.save({**definition, "default_model_id": extra["id"]}, definition["id"])
    again = client.post("/agent/fixture/v1/tasks", headers=headers, json={"prompt": "queued"})
    assert again.status_code == 202 and again.json()["id"] == response.json()["id"]
    with app.state.store.connect() as db:
        payload = json.loads(db.execute("SELECT input_json FROM service_tasks WHERE id=?", (response.json()["id"],)).fetchone()[0])
    assert payload["model_id"] == default["id"]
    tasks.start()
    for _ in range(100):
        task = client.get("/agent/fixture/v1/tasks/" + response.json()["id"], headers=headers).json()
        if task["status"] in {"completed", "failed", "cancelled"}:
            break
        time.sleep(.02)
    assert task["status"] == "completed", task
    assert client.post("/agent/fixture/v1/tasks", headers={**headers, "Idempotency-Key": "new-selection"}, json={"prompt": "new", "model_id": extra["id"]}).status_code == 422
