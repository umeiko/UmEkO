from __future__ import annotations

import json
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from umeko.cancellation import OperationCancelled
from umeko.config import ModelConfig, Settings
from umeko.host.configuration import model_from_row, resolve_provider_settings
from umeko.host.service import AgentService
from umeko.host.storage import Store
from umeko.llm.client import LLMClient
from umeko.llm.concurrency import ModelCallQueue, model_call_queue
from umeko.server.admin import create_admin_app


def wait_for(predicate):
    deadline = time.monotonic() + 5
    while not predicate():
        assert time.monotonic() < deadline, "Timed out waiting for concurrency state"
        time.sleep(0.005)


def test_fifo_cancelled_waiter_and_exception_release():
    queue = ModelCallQueue(1)
    cancel = threading.Event()
    order = []

    def call(number, should_cancel=None):
        with queue.slot(should_cancel):
            order.append(number)
            if number == 3:
                raise RuntimeError("upstream failed")

    with ThreadPoolExecutor(max_workers=4) as pool:
        with queue.slot():
            futures = []
            for number in range(4):
                futures.append(pool.submit(call, number, cancel.is_set if number == 1 else None))
                wait_for(lambda: queue.snapshot()["waiting"] == number + 1)
            cancel.set()
            with pytest.raises(OperationCancelled):
                futures[1].result(timeout=2)
            assert queue.snapshot()["waiting"] == 3
        for number in (0, 2):
            futures[number].result(timeout=2)
        with pytest.raises(RuntimeError, match="upstream failed"):
            futures[3].result(timeout=2)
    assert order == [0, 2, 3]
    assert queue.snapshot() == {"limit": 1, "active": 0, "waiting": 0}


def test_unlimited_calls_are_counted_when_limit_is_enabled():
    queue = ModelCallQueue()
    releases = [threading.Event() for _ in range(3)]

    def held_call(number):
        with queue.slot():
            assert releases[number].wait(timeout=5)

    with ThreadPoolExecutor(max_workers=4) as pool:
        try:
            running = [pool.submit(held_call, number) for number in range(3)]
            wait_for(lambda: queue.snapshot()["active"] == 3)
            queue.set_limit(1)
            waiting = pool.submit(held_call, 0)
            wait_for(lambda: queue.snapshot()["waiting"] == 1)
            for number in (0, 1):
                releases[number].set()
                running[number].result(timeout=2)
            assert queue.snapshot()["active"] == 1
            assert not waiting.done()
            releases[2].set()
            running[2].result(timeout=2)
            waiting.result(timeout=2)
        finally:
            for release in releases:
                release.set()
    assert queue.snapshot()["active"] == 0


def test_live_model_limit_changes_do_not_reset_existing_clients(tmp_path):
    store = Store(tmp_path / "db")
    pid = store.create_provider("company", "http://localhost/v1", "test-key")["id"]
    mid = store.add_model(pid, "shared", max_concurrent_requests=1)["id"]
    config = model_from_row(store.model_by_id(mid), ModelConfig("default", "", ""))
    main, sub = LLMClient(config), LLMClient(config)
    queue = main._call_queue
    assert sub._call_queue is queue
    releases = [threading.Event() for _ in range(3)]

    def call(number):
        with queue.slot():
            assert releases[number].wait(timeout=5)

    with ThreadPoolExecutor(max_workers=3) as pool:
        try:
            first = pool.submit(call, 0)
            wait_for(lambda: queue.snapshot()["active"] == 1)
            second = pool.submit(call, 1)
            wait_for(lambda: queue.snapshot()["waiting"] == 1)
            store.update_model(mid, max_concurrent_requests=2)
            wait_for(lambda: queue.snapshot()["active"] == 2)
            store.update_model(mid, max_concurrent_requests=1)
            third = pool.submit(call, 2)
            wait_for(lambda: queue.snapshot()["waiting"] == 1)
            assert LLMClient(config)._call_queue.snapshot()["limit"] == 1  # stale config can't undo it
            releases[0].set()
            first.result(timeout=2)
            assert not third.done()  # one running call still consumes the reduced quota
            store.update_model(mid, max_concurrent_requests=0)
            wait_for(lambda: queue.snapshot()["waiting"] == 0)
            assert queue.snapshot()["active"] == 2
            releases[1].set()
            releases[2].set()
            second.result(timeout=2)
            third.result(timeout=2)
        finally:
            for release in releases:
                release.set()
    other = store.add_model(pid, "independent", max_concurrent_requests=1)["id"]
    assert model_call_queue(other) is not queue
    queue.set_limit(1)
    with queue.slot(), model_call_queue(other).slot():
        assert queue.snapshot()["active"] == 1
        assert model_call_queue(other).snapshot()["active"] == 1


