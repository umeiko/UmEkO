"""Administrator approval never trusts caller bytes or bypasses session gates."""
import hashlib
import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from umeko.config import ModelConfig, Settings
from umeko.server.app import create_app
from umeko.server.admin import create_admin_app
from umeko.host import skill_approvals

PACK = "drawio-correction"
MEMBER = "scripts/prepare_correction.py"
SOURCE = b'import json\nprint(json.dumps({"ok":True,"result":"approved fixture"}))\n'


@pytest.fixture
def setup(tmp_path, request):
    prefix = getattr(request, "param", "")
    settings = Settings(ModelConfig("fixture", "unused", "https://unused.invalid"),
                        base_path="/users/work" if prefix else "", admin_base_path=prefix)
    public = create_app(settings, data_root=tmp_path / "data", workspace_root=tmp_path / "output")
    service = public.state.agent_service
    owner = service.store.create_user("approval-admin", "fixture-pass", "admin")
    library = service._skills_library_dir()
    (library / PACK / MEMBER).write_bytes(SOURCE)
    with TestClient(create_admin_app(settings, service, service.store)) as admin, TestClient(public) as user:
        yield service, owner, admin, user, prefix


def login(admin, prefix):
    assert admin.post(prefix + "/admin/login", json={"username": "approval-admin", "password": "fixture-pass"}).status_code == 200


def record(state):
    return state.session.script_trust.records / (PACK + ".json")


def target(state, member=MEMBER):
    return state.root / "client/skills" / PACK / member


def run(state):
    return state.agent._skills["run_skill_script"].handler(pack=PACK, script="prepare_correction.py", args="{}")


@pytest.mark.parametrize("setup", ["", "/operations/admin"], indirect=True)
def test_admin_only_matching_sync_and_explicit_reissue(setup):
    service, owner, admin, user, prefix = setup
    states = [service.create_session(user_id=owner["id"]) for _ in range(3)]
    matching, modified, busy = states
    baseline = json.loads(record(matching).read_text())
    baseline["files"][MEMBER]["md5"] = "0" * 32
    record(matching).write_text(json.dumps(baseline))
    target(modified).write_bytes(b'raise RuntimeError("untrusted")\n')
    url = prefix + f"/admin/v1/skill-security/{PACK}/{MEMBER}"
    body = {"sha256": hashlib.sha256(SOURCE).hexdigest()}
    assert admin.get(url).status_code == admin.post(url, json=body).status_code == 401
    login(admin, prefix)
    data = admin.get(url).json()
    assert data["current"]["md5"] == hashlib.md5(SOURCE).hexdigest()
    assert data["counts"]["mismatch"] == 2 and data["counts"]["approved"] == 1
    assert not data["events"]
    assert "SCRIPT_TRUST_REJECTED" in run(matching)
    assert "SCRIPT_TRUST_REJECTED" in run(modified)
    busy.lock.acquire()
    try:
        response = admin.post(url, json=body)
        assert response.status_code == 200, response.text
        outcome = response.json()
        assert outcome["updated"] == 1 and outcome["skipped_mismatch"] == 1 and outcome["skipped_busy"] == 1
    finally:
        busy.lock.release()
    assert run(matching) == "approved fixture"
    assert "SCRIPT_TRUST_REJECTED" in run(modified)
    assert b"untrusted" in target(modified).read_bytes()
    assert admin.post(url, json={**body, "redispatch": True}).json()["updated"] == 1
    assert target(modified).read_bytes() == SOURCE and run(modified) == "approved fixture"
    data = admin.get(url).json()
    assert data["counts"]["approved"] == 3
    assert data["events"][0]["actor"] == owner["username"] and data["events"][0]["actor_id"] == owner["id"]
    assert data["events"][0]["matches_current"]
    assert data["events"][0]["result"]["status"] == "completed"
    assert data["total"] == 3 and len(admin.get(url + "?offset=1&limit=1").json()["sessions"]) == 1
    assert admin.post(prefix + "/admin/logout").status_code == 204
    assert admin.get(url).status_code == admin.post(url, json=body).status_code == 401


