import asyncio
import base64
import json
import textwrap

import httpx
import httpx2
import pytest
from a2a import types as a2a
from a2a.client import ClientConfig, ClientFactory
from a2a.utils.errors import InvalidParamsError
from google.protobuf.json_format import ParseDict
from google.protobuf.struct_pb2 import Value
from mcp.client import Client
from mcp.client.streamable_http import streamable_http_client

from umeko.agent import UmekoAgent
from umeko.host.task_input import TaskInputError, validate_prompt
from umeko.host.tasks import validate_input


ENCODED = base64.b64encode(bytes(range(256)) * 32).decode()
PNG = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"synthetic image header" * 8).decode()
BAD_TEXT = [
    "检查图片 data:image/png;base64," + PNG,
    "检查图片 " + PNG,
    "检查文档 " + ENCODED,
    "\n".join(textwrap.wrap(ENCODED, 64)),
    "\\n".join(textwrap.wrap(ENCODED, 64)),
    base64.urlsafe_b64encode(bytes(range(256)) * 32).decode(),
    json.dumps({"prompt": "check", "files": [{"name": "input.bin", "content_base64": ENCODED[:128]}]}),
]


@pytest.mark.parametrize("prompt", BAD_TEXT, ids=["data-url", "image-bytes", "file-bytes", "wrapped", "escaped-newlines", "urlsafe", "attachment-json"])
def test_encoded_file_text_is_rejected_without_reflection(prompt):
    with pytest.raises(TaskInputError) as caught:
        validate_input({"prompt": prompt})
    detail = caught.value.detail()
    assert detail["code"] == "FILE_CONTENT_IN_TEXT"
    assert detail["retryable"] is False and detail["task_created"] is False
    assert detail["next_action"] == "fix_request_or_ask_user"
    assert "raw" in detail["file_transport"]["a2a"]
    assert "content_base64" in detail["file_transport"]["mcp_rest"]
    assert PNG not in str(detail) and ENCODED[:128] not in str(detail)


@pytest.mark.parametrize("prompt", [
    "解释 base64，例子 aGVsbG8=；以及 data:image/png;base64,... 的结构。",
    "比较以下代码：\n```python\nprint('hello world')\n```",
    "普通需求正文和代码片段。\n" * 5000,
    '请解释 files: [{"name":"input.png", "content_base64":"<base64 bytes>"}]',
    "x" * 4095,
], ids=["base64-discussion", "code", "long-prose", "schema-example", "short-run"])
def test_normal_text_and_short_encoding_examples_remain_valid(prompt):
    validate_prompt(prompt)


def test_encoding_block_boundary_and_correct_attachment():
    validate_prompt("x" * 4095)
    with pytest.raises(TaskInputError):
        validate_prompt("x" * 4096)
    payload, files = validate_input({"prompt": "处理附件", "files": [{"name": "without-extension", "content_base64": ENCODED}]})
    assert files == [bytes(range(256)) * 32]
    assert payload["files"][0]["size"] == len(files[0])
    assert "content_base64" not in payload["files"][0]


def _assert_no_task(app):
    with app.state.store.connect() as db:
        for table in ("service_tasks", "service_task_events", "agent_sessions", "messages"):
            assert db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
    assert not list(app.state.task_service.root.iterdir())
    assert not app.state.agent_service.runs and not app.state.agent_service.sessions


def _no_model(*args, **kwargs):
    pytest.fail("Rejected input must not reach a model")


@pytest.mark.parametrize("machine_app", ["", "/teams/docs/workbench"], indirect=True)
def test_rest_rejects_before_task_creation_with_small_errors(machine_server, monkeypatch, caplog):
    base, app, caller, _ = machine_server
    monkeypatch.setattr(UmekoAgent, "chat", _no_model)
    with httpx.Client(headers={"Authorization": "Bearer " + caller["token"]}, trust_env=False) as http:
        for prompt in BAD_TEXT + ["x" * 200_001]:
            response = http.post(base + "/v1/tasks", json={"prompt": prompt})
            assert response.status_code == (422 if len(prompt) > 200_000 else 400), response.text
            assert response.json()["detail"]["retryable"] is False
            assert len(response.content) < 4000
            assert ENCODED[:128] not in response.text
        # Pydantic's default error includes the rejected value. Our machine
        # validation handler must also redact malformed schema inputs.
        response = http.post(base + "/v1/tasks", json={"prompt": "检查", "files": [{"name": "x", "content": ENCODED}]})
        assert response.status_code == 422
        assert response.json()["detail"]["code"] == "INVALID_TASK_INPUT"
        assert ENCODED[:128] not in response.text
    _assert_no_task(app)
    assert ENCODED[:128] not in caplog.text


