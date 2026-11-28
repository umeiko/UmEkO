"""Multi-replica acceptance against isolated PostgreSQL and synthetic model work."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier, Event
import time

import pytest
from fastapi.testclient import TestClient

from umeko.agent import UmekoAgent
from umeko.cancellation import OperationCancelled
from umeko.config import ModelConfig, Settings
from umeko.host.builtin_skills import ASSETS, restore_missing_builtin_package
from umeko.host.identities import SCOPES
from umeko.host.replicas import ReplicaLeaseLost
from umeko.llm import LLMClient
from umeko.server.app import create_app


def eventually(read, predicate):
    timeout = time.monotonic() + 15
    while time.monotonic() < timeout:
        value = read()
        if predicate(value):
            return value
        time.sleep(.05)
    pytest.fail(f"state did not reach the expected condition: {value!r}")


@pytest.fixture(params=["", "/team/work"])
def cluster(tmp_path, test_database_url, monkeypatch, request):
    if not test_database_url:
        pytest.skip("PostgreSQL replica integration")
    entered, finish = Event(), Event()

    def chat(agent, prompt, images=None):
        if prompt == "hold":
            entered.set()
            while not finish.wait(.02):
                if agent._should_cancel():
                    raise OperationCancelled()
        if prompt.startswith("attachment"):
            assert (agent._output_root / "attachments" / "fixture.txt").read_text() == "replica fixture"
        if "submit_results" in agent._skills:
            (agent._output_root / "generate" / "fixture.txt").write_text("replica result", encoding="utf-8")
            agent._skills["submit_results"].handler(text="replica result", files=[{"path": "generate/fixture.txt"}])
        agent._on_event("assistant.delta", {"text": "replica result"})
        return "replica result"

    monkeypatch.setattr(UmekoAgent, "chat", chat)
    settings = Settings(ModelConfig("fixture", "synthetic", "https://unused.invalid"),
                        database_url=test_database_url, replica_mode=True, base_path=request.param,
                        admin_base_path="/ops/admin", task_workers=1)

    def make(data_root=tmp_path / "data"):
        return create_app(settings, data_root=data_root, workspace_root=tmp_path / "out")

    with ThreadPoolExecutor(max_workers=2) as pool:
        starts = [pool.submit(make) for _ in range(2)]
        a, b = (job.result(timeout=30) for job in starts)
    try:
        yield a, b, entered, finish, make
    finally:
        finish.set()
        for app in (a, b):
            app.state.agent_service.run_manager.shutdown()


def test_cluster_tasks_keep_live_owners_and_share_file_volume(cluster):
    a, b, entered, finish, make = cluster
    first, second = (app.state.agent_service for app in (a, b))
    with pytest.raises(RuntimeError, match="挂载同一持久化卷"):
        make(first.data_root.parent / "incorrect-volume")
    user = first.store.create_user("cluster-fixture", "fixture-password")
    principal = {"user_id": user["id"], "scopes": sorted(SCOPES)}
    with TestClient(a):
        # B accepts input while A is the only running model worker.
        task = second.task_service.submit(principal, {"prompt": "attachment", "files": [
            {"name": "fixture.txt", "content_base64": "cmVwbGljYSBmaXh0dXJl"},
        ]})
        view = eventually(lambda: second.task_service.get(principal, task["id"]), lambda row: row["status"] in {"completed", "failed"})
        assert view["status"] == "completed", view["error"]
        assert second.task_service.artifact(principal, task["id"], view["artifacts"][0]["id"])[0].read_text() == "replica result"

        queued = first.task_service.submit(principal, {"prompt": "hold"})
        assert entered.wait(15)
        with TestClient(b):
            assert second.task_service.get(principal, queued["id"])["status"] == "running"
            assert all(event["type"] != "task.failed" for event in second.task_service.events(principal, queued["id"]))
            finish.set()
            eventually(lambda: second.task_service.get(principal, queued["id"]), lambda row: row["status"] == "completed")


def test_cluster_run_sse_cancel_and_workspace_cleanup_cross_replicas(cluster):
    a, b, entered, finish, _ = cluster
    first, second = (app.state.agent_service for app in (a, b))
    owner = first.store.create_user("workspace-fixture", "fixture-password")
    principal = {"user_id": owner["id"], "scopes": sorted(SCOPES)}
    prefix = first.settings.base_path
    with TestClient(a) as ui_a, TestClient(b) as ui_b:
        token = first.store.issue_token(owner["id"])
        for client in (ui_a, ui_b):
            client.cookies.set("umeko_auth", token, path=prefix or "/")
        task = first.task_service.submit(principal, {"prompt": "prepare"})
        eventually(lambda: second.task_service.get(principal, task["id"]), lambda row: row["status"] == "completed")
        workspace = second.task_service.open_workspace(task["workspace_token"], activity=True)
        run = first.task_service.create_workspace_run(task["workspace_token"], "hold", [])
        try:
            assert entered.wait(15)
            path = prefix + "/v1/runs/" + run.id
            assert ui_b.get(path).json()["id"] == run.id
            assert ui_b.delete(prefix + "/v1/sessions/" + workspace["session_id"]).status_code == 409
            assert second.active_run(workspace["session_id"]).id == run.id
            with pytest.raises(ValueError, match="正在运行"):
                second.task_service.create_workspace_run(task["workspace_token"], "duplicate", [])
            with first.store.connect() as db:
                db.execute("UPDATE service_tasks SET workspace_expires_at=? WHERE id=?", ("2000-01-01", task["id"]))
            assert second.task_service.cleanup_workspaces() == 0
            assert (first.get_session(workspace["session_id"]).root / "generate").is_dir()
            ui_b.cookies.clear()
            temporary = prefix + "/TMP/" + task["workspace_token"]
            assert ui_b.get(temporary + "/v1/temporary").json()["expires_at"] is None
            remote_run = temporary + "/v1/runs/" + run.id
            assert ui_b.post(remote_run + "/cancel").status_code == 200
            eventually(lambda: ui_b.get(remote_run).json(), lambda row: row.get("status") == "cancelled")
            events = ui_b.get(remote_run + "/events", headers={"Last-Event-ID": "1"})
            assert events.status_code == 200 and "event: run.cancelled" in events.text
            assert "event: run.queued" not in events.text
        finally:
            finish.set()


def test_cluster_only_recovers_expired_owner_and_fences_stale_writes(cluster):
    a, b, _, _, _ = cluster
    first, second = (app.state.agent_service for app in (a, b))
    owner = first.store.create_user("expired-fixture", "fixture-password")
    principal = {"user_id": owner["id"], "scopes": sorted(SCOPES)}
    first.replicas.start()
    try:
        session = first.create_session(user_id=owner["id"])
        run = first.run_manager.create(session.id)
        task = first.task_service.submit(principal, {"prompt": "interrupted fixture"})
        with first.store.connect() as db:
            db.execute("UPDATE service_tasks SET status='running',owner_id=? WHERE id=?", (first.replicas.id, task["id"]))
            db.execute("UPDATE replica_owners SET expires_at=clock_timestamp()-interval '1 second' WHERE id=?",
                       (first.replicas.id,))
        with TestClient(b):
            assert second.get_run(run.id).status == "failed"
            assert second.get_run(run.id).events_after(1)[0]["type"] == "run.failed"
            assert second.task_service.get(principal, task["id"])["status"] == "failed"
            with pytest.raises(ReplicaLeaseLost):
                run.emit("assistant.delta", text="stale")
            with first.store.connect() as db, pytest.raises(ReplicaLeaseLost):
                first.task_service._verify_task_owner(db, task["id"])
            assert TestClient(a).get(first.settings.base_path + "/health").status_code == 503
    finally:
        first.replicas.stop()


def test_cluster_model_budget_and_first_admin_are_global(cluster):
    a, b, _, _, _ = cluster
    first, second = (app.state.agent_service for app in (a, b))
    with ThreadPoolExecutor(max_workers=2) as pool:
        both = Barrier(2)
        def create_admin(service):
            both.wait(timeout=10)
            return service.store.create_first_admin("cluster-admin", "synthetic-password")
        requests = [pool.submit(create_admin, node) for node in (first, second)]
        assert sorted(job.result(timeout=15) for job in requests) == [False, True]
    provider = first.store.create_provider("fixture", "https://models.example.invalid/v1", "synthetic")
    model = first.store.add_model(provider["id"], "fixture-model", max_concurrent_requests=1)
    first.store.set_active_model(model["id"])
    owner = first.store.create_user("cluster-limit", "fixture-password")
    with TestClient(a), TestClient(b), ThreadPoolExecutor(max_workers=1) as pool:
        queue_a, queue_b = (LLMClient(node.effective_settings_for(owner["id"]).text_model)._call_queue
                            for node in (first, second))
        waiting, acquired = Event(), Event()
        def acquire():
            with queue_b.slot(on_wait=waiting.set):
                acquired.set()
        with queue_a.slot():
            future = pool.submit(acquire)
            assert waiting.wait(10)
            assert not acquired.is_set()
            assert queue_b.snapshot() == {"active": 1, "waiting": 1, "limit": 1}
        future.result(timeout=15)
        assert acquired.is_set()


def test_shared_volume_restore_can_publish_the_same_builtin_twice(tmp_path, monkeypatch):
    both = Barrier(2)
    rename = Path.rename

    def publish(path, target):
        if path.parent.name.startswith(".skill-restore-"):
            both.wait(timeout=10)
        return rename(path, target)

    monkeypatch.setattr(Path, "rename", publish)
    library = tmp_path / "shared"
    with ThreadPoolExecutor(max_workers=2) as pool:
        tasks = [pool.submit(restore_missing_builtin_package, ASSETS, library, "doc-image-qc",
                             ASSETS / "doc-image-qc/SKILL.md") for _ in range(2)]
    assert sorted(task.result() for task in tasks) == [False, True]
    assert (library / "doc-image-qc/scripts/render_report.py").is_file()
