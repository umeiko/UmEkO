"""Web 工作台入口：python -m umeko.server [--host 0.0.0.0] [--port 8000]

云模式默认同时启动管理面（独立端口，用户面不含任何 /admin 路由）：
- 管理面默认监听 127.0.0.1:9000，仅管理员（users.role='admin'）可登录；
- 首个管理员通过环境变量引导创建：
    UMEKO_ADMIN_USERNAME（默认 admin） + UMEKO_ADMIN_PASSWORD
- 用 --no-admin 可关闭管理端口。
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import threading
from pathlib import Path


def _bootstrap_admin(store, logger: logging.Logger) -> None:
    """没有任何管理员时：环境变量优先，否则创建默认管理员 umeko/1234。
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
    parser.add_argument("--data-root", default="server_data", help="服务端数据目录")
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
    from ..config import load_settings, model_config_unconfigured
    from ..runtime import app_dir

    try:
        settings = load_settings(args.env)
    except RuntimeError as exc:
        print(exc, file=sys.stderr)
        sys.exit(1)

    # 首次运行：无 .env 时在 exe/项目目录生成模板，方便直接编辑（也可全走管理面配置）
    env_path = Path(args.env) if args.env else app_dir() / ".env"
    if model_config_unconfigured(settings) and not env_path.is_file():
        template = (
            "# UMEKO 配置模板——也可不改此文件，直接在管理面（默认 9000 端口）"
            "的 Provider/Model 页配置模型\n"
            "# 主模型（OpenAI 兼容）\n"
            "# TEXT_MODEL_NAME=your-model\n"
            "# TEXT_MODEL_BASE_URL=https://api.example.com/v1\n"
            "# TEXT_MODEL_API_KEY=sk-xxx\n"
            "# 可选：视觉模型（启用 image_reasoning）\n"
            "# VISION_MODEL_NAME=your-vision-model\n"
            "# VISION_MODEL_API_KEY=sk-xxx\n"
            "# VISION_MODEL_BASE_URL=https://api.example.com/v1\n"
        )
        try:
            env_path.write_text(template, encoding="utf-8")
            logger.info("检测到未配置模型：已生成 .env 模板（%s）", env_path)
            logger.info(
                "两种配置方式任选：1) 编辑 .env 后重启；2) 打开管理面 "
                "http://%s:%d 用默认账号登录，在 Provider/Model 页添加",
                args.admin_host, args.admin_port,
            )
        except OSError:
            pass  # 只读目录等情况，跳过不影响启动

    import uvicorn

    from ..host.storage import Store
    from .app import create_app

    app = create_app(settings, data_root=args.data_root, workspace_root=args.workspace_root)

    if not args.no_admin:
        from .admin import create_admin_app

        store = app.state.store  # 与用户面共用同一 Store 实例（同一 SQLite）
        _bootstrap_admin(store, logger)
        if store.seed_providers_from_settings(settings):
            logger.info("已用 .env 模型配置播种 Provider 注册表（default）")
        admin_app = create_admin_app(settings, app.state.agent_service, store)
        threading.Thread(
            target=_serve_admin,
            args=(admin_app, args.admin_host, args.admin_port),
            daemon=True,
        ).start()
        logger.info("管理面：http://%s:%d（仅管理员，用户面无入口）",
                    args.admin_host, args.admin_port)

    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
