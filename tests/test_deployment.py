import re

import pytest
from fastapi.testclient import TestClient

from umeko.config import ModelConfig, Settings
from umeko.server.app import create_app
from umeko.server.admin import create_admin_app


@pytest.mark.parametrize("prefix,admin_prefix", [("", ""), ("/teams/docs/app", "/operations/console")])
@pytest.mark.parametrize("serve_ui", [True, False])
def test_independent_frontend_release_and_api_only_mode(tmp_path, prefix, admin_prefix, serve_ui):
    directory = tmp_path / "ui-release"
    (directory / "assets").mkdir(parents=True)
    for entry in ("index.html", "admin.html"):
        (directory / entry).write_text(
            '<html><head><meta name="umeko-base-path" content="__UMEKO_BASE_PATH__">'
            '<script src="./assets/release.js"></script></head><body>EXTERNAL_RELEASE</body></html>',
            encoding="utf-8")
    (directory / "assets/release.js").write_text("/* external release */", encoding="utf-8")
    settings = Settings(ModelConfig("fixture", "key", "https://unused.invalid"),
                        base_path=prefix, admin_base_path=admin_prefix, ui_dir=str(directory), serve_ui=serve_ui)
    if not serve_ui:
        # API-only deployments can omit the frontend release entirely.
        from dataclasses import replace
        settings = replace(settings, ui_dir=str(tmp_path / "missing-ui"))
    app = create_app(settings, data_root=tmp_path / "data", workspace_root=tmp_path / "output")
    service, store = app.state.agent_service, app.state.store
    store.create_user("fixture-admin", "fixture-password", role="admin")
    admin_app = create_admin_app(settings, service, store)
    try:
        with TestClient(app) as user, TestClient(admin_app) as admin:
            for client, base in ((user, prefix), (admin, admin_prefix)):
                html = client.get(base + "/")
                temporary = user.get(prefix + "/TMP/fixture-token")
                if serve_ui:
                    assert html.status_code == 200 and "EXTERNAL_RELEASE" in html.text
                    assert f'content="{base}"' in html.text
                    assert client.get(base + "/static/ui/assets/release.js").text == "/* external release */"
                    assert f'src="{base}/static/ui/assets/release.js"' in html.text
                    assert 'content="/TMP/fixture-token"' in temporary.text
                else:
                    assert html.status_code == temporary.status_code == 404
                    assert client.get(base + "/static/ui/index.html").status_code == 404
                    assert client.get(base + "/static/ui/assets/release.js").status_code == 404
                assert client.get(base + "/health").status_code == 200
            login = admin.post(admin_prefix + "/admin/login",
                               json={"username": "fixture-admin", "password": "fixture-password"})
            assert login.status_code == 200
            assert f"Path={admin_prefix or '/'}" in login.headers["set-cookie"]
            assert admin.get(admin_prefix + "/admin/v1/tools").status_code == 200
            assert user.get(prefix + "/openapi.json").status_code == 200
            assert user.get(prefix + "/v1/sessions").status_code == 401
            assert user.post(prefix + "/v1/auth/login",
                             json={"username": "fixture-admin", "password": "fixture-password"}).status_code == 200
            assert user.post(prefix + "/v1/sessions", json={}).status_code == 201
            assert user.get(prefix + "/TMP/fixture-token/v1/temporary").status_code == 410
    finally:
        service.run_manager.shutdown()


@pytest.mark.parametrize("prefix", ["", "/operations/umeko", "/admin"])
def test_admin_prefix_assets_auth_and_management(tmp_path, prefix):
    settings = Settings(ModelConfig("test", "key", "https://test/v1"),
                        base_path="/workbench", admin_base_path=prefix)
    user_app = create_app(settings, data_root=tmp_path / "data", workspace_root=tmp_path / "output")
    service, store = user_app.state.agent_service, user_app.state.store
    account = store.create_user("test-admin", "test-only-password", role="admin")
    admin_app = create_admin_app(settings, service, store, public_url="https://company.internal/workbench")

    try:
        with TestClient(admin_app) as admin:
            html = admin.get(prefix + "/").text
            assert f'name="umeko-base-path" content="{prefix}"' in html
            resources = re.findall(r'(?:src|href)="([^"?]*/static/[^"?]+)', html)
            assert len(resources) >= 2
            assert all(url.startswith(prefix + "/static/ui/") and
                       admin.get(url).status_code == 200 for url in resources)
            assert admin.get(prefix + "/admin/v1/me").status_code == 401
            login = admin.post(prefix + "/admin/login",
                               json={"username": account["username"], "password": "test-only-password"})
            assert login.status_code == 200
            assert f"Path={prefix or '/'}" in login.headers["set-cookie"]
            assert admin.get(prefix + "/admin/v1/me").json()["id"] == account["id"]
            for route in ("users", "providers", "skill-library", "tools", "resources", "tasks", "agents", "service-accounts"):
                assert admin.get(prefix + "/admin/v1/" + route).status_code == 200
            dispatch = prefix + "/admin/v1/tools/fetch_url"
            access = prefix + f"/admin/v1/users/{account['id']}/tool-access"
            assert admin.put(dispatch, json={"enabled": False}).status_code == 200
            assert admin.put(access, json={"allowed_tool_names": ["fetch_url"]}).status_code == 200
            # A new page load and subsequent reads retain the cookie and saved grants.
            assert admin.get(prefix + "/").status_code == 200
            assert admin.get(access).json()["allowed_tool_names"] == ["fetch_url"]
            assert not next(tool for tool in admin.get(prefix + "/admin/v1/tools").json()["tools"]
                            if tool["name"] == "fetch_url")["enabled"]
            assert "fetch_url" in store.effective_tool_names(account["id"])
            created = admin.post(prefix + "/admin/v1/service-accounts", json={"name": "test-service"})
            assert created.status_code == 201
            assert admin.delete(prefix + "/admin/v1/service-accounts/" + created.json()["id"]).status_code == 204
            agents = admin.get(prefix + "/admin/v1/agents").json()["agents"]
            assert agents and all(agent["endpoints"]["a2a"].startswith("https://company.internal/workbench/agent/") for agent in agents)
            logout = admin.post(prefix + "/admin/logout")
            assert logout.status_code == 204 and f"Path={prefix or '/'}" in logout.headers["set-cookie"]
            assert admin.get(prefix + "/admin/v1/me").status_code == 401
            assert admin.get(prefix + "/admin/v1/tools").status_code == 401
            assert admin.put(dispatch, json={"enabled": True}).status_code == 401
            assert admin.get(access).status_code == 401
            assert admin.put(access, json={"allowed_tool_names": None}).status_code == 401
        with TestClient(user_app) as user:
            assert user.get("/workbench/admin/v1/users").status_code == 404
    finally:
        service.run_manager.shutdown()


