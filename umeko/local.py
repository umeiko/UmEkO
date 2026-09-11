"""本地 IDE 场景入口：python -m umeko.local [--port 8765]

与云场景（python -m umeko.server）共用同一套 L1 运行时、L2 宿主服务与
前端 SPA，差异只有 LOCAL_PROFILE 边界：免登录隐式单用户、放行 run_command、
回复展示真实本地路径。IDE 插件将来可以本地 HTTP + webview 直接复用，
或进程内 import umeko.host 服务（不依赖 FastAPI）。
"""

from __future__ import annotations

import argparse
import logging
import shlex
import sys

from .cancellation import OperationCancelled, run_cancellable_process

MAX_COMMAND_OUTPUT = 4000


class LocalCommandRunner:
    """本地场景的 run_command 后端：直接执行并回传输出。

    MVP 不做逐条确认（个人本机环境）；命令在会话产物目录下执行，
    输出截断防止打爆上下文。云场景永远不要装配它。
    """

    def __init__(self, cwd: str | None = None, timeout: float = 120.0):
        self._cwd = cwd
        self._timeout = timeout

    def run(self, command: str) -> str:
        try:
            argv = shlex.split(command, posix=False)
        except ValueError as exc:
            return f"错误：命令解析失败：{exc}"
        if not argv:
            return "错误：空命令"
        try:
            result = run_cancellable_process(
                argv, timeout=self._timeout, cwd=self._cwd,
                encoding="utf-8", errors="replace",
            )
        except OperationCancelled:
            return "（命令已被用户停止）"
        except FileNotFoundError:
            return f"错误：命令不存在：{argv[0]}"
        except Exception as exc:  # 超时等
            return f"错误：命令执行失败：{exc}"
        output = ((result.stdout or "") + (result.stderr or "")).strip()
        if len(output) > MAX_COMMAND_OUTPUT:
            output = output[:MAX_COMMAND_OUTPUT] + "\n…（输出过长已截断）"
        return f"退出码 {result.returncode}\n{output}" if output else f"退出码 {result.returncode}"


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="umeko.local", description="Umeko 本地工作台（个人免登录模式）"
    )
    parser.add_argument("--host", default="127.0.0.1", help="监听地址（默认 127.0.0.1）")
    parser.add_argument("--port", type=int, default=8765, help="监听端口（默认 8765）")
    parser.add_argument("--data-root", default="local_data", help="本地数据目录")
    parser.add_argument("--workspace-root", default="output", help="会话产物根目录")
    parser.add_argument("--env", default=None, help=".env 文件路径，默认 ./.env")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%H:%M:%S",
    )
    from .config import load_settings

    try:
        settings = load_settings(args.env)
    except RuntimeError as exc:
        print(exc, file=sys.stderr)
        sys.exit(1)

    import uvicorn

    from .host.profile import LOCAL_PROFILE
    from .server.app import create_app

    app = create_app(
        settings,
        data_root=args.data_root,
        workspace_root=args.workspace_root,
        profile=LOCAL_PROFILE,
        command_runner=LocalCommandRunner(cwd=args.workspace_root),
    )
    print(f"Umeko 本地工作台：http://{args.host}:{args.port}（免登录）")
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
