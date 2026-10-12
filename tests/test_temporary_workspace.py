import base64
import time
from urllib.parse import urlsplit

import pytest

from conftest import wait_task


def submit(client, account, prefix="", prompt="temporary test"):
    response = client.post(prefix + "/agent/fixture/v1/tasks", headers={"Authorization": "Bearer " + account["token"]} if account.get("token") else {},
                           json={"prompt": prompt, "files": [{"name": "input.txt", "content_base64": base64.b64encode(b"uploaded input").decode()}]})
    assert response.status_code == 202, response.text
    return response.json()


def completed(client, account, task, prefix):
    for _ in range(200):
        result = client.get(prefix + "/agent/fixture/v1/tasks/" + task["id"], headers={"Authorization": "Bearer " + account["token"]} if account.get("token") else {}).json()
        if result["status"] in {"completed", "failed", "cancelled"}:
            assert result["status"] == "completed", result
            return result
        time.sleep(.02)
    raise AssertionError("Task did not complete")


@pytest.mark.parametrize("machine_app", ["", "/dept/doc-master/consistency"], indirect=True)
@pytest.mark.parametrize("anonymous", [False, True])
def test_temporary_continuation_and_scope(machine_client, anonymous):
    client, app, account, other = machine_client
    prefix = app.root_path
    if anonymous:
        app.state.identity_store.set_auth_mode("anonymous")
        account = {}
    store, service = app.state.store, app.state.agent_service
    provider = store.create_provider("TMP provider", "https://temporary.invalid/v1", "private-fixture-key")
    model = store.add_model(provider["id"], "temporary-fixed-model", False)
    store.set_active_model(model["id"])
    store.upsert_default_skill("public.md", "---\nname: Public\ndescription: Public workflow\n---\nPUBLIC_SKILL")
    store.upsert_default_skill("private.md", "---\nname: Private\ndescription: Other workflow\n---\nOTHER_SKILL")
    definition = service.agent_registry.save({**app.state.fixture_agent, "skill_names": ["public.md"]}, app.state.fixture_agent["id"])
    app.state.fixture_agent = definition
    task = submit(client, account, prefix)
    url = task["workspace_url"]
    assert url.startswith("http://127.0.0.1" + prefix + "/TMP/")
    assert "/agent/fixture/TMP/" not in url and "workspace_token" not in task
    assert len(urlsplit(url).path.rsplit("/", 1)[1]) >= 40
    result = completed(client, account, task, prefix)
    assert result["workspace_url"] == url
    html = client.get(url)
    assert html.status_code == 200 and html.headers["cache-control"] == "no-store"
    assert 'name="umeko-temporary-path"' in html.text
    assert prefix + "/static/ui/assets/" in html.text
    base = urlsplit(url).path
    info = client.get(base + "/v1/temporary").json()
    assert info["state"] == "ready"
    sid = info["session_id"]
    models = client.get(base + "/v1/models")
    assert models.status_code == 200
    assert models.json()["providers"][0]["models"] == [{"id": model["id"], "name": "temporary-fixed-model", "vision": False}]
    assert "private-fixture-key" not in models.text and "temporary.invalid" not in models.text
    scope = base + "/v1/sessions/" + sid
    assert [row["id"] for row in client.get(base + "/v1/sessions").json()] == [sid]
    assert "uploaded input" in client.get(scope + "/messages").text
    resources = client.get(scope + "/client/skills").json()
    assert [r["name"] for r in resources] == ["public.md"]
    assert resources[0]["mounted"] is True
    assert "PUBLIC_SKILL" in client.get(scope + "/client/skills/public.md").text
    assert client.get(scope + "/client/skills/private.md").status_code == 403
    tree = client.get(scope + "/workspace/tree").json()
    assert {node["name"] for node in tree} == {"workspace", "attachments", "generate"}
    assert client.get(scope + "/workspace/files/content", params={"path": "attachments/input.txt"}).content == b"uploaded input"
    saved = client.post(scope + "/files?filename=followup.txt", content=b"followup input")
    assert saved.status_code == 201, saved.text
    run = client.post(scope + "/runs", json={"input": "Continue temporary conversation", "attachments": [saved.json()["id"]]})
    assert run.status_code == 202, run.text
    run_id = run.json()["id"]
    stream = client.get(base + "/v1/runs/" + run_id + "/events")
    assert stream.status_code == 200 and "run.completed" in stream.text
    assert stream.headers["x-accel-buffering"] == "no"
    messages = client.get(scope + "/messages").json()
    assert [m["role"] for m in messages] == ["user", "assistant", "user", "assistant"]
    assert "Continue temporary conversation" in messages[-1]["content"]
    assert client.get(base + "/v1/runs/" + run_id).json()["status"] == "completed"
    # A continuation changes the conversation, not the original protocol response.
    assert completed(client, account, task, prefix)["reply"] == result["reply"]
    other_session = service.create_session(user_id=other["user_id"])
    for path in ["/v1/auth/me", "/v1/auth/avatar", "/v1/sessions/" + other_session.id + "/messages", "/admin/v1/users", "/agent/fixture/mcp"]:
        assert client.get(base + path).status_code == 403
    for path, method, payload in [
        ("/v1/sessions", "post", {}),
        ("/v1/auth/model-prefs", "put", {"main_model_id": None}),
        ("/v1/sessions/" + sid + "/model", "put", {"model_id": None}),
        ("/v1/sessions/" + sid + "/clone", "post", {}),
        ("/v1/sessions/" + sid, "delete", None),
        ("/v1/sessions/" + sid + "/client/skills/public.md", "patch", {"mounted": False}),
    ]:
        assert client.request(method, base + path, json=payload).status_code == 403
    assert client.get(scope + "/workspace/files/content", params={"path": "../umeko.db"}).status_code == 403
    # Cache eviction is reversible; persistent deletion/expiration invalidates the capability.
    service.evict_session(sid)
    assert client.get(base + "/v1/temporary").status_code == 200
    service.delete_session_admin(sid)
    assert client.get(base + "/v1/temporary").status_code == 410
    assert client.get(scope + "/messages").status_code == 410
    assert sid not in service.sessions