def test_config_reissue_preserves_other_file_gates_and_rejects_stale_source(setup):
    service, owner, admin, _, prefix = setup
    login(admin, prefix)
    state = service.create_session(user_id=owner["id"])
    target(state).write_bytes(b"untrusted")
    member = "assets/config.json"
    url = prefix + f"/admin/v1/skill-security/{PACK}/{member}"
    initial = admin.get(url).json()["current"]["sha256"]
    library_file = service._skills_library_dir() / PACK / member
    updated = b'{"fixture": "changed by administrator"}\n'
    library_file.write_bytes(updated)
    assert admin.post(url, json={"sha256": initial, "redispatch": True}).status_code == 409
    data = admin.get(url).json()
    assert data["counts"]["old_version"] == 1
    assert admin.post(url, json={"sha256": data["current"]["sha256"]}).json()["skipped_mismatch"] == 1
    assert target(state, member).read_bytes() != updated
    response = admin.post(url, json={"sha256": data["current"]["sha256"], "redispatch": True})
    assert response.json()["updated"] == 1
    assert target(state, member).read_bytes() == updated
    assert "SCRIPT_TRUST_REJECTED" in run(state)  # Reapproving config cannot bless the other .py.
    service.evict_session(state.id)
    restored = service.get_session(state.id)
    assert target(restored, member).read_bytes() == updated


def test_invalid_records_and_links_are_not_approved(setup):
    service, owner, admin, _, prefix = setup
    login(admin, prefix)
    state = service.create_session(user_id=owner["id"])
    record(state).write_text("[]")
    url = prefix + f"/admin/v1/skill-security/{PACK}/{MEMBER}"
    # Invalid private metadata is not silently replaced with a new approval.
    response = admin.get(url)
    assert response.status_code == 200, response.text
    assert response.json()["counts"]["invalid"] == 1
    outcome = admin.post(url, json={"sha256": hashlib.sha256(SOURCE).hexdigest(), "redispatch": True})
    assert outcome.json()["skipped_invalid"] == 1
    assert record(state).read_text() == "[]"


@pytest.mark.parametrize("member", ["references/style.md", "../scripts/prepare_correction.py", "scripts/../scripts/prepare_correction.py", "scripts/prepare_correction.py:stream"])
def test_paths_and_nonprotected_files_are_rejected(setup, member):
    _, _, admin, _, prefix = setup
    login(admin, prefix)
    url = prefix + f"/admin/v1/skill-security/{PACK}/" + quote(member, safe="")
    assert admin.get(url).status_code in {400, 404}
    assert admin.post(url, json={"sha256": hashlib.sha256(SOURCE).hexdigest()}).status_code in {400, 404}


def test_payload_cannot_supply_approval_bytes_or_paths(setup):
    _, _, admin, _, prefix = setup
    login(admin, prefix)
    url = prefix + f"/admin/v1/skill-security/{PACK}/{MEMBER}"
    for payload in [{"sha256": "not-a-hash"}, {"sha256": "0" * 64, "content": "injected"},
                    {"sha256": "0" * 64, "redispatch": "true"}]:
        assert admin.post(url, json=payload).status_code == 422


def test_failed_record_publish_restores_previous_session_bytes(setup, monkeypatch):
    service, owner, admin, _, prefix = setup
    login(admin, prefix)
    state = service.create_session(user_id=owner["id"])
    target(state).write_bytes(b"original session bytes")
    before = record(state).read_bytes()
    native = skill_approvals.atomic_write
    def publish(path, data):
        if path == record(state):
            raise OSError("Synthetic storage failure")
        return native(path, data)
    monkeypatch.setattr(skill_approvals, "atomic_write", publish)
    result = admin.post(prefix + f"/admin/v1/skill-security/{PACK}/{MEMBER}",
                        json={"sha256": hashlib.sha256(SOURCE).hexdigest(), "redispatch": True}).json()
    assert result["failed"] == 1 and result["updated"] == 0
    assert target(state).read_bytes() == b"original session bytes"
    assert record(state).read_bytes() == before


