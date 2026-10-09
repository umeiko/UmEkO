"""Skill context lifetime, using real engine loops without provider requests."""
from __future__ import annotations

from copy import deepcopy
import json

import pytest
from openai.types.chat import ChatCompletionMessage

from umeko.agent import UmekoAgent
from umeko.cancellation import OperationCancelled
from umeko.config import ModelConfig, Settings
from umeko.host.service import AgentService
from umeko.prompts.system import DEFAULT_SYSTEM
from umeko.session import Session


BODY = "PRIVATE_SKILL_BODY: inspect images using the detailed checklist."


def pack(body=BODY, name="image-check", description="Inspect document images"):
    return f"---\nname: {name}\ndescription: {description}\n---\n{body}"


def response(content="done", skill=None, call_id="load"):
    calls = [{"id": call_id, "type": "function", "function": {
        "name": "use_skill", "arguments": json.dumps({"name": skill})
    }}] if skill else None
    return ChatCompletionMessage(role="assistant", content=content, tool_calls=calls)


class FakeLLM:
    last_usage = None

    def __init__(self, *replies):
        self.replies = list(replies)
        self.requests = []

    def chat_with_tools(self, messages, tools, **kwargs):
        self.requests.append(deepcopy(messages))
        item = self.replies.pop(0)
        if callable(item):
            item = item()
        if isinstance(item, Exception):
            raise item
        return item

    chat_with_tools_stream = chat_with_tools

    def chat(self, messages, **kwargs):
        self.requests.append(deepcopy(messages))
        return "Earlier task completed."

    def close(self):
        pass


@pytest.fixture
def engine(tmp_path):
    skill_dir = tmp_path / "skills"
    skill_dir.mkdir()
    (skill_dir / "image-check.md").write_text(pack(), encoding="utf-8")
    settings = Settings(ModelConfig("fixture", "unused-key", "http://unused.invalid"))
    session = Session(settings, tmp_path / "output", skill_dir=skill_dir)
    agent = UmekoAgent(settings, session, DEFAULT_SYSTEM)
    yield agent, session, skill_dir
    agent.close()


def serialized(messages):
    return json.dumps(messages, ensure_ascii=False)


def test_unrelated_turns_only_get_fresh_metadata(engine):
    agent, session, skill_dir = engine
    agent._llm = llm = FakeLLM(response(), response())
    agent.chat("hi")
    (skill_dir / "image-check.md").write_text(pack(description="Updated image scope"), encoding="utf-8")
    agent.chat("write quicksort")
    for request in llm.requests:
        assert BODY not in serialized(request)
        assert sum("[当前可按需使用的技能目录]" in str(m["content"]) for m in request) == 1
    assert "Updated image scope" in serialized(llm.requests[-1])
    assert "Inspect document images" not in serialized(llm.requests[-1])
    assert "[当前可按需使用的技能目录]" not in serialized(agent._messages)
    assert [m["content"] for m in agent._messages if m["role"] == "user"] == ["hi", "write quicksort"]
    assert not session.active_skill_packs()


def test_load_once_per_task_then_retire_body_and_reload_next_task(engine):
    agent, _, _ = engine
    logged = []
    agent._on_tool_result = lambda name, result: logged.append(result)
    agent._llm = llm = FakeLLM(
        response(skill="image-check"), response(skill="image-check", call_id="again"), response(),
        response(skill="image-check", call_id="next-task"), response(),
    )
    agent.chat("inspect the image")
    assert BODY not in serialized(llm.requests[0])
    assert serialized(llm.requests[1]).count(BODY) == 1
    assert serialized(llm.requests[2]).count(BODY) == 1
    assert "当前版本已在本任务上下文中" in logged[1]
    assert BODY in logged[0]  # Tool output logs retain the original result.
    assert BODY not in serialized(agent._messages)
    assert not agent._skill_results
    assert not agent._session.active_skill_packs()
    assert agent._messages[2]["tool_calls"][0]["id"] == agent._messages[3]["tool_call_id"]
    agent.chat("inspect another image")
    assert BODY not in serialized(llm.requests[3])
    assert serialized(llm.requests[4]).count(BODY) == 1
    assert BODY not in serialized(agent._messages)


def test_changed_body_replaces_old_version_in_same_task(engine):
    agent, _, skill_dir = engine
    def update():
        (skill_dir / "image-check.md").write_text(pack("NEW_BODY"), encoding="utf-8")
        return response(skill="image-check", call_id="updated")
    agent._llm = llm = FakeLLM(response(skill="image-check"), update, response())
    agent.chat("inspect")
    assert BODY in serialized(llm.requests[1])
    assert BODY not in serialized(llm.requests[2])
    assert serialized(llm.requests[2]).count("NEW_BODY") == 1
    assert "旧版指引已替换" in serialized(llm.requests[2])
    assert "NEW_BODY" not in serialized(agent._messages)