@pytest.mark.parametrize("streaming", [False, True])
def test_real_http_calls_share_quota_across_clients_until_stream_finishes(tmp_path, streaming):
    release = threading.Event()
    lock = threading.Lock()
    state = {"active": 0, "peak": 0, "requests": 0}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_POST(self):
            document = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            with lock:
                state["active"] += 1
                state["requests"] += 1
                state["peak"] = max(state["peak"], state["active"])
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream" if document["stream"] else "application/json")
            self.end_headers()
            if document["stream"]:
                chunk = {"id": "test", "object": "chat.completion.chunk", "created": 0,
                         "model": "shared", "choices": [{"index": 0, "delta": {"content": "ok"}, "finish_reason": None}]}
                self.wfile.write(("data: " + json.dumps(chunk) + "\n\n").encode())
                self.wfile.flush()
            assert release.wait(timeout=8)
            with lock:
                state["active"] -= 1
            if document["stream"]:
                self.wfile.write(b"data: [DONE]\n\n")
            else:
                completion = {"id": "test", "object": "chat.completion", "created": 0,
                              "model": "shared", "choices": [{"index": 0, "message": {"role": "assistant", "content": "ok"}, "finish_reason": "stop"}]}
                self.wfile.write(json.dumps(completion).encode())
            self.wfile.flush()

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    store = Store(tmp_path / "db")
    pid = store.create_provider("mock", f"http://127.0.0.1:{server.server_port}/v1", "test")["id"]
    mid = store.add_model(pid, "shared", max_concurrent_requests=2)["id"]
    config = model_from_row(store.model_by_id(mid), ModelConfig("", "", ""))
    clients = [LLMClient(config) for _ in range(5)]  # independently loaded users / roles
    queue = clients[0]._call_queue
    messages = [{"role": "user", "content": "hello"}]
    try:
        with ThreadPoolExecutor(max_workers=5) as pool:
            try:
                futures = [pool.submit(client.chat_stream, messages, lambda _: None) if streaming
                           else pool.submit(client.chat, messages) for client in clients]
                wait_for(lambda: state["requests"] == 2 and queue.snapshot()["waiting"] == 3)
                assert state["active"] == 2
                assert queue.snapshot()["active"] == 2
            finally:
                release.set()
            assert [future.result(timeout=8) for future in futures] == ["ok"] * 5
        assert state["peak"] == 2
        assert state["requests"] == 5
        assert queue.snapshot() == {"limit": 2, "active": 0, "waiting": 0}
    finally:
        release.set()
        for client in clients:
            if client._client is not None:
                client._client.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_queued_cancel_does_not_open_a_model_connection():
    client = LLMClient(ModelConfig("mock", "test", "http://unused/v1", max_concurrent_requests=1))
    cancelled = threading.Event()
    with ThreadPoolExecutor(max_workers=1) as pool:
        with client._call_queue.slot():
            future = pool.submit(client.chat, [{"role": "user", "content": "test"}], cancelled.is_set)
            wait_for(lambda: client._call_queue.snapshot()["waiting"] == 1)
            cancelled.set()
            with pytest.raises(OperationCancelled):
                future.result(timeout=2)
            assert client._client is None
    assert client._call_queue.snapshot()["active"] == 0


