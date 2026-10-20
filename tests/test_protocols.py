import asyncio
import base64
import threading

import httpx
import httpx2
import pytest
from a2a import types as a2a
from a2a.client import ClientFactory, ClientConfig
from google.protobuf.json_format import MessageToDict
from mcp.client import Client
from mcp.client.streamable_http import streamable_http_client

from umeko.agent import UmekoAgent


@pytest.mark.parametrize("mode", ["auto", "legacy"])
@pytest.mark.parametrize("machine_app", ["", "/doc-master/consistency/image-text"], indirect=True)
def test_mcp_official_client(machine_server, mode):
    base, app, a, b = machine_server
    async def check():
        async with httpx2.AsyncClient(headers={"Authorization": "Bearer " + a["token"]}, trust_env=False) as http:
            async with Client(streamable_http_client(base + "/mcp", http_client=http), mode=mode, cache=None) as client:
                tools = await client.list_tools()
                assert {t.name for t in tools.tools} == {
                    "get_agent_info", "submit_task", "get_task", "cancel_task",
                    "list_file", "download_file", "read_results",
                }
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
                assert task["workspace_url"].startswith(base.rsplit('/agent/', 1)[0] + '/TMP/')
                async with httpx.AsyncClient(trust_env=False) as browser:
                    assert (await browser.get(task["workspace_url"])).status_code == 200
                    info = await browser.get(task["workspace_url"] + '/v1/temporary')
                    assert info.status_code == 200 and info.json()['state'] == 'ready'
                artifact = task["artifacts"][0]
                assert artifact["download_url"].startswith(base + "/v1/tasks/")
                info = await client.call_tool("get_agent_info", {})
                assert info.structured_content["supportedInterfaces"][0]["url"] == base + "/a2a"
                result = await client.call_tool("read_results", {"task_id":task["id"]})
                assert "SDK attachment" in result.structured_content["text"]
                assert result.structured_content["ready"]
                file_id = result.structured_content["files"][0]["file_id"]
                download = await client.call_tool("download_file", {"task_id": task["id"], "file_id": file_id})
                assert download.structured_content["download_url"].startswith(base + "/v1/tasks/")
                assert (await client.list_resource_templates()).resource_templates == []
                hold = await client.call_tool("submit_task", {"prompt":"hold MCP"})
                await client.call_tool("cancel_task", {"task_id":hold.structured_content["id"]})
        async with httpx.AsyncClient(headers={"Authorization":"Bearer " + b["token"]},trust_env=False) as other:
            assert (await other.get(base+'/v1/tasks/'+task['id'])).status_code == 404
        async with httpx.AsyncClient(headers={"Authorization":"Bearer " + a["token"]},trust_env=False) as http:
            assert (await http.get(artifact["download_url"])).status_code == 200
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
            results_url = base + f"/v1/tasks/{task_id}/results"
            for event in events:
                if event.HasField("task"):
                    assert event.task.metadata["resultsUrl"] == results_url
                    assert "artifacts" in event.task.metadata["resultsHint"]
            task = await client.get_task(a2a.GetTaskRequest(id=task_id,history_length=0))
            assert task.status.state == a2a.TaskState.TASK_STATE_COMPLETED, task
            assert task.metadata["resultsUrl"] == results_url
            results = (await http.get(results_url)).json()
            assert results["ready"] and results["text"] == task.artifacts[0].parts[0].text
            assert results["files"] == MessageToDict(task.artifacts[0].parts[1].data)["files"]
            assert task.status.message.parts[0].text == results["text"]
            assert task.metadata["workspaceUrl"] not in task.status.message.parts[0].text
            assert "直接交付结果" in task.metadata["workspaceHint"]
            for event in events:
                if event.HasField("status_update") and event.status_update.status.state == a2a.TaskState.TASK_STATE_COMPLETED:
                    assert event.status_update.status.message.parts[0].text == results["text"]
            workspace = task.metadata['workspaceUrl']
            assert workspace.startswith(base.rsplit('/agent/', 1)[0] + '/TMP/')
            async with httpx.AsyncClient(trust_env=False) as browser:
                assert (await browser.get(workspace + '/v1/temporary')).json()['state'] == 'ready'
            assert not task.history
            assert "A2A attachment" in task.artifacts[0].parts[0].text
            assert MessageToDict(task.artifacts[0].parts[1].data)["files"][0]["path"] == "generate/report.txt"
            again = [e async for e in client.send_message(request)]
            assert next(e.task.id for e in again if e.HasField("task")) == task_id
            assert len(app.state.task_service.list({**app.state.identity_store.authenticate(a["token"]), "agent_id": app.state.fixture_agent["id"]})["tasks"]) == 1
            assert task.artifacts[1].parts[0].url.startswith(base + "/v1/tasks/")
            assert (await http.get(task.artifacts[1].parts[0].url)).status_code == 200
            with pytest.raises(Exception, match="任务列表"):
                await client.list_tasks(a2a.ListTasksRequest())
        async with httpx.AsyncClient(headers={"Authorization":"Bearer "+b["token"], "A2A-Version":"1.0"},trust_env=False) as http:
            assert (await http.get(results_url)).status_code == 404
            client = await ClientFactory(ClientConfig(httpx_client=http,streaming=False)).create_from_url(base)
            with pytest.raises(Exception):
                await client.get_task(a2a.GetTaskRequest(id=task_id))
    asyncio.run(check())


