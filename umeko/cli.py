"""命令行 REPL：与 Web 共用 L1 Runner + 事件协议（events.py / runner.py）。

用法：
    python -m umeko.cli providers import providers.local
    python -m umeko.cli
"""

from __future__ import annotations

import logging
import argparse
import json
import sys
import time
from pathlib import Path

from . import events as ev
from .agent import UmekoAgent
from .config import load_settings, model_config_unconfigured, resolve_env_path
from .prompts.system import DEFAULT_SYSTEM
from .runner import TERMINAL_STATUSES, Run, RunManager
from .session import Session

CLI_SESSION_ID = "cli"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="umeko.cli", description="Umeko REPL 与共享 Provider 管理")
    parser.add_argument("--env", default=None, help="部署 .env 路径")
    parser.add_argument("--data-root", default=None, help="覆盖 UMEKO_DATA_ROOT（与 Web 共用同一目录）")
    sub = parser.add_subparsers(dest="command")
    actions = sub.add_parser("providers", help="与网页管理面共用 Provider 注册表").add_subparsers(dest="action", required=True)
    actions.add_parser("list", help="列出 Provider/模型，不显示密钥")
    actions.add_parser("import", help="导入与网页管理面相同格式的 JSON").add_argument("file", type=Path)
    actions.add_parser("use", help="激活默认模型").add_argument("model_id")
    migrate = actions.add_parser("migrate-env", help="将旧 .env 模型配置迁移到 Provider")
    migrate.add_argument("--remove", action="store_true", help="迁移成功后删除旧 .env 模型项")
    return parser


def _providers(args, settings) -> None:
    from dotenv import dotenv_values, unset_key
    from .host.configuration import LEGACY_MODEL_KEYS, migrate_legacy_models
    from .host.storage import Store
    store = Store(Path(settings.data_root) / "umeko.db")
    if args.action == "list":
        active = store.active_model()
        providers = store.list_providers()
        for provider in providers:
            print(f"{provider['name']} ({provider['id']})")
            for model in provider["models"]:
                mark = "*" if active and active["model_id"] == model["id"] else " "
                print(f"  {mark} {model['id']}  {model['name']}  vision={model['vision']}")
        if not providers:
            print("尚未配置 Provider，请从管理面添加或使用 providers import。")
    elif args.action == "import":
        result = store.import_providers(json.loads(args.file.read_text(encoding="utf-8")))
        print(json.dumps(result, ensure_ascii=False))
    elif args.action == "use":
        store.set_active_model(args.model_id)
        print("已激活默认模型。网页服务会在下一轮提问时读取更新；CLI 用 /reload。")
    elif args.action == "migrate-env":
        path = resolve_env_path(args.env)
        if not path.is_file():
            raise RuntimeError(f"找不到旧配置文件：{path}")
        count = migrate_legacy_models(store, dotenv_values(path))
        store.set_config({"LEGACY_MODEL_CONFIG_MIGRATED": "1"})
        if args.remove:
            for key in LEGACY_MODEL_KEYS:
                if key in dotenv_values(path):
                    unset_key(str(path), key)
        print(f"已核对/迁移 {count} 个模型；注册表：{store.path}" + ("；旧 .env 模型项已移除。" if args.remove else "。"))


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
    args = _parser().parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%H:%M:%S",
    )
    try:
        settings = load_settings(args.env, args.data_root)
        if args.command == "providers":
            _providers(args, settings)
            return
        if model_config_unconfigured(settings):
            raise RuntimeError("尚未激活模型。请在管理面 Provider / Model 中配置，或使用 providers import/use。")
    except (RuntimeError, ValueError, KeyError, OSError) as exc:
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
    print("模型来自共享 Provider 注册表；/reload 读取更新并开始新对话。")
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
        if user_input == "/reload":
            try:
                updated = load_settings(args.env, args.data_root)
                if model_config_unconfigured(updated):
                    raise RuntimeError("尚未激活模型，请先配置 Provider。")
                session = Session(updated, Path("output"))
                agent = UmekoAgent(updated, session, DEFAULT_SYSTEM,
                    on_event=lambda t, d: _stream_to_run(t, d, manager),
                    should_cancel=lambda: bool((r := _active_run(manager)) and r.cancel_requested()))
                settings = updated
                print("已读取 Provider 配置并开始新对话。")
            except (RuntimeError, ValueError, OSError) as exc:
                print(f"配置更新失败：{exc}")
            continue
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
