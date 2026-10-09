from __future__ import annotations

import socket
import threading
import time

import pytest
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
def machine_server(machine_app):
    app, first, second, settings = machine_app
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    base = "http://127.0.0.1:" + str(listener.getsockname()[1])
    server = uvicorn.Server(uvicorn.Config(app, log_level="error", lifespan="on"))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started and thread.is_alive() and time.monotonic() < deadline:
        time.sleep(0.02)
    assert server.started
    yield base + settings.base_path + "/agent/fixture", app, first, second
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
