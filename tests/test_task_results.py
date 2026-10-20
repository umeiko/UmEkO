import io
import json
import zipfile

from openai.types.chat import ChatCompletionMessage
import pytest

from conftest import wait_task
from umeko.agent import UmekoAgent
from umeko.host.results import MACHINE_RESULTS_PROMPT, SUBMISSION_REMINDER
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
        agent._skills["submit_results"].handler(text="完成分析。依据和结论如下。", files=[
            {"path": "generate/final.txt", "description": "最终说明"},
            {"path": "generate/delivery", "description": "整包交付"}])
        return "普通文字收尾，不要求独立 JSON。"

    monkeypatch.setattr(UmekoAgent, "chat", chat)
    submitted = client.post(base, headers=headers, json={"prompt": "select finals"}).json()
    task_id = submitted["task_id"]
    assert submitted["results_url"] == "http://127.0.0.1" + base + "/" + task_id + "/results"
    assert "read_results" in submitted["results_hint"]
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
    assert "submit_results" in restored.agent._skills
    assert "submit_results" not in restored.agent._subagent._skills
    service.evict_session(session_id)
    ordinary = service.create_session(user_id=other["user_id"],
        agent_snapshot=service.agent_registry.snapshot(app.state.fixture_agent))
    assert MACHINE_RESULTS_PROMPT not in ordinary.agent._messages[0]["content"]
    assert "submit_results" not in ordinary.agent._skills
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
        try:
            arguments = json.loads(reply)
        except ValueError:
            arguments = None
        if isinstance(arguments, dict):
            agent._execute("submit_results", json.dumps(arguments))
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
        agent._skills["submit_results"].handler(text="几何题答案是 30°。", files=[])
        return "几何题答案是 30°。"
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


def test_real_agent_tool_loop_submits_and_finishes_without_another_model_reply(machine_client, monkeypatch):
    client, app, account, _ = machine_client
    replies = []
    def llm_chat(llm, messages, tools, **kwargs):
        assert MACHINE_RESULTS_PROMPT in messages[0]["content"]
        assert any(t["function"]["name"] == "submit_results" for t in tools)
        if not replies:
            replies.append("write")
            return ChatCompletionMessage(role="assistant", tool_calls=[{"id": "final-write", "type": "function", "function": {
                "name": "write_file", "arguments": json.dumps({"path": "generate/final.txt", "content": "real tool output"})}}])
        assert replies == ["write"], "A valid submission must end the model loop"
        replies.append("submit")
        return ChatCompletionMessage(role="assistant", content="答案已完成，准备提交。", tool_calls=[
            {"id": "submit-final", "type": "function", "function": {"name": "submit_results",
                "arguments": json.dumps({"text": "Final tool-backed result", "files": [{"path": "generate/final.txt"}]})}}])
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
    assert replies == ["write", "submit"]


def tool_call(name, arguments, identity):
    return {"id": identity, "type": "function", "function": {"name": name, "arguments": json.dumps(arguments)}}


@pytest.mark.parametrize("machine_app", ["", "/teams/docs/workbench"], indirect=True)
@pytest.mark.parametrize("can_continue", [False, True])
def test_agent_decides_whether_download_failure_blocks_the_task(machine_client, monkeypatch, can_continue):
    client, app, account, _ = machine_client
    url = "https://files.example.invalid/input.png"
    turns, downloads = [], []
    def failed_download(*args, **kwargs):
        downloads.append(args[0])
        return "错误：下载失败 [HTTP_ERROR]，HTTP 403，无法取得参考图片。"
    def llm_chat(llm, messages, tools, **kwargs):
        turns.append(len(messages))
        if len(turns) == 1:
            assert "下载或处理失败后，由你判断" in messages[0]["content"]
            return ChatCompletionMessage(role="assistant", tool_calls=[
                tool_call("download_url", {"url": url}, "download")])
        if len(turns) == 2:
            assert "HTTP_ERROR" in messages[-1]["content"]
            if can_continue:
                return ChatCompletionMessage(role="assistant", tool_calls=[
                    tool_call("write_file", {"path": "generate/summary.txt", "content": "基于已有资料完成可执行部分。"}, "write")])
        assert len(turns) == (3 if can_continue else 2), "Successful submission must finish the loop"
        text = ("可选参考图片下载失败，已用现有资料完成可执行部分。" if can_continue else
                "必要图片下载失败（HTTP 403），本轮无法继续质检。请外层 Agent 将响应 workspace_url 提供给用户，在临时工作台上传图片后继续。")
        return ChatCompletionMessage(role="assistant", tool_calls=[tool_call("submit_results", {
            "text": text, "files": [{"path": "generate/summary.txt"}] if can_continue else []}, "submit")])
    monkeypatch.setattr("umeko.skills.file_tools.download_url", failed_download)
    monkeypatch.setattr(UmekoAgent, "chat", REAL_CHAT)
    monkeypatch.setattr(LLMClient, "chat_with_tools_stream", llm_chat)
    headers = {"Authorization": "Bearer " + account["token"]}
    base = app.state.agent_service.settings.base_path + "/agent/fixture/v1/tasks"
    response = client.post(base, headers=headers, json={"prompt": "请下载参考图并按已有资料分析：" + url})
    assert response.status_code == 202, response.text
    task_id = response.json()["id"]
    completed = wait(client, base, task_id, headers)
    assert completed["status"] == "completed" and completed["error"] is None, completed
    assert completed["workspace_url"].startswith("http://127.0.0.1" + app.state.agent_service.settings.base_path + "/TMP/")
    results = client.get(base + f"/{task_id}/results", headers=headers).json()
    assert results["ready"] and "下载失败" in results["text"]
    assert len(results["files"]) == int(can_continue)
    assert downloads == [url] and len(turns) == (3 if can_continue else 2)


