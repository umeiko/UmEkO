"""Public skill distribution, authenticated discovery and real external admin workflows."""
from contextlib import contextmanager
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time

from fastapi.testclient import TestClient
import httpx
import pytest
import uvicorn

from umeko.config import ModelConfig, Settings
from umeko.server.admin import create_admin_app
from umeko.server.admin_automation import SKILL_ROOT
from umeko.server.app import create_app

SPEC = importlib.util.spec_from_file_location("admin_skill_client", SKILL_ROOT / "scripts/admin_api.py")
client_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(client_module)


@pytest.fixture(params=["", "/operations/console"])
def admin_pair(tmp_path, request):
    prefix = request.param
    settings = Settings(ModelConfig("fixture", "synthetic-key", "https://models.example.invalid/v1"),
                        base_path="/teams/workbench", admin_base_path=prefix)
    user = create_app(settings, data_root=tmp_path / "data", workspace_root=tmp_path / "output")
    service, store = user.state.agent_service, user.state.store
    account = store.create_user("automation-admin", "synthetic-password", role="admin")
    ordinary = store.create_user("automation-reader", "synthetic-password")
    admin = create_admin_app(settings, service, store)
    yield user, admin, service, account, ordinary, prefix
    service.run_manager.shutdown()


def test_download_is_public_but_management_schema_and_operations_require_admin(admin_pair):
    user, app, service, account, ordinary, prefix = admin_pair
    with TestClient(app) as client:
        manifest = client.get(prefix + "/admin/automation").json()
        assert manifest["name"] == "umeko-server-admin"
        for item in manifest["files"]:
            assert item["url"] == prefix + "/admin/automation/skill/" + item["path"]
            result = client.get(item["url"])
            assert result.status_code == 200
            assert hashlib.sha256(result.content).hexdigest() == item["sha256"]
            assert len(result.content) == item["size"]
        assert client.get(prefix + "/admin/automation/skill/not-public.txt").status_code == 404
        assert client.get(prefix + "/admin/v1/openapi.json").status_code == 401
        assert client.put(prefix + "/admin/v1/runtime-config", json={"max_tool_iterations": 3}).status_code == 401
        # A user token, including an ordinary user who signs into the user plane,
        # cannot be promoted by presenting it in the administrator cookie slot.
        token = service.store.issue_token(ordinary["id"])
        client.cookies.set("umeko_admin", token, path=prefix or "/")
        assert client.get(prefix + "/admin/v1/openapi.json").status_code == 401
        client.cookies.clear()
        assert client.post(prefix + "/admin/login", json={"username": account["username"], "password": "synthetic-password"}).status_code == 200
        schema = client.get(prefix + "/admin/v1/openapi.json").json()
        assert schema["servers"] == [{"url": prefix or "/"}]
        assert len(schema["paths"]) > 45
        for path, operations in schema["paths"].items():
            for method, operation in operations.items():
                assert operation["description"] and operation["summary"]
                if path.startswith("/admin/v1/"):
                    assert operation["security"] == [{"umeko_admin": []}]
                    assert "401" in operation["responses"]
                assert operation["x-umeko-automatic-retry"] is False
        assert schema["paths"]["/admin/v1/models/{model_id}"]["put"]["requestBody"]
        assert "反转" in schema["paths"]["/admin/v1/default-skills/{name}/toggle"]["post"]["description"]
        assert "SHA-256" in schema["paths"]["/admin/v1/skill-security/batch"]["post"]["description"]
        client.post(prefix + "/admin/logout")
        assert client.get(prefix + "/admin/v1/openapi.json").status_code == 401
    # Neither admin discovery nor its downloadable client is a user-plane API.
    with TestClient(user) as client:
        for route in ("/admin/automation", "/admin/automation/skill/SKILL.md", "/admin/v1/openapi.json"):
            assert client.get("/teams/workbench" + route).status_code == 404


@contextmanager
def running_admin(app, prefix):
    # Uvicorn uses root_path exactly as the production entry. A tiny HTTP
    # gateway strips the configured public prefix once and rejects other paths.
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    with socket.socket() as bound:
        bound.bind(("127.0.0.1", 0))
        port = bound.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error", root_path=prefix))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(200):
        if server.started:
            break
        time.sleep(.01)
    assert server.started

    class Gateway(BaseHTTPRequestHandler):
        def do_request(self):
            if prefix and not self.path.startswith(prefix + "/"):
                self.send_error(404)
                return
            raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
            with httpx.Client(trust_env=False) as upstream:
                reply = upstream.request(self.command, f"http://127.0.0.1:{port}" + (self.path[len(prefix):] if prefix else self.path),
                                         content=raw, headers={key: value for key, value in self.headers.items() if key.lower() not in {"host", "connection"}})
            self.send_response(reply.status_code)
            for key, value in reply.headers.multi_items():
                if key.lower() not in {"content-length", "transfer-encoding", "connection"}:
                    self.send_header(key, value)
            self.send_header("Content-Length", str(len(reply.content)))
            self.end_headers()
            self.wfile.write(reply.content)

        do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = do_request
        def log_message(self, *args):
            pass

    gateway = ThreadingHTTPServer(("127.0.0.1", 0), Gateway)
    worker = threading.Thread(target=gateway.serve_forever, daemon=True)
    worker.start()
    try:
        yield f"http://127.0.0.1:{gateway.server_port}" + prefix
    finally:
        gateway.shutdown()
        gateway.server_close()
        server.should_exit = True
        thread.join(5)


