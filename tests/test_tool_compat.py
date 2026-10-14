import asyncio
from copy import deepcopy
import json
from types import SimpleNamespace

import httpx
import httpx2
from openai import BadRequestError, OpenAI
from a2a import types as a2a
from a2a.client import ClientConfig, ClientFactory
from mcp.client import Client
from mcp.client.streamable_http import streamable_http_client
import pytest

from umeko.agent import UmekoAgent
from umeko.cancellation import OperationCancelled
from umeko.config import ModelConfig
from umeko.llm.client import LLMClient
from umeko.llm.tool_compat import parse_text_message, text_messages


REAL_CHAT = UmekoAgent.chat
ERROR = 'litellm.BadRequestError: OpenAIException - "auto" tool choice requires --enable-auto-tool-choice and --tool-call-parser to be set.'
TOOLS = [{"type": "function", "function": {"name": "list_dir", "description": "List files",
          "parameters": {"type": "object", "properties": {"directory": {"type": "string"}}, "required": ["directory"]}}}]
MESSAGES = [{"role": "system", "content": "Keep existing instructions"}, {"role": "user", "content": "Inspect files"}]


def model_response(text, stream=False):
    if stream:
        chunks = [{"id": "fixture", "object": "chat.completion.chunk", "created": 0, "model": "fixture",
                   "choices": [{"index": 0, "delta": {"content": text[:len(text)//2]}}]},
                  {"id": "fixture", "object": "chat.completion.chunk", "created": 0, "model": "fixture",
                   "choices": [{"index": 0, "delta": {"content": text[len(text)//2:]}, "finish_reason": "stop"}]}]
        body = "".join("data: " + json.dumps(c) + "\n\n" for c in chunks) + "data: [DONE]\n\n"
        return httpx.Response(200, text=body, headers={"Content-Type": "text/event-stream"})
    return httpx.Response(200, json={"id": "fixture", "object": "chat.completion", "created": 0, "model": "fixture",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": text}, "finish_reason": "stop"}]})


@pytest.fixture
def sdk_factory():
    clients = []
    def make(handler):
        client = OpenAI(api_key="fixture-only", base_url="https://unused.invalid/v1", max_retries=0,
                        http_client=httpx.Client(transport=httpx.MockTransport(handler), trust_env=False))
        clients.append(client)
        return client
    yield make
    for client in clients:
        client.close()


@pytest.mark.parametrize("streaming", [False, True])
def test_400_adaptation_is_per_request_and_preserves_tool_loop(sdk_factory, monkeypatch, streaming):
    client = LLMClient(ModelConfig("fixture", "fixture-only", "https://unused.invalid", max_concurrent_requests=1))
    requests = []
    def handle(request):
        assert client._call_queue.snapshot()["active"] == 1
        body = json.loads(request.content)
        requests.append(body)
        if body.get("tools"):
            return httpx.Response(400, json={"error": {"message": ERROR, "code": "400"}})
        assert "tool_choice" not in body
        assert all(m["role"] != "tool" and "tool_calls" not in m and "reasoning_content" not in m for m in body["messages"])
        answer = {"final": "Files inspected"} if any("工具返回" in (m.get("content") or "") for m in body["messages"]) else {
            "tool_calls": [{"name": "list_dir", "arguments": {"directory": "attachments"}}]}
        return model_response(json.dumps(answer), body["stream"])
    monkeypatch.setattr(client, "_get_client", lambda: sdk_factory(handle))
    deltas = []
    history = deepcopy(MESSAGES)
    def call():
        return (client.chat_with_tools_stream(history, TOOLS, deltas.append) if streaming
                else client.chat_with_tools(history, TOOLS))
    first = call()
    assert first.tool_calls[0].function.name == "list_dir"
    history.extend([{"role": "assistant", "content": "", "reasoning_content": "prior reasoning",
                     "tool_calls": [first.tool_calls[0].model_dump()]},
                    {"role": "tool", "tool_call_id": first.tool_calls[0].id, "content": "sample.png"}])
    before = deepcopy(history)
    final = call()
    assert final.content == "Files inspected" and not final.tool_calls
    assert history == before
    assert [bool(r.get("tools")) for r in requests] == [True, False, True, False]
    assert all("Keep existing instructions" in r["messages"][0]["content"] for r in requests)
    assert deltas == (["Files inspected"] if streaming else [])
    assert client._call_queue.snapshot()["active"] == 0


def test_supported_native_requests_are_unchanged(sdk_factory, monkeypatch):
    client = LLMClient(ModelConfig("native", "fixture-only", "https://unused.invalid"))
    def handle(request):
        body = json.loads(request.content)
        assert body["messages"] == MESSAGES and body["tools"] == TOOLS
        assert "tool_choice" not in body
        return model_response("Native answer", body["stream"])
    sdk = sdk_factory(handle)
    monkeypatch.setattr(client, "_get_client", lambda: sdk)
    assert client.chat_with_tools(MESSAGES, TOOLS).content == "Native answer"
    chunks = []
    assert client.chat_with_tools_stream(MESSAGES, TOOLS, chunks.append).content == "Native answer"
    assert "".join(chunks) == "Native answer"


@pytest.mark.parametrize("status,message", [(400, "context length exceeded"), (400, "Invalid image data"),
                                             (401, ERROR), (429, ERROR), (500, ERROR)])
def test_unrelated_errors_do_not_use_tool_compatibility(sdk_factory, monkeypatch, status, message):
    client = LLMClient(ModelConfig("fixture", "fixture-only", "https://unused.invalid"))
    requests = []
    def handle(request):
        body = json.loads(request.content)
        requests.append(body)
        return httpx.Response(status, json={"error": {"message": message}})
    sdk = sdk_factory(handle)
    monkeypatch.setattr(client, "_get_client", lambda: sdk)
    with pytest.raises(Exception):
        client.chat_with_tools(MESSAGES, TOOLS)
    assert len(requests) == 1 and requests[0]["tools"] == TOOLS


def test_invalid_json_and_unknown_tools_have_one_bounded_repair(sdk_factory, monkeypatch):
    client = LLMClient(ModelConfig("fixture", "fixture-only", "https://unused.invalid"))
    requests = []
    def handle(request):
        body = json.loads(request.content)
        requests.append(body)
        if body.get("tools"):
            return httpx.Response(400, json={"error": {"message": ERROR}})
        return model_response('{"tool_calls":[{"name":"run_command","arguments":{}}]}')
    sdk = sdk_factory(handle)
    monkeypatch.setattr(client, "_get_client", lambda: sdk)
    with pytest.raises(ValueError, match="已纠正一次"):
        client.chat_with_tools(MESSAGES, TOOLS)
    assert len(requests) == 3


@pytest.mark.parametrize("data", ['Text with {"tool_calls": []}', '{"final":""}',
    '{"tool_calls":[{"name":"list_dir","arguments":"bad"}]}',
    '{"tool_calls":[{"name":"run_command","arguments":{}}]}',
    '{"final":"success","tool_calls":[]}', '{"final":"done"}'])
def test_envelope_and_forced_tool_choices_are_enforced(data):
    with pytest.raises(ValueError):
        parse_text_message(SimpleNamespace(content=data), TOOLS, "required")
    with pytest.raises(ValueError):
        parse_text_message(SimpleNamespace(content='{"tool_calls":[{"name":"list_dir","arguments":{}}]}'), TOOLS, "none")


def test_malformed_old_arguments_and_multimodal_parts_survive_conversion():
    image = {"type": "image_url", "image_url": {"url": "data:image/png;base64,fixture"}}
    history = MESSAGES + [{"role": "assistant", "tool_calls": [{"function": {"name": "list_dir", "arguments": "invalid"}}]},
                          {"role": "user", "content": [{"type": "text", "text": "Inspect image"}, image]}]
    before = deepcopy(history)
    converted = text_messages(history, TOOLS)
    assert converted[-1]["content"] == history[-1]["content"] and history == before


def test_cancellation_does_not_retry_compatibility(sdk_factory, monkeypatch):
    client = LLMClient(ModelConfig("fixture", "fixture-only", "https://unused.invalid"))
    cancelled, requests = [], []
    def handle(request):
        requests.append(request)
        cancelled.append(True)
        return httpx.Response(400, json={"error": {"message": ERROR}})
    sdk = sdk_factory(handle)
    monkeypatch.setattr(client, "_get_client", lambda: sdk)
    with pytest.raises(OperationCancelled):
        client.chat_with_tools(MESSAGES, TOOLS, should_cancel=lambda: bool(cancelled))
    assert len(requests) == 1


@pytest.mark.parametrize("machine_app", ["", "/doc-master/consistency/image-text"], indirect=True)
@pytest.mark.parametrize("protocol", ["mcp", "a2a"])
def test_machine_protocol_runs_real_tools_after_upstream_400(machine_server, monkeypatch, sdk_factory, protocol):
    base, app, account, _ = machine_server
    monkeypatch.setattr(UmekoAgent, "chat", REAL_CHAT)
    requests = []
    def handle(request):
        body = json.loads(request.content)
        requests.append(body)
        if body.get("tools"):
            return httpx.Response(400, json={"error": {"message": ERROR}})
        completed = sum(m["role"] == "user" and "[工具返回" in (m.get("content") or "") for m in body["messages"])
        result = {"tool_calls": [{"name": "list_dir", "arguments": {"directory": "attachments"}}]} if not completed else (
            {"tool_calls": [{"name": "write_file", "arguments": {"path": "report.txt", "content": "COMPAT_REPORT"}}]}
            if completed == 1 else {"tool_calls": [{"name": "submit_results", "arguments": {
                "text": "COMPAT_COMPLETE", "files": [{"path": "generate/report.txt"}]}}]})
        return model_response(json.dumps(result), body["stream"])
    sdk = sdk_factory(handle)
    monkeypatch.setattr(LLMClient, "_get_client", lambda self: sdk)
    async def check():
        headers = {"Authorization": "Bearer " + account["token"]}
        if protocol == "mcp":
            async with httpx2.AsyncClient(headers=headers, trust_env=False) as http:
                async with Client(streamable_http_client(base + "/mcp", http_client=http), cache=None) as client:
                    result = await client.call_tool("submit_task", {"prompt": "Inspect files and write report"})
                    assert not result.is_error
                    task_id = result.structured_content["id"]
        else:
            async with httpx.AsyncClient(headers={**headers, "A2A-Version": "1.0"}, trust_env=False) as http:
                client = await ClientFactory(ClientConfig(httpx_client=http, streaming=False)).create_from_url(base)
                events = [e async for e in client.send_message(a2a.SendMessageRequest(message=a2a.Message(
                    message_id="compatibility-test", role=a2a.Role.ROLE_USER, parts=[a2a.Part(text="Inspect files and write report")]),
                    configuration=a2a.SendMessageConfiguration(return_immediately=True)))]
                task_id = next(e.task.id for e in events if e.HasField("task"))
        async with httpx.AsyncClient(headers=headers, trust_env=False) as http:
            for _ in range(100):
                task = (await http.get(base + "/v1/tasks/" + task_id)).json()
                if task["status"] in {"completed", "failed", "cancelled"}:
                    break
                await asyncio.sleep(.05)
            assert task["status"] == "completed", task
            assert task["reply"] == "COMPAT_COMPLETE"
            results = (await http.get(base + "/v1/tasks/" + task_id + "/results")).json()
            assert results["ready"] and results["text"] == "COMPAT_COMPLETE"
            assert [f["path"] for f in results["files"]] == ["generate/report.txt"]
            file_id = results["files"][0]["file_id"]
            assert (await http.get(base + f"/v1/tasks/{task_id}/files/{file_id}/content")).text == "COMPAT_REPORT"
            artifact = next(a for a in task["artifacts"] if a["name"] == "generate/report.txt")
            assert (await http.get(artifact["download_url"])).text == "COMPAT_REPORT"
            assert task["workspace_url"].startswith(base.rsplit("/agent/", 1)[0] + "/TMP/")
            info = (await http.get(task["workspace_url"] + "/v1/temporary")).json()
            tools = (await http.get(task["workspace_url"] + "/v1/sessions/" + info["session_id"] + "/tool-events")).json()
            assert [e["name"] for e in tools] == ["list_dir", "write_file", "submit_results"]
    asyncio.run(check())
    assert [bool(r.get("tools")) for r in requests] == [True, False] * 3
