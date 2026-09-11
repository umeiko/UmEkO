"""Run / RunManager 生命周期测试（L1，无 LLM 依赖）。"""

from __future__ import annotations

import threading

import pytest

from umeko import events as ev
from umeko.runner import TERMINAL_STATUSES, Run, RunManager


def test_run_event_buffer_and_cursor():
    run = Run("run_a", "sess_a")
    e1 = run.emit(ev.RUN_STARTED)
    e2 = run.emit(ev.ASSISTANT_DELTA, text="hi")
    assert e1["id"] == 1 and e2["id"] == 2
    assert e2["data"] == {"text": "hi"}
    assert [e["id"] for e in run.events_after(1)] == [2]
    assert run.events_after(2) == []


def test_run_finish_terminal_events():
    run = Run("run_b", "sess_a")
    run.finish("completed", reply="done")
    assert run.status == "completed" and run.reply == "done" and run.finished
    assert run.events[-1]["type"] == ev.RUN_COMPLETED

    run2 = Run("run_c", "sess_a")
    run2.finish("failed", error="boom")
    assert run2.error == "boom"
    assert run2.events[-1]["data"] == {"error": "boom"}


def test_run_cancel_marks_cancelling_once():
    run = Run("run_d", "sess_a")
    run.request_cancel()
    run.request_cancel()  # 重复取消不重复发事件
    assert run.cancel_requested()
    assert [e["type"] for e in run.events] == [ev.RUN_CANCELLING]
    run.finish("cancelled", reply="已停止")
    run.request_cancel()  # 终态后取消无效
    assert run.events[-1]["type"] == ev.RUN_CANCELLED


def test_manager_create_submit_get_cancel():
    manager = RunManager(max_workers=1)
    done = threading.Event()

    run = manager.create("sess_x")
    assert run.events[0]["type"] == ev.RUN_QUEUED
    assert manager.get(run.id) is run

    def work():
        run.emit(ev.RUN_STARTED)
        run.finish("completed", reply="ok")
        done.set()

    manager.submit(run, work)
    assert done.wait(timeout=5)
    assert run.status in TERMINAL_STATUSES
    assert run.reply == "ok"

    with pytest.raises(KeyError):
        manager.get("run_不存在")
    manager.shutdown()


def test_agent_event_fanout():
    """UmekoAgent 的 on_event 与旧回调扇出同一份事件（不触发 LLM，只测装配）。"""
    from types import SimpleNamespace

    from umeko.agent import UmekoAgent

    settings = SimpleNamespace(  # 只喂 __init__ 真正读到的字段
        text_model=SimpleNamespace(),
        text_model_vision=False,
        vision_model=None,
        sub_model=None,
        sub_model_vision=False,
        context_window=10000,
        max_tool_iterations=3,
        max_subagent_tool_iterations=3,
    )
    session = SimpleNamespace(
        output_dir=None,
        create_skill=lambda **kw: "ok",
        list_skill_packs=lambda **kw: "ok",
        use_skill=lambda **kw: "ok",
        read_working_doc=lambda **kw: "ok",
        write_working_doc=lambda **kw: "ok",
    )
    seen_events, seen_legacy = [], []

    agent = UmekoAgent(
        settings, session, "system",
        on_delta=lambda t: seen_legacy.append(("delta", t)),
        on_event=lambda t, d: seen_events.append((t, d)),
    )
    assert agent._cb_delta is not None  # 任一通道存在即走流式
    agent._cb_delta("你好")
    assert seen_legacy == [("delta", "你好")]
    assert seen_events == [(ev.ASSISTANT_DELTA, {"text": "你好"})]

    agent._emit(ev.TOOL_STARTED, name="write_file", arguments="{}")
    assert seen_events[-1] == (ev.TOOL_STARTED, {"name": "write_file", "arguments": "{}"})
