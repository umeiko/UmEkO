import base64
import json
import time

import pytest

from conftest import wait_task
from umeko.host.tasks import TaskService
from umeko.server.admin import create_admin_app
from fastapi.testclient import TestClient


def bearer(account):
    return {"Authorization": "Bearer " + account["token"]}


def test_task_roundtrip_artifact_isolation_and_memory_release(machine_client):
    client, app, a, b = machine_client
    payload = {"prompt": "inspect", "files": [{"name": "input.txt", "content_base64": base64.b64encode(b"fixture input").decode()}]}
    response = client.post("/v1/tasks", json=payload, headers={**bearer(a), "Idempotency-Key": "same"})
    assert response.status_code == 202, response.text
    task_id = response.json()["id"]
    assert client.post("/v1/tasks", json=payload, headers={**bearer(a), "Idempotency-Key": "same"}).json()["id"] == task_id
    assert client.post("/v1/tasks", json={"prompt": "different"}, headers={**bearer(a), "Idempotency-Key": "same"}).status_code == 409
    result = wait_task(client, task_id, a["token"])
    assert result["status"] == "completed", result
    assert "fixture input" in result["reply"]
    artifact = result["artifacts"][0]
    url = artifact["download_url"]
    assert "fixture input" in client.get(url, headers=bearer(a)).text
    assert client.get(url, headers=bearer(b)).status_code == 404
    assert client.get("/v1/tasks/" + task_id, headers=bearer(b)).status_code == 404
    assert client.post("/v1/tasks/" + task_id + "/cancel", headers=bearer(b)).status_code == 404
    assert client.get("/v1/tasks", headers=bearer(b)).json()["tasks"] == []
    stream = client.get("/v1/tasks/" + task_id + "/events", headers=bearer(a))
    assert stream.headers["x-accel-buffering"] == "no"
    assert "event: task.completed" in stream.text
    deadline = time.monotonic() + 5
    while app.state.task_service._active and time.monotonic() < deadline:
        time.sleep(.03)
    assert not app.state.agent_service.sessions
    assert not app.state.agent_service.runs
    assert app.state.store.sessions(a["user_id"]) == []
    assert all(u["id"] != a["user_id"] for u in app.state.store.list_users())
    assert not app.state.task_service._directory(task_id).exists()
    base = "http://127.0.0.1/v1/tasks"
    create_token = app.state.identity_store.issue_access_token(a["id"], a["token"], base, ["tasks:create"])["access_token"]
    repeated = client.post("/v1/tasks", json=payload, headers={"Authorization": "Bearer " + create_token, "Idempotency-Key": "same"})
    assert repeated.status_code == 202 and repeated.json()["id"] == task_id
    assert repeated.json()["reply"] is None and repeated.json()["artifacts"] == []
    cancel_token = app.state.identity_store.issue_access_token(a["id"], a["token"], base, ["tasks:cancel"])["access_token"]
    stopped = client.post("/v1/tasks/" + task_id + "/cancel", headers={"Authorization": "Bearer " + cancel_token})
    assert stopped.status_code == 200
    assert stopped.json()["reply"] is None and stopped.json()["artifacts"] == []


def test_bounded_admission_cancel_and_permissions(machine_client):
    client, app, a, b = machine_client
    first = client.post("/v1/tasks", json={"prompt": "hold active"}, headers=bearer(a)).json()
    wait_task(client, first["id"], a["token"], terminal=False)
    queued = [client.post("/v1/tasks", json={"prompt": "never starts"}, headers=bearer(a)).json() for _ in range(2)]
    full = client.post("/v1/tasks", json={"prompt": "too many"}, headers=bearer(b))
    assert full.status_code == 429 and full.headers["retry-after"] == "5"
    assert client.post("/v1/tasks/" + queued[0]["id"] + "/cancel", headers=bearer(a)).json()["status"] == "cancelled"
    assert client.post("/v1/tasks/" + first["id"] + "/cancel", headers=bearer(a)).status_code == 200
    assert wait_task(client, first["id"], a["token"])["status"] == "cancelled"
    readonly = app.state.identity_store.create("readonly", ["tasks:read"])
    assert client.post("/v1/tasks", json={"prompt": "forbidden"}, headers=bearer(readonly)).status_code == 403
    assert client.post("/v1/tasks", json={"prompt": "bad", "files": [{"name": "../bad.txt", "content_base64": "eA=="}]}, headers=bearer(a)).status_code == 400