def test_downloaded_client_can_manage_models_users_agents_skills_and_permissions(admin_pair):
    _, app, service, account, _, prefix = admin_pair
    with running_admin(app, prefix) as base:
        with client_module.AdminClient(base, account["username"], "synthetic-password") as client:
            assert client.request("GET", "/admin/v1/openapi.json")["servers"] == [{"url": prefix or "/"}]
            provider = client.request("POST", "/admin/v1/providers", {"name": "API fixture", "base_url": "https://models.example.invalid/v1", "api_key": "synthetic-private-key"})
            model = client.request("POST", "/admin/v1/providers/" + provider["id"] + "/models", {"name": "general", "vision": False})
            assert client.request("PUT", "/admin/v1/models/" + model["id"], {"max_concurrent_requests": 2}) is None
            listing = client.request("GET", "/admin/v1/providers")
            assert listing["providers"][0]["models"][0]["max_concurrent_requests"] == 2
            assert client_module.redact(listing)["providers"][0]["api_key"] == "********"
            user = client.request("POST", "/admin/v1/users", {"username": "api-colleague", "password": "synthetic-user-password"})
            client.request("PUT", f"/admin/v1/users/{user['id']}/model-access", {"allowed_provider_ids": [provider["id"]], "allowed_model_ids": [model["id"]]})
            client.request("PUT", f"/admin/v1/users/{user['id']}/tool-access", {"allowed_tool_names": ["list_dir"]})
            assert client.request("GET", f"/admin/v1/users/{user['id']}/tool-access")["allowed_tool_names"] == ["list_dir"]
            agent = client.request("POST", "/admin/v1/agents", {"slug": "api-reviewer", "name": "API Reviewer", "description": "Synthetic agent", "default_model_id": model["id"]})
            assert client.request("GET", f"/admin/v1/agents/{agent['id']}/mcp")["endpoint"]
            text = "---\nname: api-fixture\ndescription: Synthetic instructions\n---\nOnly inspect supplied test files."
            client.request("PUT", "/admin/v1/skill-source/api-fixture.md", {"content": text})
            client.request("POST", "/admin/v1/default-skills/import/api-fixture.md")
            client.request("PUT", "/admin/v1/skill-scripts/api-fixture/scripts/run.py", {"content": "print('fixture')\n"})
            gate = client.request("GET", "/admin/v1/skill-security/api-fixture/scripts/run.py")
            assert not gate["trusted"]
            approved = client.request("POST", "/admin/v1/skill-security/api-fixture/scripts/run.py", {"sha256": gate["current"]["sha256"]})
            assert approved["trusted"]
            revoked = client.request("DELETE", "/admin/v1/skill-security/api-fixture/scripts/run.py", {"sha256": approved["approved"]["sha256"]})
            assert revoked["status"] == "revoked"
            assert client.request("GET", "/admin/v1/tasks") == []
            client.request("DELETE", "/admin/v1/agents/" + agent["id"])
            client.request("DELETE", "/admin/v1/users/" + user["id"])
            session_cookie = next(iter(client.cookies)).value
        assert service.store.user_for_token(session_cookie) is None


def test_cli_output_redaction_and_preflight_before_mutation(admin_pair, tmp_path):
    _, app, _, account, _, prefix = admin_pair
    with running_admin(app, prefix) as base:
        script = tmp_path / "downloaded_admin_api.py"
        with httpx.Client(trust_env=False) as downloader:
            response = downloader.get(base + "/admin/automation/skill/scripts/admin_api.py")
            assert response.status_code == 200
            script.write_bytes(response.content)
        env = {**os.environ, "UMEKO_ADMIN_URL": base, "UMEKO_ADMIN_USERNAME": account["username"], "UMEKO_ADMIN_PASSWORD": "synthetic-password"}
        body = tmp_path / "request.json"
        body.write_text(json.dumps({"name": "cli-fixture"}), encoding="utf-8")
        private = tmp_path / "one-time.json"
        command = [sys.executable, str(script), "POST", "/admin/v1/service-accounts", "--json-file", str(body), "--secrets-output", str(private)]
        result = subprocess.run(command, env=env, capture_output=True, text=True, encoding="utf-8")
        assert result.returncode == 0, result.stderr
        secret = json.loads(private.read_text(encoding="utf-8"))["token"]
        assert secret not in result.stdout and secret not in result.stderr
        assert json.loads(result.stdout)["token"] == "********"
        again = subprocess.run(command, env=env, capture_output=True, text=True, encoding="utf-8")
        assert again.returncode == 2  # Existing private destination fails before POST.
        with client_module.AdminClient(base, account["username"], "synthetic-password") as client:
            assert len(client.request("GET", "/admin/v1/service-accounts")["accounts"]) == 1
        # Redaction preserves OpenAPI field definitions, which are dictionaries.
        spec = {"properties": {"password": {"type": "string"}, "api_key": {"type": "string"}}}
        assert client_module.redact(spec) == spec