def test_expired_unknown_and_pending_workspace(machine_client):
    client, app, account, _ = machine_client
    task = submit(client, account, prompt="hold original")
    path = urlsplit(task["workspace_url"]).path
    # A queued task already has a usable URL; it never creates a second session.
    info = client.get(path + "/v1/temporary")
    assert info.status_code == 200
    while not app.state.task_service._active:
        time.sleep(.01)
    queued = submit(client, account, prompt="queued pending workspace")
    waiting = client.get(queued["workspace_url"] + "/v1/temporary")
    assert waiting.status_code == 200 and waiting.json()["state"] == "pending"
    assert waiting.json()["session_id"] is None
    client.post("/agent/fixture/v1/tasks/" + queued["id"] + "/cancel", headers={"Authorization": "Bearer " + account["token"]})
    if info.json()["state"] == "ready":
        sid = info.json()["session_id"]
        assert client.post(path + "/v1/sessions/" + sid + "/runs", json={"input": "too early"}).status_code == 400
    client.post("/agent/fixture/v1/tasks/" + task["id"] + "/cancel", headers={"Authorization": "Bearer " + account["token"]})
    wait_task(client, task["id"], account["token"])
    with app.state.store.connect() as db:
        db.execute("UPDATE service_tasks SET expires_at='2000-01-01T00:00:00+00:00' WHERE id=?", (task["id"],))
    for base in [path, "/TMP/nonexistent-capability"]:
        assert client.get(base).status_code == 200
        expired = client.get(base + "/v1/temporary")
        assert expired.status_code == 410 and expired.json()["code"] == "temporary_workspace_expired"
        assert client.post(base + "/v1/sessions", json={}).status_code == 410


def test_restricted_credentials_cannot_mint_workspace_write_access(machine_client):
    client, app, account, _ = machine_client
    task = submit(client, account)
    completed(client, account, task, "")
    endpoint = "http://127.0.0.1/agent/fixture/v1/tasks"
    token = app.state.identity_store.issue_access_token(account["id"], account["token"], endpoint, ["tasks:read"])["access_token"]
    view = client.get("/agent/fixture/v1/tasks/" + task["id"], headers={"Authorization": "Bearer " + token}).json()
    assert view["workspace_url"] is None and "workspace_token" not in view
    listing = client.get("/agent/fixture/v1/tasks", headers={"Authorization": "Bearer " + token}).json()
    assert all(t["workspace_url"] is None for t in listing["tasks"])
    # Revocation invalidates an already issued capability, too.
    app.state.identity_store.update(account["id"], enabled=False)
    assert client.get(task["workspace_url"] + "/v1/temporary").status_code == 410