def test_oauth_rotation_revocation_and_audience(machine_client):
    client, app, a, b = machine_client
    token = client.post("/oauth/token", data={"grant_type": "client_credentials", "client_id": a["id"],
                        "client_secret": a["token"], "resource": "http://127.0.0.1/v1/tasks", "scope": "tasks:read"})
    assert token.status_code == 200, token.text
    key = token.json()["access_token"]
    assert client.get("/v1/tasks", headers={"Authorization": "Bearer " + key}).status_code == 200
    assert client.post("/a2a", json={}, headers={"Authorization": "Bearer " + key}).status_code == 401
    assert client.post("/v1/tasks", json={"prompt": "forbidden"}, headers={"Authorization": "Bearer " + key}).status_code == 403
    assert client.post("/oauth/token", data={"grant_type": "client_credentials", "client_id": a["id"], "client_secret": key}).status_code == 401
    assert client.post("/oauth/token", data={"grant_type": "client_credentials", "client_id": a["id"], "client_secret": a["token"], "resource": "https://wrong.invalid"}).status_code == 400
    rotated = app.state.identity_store.update(a["id"], rotate=True)
    assert client.get("/v1/tasks", headers=bearer(a)).status_code == 401
    assert client.get("/v1/tasks", headers={"Authorization": "Bearer " + key}).status_code == 401
    assert client.get("/v1/tasks", headers=bearer(rotated)).status_code == 200
    app.state.identity_store.update(a["id"], enabled=False)
    assert client.get("/v1/tasks", headers=bearer(rotated)).status_code == 401


def test_restart_queued_tasks_and_expiry(machine_app):
    app, a, b, settings = machine_app
    tasks, store = app.state.task_service, app.state.store
    principal = app.state.identity_store.authenticate(a["token"])
    queued = tasks.submit(principal, {"prompt": "resume queued"})
    with store.connect() as db:
        interrupted = tasks.submit(principal, {"prompt": "interrupted"})
        db.execute("UPDATE service_tasks SET status='running' WHERE id=?", (interrupted["id"],))
    restarted = TaskService(app.state.agent_service, settings)
    restarted.start()
    try:
        assert restarted.get(principal, interrupted["id"])["status"] == "failed"
        assert any(e["type"] == "task.failed" for e in restarted.events(principal, interrupted["id"]))
        deadline = time.monotonic()+5
        while restarted.get(principal, queued["id"])["status"] not in {"completed","failed"} and time.monotonic()<deadline:
            time.sleep(.03)
        assert restarted.get(principal, queued["id"])["status"] == "completed"
        deadline = time.monotonic()+3
        while queued["id"] in restarted._active and time.monotonic()<deadline:
            time.sleep(.02)
        with store.connect() as db:
            db.execute("UPDATE service_tasks SET expires_at='2000-01-01' WHERE id=?", (queued["id"],))
        with pytest.raises(KeyError):
            restarted.get(principal, queued["id"])
        deadline = time.monotonic()+3
        while queued["id"] in restarted._active and time.monotonic()<deadline:
            time.sleep(.02)
        assert restarted.cleanup() == 1
        with store.connect() as db:
            assert db.execute("SELECT COUNT(*) FROM agent_sessions WHERE purpose='task'").fetchone()[0] == 0
    finally:
        restarted.stop()
        app.state.agent_service.run_manager.shutdown()


def test_admin_monitor_and_credentials_are_admin_only(machine_client):
    client, app, a, b = machine_client
    store = app.state.store
    store.create_user("fixture-admin", "fixture-pass", "admin")
    user = store.create_user("ordinary", "fixture-pass")
    admin_app = create_admin_app(app.state.agent_service.settings, app.state.agent_service, store)
    with TestClient(admin_app) as admin:
        assert admin.get("/admin/v1/resources").status_code == 401
        admin.cookies.set("umeko_admin", store.issue_token(user["id"]))
        assert admin.get("/admin/v1/resources").status_code == 401
        admin.cookies.clear()
        assert admin.post("/admin/login", json={"username":"fixture-admin","password":"fixture-pass"}).status_code == 200
        resource = admin.get("/admin/v1/resources")
        assert resource.status_code == 200
        assert resource.json()["current"]["host"]["memory_total"] > 0
        created = admin.post("/admin/v1/service-accounts", json={"name":"integration"})
        assert created.status_code == 201
        assert "token" not in json.dumps(admin.get("/admin/v1/service-accounts").json()["accounts"])
        assert client.get("/admin/v1/resources").status_code == 404