@pytest.mark.parametrize("reset", ["clear", "restore", "compact", "missing"])
def test_context_changes_cannot_leave_a_false_loaded_flag(engine, reset):
    agent, _, _ = engine
    result = agent._execute("use_skill", '{"name":"image-check"}')
    agent._messages += [{"role": "user", "content": "inspect"},
                        agent._assistant_message_dict(response(skill="image-check")),
                        {"role": "tool", "tool_call_id": "load", "content": result}]
    agent._llm = FakeLLM()
    if reset == "clear":
        agent.clear_context()
    elif reset == "restore":
        agent.restore_history([{"role": "user", "content": "earlier"}], "Earlier task")
    elif reset == "compact":
        agent._messages += [{"role": "assistant", "content": "long history " * 500}]
        assert agent.compact_context()["compressed"]
        assert BODY not in serialized(agent._llm.requests)  # Summary must not retain bodies.
    else:
        agent._messages = agent._messages[:1]
    assert BODY in agent._execute("use_skill", '{"name":"image-check"}')


def test_retiring_skill_keeps_unrelated_tool_results(engine):
    agent, _, _ = engine
    result = agent._execute("use_skill", '{"name":"image-check"}')
    agent._messages += [agent._assistant_message_dict(response(skill="image-check")),
                        {"role": "tool", "tool_call_id": "load", "content": result},
                        {"role": "tool", "tool_call_id": "other-tool", "content": result}]
    agent._release_skill_context()
    assert BODY not in agent._messages[-2]["content"]
    assert BODY in agent._messages[-1]["content"]


@pytest.mark.parametrize("failure", [RuntimeError("provider failed"), OperationCancelled()])
def test_failure_and_cancellation_retire_loaded_body(engine, failure):
    agent, _, _ = engine
    agent._llm = FakeLLM(response(skill="image-check"), failure)
    if isinstance(failure, OperationCancelled):
        assert agent.chat("inspect") == "已停止当前操作。"
    else:
        with pytest.raises(RuntimeError, match="provider failed"):
            agent.chat("inspect")
    assert BODY not in serialized(agent._messages)
    assert not agent._skill_results


def test_catalog_permissions_and_web_selection_are_distinct(engine):
    _, session, skill_dir = engine
    (skill_dir / "other.md").write_text(pack(name="other", description="Other scope"), encoding="utf-8")
    session.allowed_skill_packs = {"image-check"}
    assert "Other scope" not in session.skill_catalog_prompt()
    assert "other" not in session.list_skill_packs()
    assert "未配置" in session.use_skill("other")
    session.catalog_skill_names = set()
    assert session.skill_catalog_prompt() == ""
    assert BODY in session.use_skill("image-check")  # Hidden from automatic catalogue, still permitted.


def test_multimodal_request_keeps_metadata_and_image(engine, tmp_path):
    agent, _, _ = engine
    image = tmp_path / "image.png"
    image.write_bytes(b"fixture")
    agent._vision = True
    agent._llm = llm = FakeLLM(response())
    agent.chat("inspect image", images=[image])
    assert llm.requests[0][1]["role"] == "system"
    assert llm.requests[0][-1]["content"][1]["type"] == "image_url"


def test_context_stats_include_catalogue_without_storing_it(engine):
    agent, session, _ = engine
    selected = agent.context_stats()["used_tokens"]
    session.catalog_skill_names = set()
    assert agent.context_stats()["used_tokens"] < selected


def test_web_mount_selects_metadata_without_reading_or_injecting_body(tmp_path, monkeypatch):
    settings = Settings(ModelConfig("fixture", "unused-key", "http://unused.invalid"))
    service = AgentService(settings, tmp_path / "data", tmp_path / "output")
    user = service.store.create_user("fixture-skill-user", "fixture-pass")
    state = service.create_session(user_id=user["id"])
    service.create_client_resource(state.id, "skills", "image-check.md", pack())
    monkeypatch.setattr(Session, "use_skill", lambda *args: pytest.fail("Mount must not load instructions"))
    try:
        service.update_client_resource(state.id, "skills", "image-check.md", mounted=True)
        assert "Inspect document images" in state.session.skill_catalog_prompt()
        assert BODY not in state.session.skill_catalog_prompt()
        state.agent._llm = llm = FakeLLM(response(), response())
        for question in ["hi", "write quicksort"]:
            run = service.run_manager.create(state.id)
            service._execute_run(state, run, question, [])
            assert run.status == "completed"
            assert "resource.activated" not in [e["type"] for e in run.events]
            assert BODY not in serialized(llm.requests[-1])
        # Restore enabled choices without reviving bodies or force-use instructions.
        service.evict_session(state.id)
        restored = service.get_session(state.id)
        assert restored.session.catalog_skill_names == {"image-check"}
        assert BODY not in serialized(restored.agent._messages)
        service.update_client_resource(state.id, "skills", "image-check.md", content=pack(name="renamed"))
        assert restored.session.catalog_skill_names == {"renamed"}
        service.update_client_resource(state.id, "skills", "image-check.md", mounted=False)
        assert restored.session.skill_catalog_prompt() == ""
        service.update_client_resource(state.id, "skills", "image-check.md", mounted=True)
        service.delete_client_resource(state.id, "skills", "image-check.md")
        assert restored.session.catalog_skill_names == set()
    finally:
        for sid in list(service.sessions):
            service.evict_session(sid)
        service.run_manager.shutdown()
