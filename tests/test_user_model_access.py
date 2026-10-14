"""Dispatch, per-user scopes and model resolution, using isolated data and replies."""
import sqlite3
import threading
import time

import pytest
from fastapi.testclient import TestClient

from umeko.agent import UmekoAgent
from umeko.config import ModelConfig, Settings
from umeko.host.storage import Store
from umeko.server.admin import create_admin_app
from umeko.server.app import create_app


@pytest.fixture(params=["", "/teams/docs/umeko"])
def model_access(tmp_path, request):
    settings = Settings(ModelConfig("unused", "fixture-only", "https://unused.invalid"),
                        base_path=request.param, admin_base_path="/operations/console", registry_managed=True)
    app = create_app(settings, data_root=tmp_path / "data", workspace_root=tmp_path / "output")
    service, store = app.state.agent_service, app.state.store
    owner = store.create_user("fixture-user", "fixture-password")
    manager = store.create_user("fixture-admin", "fixture-password", "admin")
    p = store.create_provider("First", "https://first.invalid/v1", "first-secret")
    q = store.create_provider("Second", "https://second.invalid/v1", "second-secret")
    main = store.add_model(p["id"], "main")
    vision = store.add_model(p["id"], "vision", True)
    alternate = store.add_model(q["id"], "alternate", True)
    hidden = store.add_model(q["id"], "private", True, user_enabled=False)
    store.set_active_model(main["id"])
    admin_app = create_admin_app(settings, service, store)
    with TestClient(app) as user, TestClient(admin_app) as admin:
        user.post(settings.base_path + "/v1/auth/login", json={"username": owner["username"], "password": "fixture-password"}).raise_for_status()
        admin.post(settings.admin_base_path + "/admin/login", json={"username": manager["username"], "password": "fixture-password"}).raise_for_status()
        yield {"user": user, "admin": admin, "app": app, "store": store, "service": service,
               "owner": owner, "prefix": settings.base_path, "admin_prefix": settings.admin_base_path,
               "p": p, "q": q, "main": main, "vision": vision, "alternate": alternate, "hidden": hidden}


def ids(response):
    return {model["id"] for p in response["providers"] for model in p["models"]}


def access_url(env):
    return env["admin_prefix"] + "/admin/v1/users/" + env["owner"]["id"] + "/model-access"


def grant(env, providers=None, models=None):
    response = env["admin"].put(access_url(env), json={"allowed_provider_ids": providers, "allowed_model_ids": models})
    response.raise_for_status()
    return response.json()


def test_dispatch_and_user_scopes_intersect_without_leaking_credentials(model_access):
    e = model_access
    default = e["admin"].get(access_url(e)).json()
    assert default["allowed_provider_ids"] is None and default["allowed_model_ids"] is None
    public = e["user"].get(e["prefix"] + "/v1/models").json()
    assert ids(public) == {e[name]["id"] for name in ("main", "vision", "alternate")}
    assert "api_key" not in str(public) and "first-secret" not in str(public) and "base_url" not in str(public)
    grant(e, [e["p"]["id"]], [e["main"]["id"], e["alternate"]["id"], e["hidden"]["id"]])
    assert ids(e["user"].get(e["prefix"] + "/v1/models").json()) == {e["main"]["id"]}
    grant(e, [e["q"]["id"]])
    public = e["user"].get(e["prefix"] + "/v1/models").json()
    assert ids(public) == {e["alternate"]["id"]} and public["active_model_id"] == e["alternate"]["id"]
    grant(e, [], None)
    public = e["user"].get(e["prefix"] + "/v1/models").json()
    assert public["providers"] == [] and public["active_model_id"] is None
    grant(e, None, [])
    assert not ids(e["user"].get(e["prefix"] + "/v1/models").json())


def test_direct_preferences_and_overrides_cannot_bypass_scope(model_access):
    e = model_access
    uid = e["owner"]["id"]
    session = e["user"].post(e["prefix"] + "/v1/sessions", json={}).json()["id"]
    grant(e, [e["p"]["id"]], [e["main"]["id"]])
    for role in ("main_model_id", "sub_model_id", "vision_model_id"):
        for model in (e["vision"], e["alternate"], e["hidden"]):
            response = e["user"].put(e["prefix"] + "/v1/auth/model-prefs", json={role: model["id"]})
            assert response.status_code == 403
            assert e["store"].user_model_prefs(uid) == Store._empty_prefs()
    response = e["user"].put(e["prefix"] + f"/v1/sessions/{session}/model", json={"model_id": e["alternate"]["id"]})
    assert response.status_code == 403 and e["store"].session_by_id(session)["model_override_id"] is None
    assert e["user"].put(e["prefix"] + f"/v1/sessions/{session}/model", json={"model_id": e["main"]["id"]}).status_code == 204
    assert e["user"].put(e["prefix"] + "/v1/auth/model-prefs", json={"main_model_id": e["main"]["id"]}).status_code == 200
    assert e["user"].put(e["prefix"] + "/v1/auth/model-prefs", json={"main_model_id": "missing"}).status_code == 404


