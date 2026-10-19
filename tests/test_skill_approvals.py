"""Explicit approvals authorize library versions, never rewrite old sessions."""
import hashlib
import json
import os
from types import SimpleNamespace
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from umeko.config import ModelConfig, Settings
from umeko.server.app import create_app
from umeko.server.admin import create_admin_app
from umeko.host.skill_approvals import SkillApprovals
from umeko.skill_security import _files, protected_name
from umeko.skills import script_runner

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
    (service._skills_library_dir() / PACK / MEMBER).write_bytes(SOURCE)
    with TestClient(create_admin_app(settings, service, service.store)) as admin, TestClient(public) as user:
        yield service, owner, admin, user, prefix


def login(admin, prefix):
    assert admin.post(prefix + "/admin/login", json={"username": "approval-admin", "password": "fixture-pass"}).status_code == 200


def approve_package(service, owner):
    for member, path in _files(service._skills_library_dir() / PACK):
        if protected_name(path):
            service.skill_approvals.approve(PACK, member, hashlib.sha256(path.read_bytes()).hexdigest(),
                                          actor=owner["username"], actor_id=owner["id"])


def record(state):
    return state.session.script_trust.records / (PACK + ".json")


def target(state, member=MEMBER):
    return state.root / "client/skills" / PACK / member


def run(state):
    return state.agent._skills["run_skill_script"].handler(pack=PACK, script="prepare_correction.py", args="{}")


@pytest.mark.parametrize("setup", ["", "/operations/admin"], indirect=True)
def test_current_version_approval_admin_only_and_no_old_session_changes(setup, monkeypatch):
    service, owner, admin, _, prefix = setup
    old = service.create_session(user_id=owner["id"])
    old_record, old_bytes = record(old).read_bytes(), target(old).read_bytes()
    url = prefix + f"/admin/v1/skill-security/{PACK}/{MEMBER}"
    body = {"sha256": hashlib.sha256(SOURCE).hexdigest()}
    assert admin.get(url).status_code == admin.post(url, json=body).status_code == 401
    login(admin, prefix)
    data = admin.get(url).json()
    assert data["status"] == "unlisted" and data["trusted"] is False and data["approved"] is None
    assert "sessions" not in data and "counts" not in data
    assert "SCRIPT_TRUST_REJECTED" in run(old)
    with monkeypatch.context() as patch:
        patch.setattr(script_runner.subprocess, "Popen", lambda *a, **kw: pytest.fail("approval executed code"))
        response = admin.post(url, json=body)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["trusted"] is True and data["status"] == "trusted"
    assert data["approved"]["actor"] == owner["username"] and data["approved"]["actor_id"] == owner["id"]
    assert data["current"]["md5"] == hashlib.md5(SOURCE).hexdigest()
    assert data["approved"]["sha256"] == body["sha256"]
    approve_package(service, owner)
    assert record(old).read_bytes() == old_record and target(old).read_bytes() == old_bytes
    assert "SCRIPT_TRUST_REJECTED" in run(old)
    assert run(service.create_session(user_id=owner["id"])) == "approved fixture"
    assert admin.post(prefix + "/admin/logout").status_code == 204
    assert admin.get(url).status_code == admin.post(url, json=body).status_code == 401


