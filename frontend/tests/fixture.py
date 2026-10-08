"""Isolated browser-test server. Never loads .env or calls a model provider."""

import argparse
import json
from pathlib import Path
import secrets
import threading
import time

import uvicorn

from umeko.config import ModelConfig, Settings
from umeko.host import service as service_module
from umeko.server import admin as admin_module
from umeko.server.app import create_app
from umeko.skills import script_runner


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--admin-port", type=int, required=True)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--prefix", default="")
    args = parser.parse_args()
    directory = args.directory.resolve()
    # Skill source writes stay in the test directory, including Python scripts.
    admin_module.app_dir = lambda: directory
    service_module.app_dir = lambda: directory
    script_runner.skill_packs_dir = lambda: directory / "skills"
    settings = Settings(ModelConfig("fixture-text", "fixture-only", "https://example.invalid/v1"),
                        base_path=args.prefix)
    app = create_app(settings, data_root=directory / "data", workspace_root=directory / "output")
    service, store = app.state.agent_service, app.state.store
    password = secrets.token_urlsafe(20)
    user = store.create_user("ui-admin", password, role="admin")
    provider = store.create_provider("FixtureProvider", "https://example.invalid/v1", "fixture-only")
    text = store.add_model(provider["id"], "fixture-text", False)
    vision = store.add_model(provider["id"], "fixture-vision", True)
    store.set_active_model(text["id"])
    service.reload_config()

    def execute(session, run, user_input, paths):
        """Exercise real Run, persistence and SSE transport with deterministic events."""
        with session.lock:
            run.status = "running"
            run.emit("run.started")
            try:
                if "STOP_TEST" in user_input:
                    for _ in range(200):
                        if run.cancel_requested():
                            store.add_message(session.id, "assistant", "任务已停止。")
                            run.finish("cancelled", reply="任务已停止。")
                            return
                        time.sleep(.05)
                    raise AssertionError("Cancellation did not arrive")
                for i in range(20):
                    arguments = json.dumps({"index": i})
                    run.emit("tool.started", name="fixture_tool", arguments=arguments)
                    event_id = store.add_tool_event(session.id, "main", "fixture_tool",
                                                    arguments=arguments, run_id=run.id)
                    time.sleep(.06)
                    result = json.dumps({"ok": True, "index": i})
                    store.complete_tool_event(event_id, result)
                    run.emit("tool.completed", name="fixture_tool", result=result)
                for text in ("STREAM_", "UI_", "OK"):
                    run.emit("assistant.delta", text=text)
                    time.sleep(.3)
                store.add_message(session.id, "assistant", "STREAM_UI_OK")
                run.finish("completed", reply="STREAM_UI_OK")
            except Exception as exc:
                run.finish("failed", error=str(exc))
            finally:
                session.active_run_holder["run"] = None

    service._execute_run = execute
    admin_app = admin_module.create_admin_app(settings, service, store,
                                             public_url=f"http://127.0.0.1:{args.port}{args.prefix}")
    (directory / "state.json").write_text(json.dumps({
        "username": user["username"], "password": password,
        "text_model": text["id"], "vision_model": vision["id"],
    }), encoding="utf-8")
    threading.Thread(target=lambda: uvicorn.run(admin_app, host="127.0.0.1", port=args.admin_port,
                                               log_level="error"), daemon=True).start()
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="error")


if __name__ == "__main__":
    main()