def test_revocation_revalidates_every_role_and_never_uses_hidden_visual_fallback(model_access):
    e = model_access
    store, service, uid = e["store"], e["service"], e["owner"]["id"]
    store.set_user_model_prefs(uid, main_model_id=e["alternate"]["id"], sub_model_id=e["alternate"]["id"], vision_model_id=e["vision"]["id"])
    session = service.create_session(user_id=uid)
    store.set_session_model_override(session.id, e["alternate"]["id"])
    grant(e, [e["p"]["id"]])
    effective = service.effective_settings_for(uid, session.id)
    assert effective.text_model.model_id == e["main"]["id"] and effective.sub_model is None
    assert effective.vision_model.model_id == e["vision"]["id"]
    store.update_model(e["vision"]["id"], user_enabled=False)
    effective = service.effective_settings_for(uid, session.id)
    assert effective.vision_model is None
    assert e["user"].get(e["prefix"] + "/v1/models").json()["prefs"] == Store._empty_prefs()
    # A globally hidden default and stale preference cannot escape the permitted fallback.
    store.set_active_model(e["alternate"]["id"])
    store.update_model(e["alternate"]["id"], user_enabled=False)
    assert service.effective_settings_for(uid, session.id).text_model.model_id == e["main"]["id"]
    grant(e, None, [])
    effective = service.effective_settings_for(uid, session.id)
    assert effective.text_model.model_id is None and not effective.text_model.api_key
    assert effective.sub_model is None and effective.vision_model is None
    assert e["user"].get(e["prefix"] + f"/v1/sessions/{session.id}/workspace/tree").status_code == 200
    blocked = e["user"].post(e["prefix"] + f"/v1/sessions/{session.id}/runs", json={"input": "must not call"})
    assert blocked.status_code == 400 and "开放" in blocked.json()["detail"]


def test_changes_do_not_cancel_running_request_and_next_run_rebuilds(model_access, monkeypatch):
    e = model_access
    started, release = threading.Event(), threading.Event()
    seen = []
    def chat(agent, prompt, images=None):
        seen.append(agent.settings.text_model.model_id)
        if len(seen) == 1:
            started.set()
            assert release.wait(5)
        return "controlled answer"
    monkeypatch.setattr(UmekoAgent, "chat", chat)
    session = e["user"].post(e["prefix"] + "/v1/sessions", json={}).json()["id"]
    service = e["service"]
    first = service.create_run(session, "first", [])
    try:
        assert started.wait(5)
        grant(e, [e["q"]["id"]], [e["alternate"]["id"]])
        assert not first.cancel_requested()
    finally:
        release.set()
    for _ in range(200):
        if first.finished and service.get_session(session).active_run_holder["run"] is None:
            break
        time.sleep(.01)
    second = service.create_run(session, "second", [])
    for _ in range(200):
        if second.finished:
            break
        time.sleep(.01)
    assert first.status == second.status == "completed"
    assert seen == [e["main"]["id"], e["alternate"]["id"]]


def test_management_validation_auth_persistence_and_import(model_access):
    e = model_access
    url = access_url(e)
    other = TestClient(e["admin"].app)
    assert other.get(url).status_code == 401
    other.post(e["admin_prefix"] + "/admin/login", json={"username": "fixture-user", "password": "fixture-password"})
    assert other.put(url, json={"allowed_provider_ids": None, "allowed_model_ids": None}).status_code == 401
    assert e["user"].get(e["prefix"] + "/admin/v1/users").status_code == 404
    original = grant(e, [e["p"]["id"]], [e["main"]["id"]])
    assert e["admin"].put(url, json={"allowed_provider_ids": [], "allowed_model_ids": ["missing"]}).status_code == 400
    assert {key: e["admin"].get(url).json()[key] for key in original} == original
    assert e["admin"].get(url.replace(e["owner"]["id"], "missing")).status_code == 404
    assert e["admin"].put(url, json={"allowed_provider_ids": None}).status_code == 422
    assert e["admin"].put(url, json={"allowed_provider_ids": None, "allowed_model_ids": None, "unexpected": 1}).status_code == 422
    route = e["admin_prefix"] + "/admin/v1/models/" + e["main"]["id"]
    created = e["admin"].post(e["admin_prefix"] + f"/admin/v1/providers/{e['p']['id']}/models",
                            json={"name": "never-dispatch", "user_enabled": False})
    assert created.status_code == 201 and created.json()["user_enabled"] is False
    assert e["admin"].put(route, json={"user_enabled": False}).status_code == 204
    # An explicit personal grant still works after global dispatch is turned off.
    assert ids(e["user"].get(e["prefix"] + "/v1/models").json()) == {e["main"]["id"]}
    for invalid in ("false", 0, 1):
        assert e["admin"].put(route, json={"user_enabled": invalid}).status_code == 422
    assert Store(e["store"].path).user_model_access(e["owner"]["id"]) == original
    provider = {"name": e["p"]["name"], "models": [{"name": "main", "vision": True}]}
    e["store"].import_providers({"providers": [provider]})
    assert not e["store"].list_providers()[0]["models"][0]["user_enabled"]
    provider["models"][0]["user_enabled"] = True
    e["store"].import_providers({"providers": [provider]})
    assert ids(e["user"].get(e["prefix"] + "/v1/models").json()) == {e["main"]["id"]}
    # Deleting scoped models/providers must not turn an explicit list into unrestricted access.
    e["store"].delete_provider(e["p"]["id"])
    assert not e["store"].allowed_model_rows(e["owner"]["id"])
    assert e["store"].user_model_access(e["owner"]["id"]) == {"allowed_provider_ids": [], "allowed_model_ids": []}


