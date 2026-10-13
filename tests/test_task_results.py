import io
import json
import zipfile

from openai.types.chat import ChatCompletionMessage
import pytest

from conftest import wait_task
from umeko.agent import UmekoAgent
from umeko.host.results import MACHINE_RESULTS_PROMPT
from umeko.llm import LLMClient

REAL_CHAT = UmekoAgent.chat


def wait(client, base, task_id, headers):
    import time
    for _ in range(200):
        result = client.get(base + "/" + task_id, headers=headers).json()
        if result["status"] in {"completed", "failed", "cancelled"}:
            return result
        time.sleep(.02)
    raise AssertionError("Task did not finish")


@pytest.mark.parametrize("machine_app", ["", "/teams/docs/umeko"], indirect=True)
@pytest.mark.parametrize("auth_mode", ["required", "anonymous"])
def test_results_select_final_files_and_direct_download(machine_client, monkeypatch, auth_mode):
    client, app, account, other = machine_client
    service, store = app.state.agent_service, app.state.store
    app.state.identity_store.set_auth_mode(auth_mode)
    headers = {"Authorization": "Bearer " + account["token"]} if auth_mode == "required" else {}
    prefix = service.settings.base_path
    base = prefix + "/agent/fixture/v1/tasks"

    def chat(agent, prompt, images=None):
        assert MACHINE_RESULTS_PROMPT in agent._messages[0]["content"]
        generate = agent._output_root / "generate"
        (generate / "draft.xml").write_text("intermediate", encoding="utf-8")
        (generate / "final.txt").write_text("final content", encoding="utf-8")
        (generate / "delivery").mkdir(exist_ok=True)
        (generate / "delivery/evidence.txt").write_text("evidence", encoding="utf-8")
        return json.dumps({"text": "完成分析。依据和结论如下。", "files": [
            {"path": "generate/final.txt", "description": "最终说明"},
            {"path": "generate/delivery", "description": "整包交付"}]})

    monkeypatch.setattr(UmekoAgent, "chat", chat)
    submitted = client.post(base, headers=headers, json={"prompt": "select finals"}).json()
    task_id = submitted["task_id"]
    completed = wait(client, base, task_id, headers)
    assert completed["status"] == "completed", completed
    assert completed["reply"] == "完成分析。依据和结论如下。"
    results_url = base + "/" + task_id + "/results"
    results = client.get(results_url, headers=headers).json()
    assert results["ready"] and results["text"] == completed["reply"]
    assert [item["path"] for item in results["files"]] == ["generate/final.txt", "generate/delivery"]
    assert [item["name"] for item in completed["artifacts"]] == ["generate/final.txt"]
    for item in results["files"]:
        response = client.get(base + f"/{task_id}/files/{item['file_id']}/content", headers=headers)
        assert response.status_code == 200
        if item["type"] == "directory":
            with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
                assert archive.read("delivery/evidence.txt") == b"evidence"
        else:
            assert response.content == b"final content"
    assert client.get(results_url, headers={"Authorization": "Bearer " + other["token"]}).status_code == 404
    service.agent_registry.save({"slug": "other-agent", "name": "Other", "description": "fixture"})
    assert client.get(results_url.replace("/agent/fixture/", "/agent/other-agent/"), headers=headers).status_code == 404
    with store.connect() as db:
        session_id = db.execute("SELECT session_id FROM service_tasks WHERE id=?", (task_id,)).fetchone()[0]
    restored = service.get_session(session_id)
    assert MACHINE_RESULTS_PROMPT in restored.agent._messages[0]["content"]
    service.evict_session(session_id)
    ordinary = service.create_session(user_id=other["user_id"])
    assert MACHINE_RESULTS_PROMPT not in ordinary.agent._messages[0]["content"]
    service.evict_session(ordinary.id)
    with store.connect() as db:
        db.execute("UPDATE service_tasks SET workspace_expires_at='2000-01-01T00:00:00+00:00' WHERE id=?", (task_id,))
    expired = client.get(results_url, headers=headers).json()
    assert expired["ready"] and expired["files"] == results["files"] and expired["workspace_state"] == "expired"
    assert client.get(base + f"/{task_id}/files/{results['files'][0]['file_id']}/content", headers=headers).status_code == 404