def test_model_can_correct_invalid_submission_and_later_calls_are_not_executed(machine_client, monkeypatch):
    client, app, account, _ = machine_client
    turns = []
    def llm_chat(llm, messages, tools, **kwargs):
        turns.append(messages)
        if len(turns) == 1:
            return ChatCompletionMessage(role="assistant", tool_calls=[tool_call("submit_results",
                {"text": "too soon", "files": [{"path": "generate/missing.txt"}]}, "bad-submit")])
        assert len(turns) == 2, "Submitting the corrected answer must finish the turn"
        feedback = json.loads(messages[-1]["content"])
        assert not feedback["ok"] and "不存在" in feedback["error"]
        return ChatCompletionMessage(role="assistant", tool_calls=[
            tool_call("write_file", {"path": "generate/final.txt", "content": "corrected"}, "write-final"),
            tool_call("submit_results", {"text": "**已修正**，自然语言答案。", "files": [{"path": "generate/final.txt"}]}, "good-submit"),
            tool_call("write_file", {"path": "generate/unwanted.txt", "content": "must not execute"}, "after-submit")])
    monkeypatch.setattr(UmekoAgent, "chat", REAL_CHAT)
    monkeypatch.setattr(LLMClient, "chat_with_tools_stream", llm_chat)
    headers = {"Authorization": "Bearer " + account["token"]}
    base = "/agent/fixture/v1/tasks"
    task_id = client.post(base, headers=headers, json={"prompt": "correct the manifest"}).json()["id"]
    completed = wait_task(client, task_id, account["token"])
    assert completed["status"] == "completed", completed
    read = client.get(base + f"/{task_id}/results", headers=headers).json()
    assert read["text"] == "**已修正**，自然语言答案。"
    assert [f["path"] for f in read["files"]] == ["generate/final.txt"]
    with app.state.store.connect() as db:
        sid = db.execute("SELECT session_id FROM service_tasks WHERE id=?", (task_id,)).fetchone()[0]
        skipped = db.execute("SELECT result FROM tool_events WHERE session_id=? AND name='write_file' ORDER BY id DESC LIMIT 1", (sid,)).fetchone()
    root = app.state.agent_service.data_root / "users" / account["user_id"] / "sessions" / sid
    assert not (root / "generate/unwanted.txt").exists()
    assert skipped and "未执行" in skipped[0]


def test_plain_first_reply_gets_one_submission_reminder(machine_client, monkeypatch):
    client, app, account, _ = machine_client
    calls = []
    def llm_chat(llm, messages, tools, **kwargs):
        calls.append(messages)
        if len(calls) == 1:
            return ChatCompletionMessage(role="assistant", content="答案是 30°，不需要文件。")
        assert len(calls) == 2 and messages[-1]["content"] == SUBMISSION_REMINDER
        return ChatCompletionMessage(role="assistant", tool_calls=[tool_call("submit_results",
            {"text": "答案是 30°，依据是三角形内角和。", "files": []}, "submit-text")])
    monkeypatch.setattr(UmekoAgent, "chat", REAL_CHAT)
    monkeypatch.setattr(LLMClient, "chat_with_tools_stream", llm_chat)
    headers = {"Authorization": "Bearer " + account["token"]}
    base = "/agent/fixture/v1/tasks"
    task_id = client.post(base, headers=headers, json={"prompt": "plain mathematical answer"}).json()["id"]
    completed = wait_task(client, task_id, account["token"])
    assert completed["status"] == "completed", completed
    results = client.get(base + f"/{task_id}/results", headers=headers).json()
    assert results["ready"] and results["files"] == [] and "内角和" in results["text"]
    assert len(calls) == 2


def test_continuation_cannot_reuse_previous_submission(machine_client, monkeypatch):
    import time
    from urllib.parse import urlsplit

    client, app, account, _ = machine_client
    headers = {"Authorization": "Bearer " + account["token"]}
    base = "/agent/fixture/v1/tasks"
    task = client.post(base, headers=headers, json={"prompt": "original answer"}).json()
    assert wait_task(client, task["id"], account["token"])["status"] == "completed"
    previous = client.get(base + f"/{task['id']}/results", headers=headers).json()
    for _ in range(100):
        if not app.state.task_service._active:
            break
        time.sleep(.02)
    workspace = urlsplit(task["workspace_url"]).path
    sid = client.get(workspace + "/v1/temporary").json()["session_id"]
    calls = []
    def no_submission(agent, prompt, images=None):
        assert "submit_results" in agent._skills
        calls.append(prompt)
        return "只给文字，没有提交。"
    monkeypatch.setattr(UmekoAgent, "chat", no_submission)
    response = client.post(workspace + f"/v1/sessions/{sid}/runs", json={"input": "a new answer"})
    run_id = response.json()["id"]
    for _ in range(100):
        run = client.get(workspace + f"/v1/runs/{run_id}").json()
        if run["status"] in {"completed", "failed", "cancelled"}:
            break
        time.sleep(.02)
    assert run["status"] == "failed" and "submit_results" in run["error"]
    assert calls == ["a new answer", SUBMISSION_REMINDER]
    current = client.get(base + f"/{task['id']}/results", headers=headers).json()
    assert current["text"] == previous["text"] and current["files"] == previous["files"]
