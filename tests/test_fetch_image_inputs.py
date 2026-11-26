"""Real URL image transfer into builtin visual tools; no live model calls."""
import base64
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading
import time

from fastapi.testclient import TestClient
import pytest

from umeko.agent import UmekoAgent
from umeko.config import ModelConfig, Settings
from umeko.llm import LLMClient
from umeko.server.app import create_app
from umeko.skills import download


@pytest.mark.parametrize("prefix", ["", "/teams/docs/workbench"])
@pytest.mark.parametrize("slug,skill", [("image-qc", "doc-image-qc"), ("image-resioning-agent", "image-reasoning")])
def test_builtin_image_agents_download_url_input_then_use_vision(tmp_path, monkeypatch, prefix, slug, skill):
    image = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGP4//8/AAX+Av4N70a4AAAAAElFTkSuQmCC")
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            assert self.path == "/image"
            assert self.headers.get("Authorization") is None and self.headers.get("Cookie") is None
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(image)))
            self.end_headers()
            self.wfile.write(image)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    original = download._addresses
    monkeypatch.setattr(download, "_addresses", lambda host, port, blocked_hosts=():
                        ["127.0.0.1"] if host == "images.example.test" and port == server.server_port
                        else original(host, port, blocked_hosts))
    app = create_app(Settings(ModelConfig("fixture", "fixture-key", "https://unused.invalid"), base_path=prefix),
                     data_root=tmp_path / "data", workspace_root=tmp_path / "output")
    store = app.state.store
    provider = store.create_provider("fixture", "https://unused.invalid", "fixture-key")
    main = store.add_model(provider["id"], "main", vision=False)
    vision = store.add_model(provider["id"], "vision", vision=True)
    store.set_active_model(main["id"])
    registry = app.state.agent_service.agent_registry
    definition = registry.by_slug(slug)
    registry.save({**definition, "default_vision_model_id": vision["id"]}, definition["id"])
    app.state.identity_store.set_auth_mode("anonymous")
    calls = []

    def visual(llm, messages, image_paths, **kwargs):
        assert llm._model.model_id == vision["id"]
        assert len(image_paths) == 1 and image_paths[0].read_bytes() == image
        calls.append(image_paths[0].name)
        return "controlled image evidence"

    def chat(agent, prompt, images=None):
        assert "image_reasoning" in agent._skills and "read_image" not in agent._skills
        loaded = agent._skills["use_skill"].handler(name=skill)
        assert loaded and not loaded.startswith("错误")
        result = json.loads(agent._skills["fetch_url"].handler(
            url=f"http://images.example.test:{server.server_port}/image", mode="download", path="workspace/url-images/001.bin"))
        assert result["ok"] and result["path"] == "workspace/url-images/001.bin"
        output = agent._skills["image_reasoning"].handler(prompt="Inspect the supplied image", image_paths=[result["path"]])
        agent._skills["submit_results"].handler(text=output, files=[])
        return output

    monkeypatch.setattr(LLMClient, "chat_with_images_stream", visual)
    monkeypatch.setattr(UmekoAgent, "chat", chat)
    try:
        with TestClient(app) as client:
            base = prefix + f"/agent/{slug}/v1/tasks"
            submitted = client.post(base, json={"prompt": f"Inspect http://images.example.test:{server.server_port}/image"})
            assert submitted.status_code == 202, submitted.text
            for _ in range(200):
                task = client.get(base + "/" + submitted.json()["id"]).json()
                if task["status"] in {"completed", "failed", "cancelled"}:
                    break
                time.sleep(.02)
            assert task["status"] == "completed", task
            assert task["reply"] == "controlled image evidence"
        assert calls == ["001.bin"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(2)