def test_active_continuation_survives_gc_and_renews_metadata(machine_client):
    client, app, account, _ = machine_client
    task = submit(client, account)
    completed(client, account, task, "")
    while app.state.task_service._active:
        time.sleep(.01)
    base = urlsplit(task["workspace_url"]).path
    sid = client.get(base + "/v1/temporary").json()["session_id"]
    scope = base + "/v1/sessions/" + sid
    upload = client.post(scope + "/workspace/files?filename=later.txt&path=generate", content=b"continuation metadata")
    assert upload.status_code == 201
    run = client.post(scope + "/runs", json={"input": "hold continuation"})
    assert run.status_code == 202, run.text
    with app.state.store.connect() as db:
        db.execute("UPDATE service_tasks SET expires_at='2000-01-01T00:00:00+00:00' WHERE id=?", (task["id"],))
    assert app.state.task_service.cleanup() == 0
    assert client.get(base + "/v1/temporary").status_code == 200
    assert client.post(base + "/v1/runs/" + run.json()["id"] + "/cancel").status_code == 200
    for _ in range(200):
        with app.state.store.connect() as db:
            row = db.execute("SELECT expires_at,file_manifest_json FROM service_tasks WHERE id=?", (task["id"],)).fetchone()
        if row["expires_at"] > '2020' and 'later.txt' in (row["file_manifest_json"] or ''):
            break
        time.sleep(.02)
    else:
        raise AssertionError("Continuation did not renew its lease and file snapshot")
    assert client.get(base + "/v1/temporary").status_code == 200


def test_idle_lease_heartbeat_activity_and_metadata_preservation(machine_client):
    client, app, account, _ = machine_client
    task = submit(client, account)
    completed(client, account, task, "")
    while app.state.task_service._active:
        time.sleep(.01)
    with app.state.store.connect() as db:
        pure = dict(db.execute("SELECT * FROM service_tasks WHERE id=?", (task["id"],)).fetchone())
    assert pure["workspace_opened_at"] is None
    from datetime import datetime, timezone
    assert 0 < (datetime.fromisoformat(pure["workspace_expires_at"]) - datetime.now(timezone.utc)).total_seconds() <= 900
    url = task["workspace_url"]
    first = client.get(url + "/v1/temporary").json()
    sid = first["session_id"]
    assert first["idle_seconds"] == 3600
    with app.state.store.connect() as db:
        opened = dict(db.execute("SELECT * FROM service_tasks WHERE id=?", (task["id"],)).fetchone())
    assert 3500 < (datetime.fromisoformat(opened["workspace_expires_at"]) - datetime.now(timezone.utc)).total_seconds() <= 3600
    client.get(url + "/v1/temporary")
    with app.state.store.connect() as db:
        heartbeat = dict(db.execute("SELECT * FROM service_tasks WHERE id=?", (task["id"],)).fetchone())
    assert heartbeat["workspace_expires_at"] == opened["workspace_expires_at"]
    assert client.post(url + "/v1/temporary/activity").status_code == 200
    with app.state.store.connect() as db:
        activity = dict(db.execute("SELECT * FROM service_tasks WHERE id=?", (task["id"],)).fetchone())
        db.execute("UPDATE service_tasks SET workspace_expires_at='2000-01-01T00:00:00+00:00' WHERE id=?", (task["id"],))
    assert activity["workspace_expires_at"] > heartbeat["workspace_expires_at"]
    expired_result = completed(client, account, task, "")
    for artifact in expired_result["artifacts"]:
        assert client.get(artifact["download_url"], headers={"Authorization": "Bearer " + account["token"]}).status_code == 404
    root = app.state.agent_service.sessions[sid].root if sid in app.state.agent_service.sessions else app.state.agent_service.data_root / "users" / activity["user_id"] / "sessions" / sid
    assert root.is_dir()
    assert app.state.task_service.cleanup_workspaces() == 1
    assert not root.exists()
    assert client.get(url + "/v1/temporary").status_code == 410
    assert client.post(url + "/v1/temporary/activity").status_code == 410
    assert app.state.store.messages(sid)  # Call records survive file/node reclamation.
    with app.state.store.connect() as db:
        retained = dict(db.execute("SELECT * FROM service_tasks WHERE id=?", (task["id"],)).fetchone())
    assert retained["file_manifest_json"] and retained["workspace_evicted_at"]
    assert completed(client, account, task, "")["workspace_state"] == "expired"
    with pytest.raises(KeyError, match="已过期"):
        app.state.agent_service.get_session(sid)
    assert not root.exists()