def test_saved_source_change_requires_new_approval_and_stale_preview_is_409(setup):
    service, owner, admin, _, prefix = setup
    login(admin, prefix)
    approve_package(service, owner)
    old = service.create_session(user_id=owner["id"])
    original_record = record(old).read_bytes()
    url = prefix + f"/admin/v1/skill-security/{PACK}/{MEMBER}"
    initial = admin.get(url).json()
    edited = SOURCE.replace(b"approved fixture", b"updated fixture")
    assert admin.put(prefix + f"/admin/v1/skill-scripts/{PACK}/{MEMBER}",
                     json={"content": edited.decode()}).status_code == 201
    data = admin.get(url).json()
    assert data["status"] == "changed" and data["trusted"] is False
    assert data["approved"]["sha256"] == initial["current"]["sha256"]
    assert admin.post(url, json={"sha256": initial["current"]["sha256"]}).status_code == 409
    assert "SCRIPT_TRUST_REJECTED" in run(service.create_session(user_id=owner["id"]))
    test_url = prefix + f"/admin/v1/skill-scripts/{PACK}/{MEMBER}/test"
    assert "SCRIPT_TRUST_REJECTED" in admin.post(test_url, json={"args": "{}", "timeout": 5}).json()["output"]
    assert admin.post(url, json={"sha256": data["current"]["sha256"]}).json()["trusted"]
    assert run(service.create_session(user_id=owner["id"])) == "updated fixture"
    assert admin.post(test_url, json={"args": "{}", "timeout": 5}).json()["output"] == "updated fixture"
    service.evict_session(old.id)
    restored = service.get_session(old.id)
    assert run(restored) == "approved fixture" and record(restored).read_bytes() == original_record


@pytest.mark.parametrize("member", ["assets/config.json", "scripts/_runtime.py"])
def test_approval_of_entry_cannot_authorize_changed_helpers_or_config(setup, member):
    service, owner, admin, _, prefix = setup
    login(admin, prefix)
    # A synthetic helper ensures this tests the package gate, not imports.
    path = service._skills_library_dir() / PACK / member
    if not path.exists():
        path.write_bytes(b"VALUE = 1\n")
    approve_package(service, owner)
    original = path.read_bytes()
    path.write_bytes(original + b"\n")
    url = prefix + f"/admin/v1/skill-security/{PACK}/{member}"
    status = admin.get(url).json()
    assert status["status"] == "changed"
    failed = run(service.create_session(user_id=owner["id"]))
    assert "SCRIPT_TRUST_REJECTED" in failed and "MD5" in failed and member in failed
    assert admin.post(url, json={"sha256": status["current"]["sha256"]}).json()["trusted"]
    assert run(service.create_session(user_id=owner["id"])) == "approved fixture"


def test_approval_persists_but_restart_does_not_approve_new_bytes(setup):
    service, owner, _, _, _ = setup
    approve_package(service, owner)
    path = service._skills_library_dir() / PACK / MEMBER
    path.write_bytes(SOURCE.replace(b"\n", b"\r\n"))
    service.skill_approvals = SkillApprovals(service)
    assert service.skill_approvals.status(PACK, MEMBER)["status"] == "changed"
    assert "MD5" in run(service.create_session(user_id=owner["id"]))


def test_md5_match_does_not_bypass_sha256_and_approval_transaction_rolls_back(setup):
    service, owner, _, _, _ = setup
    approve_package(service, owner)
    with service.store.connect() as db:
        db.execute("UPDATE skill_file_approvals SET sha256=? WHERE pack=? AND member=?", ("0" * 64, PACK, MEMBER))
    assert service.skill_approvals.status(PACK, MEMBER)["trusted"] is False
    assert "SHA-256" in run(service.create_session(user_id=owner["id"]))
    with service.store.connect() as db:
        db.execute("CREATE TRIGGER fail_approval_audit BEFORE INSERT ON skill_file_approval_events "
                   "BEGIN SELECT RAISE(ABORT, 'synthetic failure'); END")
    with pytest.raises(Exception, match="synthetic failure"):
        service.skill_approvals.approve(PACK, MEMBER, hashlib.sha256(SOURCE).hexdigest(), actor=owner["username"])
    assert service.skill_approvals.approved_files(PACK)[MEMBER]["sha256"] == "0" * 64


@pytest.mark.parametrize("member", ["references/style.md", "../scripts/prepare_correction.py", "scripts/../scripts/prepare_correction.py", "scripts/prepare_correction.py:stream"])
def test_paths_and_nonprotected_files_are_rejected(setup, member):
    _, _, admin, _, prefix = setup
    login(admin, prefix)
    url = prefix + f"/admin/v1/skill-security/{PACK}/" + quote(member, safe="")
    assert admin.get(url).status_code in {400, 404}
    assert admin.post(url, json={"sha256": hashlib.sha256(SOURCE).hexdigest()}).status_code in {400, 404}