def test_regular_user_tokens_and_user_port_cannot_approve(setup):
    service, owner, admin, user, prefix = setup
    guest = service.store.create_user("approval-guest", "fixture-pass")
    with TestClient(admin.app) as ordinary:
        ordinary.cookies.set("umeko_admin", service.store.issue_token(guest["id"]))
        url = prefix + f"/admin/v1/skill-security/{PACK}/{MEMBER}"
        assert ordinary.get(url).status_code == 401
        assert ordinary.post(url, json={"sha256": hashlib.sha256(SOURCE).hexdigest(), "redispatch": True}).status_code == 401
    user.post(service.settings.base_path + "/v1/auth/login", json={"username": owner["username"], "password": "fixture-pass"}).raise_for_status()
    route = service.settings.base_path + f"/admin/v1/skill-security/{PACK}/{MEMBER}"
    assert user.get(route).status_code == user.post(route, json={"sha256": hashlib.sha256(SOURCE).hexdigest()}).status_code == 404


def test_queued_run_skipped_even_after_memory_eviction(setup):
    service, owner, admin, _, prefix = setup
    login(admin, prefix)
    state = service.create_session(user_id=owner["id"])
    target(state).write_bytes(b"stale")
    queued = service.run_manager.create(state.id)
    service.evict_session(state.id)
    response = admin.post(prefix + f"/admin/v1/skill-security/{PACK}/{MEMBER}",
                          json={"sha256": hashlib.sha256(SOURCE).hexdigest(), "redispatch": True})
    assert response.json()["skipped_busy"] == 1
    assert target(state).read_bytes() == b"stale"
    queued.finish("cancelled")


def test_hardlinked_session_file_is_not_reissued(setup):
    service, owner, admin, _, prefix = setup
    login(admin, prefix)
    state = service.create_session(user_id=owner["id"])
    other = state.root / "generate/linked.txt"
    other.write_bytes(SOURCE)
    target(state).unlink()
    try:
        os.link(other, target(state))
    except OSError:
        pytest.skip("Hard links unavailable")
    url = prefix + f"/admin/v1/skill-security/{PACK}/{MEMBER}"
    assert admin.get(url).json()["counts"]["invalid"] == 1
    assert admin.post(url, json={"sha256": hashlib.sha256(SOURCE).hexdigest(), "redispatch": True}).json()["skipped_invalid"] == 1
    assert other.stat().st_nlink == 2


def test_session_access_waits_for_code_and_approval_to_publish_together(setup, monkeypatch):
    service, owner, _, _, _ = setup
    state = service.create_session(user_id=owner["id"])
    target(state).write_bytes(b"stale")
    publishing, release, reading, finished = (threading.Event() for _ in range(4))
    native = skill_approvals.atomic_write
    def publish(path, data):
        if path == record(state):
            publishing.set()
            assert release.wait(5)
        return native(path, data)
    monkeypatch.setattr(skill_approvals, "atomic_write", publish)
    def read():
        reading.set()
        loaded = service.get_session(state.id)
        with loaded.session.script_trust.execution(PACK, "prepare_correction.py") as (script, _):
            assert script.read_bytes() == SOURCE
        finished.set()
    with ThreadPoolExecutor(max_workers=2) as pool:
        approval = pool.submit(service.skill_approvals.approve, PACK, MEMBER, hashlib.sha256(SOURCE).hexdigest(),
                               actor=owner["username"], actor_id=owner["id"], redispatch=True)
        assert publishing.wait(3)
        reader = pool.submit(read)
        assert reading.wait(1)
        try:
            assert not finished.wait(.1)
        finally:
            release.set()
        assert approval.result(timeout=5)["updated"] == 1
        reader.result(timeout=5)
