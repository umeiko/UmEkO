"""Web 工作台入口：python -m umeko.server [--host 0.0.0.0] [--port 8000]

云模式默认同时启动管理面（独立端口，用户面不含任何 /admin 路由）：
- 管理面默认监听 127.0.0.1:9000，仅管理员（users.role='admin'）可登录；
- 首个管理员通过环境变量引导创建：
    UMEKO_ADMIN_USERNAME + UMEKO_ADMIN_PASSWORD
- 用 --no-admin 可关闭管理端口。
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import threading


def _bootstrap_admin(store, logger: logging.Logger) -> None:
    """没有任何管理员时：环境变量优先，否则创建默认管理员 your-admin-name / your-admin-password。
    首次登录后请立即在管理面修改密码。"""
    if store.has_admin():
        return
    username = os.getenv("UMEKO_ADMIN_USERNAME", "umeko")
    password = os.getenv("UMEKO_ADMIN_PASSWORD", "1234")
    store.create_user(username, password, role="admin")
    logger.info(
        "已创建默认管理员账号：%s / %s（请尽快在管理面修改密码）", username, password
    )


def _serve_admin(app, host: str, port: int) -> None:
    import uvicorn

    uvicorn.run(app, host=host, port=port, log_level="warning")


def main() -> None:
    parser = argparse.ArgumentParser(prog="umeko.server", description="Umeko Web 工作台")
    parser.add_argument("--host", default="127.0.0.1", help="监听地址（默认 127.0.0.1）")
    parser.add_argument("--port", type=int, default=8000, help="监听端口（默认 8000）")
    parser.add_argument("--data-root", default=None, help="数据目录（覆盖 UMEKO_DATA_ROOT，默认 server_data）")
    parser.add_argument("--workspace-root", default="output", help="会话产物根目录")
    parser.add_argument("--env", default=None, help=".env 文件路径，默认 ./.env")
    parser.add_argument("--admin-host", default="127.0.0.1",
                        help="管理面监听地址（默认 127.0.0.1，云部署建议内网网卡）")
    parser.add_argument("--admin-port", type=int, default=9000, help="管理面端口（默认 9000）")
    parser.add_argument("--no-admin", action="store_true", help="不启动管理端口")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%H:%M:%S",
    )
    logger = logging.getLogger("umeko.server")
    from ..config import load_settings, model_config_unconfigured, resolve_env_path

    try:
        settings = load_settings(args.env, args.data_root)
    except RuntimeError as exc:
        print(exc, file=sys.stderr)
        sys.exit(1)

    # 首次运行：无 .env 时在 exe/项目目录生成模板，方便直接编辑（也可全走管理面配置）
    env_path = resolve_env_path(args.env)
    if model_config_unconfigured(settings) and not env_path.is_file():
        template = (
            "# 模型地址、密钥、模型名在管理面 Provider / Model 或 CLI 中配置。\n"
            "# 部署配置（修改后重启；本地开发前缀/CA 保持为空）\n"
            "UMEKO_BASE_PATH=\n"
            "MODEL_CA_FILE=\n"
            "UMEKO_DATA_ROOT=server_data\n"
        )
        try:
            env_path.write_text(template, encoding="utf-8")
            logger.info("检测到未配置模型：已生成 .env 模板（%s）", env_path)
            logger.info(
                "模型配置：打开管理面 "
                "http://%s:%d 用默认账号登录，在 Provider/Model 页添加",
                args.admin_host, args.admin_port,
            )
        except OSError:
            pass  # 只读目录等情况，跳过不影响启动

    import uvicorn

    from .app import create_app

    app = create_app(settings, data_root=args.data_root, workspace_root=args.workspace_root)

    if not args.no_admin:
        from .admin import create_admin_app

        store = app.state.store  # 与用户面共用同一 Store 实例（同一 SQLite）
        _bootstrap_admin(store, logger)
        admin_app = create_admin_app(settings, app.state.agent_service, store)
        threading.Thread(
            target=_serve_admin,
            args=(admin_app, args.admin_host, args.admin_port),
            daemon=True,
        ).start()
        logger.info("管理面：http://%s:%d（仅管理员，用户面无入口）",
                    args.admin_host, args.admin_port)

    uvicorn.run(app, host=args.host, port=args.port, log_level="info",
                root_path=settings.base_path)


if __name__ == "__main__":
    main()