def test_payload_cannot_supply_bytes_actors_or_old_session_options(setup):
    _, _, admin, _, prefix = setup
    login(admin, prefix)
    url = prefix + f"/admin/v1/skill-security/{PACK}/{MEMBER}"
    for payload in [{"sha256": "not-a-hash"}, {"sha256": "0" * 64, "content": "injected"},
                    {"sha256": "0" * 64, "redispatch": True}, {"sha256": "0" * 64, "actor": "injected"}]:
        assert admin.post(url, json=payload).status_code == 422


def test_regular_user_tokens_and_user_port_cannot_approve(setup):
    service, owner, admin, user, prefix = setup
    guest = service.store.create_user("approval-guest", "fixture-pass")
    with TestClient(admin.app) as ordinary:
        ordinary.cookies.set("umeko_admin", service.store.issue_token(guest["id"]))
        url = prefix + f"/admin/v1/skill-security/{PACK}/{MEMBER}"
        assert ordinary.get(url).status_code == 401
        assert ordinary.post(url, json={"sha256": hashlib.sha256(SOURCE).hexdigest()}).status_code == 401
    user.post(service.settings.base_path + "/v1/auth/login", json={"username": owner["username"], "password": "fixture-pass"}).raise_for_status()
    route = service.settings.base_path + f"/admin/v1/skill-security/{PACK}/{MEMBER}"
    assert user.get(route).status_code == user.post(route, json={"sha256": hashlib.sha256(SOURCE).hexdigest()}).status_code == 404


def test_hardlinked_library_file_cannot_be_approved(setup):
    service, _, admin, _, prefix = setup
    login(admin, prefix)
    path = service._skills_library_dir() / PACK / MEMBER
    try:
        os.link(path, path.parent / "linked.txt")
    except OSError:
        pytest.skip("Hard links unavailable")
    url = prefix + f"/admin/v1/skill-security/{PACK}/{MEMBER}"
    assert admin.get(url).status_code == 400
    assert admin.post(url, json={"sha256": hashlib.sha256(SOURCE).hexdigest()}).status_code == 400


@pytest.mark.parametrize("setup", ["", "/operations/admin"], indirect=True)
def test_proxy_optional_skill_dispatch_also_requires_explicit_library_approval(setup, monkeypatch):
    service, owner, _, user, _ = setup
    pack = "fixture-manual"
    package = service._skills_library_dir() / pack
    (package / "scripts").mkdir(parents=True)
    (package / "SKILL.md").write_text("---\nname: fixture-manual\ndescription: Isolated fixture\n---\n# Fixture\n", encoding="utf-8")
    (package / "scripts/run.py").write_bytes(SOURCE)
    # Exercise optional dispatch without contacting a model or starting work.
    monkeypatch.setattr(service, "create_run", lambda *a, **kw: SimpleNamespace(id="fixture-run"))
    prefix = service.settings.base_path
    user.post(prefix + "/v1/auth/login", json={"username": owner["username"], "password": "fixture-pass"}).raise_for_status()
    def dispatched():
        response = user.post(prefix + "/v1/proxy/sessions", data={"prompt": "Fixture", "skill": pack})
        assert response.status_code == 201, response.text
        return service.get_session(response.json()["session_id"]).session.script_trust
    unapproved = dispatched()
    assert json.loads((unapproved.records / (pack + ".json")).read_text())["files"] == {}
    service.skill_approvals.approve(pack, "scripts/run.py", hashlib.sha256(SOURCE).hexdigest(), actor=owner["username"])
    approved = dispatched()
    with approved.execution(pack, "run.py") as (script, _):
        assert script.read_bytes() == SOURCE
    assert json.loads((unapproved.records / (pack + ".json")).read_text())["files"] == {}