@pytest.mark.parametrize("auth_mode", ["required", "anonymous"])
@pytest.mark.parametrize("machine_app", ["", "/teams/docs/umeko"], indirect=True)
def test_a2a_results_discovery_receipt_and_workspace_continuation(machine_server, monkeypatch, auth_mode):
    base, app, account, _ = machine_server
    app.state.identity_store.set_auth_mode(auth_mode)
    release = threading.Event()
    fixture_chat = UmekoAgent.chat

    def delayed_chat(agent, prompt, images=None):
        assert release.wait(10), "Fixture was not released"
        return fixture_chat(agent, prompt, images)

    monkeypatch.setattr(UmekoAgent, "chat", delayed_chat)

    async def check():
        headers = {"A2A-Version": "1.0"}
        if auth_mode == "required":
            headers["Authorization"] = "Bearer " + account["token"]
        async with httpx.AsyncClient(headers=headers, trust_env=False, timeout=15) as http:
            card = (await http.get(base + "/.well-known/agent-card.json")).json()
            extension, = card["capabilities"]["extensions"]
            client = await ClientFactory(ClientConfig(httpx_client=http, streaming=False)).create_from_url(base)
            request = a2a.SendMessageRequest(message=a2a.Message(message_id="results-discovery",
                role=a2a.Role.ROLE_USER, parts=[a2a.Part(text="Original A2A result")]),
                configuration=a2a.SendMessageConfiguration(return_immediately=True))
            events = [event async for event in client.send_message(request)]
            task = next(event.task for event in events if event.HasField("task"))
            assert "不必跳转" in task.metadata["workspaceHint"]
            results_url = task.metadata["resultsUrl"]
            assert results_url == extension["params"]["urlTemplate"].replace("{task_id}", task.id)
            pending = await http.get(results_url)
            assert pending.status_code == 200
            assert not pending.json()["ready"] and pending.json()["text"] is None
            assert pending.json()["files"] == []
            release.set()
            for _ in range(100):
                task = await client.get_task(a2a.GetTaskRequest(id=task.id, history_length=0))
                if task.status.state == a2a.TaskState.TASK_STATE_COMPLETED:
                    break
                await asyncio.sleep(.05)
            assert task.status.state == a2a.TaskState.TASK_STATE_COMPLETED
            original = (await http.get(results_url)).json()
            assert original["ready"] and "Original A2A result" in original["text"]
            assert len(original["files"]) == 1

            if auth_mode == "required":
                # Protocol-specific OAuth audiences must not be widened by a link.
                for resource, scope, expected in [(base + "/a2a", "tasks:read", 401),
                                                  (base + "/v1/tasks", "tasks:create", 403),
                                                  (base + "/v1/tasks", "tasks:read", 200)]:
                    token = await http.post(base + "/oauth/token", data={"grant_type": "client_credentials",
                        "client_id": account["id"], "client_secret": account["token"],
                        "resource": resource, "scope": scope})
                    assert token.status_code == 200, token.text
                    response = await http.get(results_url, headers={"Authorization": "Bearer " + token.json()["access_token"]})
                    assert response.status_code == expected, response.text

            for _ in range(100):
                if not app.state.task_service._active:
                    break
                await asyncio.sleep(.01)
            async with httpx.AsyncClient(trust_env=False, timeout=15) as browser:
                workspace = task.metadata["workspaceUrl"]
                info = (await browser.get(workspace + "/v1/temporary")).json()
                run = await browser.post(workspace + f"/v1/sessions/{info['session_id']}/runs",
                                         json={"input": "Continued in temporary workspace"})
                assert run.status_code == 202, run.text
                for _ in range(100):
                    state = (await browser.get(workspace + "/v1/runs/" + run.json()["id"])).json()
                    if state["status"] in {"completed", "failed", "cancelled"}:
                        break
                    await asyncio.sleep(.05)
                assert state["status"] == "completed", state
            updated = (await http.get(results_url)).json()
            assert updated["ready"] and "Continued in temporary workspace" in updated["text"]
            assert updated["text"] != original["text"]
            # Reading the latest result does not rewrite the original A2A response.
            task = await client.get_task(a2a.GetTaskRequest(id=task.id, history_length=0))
            assert task.metadata["resultsUrl"] == results_url
            assert task.artifacts[0].parts[0].text == original["text"]
            assert task.status.message.parts[0].text == original["text"]

    try:
        asyncio.run(check())
    finally:
        release.set()


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
