"""Exercise the new agent's dispatch and real URL tool with controlled responses."""
import asyncio
import base64
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
from umeko.host.builtin_agents import DOCUMENT_CHECK_SLUG
from umeko.skills import download


@pytest.mark.parametrize("protocol", ["a2a", "mcp"])
@pytest.mark.parametrize("machine_app", ["", "/teams/docs/workbench"], indirect=True)
def test_document_agent_uses_download_tool_and_delivers_results(machine_server, monkeypatch, protocol):
    base, app, caller, _ = machine_server
    base = base.rsplit("/agent/", 1)[0] + "/agent/" + DOCUMENT_CHECK_SLUG
    visits = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            visits.append(self.path)
            status = {"/guide": 200, "/missing": 404, "/protected": 401}[self.path]
            body = b"<html><title>Fixture guide</title><p>Input and output</p></html>" if status == 200 else b""
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
                        ["127.0.0.1"] if host == "docs.example.test" and port == server.server_port
                        else original_addresses(host, port, internal_hosts))
    urls = [f"http://docs.example.test:{server.server_port}{path}" for path in ("/guide", "/missing", "/protected")]
    document = "# Review fixture\n" + "\n".join(urls)

    def chat(agent, prompt, images=None):
        loaded = agent._skills["use_skill"].handler(name="document-check")
        assert loaded and not loaded.startswith("错误")
        assert agent._skills["read_document"].handler(path="attachments/manual.md") == document
        valid = json.loads(agent._skills["fetch_url"].handler(url=urls[0]))
        assert valid["ok"] and valid["title"] == "Fixture guide"
        assert valid["content"] == "Input and output" and valid["files"] == []
        missing = agent._skills["fetch_url"].handler(url=urls[1], path="workspace/link-check/002.html")
        protected = agent._skills["fetch_url"].handler(url=urls[2], path="workspace/link-check/003.html")
        assert "HTTP 404" in missing and "HTTP 401" in protected
        text = "已读取文档并核验三个链接。404 未找到；401 需要授权，内容未验证。"
        agent._skills["write_file"].handler(path="generate/document-review.md", content=text)
        agent._skills["submit_results"].handler(text=text, files=[{"path": "generate/document-review.md"}])
        return text

    monkeypatch.setattr(UmekoAgent, "chat", chat)

    async def check():
        headers = {"Authorization": "Bearer " + caller["token"]}
        encoded = base64.b64encode(document.encode()).decode()
        if protocol == "mcp":
            async with httpx2.AsyncClient(headers=headers, trust_env=False) as http:
                async with Client(streamable_http_client(base + "/mcp", http_client=http), cache=None) as client:
                    submitted = await client.call_tool("submit_task", {"prompt": "检查附件文档及链接", "files": [
                        {"name": "manual.md", "content_base64": encoded}]})
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
                request = a2a.SendMessageRequest(message=a2a.Message(message_id="document-review",
                    role=a2a.Role.ROLE_USER, parts=[a2a.Part(text="检查附件文档及链接"),
                        a2a.Part(raw=document.encode(), filename="manual.md", media_type="text/markdown")]))
                events = [event async for event in client.send_message(request)]
                task_id = next(event.task.id for event in events if event.HasField("task"))
                task = await client.get_task(a2a.GetTaskRequest(id=task_id, history_length=0))
                assert task.status.state == a2a.TaskState.TASK_STATE_COMPLETED, task
                results_url = task.metadata["resultsUrl"]
                assert "内容未验证" in task.status.message.parts[0].text
        assert results_url == base + f"/v1/tasks/{task_id}/results"
        async with httpx.AsyncClient(headers=headers, trust_env=False) as http:
            result = (await http.get(results_url)).json()
            assert result["ready"] and "内容未验证" in result["text"]
            assert [file["path"] for file in result["files"]] == ["generate/document-review.md"]
        assert visits == ["/guide", "/missing", "/protected"]

    try:
        asyncio.run(check())
    finally:
        server.shutdown()
        server.server_close()
        thread.join(2)
