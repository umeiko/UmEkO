import asyncio
import time
import base64

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
from conftest import wait_task


def wait_worker_release(tasks, task_id):
    for _ in range(200):
        with tasks._lock:
            if task_id not in tasks._active:
                return
        time.sleep(.01)
    raise AssertionError("Task worker did not release")


def test_delete_service_account_revokes_credentials_and_cleans_own_history(machine_client, monkeypatch):
    client, app, account, other = machine_client
    service, store, identities, tasks = app.state.agent_service, app.state.store, app.state.identity_store, app.state.task_service
    admin_user = store.create_user("deletion-admin", "fixture-pass", "admin")
    ordinary = store.create_user("deletion-ordinary", "fixture-pass")
    admin_app = create_admin_app(service.settings, service, store)
    path = "/admin/v1/service-accounts/" + account["id"]
    resource = "http://127.0.0.1/agent/fixture/v1/tasks"
    access = identities.issue_access_token(account["id"], account["token"], resource, ["tasks:read"])["access_token"]
    stale = identities.authenticate(account["token"])
    submitted = client.post("/agent/fixture/v1/tasks", json={"prompt": "delete own history", "files": [
        {"name": "input.txt", "content_base64": base64.b64encode(b"own attachment").decode()}]},
        headers={"Authorization": "Bearer " + account["token"]}).json()
    completed = wait_task(client, submitted["id"], account["token"])
    assert completed["status"] == "completed" and completed["artifacts"]
    wait_worker_release(tasks, completed["id"])
    with store.connect() as db:
        session_id = db.execute("SELECT session_id FROM service_tasks WHERE id=?", (completed["id"],)).fetchone()[0]
    # Reopen the completed session to exercise eviction as well as disk/DB cleanup.
    service.get_session(session_id)
    own_root = service.data_root / "users" / account["user_id"]
    other_session = service.create_session(user_id=other["user_id"])
    staging = tasks._directory(completed["id"])
    staging.mkdir()
    (staging / "leftover.txt").write_text("stale upload", encoding="utf-8")
    with TestClient(admin_app) as admin:
        assert admin.delete(path).status_code == 401
        admin.cookies.set("umeko_admin", store.issue_token(ordinary["id"]))
        assert admin.delete(path).status_code == 401
        admin.cookies.set("umeko_admin", store.issue_token(admin_user["id"]))
        assert admin.delete(path).status_code == 204
        assert admin.delete(path).status_code == 404
        assert all(a["id"] != account["id"] for a in admin.get("/admin/v1/service-accounts").json()["accounts"])
        assert admin.get("/admin/v1/tasks").json() == []
        replacement = admin.post("/admin/v1/service-accounts", json={"name": account["name"]})
        assert replacement.status_code == 201 and replacement.json()["id"] != account["id"]
    assert identities.authenticate(account["token"]) is None
    assert identities.authenticate(access, resource) is None
    assert not own_root.exists() and not staging.exists() and session_id not in service.sessions
    assert other_session.root.exists() and store.session_by_id(other_session.id)
    assert identities.authenticate(other["token"])
    with store.connect() as db:
        for table, column, value in [("users", "id", account["user_id"]), ("agent_sessions", "user_id", account["user_id"]),
                                     ("messages", "session_id", session_id), ("session_files", "session_id", session_id),
                                     ("service_tasks", "user_id", account["user_id"]), ("service_task_events", "task_id", completed["id"]),
                                     ("service_task_artifacts", "task_id", completed["id"]), ("service_access_tokens", "account_id", account["id"])]:
            assert db.execute(f"SELECT COUNT(*) FROM {table} WHERE {column}=?", (value,)).fetchone()[0] == 0
    # An already authenticated request must not recreate deleted task data.
    with pytest.raises(PermissionError, match="已删除"):
        tasks.submit(stale, {"prompt": "in flight after deletion"})
    with monkeypatch.context() as in_flight:
        in_flight.setattr(identities, "authenticate", lambda *_: stale)
        with pytest.raises(PermissionError, match="invalid_client"):
            identities.issue_access_token(account["id"], account["token"], resource, ["tasks:read"])
    # Even in open access mode, a supplied deleted credential cannot fall back to anonymous.
    identities.set_auth_mode("anonymous")
    assert client.get("/agent/fixture/v1/tasks", headers={"Authorization": "Bearer " + account["token"]}).status_code == 401


@pytest.mark.parametrize("status", ["queued", "running"])
def test_delete_service_account_waits_for_unfinished_tasks(machine_client, status):
    client, app, account, _ = machine_client
    service, store, tasks = app.state.agent_service, app.state.store, app.state.task_service
    if status == "queued":
        tasks.stop()
    admin_user = store.create_user("busy-admin", "fixture-pass", "admin")
    submitted = client.post("/agent/fixture/v1/tasks", json={"prompt": "hold until stopped"},
                            headers={"Authorization": "Bearer " + account["token"]}).json()
    if status == "running":
        wait_task(client, submitted["id"], account["token"], terminal=False)
    with TestClient(create_admin_app(service.settings, service, store)) as admin:
        admin.cookies.set("umeko_admin", store.issue_token(admin_user["id"]))
        path = "/admin/v1/service-accounts/" + account["id"]
        rejected = admin.delete(path)
        assert rejected.status_code == 409 and "资源监控" in rejected.json()["detail"]
        assert app.state.identity_store.authenticate(account["token"])
        assert admin.post("/admin/v1/tasks/" + submitted["id"] + "/cancel").status_code == 200
        assert wait_task(client, submitted["id"], account["token"])["status"] == "cancelled"
        wait_worker_release(tasks, submitted["id"])
        assert admin.delete(path).status_code == 204


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
