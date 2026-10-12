import base64
import json
import os
from pathlib import Path
import subprocess
import time

import pytest
from fastapi.testclient import TestClient

from conftest import wait_task
from umeko.agent import UmekoAgent
from umeko.host.file_manifest import capture, recorded_files, session_root
from umeko.server.admin import create_admin_app


def flatten(manifest):
    nodes = []
    pending = list(manifest["roots"])
    while pending:
        node = pending.pop()
        nodes.append(node)
        pending.extend(node.get("children", []))
    return {node["path"]: node for node in nodes}


def test_capture_is_only_safe_metadata_and_preserves_empty_and_hidden_entries(tmp_path, monkeypatch):
    root = tmp_path / "session"
    for name in ("workspace", "attachments", "generate", "client"):
        (root / name).mkdir(parents=True)
    (root / "workspace" / "empty").mkdir()
    (root / "attachments" / "pasted.png").write_bytes(b"PRIVATE_UPLOADED_CONTENT")
    (root / "workspace" / ".notes").write_text("PRIVATE_WORKSPACE_CONTENT")
    (root / "generate" / "reports").mkdir()
    (root / "generate" / "reports" / "result.html").write_text("PRIVATE_GENERATED_CONTENT")
    (root / "client" / "private-key.txt").write_text("PRIVATE_CREDENTIAL")
    def no_content(*args, **kwargs):
        raise AssertionError("File contents must not be read")
    monkeypatch.setattr(Path, "open", no_content)
    manifest = capture(root)
    nodes = flatten(manifest)
    assert manifest["complete"] and manifest["file_count"] == 3
    assert nodes["workspace/empty"]["children"] == []
    assert nodes["attachments/pasted.png"]["size"] == len(b"PRIVATE_UPLOADED_CONTENT")
    assert nodes["generate/reports/result.html"]["modified_at"]
    assert "workspace/.notes" in nodes
    assert all(not Path(path).is_absolute() for path in nodes)
    assert "PRIVATE_" not in json.dumps(manifest)
    assert "private-key.txt" not in json.dumps(manifest)


def test_capture_is_bounded_and_distinguishes_truncation_from_empty(tmp_path):
    (tmp_path / "workspace" / "nested" / "deeper").mkdir(parents=True)
    for index in range(5):
        (tmp_path / "workspace" / f"{index}.txt").write_text("fixture")
    for name in ("attachments", "generate"):
        (tmp_path / name).mkdir()
    limited = capture(tmp_path, max_entries=2)
    assert not limited["complete"] and limited["file_count"] <= 2
    shallow = capture(tmp_path, max_depth=1)
    assert not shallow["complete"]
    assert flatten(shallow)["workspace/nested"]["truncated"]
    assert not flatten(shallow)["workspace/nested"]["children"]


def test_links_are_recorded_without_traversal_or_foreign_paths(tmp_path):
    root, outside = tmp_path / "session", tmp_path / "outside"
    (root / "workspace").mkdir(parents=True)
    outside.mkdir()
    (outside / "FOREIGN_SECRET.txt").write_text("secret")
    link = root / "workspace" / "link"
    if os.name == "nt":
        subprocess.run(['cmd', '/c', 'mklink', '/J', str(link), str(outside)], check=True,
                       capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
    else:
        link.symlink_to(outside, target_is_directory=True)
    try:
        manifest = capture(root)
        assert flatten(manifest)["workspace/link"]["type"] == "link"
        assert "FOREIGN_SECRET" not in json.dumps(manifest)
        assert str(outside) not in json.dumps(manifest)
        assert manifest["file_count"] == 0
    finally:
        if os.name == "nt":
            link.rmdir()
        else:
            link.unlink()


def test_root_and_legacy_paths_are_bounded(tmp_path):
    assert session_root(tmp_path, "../other-user", "session") is None
    partial = recorded_files({"files": [{"name": "same.txt", "size": 3}, {"name": "same.txt", "size": 5}]},
                             [{"name": "generate/reports/result.zip", "size": 25},
                              {"name": "../private/key.txt", "size": 10}], "fixture-time")
    assert not partial["complete"] and partial["file_count"] == 3
    assert len(flatten(partial)["attachments"]["children"]) == 2
    assert "private" not in json.dumps(partial)
    assert flatten(partial)["generate/reports/result.zip"]["size"] == 25


@pytest.mark.parametrize("outcome", ["completed", "failed", "cancelled"])
def test_task_snapshot_survives_file_removal_without_rehydration(machine_client, monkeypatch, outcome):
    client, app, caller, _ = machine_client
    service, store = app.state.agent_service, app.state.store
    if outcome == "failed":
        def fail(agent, prompt, images=None):
            (agent._output_root / "generate" / "partial.txt").write_text("PRIVATE_PARTIAL_CONTENT")
            raise ValueError("Fixture failure")
        monkeypatch.setattr(UmekoAgent, "chat", fail)
    task = client.post('/agent/fixture/v1/tasks', headers={"Authorization": "Bearer " + caller["token"]},
                       json={"prompt": "hold metadata" if outcome == "cancelled" else "file metadata",
                             "files": [{"name": "input.txt", "content_base64": base64.b64encode(b"PRIVATE_UPLOAD_CONTENT").decode()}]}).json()
    if outcome == "cancelled":
        wait_task(client, task["id"], caller["token"], terminal=False)
        client.post('/agent/fixture/v1/tasks/' + task["id"] + '/cancel', headers={"Authorization": "Bearer " + caller["token"]})
    result = wait_task(client, task["id"], caller["token"])
    assert result["status"] == outcome
    for _ in range(100):
        with store.connect() as db:
            row = db.execute("SELECT session_id,file_manifest_json FROM service_tasks WHERE id=?", (task["id"],)).fetchone()
        if row["file_manifest_json"] and row["session_id"] not in service.sessions:
            break
        time.sleep(.02)
    assert row["file_manifest_json"]
    manifest = json.loads(row["file_manifest_json"])
    assert manifest["file_count"] == (1 if outcome == "cancelled" else 2)
    assert "PRIVATE_" not in row["file_manifest_json"]
    root = session_root(service.data_root, caller["user_id"], row["session_id"])
    for entry in root.rglob('*'):
        if entry.is_file() and entry.parent.name in {'generate', 'attachments'}:
            entry.unlink()
    administrator = store.create_user("manifest-admin", "fixture-only-password", "admin")
    with TestClient(create_admin_app(service.settings, service, store)) as admin:
        url = '/admin/v1/tasks/' + task['id'] + '/files'
        assert admin.get(url).status_code == 401
        admin.cookies.set('umeko_admin', store.issue_token(administrator['id']))
        def no_scan(*args, **kwargs):
            raise AssertionError("Persisted snapshots must not depend on file contents or scanning")
        monkeypatch.setattr('umeko.server.inspection.capture', no_scan)
        before = set(service.sessions)
        response = admin.get(url)
        assert response.status_code == 200
        assert response.json() == {**manifest, 'source': 'snapshot'}
        assert set(service.sessions) == before
        assert admin.get('/admin/v1/tasks/missing/files').status_code == 404
        assert client.get(url).status_code == 404
        with store.connect() as db:
            db.execute("UPDATE service_tasks SET expires_at='2000-01-01' WHERE id=?", (task['id'],))
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            with service.task_service._lock:
                if task['id'] not in service.task_service._active:
                    break
            time.sleep(.02)
        service.task_service.cleanup()
        assert admin.get(url).status_code == 404