@pytest.mark.parametrize("setup", ["", "/operations/admin"], indirect=True)
def test_library_catalog_filters_pagination_selection_and_admin_only(setup):
    service, owner, admin, user, prefix = setup
    package = service._skills_library_dir() / "catalog-fixture"
    (package / "scripts").mkdir(parents=True)
    for index in range(65):
        (package / "scripts" / f"unit-{index:03}.py").write_bytes(SOURCE)
    member = "scripts/unit-000.py"
    service.skill_approvals.approve("catalog-fixture", member, hashlib.sha256(SOURCE).hexdigest(), actor=owner["username"])
    url = prefix + "/admin/v1/skill-security/catalog"
    select_url = prefix + "/admin/v1/skill-security/selection"
    assert admin.get(url).status_code == admin.get(select_url).status_code == 401
    assert admin.post(prefix + "/admin/v1/skill-security/batch", json={}).status_code == 401
    login(admin, prefix)
    response = admin.get(url, params={"pack": "catalog-fixture", "limit": 25})
    assert response.status_code == 200, response.text
    page = response.json()
    assert page["total"] == 65 and len(page["items"]) == 25
    assert page["counts"]["trusted"] == 1 and page["counts"]["unlisted"] == 64
    assert "catalog-fixture" in page["packs"] and page["items"][0]["trusted"]
    next_page = admin.get(url, params={"pack": "catalog-fixture", "offset": 25, "limit": 25}).json()
    assert not ({r["member"] for r in page["items"]} & {r["member"] for r in next_page["items"]})
    selected = admin.get(select_url, params={"pack": "catalog-fixture"}).json()
    assert selected["total"] == len(selected["items"]) == 65
    assert selected["items"][0]["approved_sha256"] == hashlib.sha256(SOURCE).hexdigest()
    assert all("content" not in item and "current" not in item for item in selected["items"])
    filtered = admin.get(url, params={"q": "CATALOG-FIXTURE/scripts/unit-00", "status": "unlisted", "kind": "python"}).json()
    assert filtered["total"] == 9
    assert admin.get(url, params={"pack": "catalog-fixture", "kind": "config"}).json()["total"] == 0
    assert admin.get(url, params={"limit": 201}).status_code == 422
    assert admin.get(url, params={"status": "unknown"}).status_code == 422
    assert admin.get(url, params={"pack": "../outside"}).status_code == 400
    user.post(service.settings.base_path + "/v1/auth/login", json={"username": owner["username"], "password": "fixture-pass"}).raise_for_status()
    assert user.get(service.settings.base_path + "/admin/v1/skill-security/catalog").status_code == 404
    assert admin.post(prefix + "/admin/logout").status_code == 204
    assert admin.get(url).status_code == admin.get(select_url).status_code == 401


@pytest.mark.parametrize("member", [MEMBER, "assets/config.json"])
def test_revoke_blocks_existing_and_legacy_manifests_without_rewriting_them(setup, member):
    service, owner, admin, _, prefix = setup
    login(admin, prefix)
    approve_package(service, owner)
    old = service.create_session(user_id=owner["id"])
    manifest = json.loads(record(old).read_text())
    for hashes in manifest["files"].values():
        hashes.pop("approval_id", None)  # Sessions issued before revocation support.
    record(old).write_text(json.dumps(manifest))
    original = record(old).read_bytes()
    assert run(old) == "approved fixture"
    url = prefix + f"/admin/v1/skill-security/{PACK}/{member}"
    data = admin.get(url).json()
    assert admin.request("DELETE", url, json={"sha256": "0" * 64}).status_code == 409
    response = admin.request("DELETE", url, json={"sha256": data["approved"]["sha256"]})
    assert response.status_code == 200, response.text
    assert admin.get(url).json()["status"] == "revoked"
    assert "移出可信区" in run(old)
    assert "SCRIPT_TRUST_REJECTED" in run(service.create_session(user_id=owner["id"]))
    service.evict_session(old.id)
    restored = service.get_session(old.id)
    assert "移出可信区" in run(restored)
    assert record(restored).read_bytes() == original
    service.skill_approvals = SkillApprovals(service)
    assert service.skill_approvals.status(PACK, member)["status"] == "revoked"
    # Reapproval only issues a new generation; it must not revive old grants.
    assert admin.post(url, json={"sha256": data["current"]["sha256"]}).json()["trusted"]
    assert run(service.create_session(user_id=owner["id"])) == "approved fixture"
    cloned = service.clone_session(restored.id, owner["id"])
    assert "移出可信区" in run(cloned)
    assert record(restored).read_bytes() == original
    with service.store.connect() as db:
        events = db.execute("SELECT action,actor_id FROM skill_file_approval_events WHERE pack=? AND member=? ORDER BY id", (PACK, member)).fetchall()
        assert [r["action"] for r in events][-2:] == ["revoke", "approve"]
        assert events[-1]["actor_id"] == owner["id"]


