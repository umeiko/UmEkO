import asyncio
import time

import httpx
import httpx2
import pytest
from a2a import types as a2a
from a2a.client import ClientConfig, ClientFactory
from fastapi.testclient import TestClient
from mcp.client import Client
from mcp.client.streamable_http import streamable_http_client

from umeko.host.identities import IdentityStore
from umeko.server.admin import create_admin_app


def test_access_mode_admin_controls_shared_identity_and_ip_log(machine_client):
    client, app, account, _ = machine_client
    store, identities = app.state.store, app.state.identity_store
    admin_user = store.create_user("access-admin", "fixture-pass", "admin")
    admin_app = create_admin_app(app.state.agent_service.settings, app.state.agent_service, store)
    with TestClient(admin_app) as admin:
        assert admin.put("/admin/v1/service-access", json={"auth_mode": "anonymous"}).status_code == 401
        admin.cookies.set("umeko_admin", store.issue_token(admin_user["id"]))
        assert admin.get("/admin/v1/service-access").json()["auth_mode"] == "required"
        assert client.post("/agent/fixture/v1/tasks", json={"prompt": "anonymous"}).status_code == 401
        assert admin.put("/admin/v1/service-access", json={"auth_mode": "invalid"}).status_code == 422
        assert admin.put("/admin/v1/service-access", json={"auth_mode": "anonymous"}).status_code == 200
        assert IdentityStore(store).auth_mode() == "anonymous"
        assert not client.get("/agent/fixture/.well-known/agent-card.json").json().get("securityRequirements")
        first_ip = TestClient(app, base_url="http://127.0.0.1", client=("192.0.2.7", 5000))
        second_ip = TestClient(app, base_url="http://127.0.0.1", client=("192.0.2.8", 5001))
        response = first_ip.post("/agent/fixture/v1/tasks", json={"prompt": "anonymous"}, headers={"X-Forwarded-For": "198.51.100.99"})
        assert response.status_code == 202
        task_id = response.json()["id"]
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            task = second_ip.get("/agent/fixture/v1/tasks/" + task_id).json()
            if task["status"] in {"completed", "failed", "cancelled"}:
                break
            time.sleep(.03)
        assert task["status"] == "completed"
        assert "caller_ip" not in task
        artifact = task["artifacts"][0]
        assert second_ip.get(artifact["download_url"]).status_code == 200
        entry = next(t for t in admin.get("/admin/v1/tasks").json() if t["id"] == task_id)
        assert entry["caller"] == "免鉴权调用" and entry["caller_ip"] == "192.0.2.7"
        assert len(second_ip.get("/agent/fixture/v1/tasks").json()["tasks"]) == 1
        assert identities.anonymous_principal()["user_id"] == IdentityStore(store).anonymous_principal()["user_id"]
        with store.connect() as db:
            assert db.execute("SELECT COUNT(*) FROM users WHERE kind='anonymous'").fetchone()[0] == 1
        assert client.get("/agent/fixture/v1/tasks", headers={"Authorization": "Bearer invalid"}).status_code == 401
        headers = {"Authorization": "Bearer " + account["token"]}
        assert client.get("/agent/fixture/v1/tasks", headers=headers).json()["tasks"] == []
        assert client.get("/agent/fixture/v1/tasks/" + task_id, headers=headers).status_code == 404
        assert client.get("/v1/sessions").status_code == 401
        assert client.put("/admin/v1/service-access", json={"auth_mode": "required"}).status_code == 404
        assert admin.put("/admin/v1/service-access", json={"auth_mode": "required"}).status_code == 200
        assert client.get("/agent/fixture/v1/tasks/" + task_id).status_code == 401
        assert client.get("/agent/fixture/v1/tasks", headers=headers).status_code == 200
        assert client.get("/agent/fixture/.well-known/agent-card.json").json()["securityRequirements"]
        first_ip.close()
        second_ip.close()


@pytest.mark.parametrize("machine_app", ["", "/doc-master/consistency/image-text"], indirect=True)
def test_anonymous_official_mcp_and_a2a_clients(machine_server):
    base, app, _, _ = machine_server
    app.state.identity_store.set_auth_mode("anonymous")

    async def check():
        async with httpx2.AsyncClient(trust_env=False) as http:
            async with Client(streamable_http_client(base + "/mcp", http_client=http), cache=None) as client:
                result = await client.call_tool("submit_task", {"prompt": "hi MCP"})
                assert not result.is_error, result
                task = result.structured_content
                for _ in range(100):
                    result = await client.call_tool("get_task", {"task_id": task["id"]})
                    task = result.structured_content
                    if task["status"] in {"completed", "failed", "cancelled"}:
                        break
                    await asyncio.sleep(.03)
                assert task["status"] == "completed"
                artifact = task["artifacts"][0]
                result = await client.call_tool("read_artifact", {"task_id": task["id"], "artifact_id": artifact["id"]})
                assert "hi MCP" in result.structured_content["text"]
        async with httpx.AsyncClient(headers={"A2A-Version": "1.0"}, trust_env=False, timeout=15) as http:
            client = await ClientFactory(ClientConfig(httpx_client=http, streaming=True)).create_from_url(base)
            request = a2a.SendMessageRequest(message=a2a.Message(message_id="anonymous-hi", role=a2a.Role.ROLE_USER,
                                                              parts=[a2a.Part(text="hi A2A")]))
            events = [event async for event in client.send_message(request)]
            task_id = next(e.task.id for e in events if e.HasField("task"))
            task = await client.get_task(a2a.GetTaskRequest(id=task_id, history_length=0))
            assert task.status.state == a2a.TaskState.TASK_STATE_COMPLETED
            assert "hi A2A" in task.artifacts[0].parts[0].text
            assert events[-1].status_update.status.state == a2a.TaskState.TASK_STATE_COMPLETED
        with app.state.store.connect() as db:
            records = db.execute("SELECT user_id,source,caller_ip FROM service_tasks ORDER BY source").fetchall()
            assert len(records) == 2
            assert records[0]["user_id"] == records[1]["user_id"]
            assert {r["source"] for r in records} == {"a2a", "mcp"}
            assert all(r["caller_ip"] == "127.0.0.1" for r in records)

    asyncio.run(check())
