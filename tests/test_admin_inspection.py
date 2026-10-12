import base64
from dataclasses import replace
import json

import pytest
from fastapi.testclient import TestClient

from conftest import wait_task
from umeko.server.admin import create_admin_app


@pytest.mark.parametrize("machine_app", ["", "/team/workbench"], indirect=True)
def test_admin_record_inspection_auth_context_and_no_session_wakeup(machine_app):
    app, caller, _, settings = machine_app
    service, store = app.state.agent_service, app.state.store
    prefix = "/operations/umeko" if settings.base_path else ""
    admin_app = create_admin_app(replace(settings, admin_base_path=prefix), service, store)
    admin_user = store.create_user("inspection-admin", "fixture-only-password", "admin")
    owner = store.create_user("record-owner", "fixture-only-password")
    session = service.create_session(user_id=owner["id"], title="Inspection fixture")
    store.add_message(session.id, "user", "Old question")
    store.save_context_summary(session.id, "Earlier conversation summary", 0)
    store.add_message(session.id, "assistant", "A saved **answer**")
    store.add_message(session.id, "user", "Latest question", json.dumps(["pasted.png"]))
    session_tool = store.add_tool_event(session.id, "subagent", "read_pack_file",
                                        json.dumps(json.dumps({"path": "SKILL.md"})),
                                        json.dumps("workspace/\n└── input.txt"), "web-run")
    service.evict_session(session.id)
    session_url = prefix + "/admin/v1/sessions/" + session.id
    with TestClient(app) as user, TestClient(admin_app) as admin:
        assert admin.get(session_url).status_code == 401
        admin.cookies.set("umeko_admin", store.issue_token(owner["id"]), path=prefix or "/")
        assert admin.get(session_url).status_code == 401
        admin.cookies.clear()
        assert admin.post(prefix + "/admin/login", json={
            "username": admin_user["username"], "password": "fixture-only-password",
        }).status_code == 200
        loaded_before = set(service.sessions)
        view = admin.get(session_url).json()
        assert view["kind"] == "session"
        assert view["record"]["username"] == owner["username"]
        assert view["record"]["loaded"] is False
        assert view["context"]["summary"] == "Earlier conversation summary"
        assert [m["in_context"] for m in view["messages"]] == [False, True, True]
        assert view["messages"][-1]["attachments"] == ["pasted.png"]
        assert view["tools"][0]["id"] == session_tool
        assert json.loads(view["tools"][0]["result"]) == "workspace/\n└── input.txt"
        assert set(service.sessions) == loaded_before
        assert user.get(settings.base_path + "/admin/v1/sessions/" + session.id).status_code == 404

        definition = app.state.fixture_agent
        service.agent_registry.save({**definition, "system_prompt": "Original instruction"}, definition["id"])
        task = user.post(settings.base_path + "/agent/fixture/v1/tasks", json={
            "prompt": "inspect task", "files": [{"name": "input.txt", "content_base64": base64.b64encode(b"saved input").decode()}],
        }, headers={"Authorization": "Bearer " + caller["token"]}).json()
        # Use the underlying service for the prefixed case; wait_task assumes a root route.
        if settings.base_path:
            import time
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                result = user.get(settings.base_path + "/agent/fixture/v1/tasks/" + task["id"],
                                  headers={"Authorization": "Bearer " + caller["token"]}).json()
                if result["status"] == "completed":
                    break
                time.sleep(.02)
            assert result["status"] == "completed"
        else:
            assert wait_task(user, task["id"], caller["token"])["status"] == "completed"
        with store.connect() as db:
            row = db.execute("SELECT session_id,run_id FROM service_tasks WHERE id=?", (task["id"],)).fetchone()
        own_tool = store.add_tool_event(row["session_id"], "main", "run_skill_script", '{"script":"fixture.py"}', "saved tool output", row["run_id"])
        store.add_tool_event(row["session_id"], "main", "other_run", "{}", "must not leak into this task", "different-run")
        service.agent_registry.save({**definition, "system_prompt": "Changed later"}, definition["id"])
        loaded_before = set(service.sessions)
        detail = admin.get(prefix + "/admin/v1/tasks/" + task["id"]).json()
        assert detail["input"]["prompt"] == "inspect task"
        assert detail["input"]["files"][0]["name"] == "input.txt"
        assert "content_base64" not in detail["input"]["files"][0]
        assert detail["output"]["reply"] == "Processed: inspect task / saved input"
        assert detail["output"]["artifacts"][0]["name"] == "generate/report.txt"
        assert detail["context"]["agent_snapshot"]["system_prompt"] == "Original instruction"
        assert [t["id"] for t in detail["tools"]] == [own_tool]
        assert detail["messages"][0]["content"] == "inspect task"
        assert detail["messages"][-1]["content"] == detail["output"]["reply"]
        assert detail["events"] and detail["record"]["run_id"] == row["run_id"]
        assert set(service.sessions) == loaded_before
        assert "fixture-key" not in json.dumps(detail)
        assert "password_hash" not in json.dumps(detail)
        assert user.get(settings.base_path + "/admin/v1/tasks/" + task["id"]).status_code == 404
        assert admin.get(prefix + "/admin/v1/tasks/missing").status_code == 404
        assert admin.get(prefix + "/admin/v1/sessions/missing").status_code == 404
        admin.post(prefix + "/admin/logout")
        assert admin.get(session_url).status_code == 401
        assert admin.get(prefix + "/admin/v1/tasks/" + task["id"]).status_code == 401


def test_admin_queued_and_failed_tasks_without_execution_session(machine_app):
    app, caller, _, settings = machine_app
    service, store = app.state.agent_service, app.state.store
    definition = app.state.fixture_agent
    principal = {"user_id": caller["user_id"], "agent_id": definition["id"],
                 "agent_definition": definition, "scopes": caller["scopes"]}
    task = service.task_service.submit(principal, {"prompt": "Not started"})
    user = store.create_user("inspection-admin", "fixture-only-password", "admin")
    admin_app = create_admin_app(settings, service, store)
    try:
        with TestClient(admin_app) as admin:
            admin.cookies.set("umeko_admin", store.issue_token(user["id"]))
            queued = admin.get("/admin/v1/tasks/" + task["id"]).json()
            assert queued["record"]["status"] == "queued"
            assert queued["context"]["session_available"] is False
            assert queued["messages"] == queued["tools"] == []
            assert queued["input"]["prompt"] == "Not started"
            with store.connect() as db:
                db.execute("UPDATE service_tasks SET status='failed',error=? WHERE id=?", ("Startup failed", task["id"]))
            failed = admin.get("/admin/v1/tasks/" + task["id"]).json()
            assert failed["output"]["error"] == "Startup failed"
            assert failed["output"]["reply"] is None
    finally:
        service.run_manager.shutdown()