def test_catalog_can_revoke_missing_and_changed_files_and_exposes_invalid_code(setup):
    service, owner, admin, _, prefix = setup
    login(admin, prefix)
    approve_package(service, owner)
    package = service._skills_library_dir() / PACK
    missing = "assets/config.json"
    (package / missing).unlink()
    (package / MEMBER).write_bytes(SOURCE + b"\n")
    (package / "references/unsupported.py").write_bytes(SOURCE)
    url = prefix + "/admin/v1/skill-security/catalog"
    catalog = admin.get(url, params={"pack": PACK}).json()
    rows = {r["member"]: r for r in catalog["items"]}
    assert rows[missing]["status"] == "missing" and not rows[missing]["approvable"]
    assert rows[MEMBER]["status"] == "changed" and rows[MEMBER]["approvable"]
    assert rows["references/unsupported.py"]["status"] == "invalid"
    items = [{"pack": PACK, "member": m, "sha256": rows[m]["approved"]["sha256"]} for m in [missing, MEMBER]]
    result = admin.post(prefix + "/admin/v1/skill-security/batch", json={"action": "revoke", "items": items}).json()
    assert result["succeeded"] == 2 and result["failed"] == 0
    assert not service.skill_approvals.approved_files(PACK).get(missing)
    with service.store.connect() as db:
        assert db.execute("SELECT count(*) FROM skill_file_revocations WHERE pack=?", (PACK,)).fetchone()[0] == 2


def test_batch_reports_stale_files_without_approving_them_or_rolling_back_successes(setup):
    service, owner, admin, _, prefix = setup
    login(admin, prefix)
    config = "assets/config.json"
    first = service.skill_approvals.status(PACK, MEMBER)
    second = service.skill_approvals.status(PACK, config)
    (service._skills_library_dir() / PACK / config).write_bytes(b"{}\n")
    items = [{"pack": PACK, "member": item["member"], "sha256": item["current"]["sha256"]} for item in [first, second]]
    url = prefix + "/admin/v1/skill-security/batch"
    result = admin.post(url, json={"action": "approve", "items": items}).json()
    assert result["succeeded"] == result["failed"] == 1
    assert result["results"][0]["ok"] and not result["results"][1]["ok"]
    assert service.skill_approvals.status(PACK, MEMBER)["trusted"]
    assert not service.skill_approvals.status(PACK, config)["trusted"]
    assert admin.post(url, json={"action": "approve", "items": [items[0], items[0]]}).status_code == 400
    assert admin.post(url, json={"action": "approve", "items": items * 101}).status_code == 422
    assert admin.post(url, json={"action": "anything", "items": items}).status_code == 422
    assert admin.post(url, json={"action": "approve", "items": []}).status_code == 422


def test_failed_revocation_audit_cannot_remove_an_approval(setup):
    service, owner, _, _, _ = setup
    approve_package(service, owner)
    with service.store.connect() as db:
        db.execute("CREATE TRIGGER fail_revocation BEFORE INSERT ON skill_file_approval_events "
                   "WHEN NEW.action='revoke' BEGIN SELECT RAISE(ABORT, 'synthetic failure'); END")
    with pytest.raises(Exception, match="synthetic failure"):
        service.skill_approvals.revoke(PACK, MEMBER, hashlib.sha256(SOURCE).hexdigest(), actor=owner["username"])
    assert service.skill_approvals.status(PACK, MEMBER)["trusted"]
    assert run(service.create_session(user_id=owner["id"])) == "approved fixture"