def test_stream_fallback_reacquires_a_single_slot_and_failure_releases_it(monkeypatch):
    client = LLMClient(ModelConfig("mock", "test", "http://unused/v1", max_concurrent_requests=1))
    calls = []

    def create(**kwargs):
        assert client._call_queue.snapshot()["active"] == 1
        calls.append(kwargs["stream"])
        if kwargs["stream"]:
            raise RuntimeError("stream not supported")
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="ok", tool_calls=None))])

    monkeypatch.setattr(client, "_get_client", lambda: SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))))
    with ThreadPoolExecutor(max_workers=1) as pool:
        assert pool.submit(client.chat_stream, [], lambda _: None).result(timeout=2) == "ok"
    assert calls == [True, False]
    assert client._call_queue.snapshot()["active"] == 0

    def failed(**_kwargs):
        raise RuntimeError("model failed")

    monkeypatch.setattr(client, "_get_client", lambda: SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=failed))))
    with pytest.raises(RuntimeError, match="model failed"):
        client.chat([])
    assert client._call_queue.snapshot()["active"] == 0


@pytest.mark.parametrize("streaming", [False, True])
def test_cancel_active_stream_releases_slot_even_if_gateway_ignores_stream_false(monkeypatch, streaming):
    entered = threading.Event()
    closed = threading.Event()
    cancelled = threading.Event()
    client = LLMClient(ModelConfig("mock", "test", "http://unused/v1", max_concurrent_requests=1))

    class BlockingStream:
        def __iter__(self):
            return self

        def __next__(self):
            entered.set()
            assert closed.wait(timeout=5)
            raise RuntimeError("connection closed")

        def close(self):
            closed.set()

    stream = BlockingStream()
    fake = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **_: stream)), close=stream.close)
    monkeypatch.setattr(client, "_get_client", lambda: fake)
    with ThreadPoolExecutor(max_workers=1) as pool:
        if streaming:
            future = pool.submit(client.chat_stream, [], lambda _: None, should_cancel=cancelled.is_set)
        else:
            future = pool.submit(client.chat, [], cancelled.is_set)
        assert entered.wait(timeout=2)
        assert client._call_queue.snapshot()["active"] == 1
        cancelled.set()
        with pytest.raises(OperationCancelled):
            future.result(timeout=2)
    assert closed.is_set()
    assert client._call_queue.snapshot()["active"] == 0

def test_legacy_database_and_import_preserve_per_model_limits(tmp_path):
    path = tmp_path / "db"
    with sqlite3.connect(path) as db:
        db.executescript("""
            CREATE TABLE provider_models (id TEXT PRIMARY KEY, provider_id TEXT NOT NULL,
                name TEXT NOT NULL, vision INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL,
                UNIQUE(provider_id, name));
            INSERT INTO provider_models VALUES ('old', 'legacy', 'old-model', 0, 'old');
        """)
    store = Store(path)
    with store.connect() as db:
        assert db.execute("SELECT max_concurrent_requests FROM provider_models WHERE id='old'").fetchone()[0] == 0
    store.import_providers({"providers": [{"name": "new", "base_url": "http://test/v1", "api_key": "test",
                                            "models": [{"name": "text", "max_concurrent_requests": 2}, {"name": "vision", "vision": True}]}], "active": "new/text"})
    settings = resolve_provider_settings(Settings(ModelConfig("", "", "")), store)
    assert settings.text_model.max_concurrent_requests == 2
    assert settings.vision_model.max_concurrent_requests == 0
    assert settings.vision_model.model_id is not None
    store.import_providers({"providers": [{"name": "new", "models": [{"name": "text", "vision": True}]}]})
    assert store.active_model()["max_concurrent_requests"] == 2
    store.import_providers({"providers": [{"name": "new", "models": [{"name": "text", "max_concurrent_requests": 0}]}]})
    assert Store(path).active_model()["max_concurrent_requests"] == 0