@pytest.mark.parametrize("reply", ["Plain answer", '{"text":"answer"}',
    '{"text":"answer","files":[{"path":"generate/missing.txt"}]}',
    '{"text":"answer","files":[{"path":"attachments/input.txt"}]}',
    '{"text":"answer","files":[{"path":"generate/../client/private.txt"}]}'])
def test_invalid_results_do_not_publish_inferred_files(machine_client, monkeypatch, reply):
    client, app, account, _ = machine_client
    def chat(agent, prompt, images=None):
        (agent._output_root / "generate/unselected.txt").write_text("not a final", encoding="utf-8")
        return reply
    monkeypatch.setattr(UmekoAgent, "chat", chat)
    headers = {"Authorization": "Bearer " + account["token"]}
    base = "/agent/fixture/v1/tasks"
    task_id = client.post(base, headers=headers, json={"prompt": "invalid result"}).json()["id"]
    result = wait_task(client, task_id, account["token"])
    assert result["status"] == "failed" and result["error"] and result["artifacts"] == []
    read = client.get(base + "/" + task_id + "/results", headers=headers).json()
    assert not read["ready"] and read["files"] == [] and read["error"]


def test_no_file_answer_and_legacy_result_are_not_inferred(machine_client, monkeypatch):
    client, app, account, _ = machine_client
    def chat(agent, prompt, images=None):
        (agent._output_root / "generate/scratch.txt").write_text("scratch", encoding="utf-8")
        return json.dumps({"text": "几何题答案是 30°。", "files": []})
    monkeypatch.setattr(UmekoAgent, "chat", chat)
    headers = {"Authorization": "Bearer " + account["token"]}
    base = "/agent/fixture/v1/tasks"
    task_id = client.post(base, headers=headers, json={"prompt": "geometry"}).json()["id"]
    assert wait_task(client, task_id, account["token"])["status"] == "completed"
    read = client.get(base + "/" + task_id + "/results", headers=headers).json()
    assert read["ready"] and read["files"] == [] and "30°" in read["text"]
    with app.state.store.connect() as db:
        db.execute("UPDATE service_tasks SET result_json=NULL WHERE id=?", (task_id,))
    legacy = client.get(base + "/" + task_id + "/results", headers=headers).json()
    assert not legacy["ready"] and legacy["files"] == [] and "历史" in legacy["error"]


def test_real_agent_tool_loop_returns_final_json(machine_client, monkeypatch):
    client, app, account, _ = machine_client
    replies = []
    def llm_chat(llm, messages, tools, **kwargs):
        assert MACHINE_RESULTS_PROMPT in messages[0]["content"]
        if not replies:
            replies.append("write")
            return ChatCompletionMessage(role="assistant", tool_calls=[{"id": "final-write", "type": "function", "function": {
                "name": "write_file", "arguments": json.dumps({"path": "generate/final.txt", "content": "real tool output"})}}])
        return ChatCompletionMessage(role="assistant", content=json.dumps({"text": "Final tool-backed result", "files": [{"path": "generate/final.txt"}]}))
    monkeypatch.setattr(UmekoAgent, "chat", REAL_CHAT)
    monkeypatch.setattr(LLMClient, "chat_with_tools_stream", llm_chat)
    headers = {"Authorization": "Bearer " + account["token"]}
    base = "/agent/fixture/v1/tasks"
    task_id = client.post(base, headers=headers, json={"prompt": "generate final"}).json()["id"]
    completed = wait_task(client, task_id, account["token"])
    assert completed["status"] == "completed", completed
    results = client.get(base + "/" + task_id + "/results", headers=headers).json()
    assert results["text"] == "Final tool-backed result" and len(results["files"]) == 1
    downloaded = client.get(base + f"/{task_id}/files/{results['files'][0]['file_id']}/content", headers=headers)
    assert downloaded.content == b"real tool output"
