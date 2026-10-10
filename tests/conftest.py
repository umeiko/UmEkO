from __future__ import annotations

import socket
import os
import subprocess
import threading
import time

import pytest
import httpx
import uvicorn
from fastapi.testclient import TestClient

from umeko.agent import UmekoAgent
from umeko.cancellation import OperationCancelled
from umeko.config import ModelConfig, Settings
from umeko.host.identities import SCOPES
from umeko.server.app import create_app


@pytest.fixture(autouse=True)
def isolated_skill_library(tmp_path, monkeypatch):
    # Server bootstrap and admin edits must never touch the developer's skill library.
    monkeypatch.setenv("UMEKO_SKILL_DIR", str(tmp_path / "skills"))


@pytest.fixture
def machine_app(tmp_path, monkeypatch, request):
    def chat(agent, prompt, images=None):
        if prompt.startswith("hold"):
            while not agent._should_cancel():
                time.sleep(0.01)
            raise OperationCancelled()
        time.sleep(0.05)
        attachments = agent._output_root / "attachments"
        content = " | ".join(p.read_text(encoding="utf-8") for p in attachments.glob("*.txt"))
        text = "Processed: " + prompt.split("\n")[0] + (" / " + content if content else "")
        (agent._output_root / "generate" / "report.txt").write_text(text, encoding="utf-8")
        agent._on_event("assistant.delta", {"text": text})
        return text
    monkeypatch.setattr(UmekoAgent, "chat", chat)
    settings = Settings(ModelConfig("fixture", "fixture-key", "http://unused.invalid"), base_path=getattr(request,"param",""),
                        task_workers=1, task_queue_limit=2, task_caller_limit=3,
                        task_retention_seconds=60, task_timeout_seconds=15)
    app = create_app(settings, data_root=tmp_path / "data", workspace_root=tmp_path / "out")
    app.state.fixture_agent = app.state.agent_service.agent_registry.save({
        "slug": "fixture", "name": "Fixture Agent", "description": "Protocol test service", "skill_names": []})
    first = app.state.identity_store.create("first", sorted(SCOPES))
    second = app.state.identity_store.create("second", sorted(SCOPES))
    return app, first, second, settings


@pytest.fixture
def machine_client(machine_app):
    app, first, second, settings = machine_app
    with TestClient(app, base_url="http://127.0.0.1") as client:
        yield client, app, first, second


@pytest.fixture
def machine_server(machine_app, tmp_path):
    app, first, second, settings = machine_app
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    base = "http://127.0.0.1:" + str(listener.getsockname()[1])
    nginx = os.getenv("UMEKO_TEST_NGINX") if settings.base_path else None
    server = uvicorn.Server(uvicorn.Config(app, log_level="error", lifespan="on",
                                         root_path=settings.base_path if nginx else ""))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started and thread.is_alive() and time.monotonic() < deadline:
        time.sleep(0.02)
    proxy = None
    proxy_args = []
    try:
        assert server.started
        if nginx:
            folder = tmp_path / "nginx"
            (folder / "logs").mkdir(parents=True)
            (folder / "temp").mkdir()
            with socket.socket() as reservation:
                reservation.bind(("127.0.0.1", 0))
                proxy_port = reservation.getsockname()[1]
            config = f'''worker_processes 1;
daemon off;
pid "{folder.as_posix()}/nginx.pid";
error_log "{folder.as_posix()}/error.log";
events {{ worker_connections 128; }}
http {{
    access_log off;
    client_max_body_size 64m;
    client_body_temp_path "{folder.as_posix()}/body";
    proxy_temp_path "{folder.as_posix()}/proxy";
    fastcgi_temp_path "{folder.as_posix()}/fastcgi";
    uwsgi_temp_path "{folder.as_posix()}/uwsgi";
    scgi_temp_path "{folder.as_posix()}/scgi";
    server {{
        listen 127.0.0.1:{proxy_port};
        location {settings.base_path}/ {{
            proxy_pass {base}/;
            proxy_http_version 1.1;
            proxy_set_header Connection "";
            proxy_set_header Host $http_host;
            proxy_buffering off;
            proxy_read_timeout 30s;
        }}
        location / {{ return 404; }}
    }}
}}
'''
            (folder / "proxy.conf").write_text(config, encoding="utf-8")
            proxy_args = [nginx, "-p", folder.as_posix() + "/", "-c", "proxy.conf"]
            flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            subprocess.run([*proxy_args, "-t"], check=True, capture_output=True, creationflags=flags)
            proxy = subprocess.Popen(proxy_args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                     creationflags=flags)
            base = f"http://127.0.0.1:{proxy_port}"
            with httpx.Client(trust_env=False, timeout=1) as http:
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    assert proxy.poll() is None, "NGINX exited"
                    try:
                        if http.get(base + settings.base_path + "/health").status_code == 200:
                            break
                    except httpx.ConnectError:
                        pass
                    time.sleep(.02)
                else:
                    raise AssertionError("NGINX startup timed out")
                assert http.get(base + "/agent/fixture/.well-known/agent-card.json").status_code == 404
        yield base + settings.base_path + "/agent/fixture", app, first, second
    finally:
        try:
            if proxy is not None and proxy.poll() is None:
                subprocess.run([*proxy_args, "-s", "quit"], check=True, capture_output=True, creationflags=flags)
                proxy.wait(timeout=5)
        finally:
            server.should_exit = True
            thread.join(timeout=15)
            listener.close()
            assert not thread.is_alive()


def wait_task(client, task_id, token, terminal=True):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        response = client.get("/agent/fixture/v1/tasks/" + task_id, headers={"Authorization": "Bearer " + token})
        assert response.status_code == 200, response.text
        task = response.json()
        if task["status"] in {"completed", "failed", "cancelled"} if terminal else task["status"] == "running":
            return task
        time.sleep(0.03)
    raise AssertionError("Task did not reach expected state")