@pytest.mark.parametrize("machine_app", ["", "/teams/docs/workbench"], indirect=True)
def test_mcp_rejection_and_immediate_workspace_receipt(machine_server, monkeypatch):
    base, app, caller, _ = machine_server
    async def check():
        async with httpx2.AsyncClient(headers={"Authorization": "Bearer " + caller["token"]}, trust_env=False) as http:
            async with Client(streamable_http_client(base + "/mcp", http_client=http), cache=None) as client:
                submit = next(tool for tool in (await client.list_tools()).tools if tool.name == "submit_task")
                assert '"content_base64"' in json.dumps(submit.input_schema)
                assert '"name"' in json.dumps(submit.input_schema)
                with monkeypatch.context() as guard:
                    guard.setattr(UmekoAgent, "chat", _no_model)
                    for prompt in BAD_TEXT:
                        result = await client.call_tool("submit_task", {"prompt": prompt})
                        assert result.is_error
                        error = result.structured_content["error"]
                        assert error["code"] == "FILE_CONTENT_IN_TEXT" and error["retryable"] is False
                        assert len(str(result.content)) < 4000
                        assert ENCODED[:128] not in str(result.content)
                    _assert_no_task(app)
                # Pause scheduling to prove the URL exists in the submit receipt,
                # before a session/run or model result has been produced.
                app.state.task_service.stop()
                result = await client.call_tool("submit_task", {"prompt": "正常任务", "files": [
                    {"name": "input.bin", "content_base64": ENCODED}]})
                assert not result.is_error
                receipt = result.structured_content
                assert receipt["status"] == "queued" and receipt["reply"] is None
                workspace = receipt["workspace_url"]
                assert workspace.startswith(base.rsplit("/agent/", 1)[0] + "/TMP/")
                assert "立即" in receipt["workspace_hint"]
                assert workspace in result.content[-1].text and "请立即向用户展示" in result.content[-1].text
                async with httpx.AsyncClient(trust_env=False) as browser:
                    assert (await browser.get(workspace)).status_code == 200
    asyncio.run(check())


@pytest.mark.parametrize("streaming", [False, True])
@pytest.mark.parametrize("machine_app", ["", "/teams/docs/workbench"], indirect=True)
def test_a2a_rejects_text_and_data_file_encodings(machine_server, monkeypatch, streaming):
    base, app, caller, _ = machine_server
    monkeypatch.setattr(UmekoAgent, "chat", _no_model)
    async def check():
        headers = {"Authorization": "Bearer " + caller["token"], "A2A-Version": "1.0"}
        async with httpx.AsyncClient(headers=headers, trust_env=False) as http:
            client = await ClientFactory(ClientConfig(httpx_client=http, streaming=streaming)).create_from_url(base)
            parts_cases = [[a2a.Part(text=prompt)] for prompt in BAD_TEXT]
            parts_cases += [
                [a2a.Part(text="check"), a2a.Part(data=ParseDict({"raw": ENCODED}, Value()))],
                [a2a.Part(text=ENCODED[i:i+64]) for i in range(0, 8192, 64)],
                [a2a.Part(text="x" * 110_000), a2a.Part(text="x" * 110_000)],
            ]
            for i, parts in enumerate(parts_cases):
                request = a2a.SendMessageRequest(message=a2a.Message(
                    message_id=f"rejected-{i}", role=a2a.Role.ROLE_USER, parts=parts))
                with pytest.raises(InvalidParamsError) as caught:
                    _ = [event async for event in client.send_message(request)]
                assert caught.value.data["retryable"] is False
                assert caught.value.data["task_created"] is False
                assert len(str(caught.value)) < 4000 and ENCODED[:128] not in str(caught.value)
            _assert_no_task(app)
    asyncio.run(check())


@pytest.mark.parametrize("machine_app", ["", "/teams/docs/workbench"], indirect=True)
def test_a2a_immediate_workspace_receipt(machine_server):
    base, app, caller, _ = machine_server
    app.state.task_service.stop()
    async def check():
        async with httpx.AsyncClient(headers={"Authorization": "Bearer " + caller["token"], "A2A-Version": "1.0"}, trust_env=False) as http:
            client = await ClientFactory(ClientConfig(httpx_client=http, streaming=False)).create_from_url(base)
            request = a2a.SendMessageRequest(message=a2a.Message(message_id="queued-workspace", role=a2a.Role.ROLE_USER,
                parts=[a2a.Part(text="检查附件"), a2a.Part(raw=b"file bytes", filename="input.bin")]),
                configuration=a2a.SendMessageConfiguration(return_immediately=True))
            events = [event async for event in client.send_message(request)]
            task = events[0].task
            assert task.status.state == a2a.TaskState.TASK_STATE_SUBMITTED
            workspace = task.metadata["workspaceUrl"]
            assert workspace.startswith(base.rsplit("/agent/", 1)[0] + "/TMP/")
            assert workspace in task.status.message.parts[0].text
            assert "立即" in task.status.message.parts[0].text
            assert (await http.get(workspace)).status_code == 200
    asyncio.run(check())