@pytest.mark.parametrize("prefix", ["", "/doc-master/consistency/image-text", "/v1"])
def test_root_and_prefixed_ui_auth_and_session_isolation(tmp_path, prefix):
    app = create_app(Settings(ModelConfig("test", "key", "https://test/v1"), base_path=prefix),
                     data_root=tmp_path / "data", workspace_root=tmp_path / "output")
    try:
        # One running server lifecycle, with two independent client cookie jars.
        with TestClient(app) as owner:
            other = TestClient(app)
            html = owner.get(prefix + "/").text
            assert f'name="umeko-base-path" content="{prefix}"' in html
            resources = re.findall(r'(?:src|href)="([^"?]*/static/[^"?]+)', html)
            assert len(resources) >= 2  # Bundled scripts, styles and shared module preload.
            assert all(url.startswith(prefix + "/static/") and owner.get(url).status_code == 200 for url in resources)
            # Admin is a separate entry and serves its own bundled modules publicly,
            # while management API requests still require an admin cookie.
            admin_app = create_admin_app(app.state.agent_service.settings, app.state.agent_service, app.state.store)
            with TestClient(admin_app) as admin:
                admin_html = admin.get("/").text
                assert 'name="umeko-base-path" content=""' in admin_html
                admin_resources = re.findall(r'(?:src|href)="([^"?]*/static/[^"?]+)', admin_html)
                assert len(admin_resources) >= 2
                assert all(url.startswith("/static/ui/") and admin.get(url).status_code == 200 for url in admin_resources)
                assert admin.get("/admin/v1/me").status_code == 401
            assert other.get(prefix + "/v1/sessions").status_code == 401
            register = owner.post(prefix + "/v1/auth/register", json={"username": "owner", "password": "password"})
            assert register.status_code == 201
            assert f"Path={prefix or '/'}" in register.headers["set-cookie"]
            sid = owner.post(prefix + "/v1/sessions", json={}).json()["id"]
            other.post(prefix + "/v1/auth/register", json={"username": "other", "password": "password"}).raise_for_status()
            assert other.get(prefix + f"/v1/sessions/{sid}/workspace/tree").status_code == 404
            assert owner.get(prefix + f"/v1/sessions/{sid}/workspace/tree").status_code == 200
            tree_path = prefix + f"/v1/sessions/{sid}/workspace/tree"
            assert owner.get(tree_path, params={"filter": "["}).status_code == 400
            # Tool history retains its task identity for grouping and active-run replay.
            event_id = app.state.store.add_tool_event(
                sid, "main", "read_document", arguments='{"path":"sample.txt"}', run_id="run_history")
            app.state.store.complete_tool_event(event_id, '{"text":"sample"}')
            history = owner.get(prefix + f"/v1/sessions/{sid}/tool-events").json()
            assert history[0]["run_id"] == "run_history"
            assert history[0]["result"] == '{"text":"sample"}'
            assert other.get(prefix + f"/v1/sessions/{sid}/tool-events").status_code == 404
            # The one-shot status adapter must enforce the same ownership boundary.
            assert owner.get(prefix + f"/v1/proxy/sessions/{sid}").status_code == 200
            assert other.get(prefix + f"/v1/proxy/sessions/{sid}").status_code == 404
            assert owner.get(prefix + "/v1/proxy/sessions/missing").status_code == 404
            assert owner.post(prefix + "/v1/auth/logout").status_code == 204
            assert owner.get(prefix + "/v1/auth/me").status_code == 401
            owner.post(prefix + "/v1/auth/login", json={"username": "owner", "password": "password"}).raise_for_status()
            assert owner.get(prefix + "/v1/auth/me").json()["username"] == "owner"
    finally:
        app.state.agent_service.run_manager.shutdown()
