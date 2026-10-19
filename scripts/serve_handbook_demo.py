"""Isolated synthetic data for handbook screenshots; never load .env or a real model.

Run from the repository with the server dependencies installed. The generated
sign-in state stays under ignored smoke/; no credential belongs in the handbook.
"""
from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import secrets
import sys
import tempfile
import threading

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import uvicorn
from umeko.agent import UmekoAgent
from umeko.config import ModelConfig, Settings
from umeko.host.identities import SCOPES
from umeko.server.app import create_app
from umeko.server.admin import create_admin_app
from umeko.server import admin as admin_module
from umeko.server.__main__ import _serve_admin


def main():
    with tempfile.TemporaryDirectory(prefix="umeko-handbook-demo-") as temporary:
        folder = Path(temporary)
        os.environ["UMEKO_SKILL_DIR"] = str(folder / "skills")
        settings = Settings(ModelConfig("demo", "synthetic", "https://models.example.invalid/v1"),
                            base_path="/teams/demo", admin_base_path="/operations/guide",
                            public_url="https://agents.example.internal/teams/demo")
        app = create_app(settings, data_root=folder / "data", workspace_root=folder / "output")
        # Keep demonstration sign-in independent from another local deployment.
        admin_module.ADMIN_COOKIE = "umeko_handbook_demo"
        service, store = app.state.agent_service, app.state.store
        real_snapshot = service.resource_monitor.snapshot

        def synthetic_snapshot():
            snapshot = real_snapshot()
            for sample in [snapshot["current"], *snapshot["history"]]:
                sample["host"] = {"cpu_percent": 12, "cpu_count": 8,
                    "memory_total": 16 * 1024**3, "memory_used": 4 * 1024**3, "memory_percent": 25,
                    "disk_total": 100 * 1024**3, "disk_used": 30 * 1024**3,
                    "disk_free": 70 * 1024**3, "disk_percent": 30}
                sample["process"] = {"pid": 1001, "cpu_percent": 3, "memory_rss": 256 * 1024**2, "threads": 8}
                sample["uptime_seconds"] = 600
            return snapshot

        service.resource_monitor.snapshot = synthetic_snapshot
        password = secrets.token_urlsafe(20)
        admin = store.create_user("guide-admin", password, role="admin")
        store.create_user("demo-reader", secrets.token_urlsafe(20))
        provider = store.create_provider("示例模型服务", "https://models.example.invalid/v1", "synthetic-demo-key")
        model = store.add_model(provider["id"], "general-chat", False)
        vision = store.add_model(provider["id"], "vision-instruct", True)
        store.update_model(model["id"], max_concurrent_requests=2)
        store.update_model(vision["id"], max_concurrent_requests=1)
        store.set_active_model(model["id"])
        store.set_config({"SUB_MODEL_ID": model["id"], "VISION_MODEL_ID": vision["id"]})
        service.reload_config()
        account = service.identity_store.create("文档演示调用方", sorted(SCOPES))
        definition = service.agent_registry.save({"slug": "reviewer", "name": "资料检查助手",
            "description": "检查用户提供的图片与文档，给出有依据的问题清单和改进建议。",
            "system_prompt": "按用户要求检查资料，明确检查范围、证据与无法核对的项目。",
            "skill_names": ["doc-image-qc.md"], "default_model_id": model["id"],
            "default_vision_model_id": vision["id"]})

        def chat(agent, prompt, images=None):
            with store.connect() as db:
                row = db.execute("SELECT session_id FROM service_tasks WHERE session_id IS NOT NULL ORDER BY created_at DESC LIMIT 1").fetchone()
            if row:
                store.add_tool_event(row["session_id"], "main", "list_dir", '{"directory":"attachments"}',
                                     "attachments/\n└── requirements.md (104 B)")
            text = "## 检查结论\n\n已核对示例材料中的目标、输入与交付要求。\n\n- 检查范围：资料结构与说明完整性。\n- 发现 1 项待补充：请说明报告的目标读者。\n- 未对没有提供的图片内容作推断。"
            (agent._output_root / "generate/check-report.md").write_text(text, encoding="utf-8")
            agent._on_event("assistant.delta", {"text": text})
            agent._skills["submit_results"].handler(text=text, files=[{"path": "generate/check-report.md", "description": "示例检查报告"}])
            return text
        UmekoAgent.chat = chat
        principal = {**service.identity_store.authenticate(account["token"]), "agent_id": definition["id"], "agent_definition": definition}
        task = service.task_service.submit(principal, {"prompt": "请核对资料中的任务目标与交付要求，整理检查清单。",
            "files": [{"name": "requirements.md", "content_base64": base64.b64encode("# 示例任务\n核对说明是否完整，并给出可执行的改进建议。".encode()).decode()}]}, source="mcp", caller_ip="192.0.2.15")
        service.task_service.submit(principal, {"prompt": "请根据示例说明生成简短的审查摘要。"}, source="a2a", caller_ip="192.0.2.20")
        state = ROOT / "smoke/handbook-demo.local.json"
        state.parent.mkdir(exist_ok=True)
        state.write_text(json.dumps({"username": admin["username"], "password": password,
                                     "task_id": task["id"], "agent_id": definition["id"]}), encoding="utf-8")
        admin_app = create_admin_app(settings, service, store)
        threading.Thread(target=_serve_admin, args=(admin_app, "127.0.0.1", 19008), daemon=True).start()
        uvicorn.run(app, host="127.0.0.1", port=18008, log_level="error", root_path=settings.base_path)


if __name__ == "__main__":
    main()