def test_admin_api_validates_and_applies_limit_to_loaded_clients(tmp_path):
    store = Store(tmp_path / "db")
    settings = Settings(ModelConfig("", "", ""))
    service = AgentService(settings, tmp_path / "data", tmp_path / "output", store=store)
    store.create_user("admin", "test-password", role="admin")
    app = create_admin_app(settings, service, store)
    try:
        with TestClient(app) as api:
            assert api.post("/admin/v1/providers", json={"name": "company", "base_url": "http://test", "api_key": "test"}).status_code == 401
            api.post("/admin/login", json={"username": "admin", "password": "test-password"}).raise_for_status()
            pid = api.post("/admin/v1/providers", json={"name": "company", "base_url": "http://test", "api_key": "test"}).json()["id"]
            mid = api.post(f"/admin/v1/providers/{pid}/models", json={"name": "main"}).json()["id"]
            client = LLMClient(model_from_row(store.model_by_id(mid), settings.text_model))
            assert client._call_queue.snapshot()["limit"] == 0
            assert api.put(f"/admin/v1/models/{mid}", json={"max_concurrent_requests": 3}).status_code == 204
            assert client._call_queue.snapshot()["limit"] == 3
            for invalid in (-1, 1.5, True, "2"):
                assert api.put(f"/admin/v1/models/{mid}", json={"max_concurrent_requests": invalid}).status_code == 422
            assert api.put("/admin/v1/models/missing", json={"max_concurrent_requests": 1}).status_code == 404
            assert api.get("/admin/v1/providers").json()["providers"][0]["models"][0]["max_concurrent_requests"] == 3
            assert api.put(f"/admin/v1/models/{mid}", json={"max_concurrent_requests": 0}).status_code == 204
            assert client._call_queue.snapshot()["limit"] == 0
            imported = api.post("/admin/v1/providers/import", json={"document": {"providers": [
                {"name": "company", "models": [{"name": "main", "max_concurrent_requests": 2}]}]}})
            assert imported.status_code == 200
            assert client._call_queue.snapshot()["limit"] == 2
    finally:
        service.run_manager.shutdown()


def test_main_subagent_and_vision_roles_resolve_to_their_model_queue(tmp_path):
    store = Store(tmp_path / "db")
    pid = store.create_provider("company", "http://unused/v1", "test")["id"]
    main = store.add_model(pid, "main", max_concurrent_requests=2)["id"]
    vision = store.add_model(pid, "vision", vision=True, max_concurrent_requests=1)["id"]
    store.set_active_model(main)
    user = store.create_user("person", "test-password")
    store.set_user_model_prefs(user["id"], main_model_id=main, sub_model_id=main, vision_model_id=vision)
    service = AgentService(Settings(ModelConfig("", "", ""), registry_managed=True),
                           tmp_path / "data", tmp_path / "output", store=store)
    try:
        first = service.create_session(user_id=user["id"], settings=service.effective_settings_for(user["id"]))
        other_user = store.create_user("other", "test-password")
        store.set_user_model_prefs(other_user["id"], main_model_id=main, sub_model_id=main, vision_model_id=vision)
        second = service.create_session(user_id=other_user["id"], settings=service.effective_settings_for(other_user["id"]))
        agent = service.get_session(first.id).agent
        other = service.get_session(second.id).agent
        assert agent._llm._call_queue is agent._subagent._llm._call_queue
        assert agent._llm._call_queue is other._llm._call_queue
        assert agent._subagent._image_reasoning_llm._call_queue is model_call_queue(vision)
        assert agent._llm._call_queue is not model_call_queue(vision)
        store.update_model(main, max_concurrent_requests=1)
        assert agent._llm._call_queue.snapshot()["limit"] == 1
        assert other._subagent._llm._call_queue.snapshot()["limit"] == 1
    finally:
        service.run_manager.shutdown()
