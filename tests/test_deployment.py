import re

import pytest
from fastapi.testclient import TestClient

from umeko.config import ModelConfig, Settings
from umeko.server.app import create_app


@pytest.mark.parametrize("prefix", ["", "/doc-master/consistency/image-text", "/v1"])
def test_root_and_prefixed_ui_auth_and_session_isolation(tmp_path, prefix):
    app = create_app(Settings(ModelConfig("test", "key", "https://test/v1"), base_path=prefix),
                     data_root=tmp_path / "data", workspace_root=tmp_path / "output")
    try:
        with TestClient(app) as owner, TestClient(app) as other:
            html = owner.get(prefix + "/").text
            assert f'<meta name="umeko-base-path" content="{prefix}">' in html
            resources = re.findall(r'(?:src|href)="([^"?]*/static/[^"?]+)', html)
            assert len(resources) == 5
            assert all(url.startswith(prefix + "/static/") and owner.get(url).status_code == 200 for url in resources)
            assert other.get(prefix + "/v1/sessions").status_code == 401
            register = owner.post(prefix + "/v1/auth/register", json={"username": "owner", "password": "password"})
            assert register.status_code == 201
            assert f"Path={prefix or '/'}" in register.headers["set-cookie"]
            sid = owner.post(prefix + "/v1/sessions", json={}).json()["id"]
            other.post(prefix + "/v1/auth/register", json={"username": "other", "password": "password"}).raise_for_status()
            assert other.get(prefix + f"/v1/sessions/{sid}/workspace/tree").status_code == 404
            assert owner.get(prefix + f"/v1/sessions/{sid}/workspace/tree").status_code == 200
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
