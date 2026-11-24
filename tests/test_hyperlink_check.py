"""Controlled page evidence and builtin dispatch; model judgment is not simulated."""
import asyncio
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading

import httpx
import httpx2
import pytest
from a2a import types as a2a
from a2a.client import ClientConfig, ClientFactory
from mcp.client import Client
from mcp.client.streamable_http import streamable_http_client

from umeko.agent import UmekoAgent
from umeko.host.builtin_agents import HYPERLINK_CHECK_SLUG
from umeko.skills import download


@pytest.fixture
def link_pages(monkeypatch):
    pages = {
        "/missing": (404, "Not found", "Requested page not found."),
        "/gone": (410, "Gone", "Requested page was removed."),
        "/withdrawn": (200, "Document withdrawn", "The requested handbook was removed from publication."),
        "/books": (200, "Bookshelf", "No matching handbook for this product and version."),
        "/manual": (200, "Device handbook 2.0", '<nav>Complete contents: <a href="#setup">Setup</a></nav>'
                    '<main><h1 id="setup">Setup</h1><p>Connect the device.</p></main>'),
        "/login": (200, "Employee sign-in", "Company employees only. A company account is required."),
        "/protected": (401, "Sign-in required", "Please sign in."),
        "/forbidden": (403, "Forbidden", "Access denied."),
        "/dynamic": (200, "Device handbook", '<div id="app"></div><script>renderHandbook()</script>'),
        "/long": (200, "Long handbook", '<p>' + 'Context. ' * 2000 + '</p><h2 id="network">Network setup</h2>'),
    }
    visits = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            visits.append((self.path, self.headers.get("Authorization"), self.headers.get("Cookie")))
            status, title, content = pages[self.path]
            body = f"<html><head><title>{title}</title></head><body>{content}</body></html>".encode()
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    original_addresses = download._addresses
    monkeypatch.setattr(download, "_addresses", lambda host, port, internal_hosts=():
                        ["127.0.0.1"] if host == "links.example.test" and port == server.server_port
                        else original_addresses(host, port, internal_hosts))
    try:
        yield f"http://links.example.test:{server.server_port}", visits
    finally:
        server.shutdown()
        server.server_close()
        thread.join(2)


def test_fetch_preserves_evidence_and_raw_html_for_target_checks(link_pages, tmp_path):
    base, visits = link_pages
    def fetch(route, **kwargs):
        return download.fetch_url(base + route, root=tmp_path, **kwargs)

    for route, status in (("/missing", 404), ("/gone", 410), ("/protected", 401), ("/forbidden", 403)):
        assert f"HTTP {status}" in fetch(route)
    for route, title, evidence in (
        ("/withdrawn", "Document withdrawn", "removed from publication"),
        ("/books", "Bookshelf", "No matching handbook"),
        ("/login", "Employee sign-in", "Company employees only"),
    ):
        page = json.loads(fetch(route))
        assert page["http_status"] == 200 and page["title"] == title
        assert evidence in page["content"] and not page["truncated"]

    manual = json.loads(fetch("/manual#network"))
    assert manual["title"] == "Device handbook 2.0" and "Setup" in manual["content"]
    assert "Complete contents" not in manual["content"]  # Extraction omits navigation.
    raw = json.loads(fetch("/manual#network", path="workspace/manual.html"))
    source = (tmp_path / raw["path"]).read_text(encoding="utf-8")
    assert "Complete contents" in source and 'id="setup"' in source and 'id="network"' not in source
    assert json.loads(fetch("/dynamic"))["content"] == ""  # Not proof of missing content.
    preview = json.loads(fetch("/long#network"))
    assert preview["truncated"] and "Network setup" not in preview["content"]
    full = json.loads(fetch("/long#network", path="workspace/long.html"))
    assert 'id="network"' in (tmp_path / full["path"]).read_text(encoding="utf-8")
    assert all(auth is None and cookie is None for _, auth, cookie in visits)
    assert not any("#" in path for path, _, _ in visits)


@pytest.mark.parametrize("protocol", ["a2a", "mcp"])
@pytest.mark.parametrize("machine_app", ["", "/teams/docs/workbench"], indirect=True)
def test_builtin_hyperlink_agent_protocol_delivery(machine_server, link_pages, monkeypatch, protocol):
    base, app, caller, _ = machine_server
    base = base.rsplit("/agent/", 1)[0] + "/agent/" + HYPERLINK_CHECK_SLUG
    pages, visits = link_pages
    prompt = f"检查链接：{pages}/withdrawn；期望 Device handbook 2.0；受众为外部用户。"

    def chat(agent, request, images=None):
        assert prompt in request
        loaded = agent._skills["use_skill"].handler(name="hyperlink-check")
        assert loaded and not loaded.startswith("错误")
        page = json.loads(agent._skills["fetch_url"].handler(url=pages + "/withdrawn"))
        assert page["http_status"] == 200 and page["title"] == "Document withdrawn"
        # Exercise result plumbing using real fetched evidence, not an LLM correctness claim.
        text = "页面证据：" + page["content"]
        agent._skills["write_file"].handler(path="generate/hyperlink-report.md", content=text)
        agent._skills["submit_results"].handler(text=text, files=[{"path": "generate/hyperlink-report.md"}])
        return text

    monkeypatch.setattr(UmekoAgent, "chat", chat)

    async def check():
        headers = {"Authorization": "Bearer " + caller["token"]}
        if protocol == "mcp":
            async with httpx2.AsyncClient(headers=headers, trust_env=False) as http:
                async with Client(streamable_http_client(base + "/mcp", http_client=http), cache=None) as client:
                    info = await client.call_tool("get_agent_info", {})
                    assert not info.is_error and info.structured_content["name"] == "超链接检查"
                    submitted = await client.call_tool("submit_task", {"prompt": prompt})
                    assert not submitted.is_error, submitted
                    task_id = submitted.structured_content["task_id"]
                    for _ in range(100):
                        result = await client.call_tool("get_task", {"task_id": task_id})
                        assert not result.is_error, result
                        task = result.structured_content
                        if task["status"] in {"completed", "failed", "cancelled"}:
                            break
                        await asyncio.sleep(.05)
                    assert task["status"] == "completed", task
                    results_url = task["results_url"]
        else:
            async with httpx.AsyncClient(headers={**headers, "A2A-Version": "1.0"}, trust_env=False, timeout=15) as http:
                client = await ClientFactory(ClientConfig(httpx_client=http, streaming=False)).create_from_url(base)
                request = a2a.SendMessageRequest(message=a2a.Message(message_id="hyperlink-review",
                    role=a2a.Role.ROLE_USER, parts=[a2a.Part(text=prompt)]))
                events = [event async for event in client.send_message(request)]
                task_id = next(event.task.id for event in events if event.HasField("task"))
                task = await client.get_task(a2a.GetTaskRequest(id=task_id, history_length=0))
                assert task.status.state == a2a.TaskState.TASK_STATE_COMPLETED, task
                results_url = task.metadata["resultsUrl"]
        assert results_url == base + f"/v1/tasks/{task_id}/results"
        async with httpx.AsyncClient(headers=headers, trust_env=False) as http:
            result = (await http.get(results_url)).json()
            assert result["ready"] and "removed from publication" in result["text"]
            file = result["files"][0]
            assert file["path"] == "generate/hyperlink-report.md"
            report = await http.get(base + f"/v1/tasks/{task_id}/files/{file['file_id']}/content")
            assert report.status_code == 200 and "removed from publication" in report.text
        assert visits == [("/withdrawn", None, None)]

    asyncio.run(check())
