"""命令行 REPL：与 Web 共用 L1 Runner + 事件协议（events.py / runner.py）。

用法：
    cp .env.example .env  # 填写模型配置
    python -m umeko.cli
"""

from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

from . import events as ev
from .agent import UmekoAgent
from .config import load_settings
from .prompts.system import DEFAULT_SYSTEM
from .runner import TERMINAL_STATUSES, Run, RunManager
from .session import Session

CLI_SESSION_ID = "cli"


def _render(event: dict) -> None:
    """把统一事件渲染到终端（对应 Web 前端的 SSE 渲染）。"""
    etype, data = event["type"], event["data"]
    if etype == ev.ASSISTANT_DELTA:
        print(data["text"], end="", flush=True)
    elif etype == ev.REASONING_DELTA:
        print(f"\033[2m{data['text']}\033[0m", end="", flush=True)  # 思考流灰显
    elif etype == ev.TOOL_STARTED:
        print(f"\n[tool] {data['name']} …", flush=True)
    elif etype == ev.TOOL_COMPLETED:
        result = data.get("result", "")
        preview = result[:120].replace("\n", " ")
        print(f"[tool] {data['name']} -> {preview}", flush=True)
    elif etype.startswith(ev.SUBAGENT_PREFIX):
        print(f"\n[subagent:{etype[len(ev.SUBAGENT_PREFIX):]}]", flush=True)
    elif etype == ev.RUN_FAILED:
        print(f"\n（运行失败：{data.get('error')}）", flush=True)


def _run_turn(manager: RunManager, agent: UmekoAgent, user_input: str) -> str | None:
    """一轮对话：走与 Web 相同的 Run 生命周期，增量渲染事件流。"""
    run = manager.create(CLI_SESSION_ID, emit_queued=False)

    def work() -> None:
        reply = agent.chat(user_input)
        if run.cancel_requested():
            run.finish("cancelled", reply=reply)
        else:
            run.finish("completed", reply=reply)

    manager.submit(run, work)
    cursor = 0
    try:
        while True:
            for event in run.events_after(cursor):
                cursor = event["id"]
                _render(event)
            if run.status in TERMINAL_STATUSES and not run.events_after(cursor):
                break
            time.sleep(0.05)
    except KeyboardInterrupt:  # Ctrl+C 取消当前 Run，不退出 REPL
        run.request_cancel()
        print("\n（正在停止…）")
        while run.status not in TERMINAL_STATUSES:
            time.sleep(0.05)
    print()
    return run.reply


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%H:%M:%S",
    )
    try:
        settings = load_settings()
    except RuntimeError as exc:
        print(exc, file=sys.stderr)
        sys.exit(1)
    session = Session(settings, Path("output"))
    manager = RunManager(max_workers=1)
    agent = UmekoAgent(
        settings, session, DEFAULT_SYSTEM,
        on_event=lambda t, d: _stream_to_run(t, d, manager),
        should_cancel=lambda: bool(
            (r := _active_run(manager)) and r.cancel_requested()
        ),
    )
    print("UMEKO REPL（Ctrl+C 取消本轮，/quit 退出）；产物目录：", session.output_dir)
    while True:
        try:
            user_input = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not user_input:
            continue
        if user_input in {"/quit", "/exit"}:
            break
        if user_input == "/stats":
            print(agent.context_stats())
            continue
        if user_input == "/compact":
            print(agent.compact_context())
            continue
        if user_input == "/clear":
            print(agent.clear_context())
            continue
        _run_turn(manager, agent, user_input)
    manager.shutdown()


def _active_run(manager: RunManager) -> Run | None:
    return next(
        (r for r in manager.runs.values() if r.status not in TERMINAL_STATUSES), None
    )


def _stream_to_run(event_type: str, data: dict, manager: RunManager) -> None:
    """引擎事件 -> 当前活跃 Run 的事件缓冲（对应 host/service 的 L2 合成）。"""
    run = _active_run(manager)
    if run is not None:
        run.emit(event_type, **data)


if __name__ == "__main__":
    main()