def test_vip_grant_exposes_private_model_only_to_that_user_and_can_be_revoked(model_access, monkeypatch):
    e = model_access
    service, store = e["service"], e["store"]
    private = e["hidden"]["id"]
    other = store.create_user("ordinary-reader", "fixture-password")
    assert private not in ids(e["user"].get(e["prefix"] + "/v1/models").json())
    grant(e, [e["q"]["id"]], [private])
    exposed = e["user"].get(e["prefix"] + "/v1/models").json()
    assert ids(exposed) == {private} and exposed["active_model_id"] == private
    assert private not in {row["model_id"] for row in store.allowed_model_rows(other["id"])}
    prefs = {key: private for key in ("main_model_id", "sub_model_id", "vision_model_id")}
    assert e["user"].put(e["prefix"] + "/v1/auth/model-prefs", json=prefs).status_code == 200
    sid = e["user"].post(e["prefix"] + "/v1/sessions", json={}).json()["id"]
    model_url = e["prefix"] + f"/v1/sessions/{sid}/model"
    assert e["user"].put(model_url, json={"model_id": private}).status_code == 204
    seen = []
    def chat(agent, prompt, images=None):
        settings = agent.settings
        seen.append((settings.text_model.model_id, settings.sub_model.model_id if settings.sub_model else None,
                     settings.vision_model.model_id if settings.vision_model else None))
        return "controlled VIP answer"
    monkeypatch.setattr(UmekoAgent, "chat", chat)
    first = service.create_run(sid, "use the private model", [])
    for _ in range(200):
        if first.finished and service.get_session(sid).active_run_holder["run"] is None:
            break
        time.sleep(.01)
    assert first.status == "completed" and seen == [(private, private, private)]
    # Closing the provider still blocks even an explicit VIP grant.
    grant(e, [], [private])
    assert not ids(e["user"].get(e["prefix"] + "/v1/models").json())
    assert e["user"].put(model_url, json={"model_id": private}).status_code == 403
    # Following default dispatch revokes the exception; old prefs/overrides cannot retain it.
    grant(e)
    exposed = e["user"].get(e["prefix"] + "/v1/models").json()
    assert private not in ids(exposed) and exposed["prefs"] == Store._empty_prefs()
    assert e["user"].put(model_url, json={"model_id": private}).status_code == 403
    second = service.create_run(sid, "after revocation", [])
    for _ in range(200):
        if second.finished:
            break
        time.sleep(.01)
    assert second.status == "completed" and private not in seen[-1]


def test_manual_context_compaction_rechecks_model_access(model_access, monkeypatch):
    e = model_access
    seen = []
    def compact(agent):
        seen.append(agent.settings.text_model.model_id)
        return {"compressed": False}
    monkeypatch.setattr(UmekoAgent, "compact_context", compact)
    session = e["service"].create_session(user_id=e["owner"]["id"])
    grant(e, [e["q"]["id"]], [e["alternate"]["id"]])
    e["service"].compact_context(session.id)
    assert seen == [e["alternate"]["id"]]
    grant(e, None, [])
    with pytest.raises(ValueError, match="开放"):
        e["service"].compact_context(session.id)
    assert seen == [e["alternate"]["id"]]


def test_dispatch_migration_defaults_existing_models_to_enabled(tmp_path):
    path = tmp_path / "legacy.db"
    with sqlite3.connect(path) as db:
        db.executescript("""CREATE TABLE provider_models (id TEXT PRIMARY KEY,provider_id TEXT NOT NULL,
          name TEXT NOT NULL,vision INTEGER NOT NULL DEFAULT 0,created_at TEXT NOT NULL);
          INSERT INTO provider_models VALUES ('legacy','provider','old',0,'old');""")
    store = Store(path)
    with store.connect() as db:
        assert db.execute("SELECT user_enabled FROM provider_models WHERE id='legacy'").fetchone()[0] == 1


def test_machine_agent_can_use_admin_model_without_dispatch(machine_client):
    from conftest import wait_task
    client, app, account, _ = machine_client
    store, registry = app.state.store, app.state.agent_service.agent_registry
    p = store.create_provider("private", "https://unused.invalid", "fixture-key")
    model = store.add_model(p["id"], "internal", user_enabled=False)
    registry.save({**app.state.fixture_agent, "default_model_id": model["id"]}, app.state.fixture_agent["id"])
    headers = {"Authorization": "Bearer " + account["token"]}
    task = client.post("/agent/fixture/v1/tasks", headers=headers, json={"prompt": "configured service model"}).json()
    assert wait_task(client, task["id"], account["token"])["status"] == "completed"
