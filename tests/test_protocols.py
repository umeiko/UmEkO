import asyncio
import base64

import httpx
import httpx2
import pytest
from a2a import types as a2a
from a2a.client import ClientFactory, ClientConfig
from mcp.client import Client
from mcp.client.streamable_http import streamable_http_client


@pytest.mark.parametrize("mode", ["auto", "legacy"])
@pytest.mark.parametrize("machine_app", ["", "/doc-master/consistency/image-text"], indirect=True)
def test_mcp_official_client(machine_server, mode):
    base, app, a, b = machine_server
    async def check():
        async with httpx2.AsyncClient(headers={"Authorization": "Bearer " + a["token"]}, trust_env=False) as http:
            async with Client(streamable_http_client(base + "/mcp", http_client=http), mode=mode, cache=None) as client:
                tools = await client.list_tools()
                assert {"submit_task","get_task","cancel_task","read_artifact"} <= {t.name for t in tools.tools}
                result = await client.call_tool("submit_task", {"prompt":"SDK test","files":[{"name":"a.txt","content_base64":base64.b64encode(b"SDK attachment").decode()}]})
                assert not result.is_error, result
                task = result.structured_content
                for _ in range(100):
                    result = await client.call_tool("get_task", {"task_id":task["id"]})
                    assert not result.is_error, result
                    task = result.structured_content
                    if task["status"] in {"completed","failed","cancelled"}:
                        break
                    await asyncio.sleep(.05)
                assert task["status"] == "completed", task
                artifact = task["artifacts"][0]
                result = await client.call_tool("read_artifact", {"task_id":task["id"],"artifact_id":artifact["id"]})
                assert "SDK attachment" in result.structured_content["text"]
                resource = await client.read_resource(artifact["resource_uri"])
                assert base64.b64decode(resource.contents[0].blob).decode().endswith("SDK attachment")
                hold = await client.call_tool("submit_task", {"prompt":"hold MCP"})
                await client.call_tool("cancel_task", {"task_id":hold.structured_content["id"]})
        async with httpx.AsyncClient(headers={"Authorization":"Bearer " + b["token"]},trust_env=False) as other:
            assert (await other.get(base+'/v1/tasks/'+task['id'])).status_code == 404
    asyncio.run(check())


@pytest.mark.parametrize("streaming", [False, True])
@pytest.mark.parametrize("machine_app", ["", "/doc-master/consistency/image-text"], indirect=True)
def test_a2a_official_client(machine_server, streaming):
    base, app, a, b = machine_server
    async def check():
        async with httpx.AsyncClient(headers={"Authorization":"Bearer "+a["token"], "A2A-Version":"1.0"}, trust_env=False, timeout=15) as http:
            client = await ClientFactory(ClientConfig(httpx_client=http,streaming=streaming)).create_from_url(base)
            request = a2a.SendMessageRequest(message=a2a.Message(message_id="sdk-message",role=a2a.Role.ROLE_USER,
                parts=[a2a.Part(text="A2A SDK"),a2a.Part(raw=b"A2A attachment",filename="input.txt",media_type="text/plain")]))
            events = [event async for event in client.send_message(request)]
            assert events
            task_id = next(e.task.id for e in events if e.HasField("task"))
            task = await client.get_task(a2a.GetTaskRequest(id=task_id,history_length=0))
            assert task.status.state == a2a.TaskState.TASK_STATE_COMPLETED, task
            assert not task.history
            assert "A2A attachment" in task.artifacts[0].parts[0].text
            again = [e async for e in client.send_message(request)]
            assert next(e.task.id for e in again if e.HasField("task")) == task_id
            assert len(app.state.task_service.list(app.state.identity_store.authenticate(a["token"]))["tasks"]) == 1
            assert (await http.get(task.artifacts[1].parts[0].url)).status_code == 200
            listing = await client.list_tasks(a2a.ListTasksRequest(status=a2a.TaskState.TASK_STATE_COMPLETED, history_length=0))
            assert listing.total_size == 1 and not listing.tasks[0].history
            empty = await client.list_tasks(a2a.ListTasksRequest(status=a2a.TaskState.TASK_STATE_INPUT_REQUIRED))
            assert empty.total_size == 0
            future_request = a2a.ListTasksRequest()
            future_request.status_timestamp_after.FromJsonString("2099-01-01T00:00:00Z")
            future = await client.list_tasks(future_request)
            assert future.total_size == 0
        async with httpx.AsyncClient(headers={"Authorization":"Bearer "+b["token"], "A2A-Version":"1.0"},trust_env=False) as http:
            client = await ClientFactory(ClientConfig(httpx_client=http,streaming=False)).create_from_url(base)
            with pytest.raises(Exception):
                await client.get_task(a2a.GetTaskRequest(id=task_id))
    asyncio.run(check())


def test_a2a_subscribe_cancel_and_streamed_body_limits(machine_server):
    base, app, a, _ = machine_server
    async def check():
        headers = {"Authorization": "Bearer " + a["token"], "A2A-Version": "1.0"}
        async with httpx.AsyncClient(headers=headers, trust_env=False, timeout=15) as http:
            sender = await ClientFactory(ClientConfig(httpx_client=http, streaming=False)).create_from_url(base)
            request = a2a.SendMessageRequest(message=a2a.Message(message_id="subscription-test",
                role=a2a.Role.ROLE_USER, parts=[a2a.Part(text="hold subscription")]),
                configuration=a2a.SendMessageConfiguration(return_immediately=True))
            events = [e async for e in sender.send_message(request)]
            task_id = events[0].task.id
            subscriber = await ClientFactory(ClientConfig(httpx_client=http, streaming=True)).create_from_url(base)
            stream = subscriber.subscribe(a2a.SubscribeToTaskRequest(id=task_id))
            initial = await anext(stream)
            assert initial.task.id == task_id
            await sender.cancel_task(a2a.CancelTaskRequest(id=task_id))
            remaining = [e async for e in stream]
            assert remaining[-1].status_update.status.state == a2a.TaskState.TASK_STATE_CANCELED
            async def large_body():
                for _ in range(31):
                    yield b"x" * 1024 * 1024
            assert (await http.post(base + "/v1/tasks", content=large_body())).status_code == 413
            async def large_form():
                yield b"x" * (16 * 1024 + 1)
            assert (await http.post(base + "/oauth/token", content=large_form())).status_code == 413
    asyncio.run(check())
