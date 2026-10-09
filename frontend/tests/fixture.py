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

MARKDOWN_SAMPLE = '''# 质检图片清单

本轮 **检查已完成**，以下是整理后的结果。

## 检查范围

- **图片路径**：`workspace/fig7_2.png`
- **来源**：用户上传的截图
  - 检查文字清晰度
  - 核对内容一致性

| 项目 | 结果 | 备注 |
| --- | --- | --- |
| 文字清晰度 | 通过 | 字体可辨认 |
| 内容一致性 | 通过 | 与说明一致 |

> 可以在右侧切换预览与原文，文件链接会打开对应内容。

## Python 示例

```python
def greet(name):
    print(f"Hello, {name}!")

greet("世界")
```

查看[数据表](workspace-file:attachments%2Ftable.csv)。
'''


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
    text = store.add_model(provider["id"],
                           "fixture-model-for-document-and-image-consistency-with-a-long-name", False)
    vision = store.add_model(provider["id"], "fixture-vision", True)
    store.set_active_model(text["id"])
    service.reload_config()

    def execute(session, run, user_input, paths):
        """Exercise real Run, persistence and SSE transport with deterministic events."""
        with session.lock:
            run.status = "running"
            run.emit("run.started")
            try:
                if "MARKDOWN_TEST" in user_input:
                    chunks = (MARKDOWN_SAMPLE[:120], MARKDOWN_SAMPLE[120:380], MARKDOWN_SAMPLE[380:])
                    for chunk in chunks:
                        run.emit("assistant.delta", text=chunk)
                        time.sleep(.7)
                    store.add_message(session.id, "assistant", MARKDOWN_SAMPLE)
                    run.finish("completed", reply=MARKDOWN_SAMPLE)
                    return
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
                    time.sleep(.7)
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
        "markdown_sample": MARKDOWN_SAMPLE,
    }), encoding="utf-8")
    threading.Thread(target=lambda: uvicorn.run(admin_app, host="127.0.0.1", port=args.admin_port,
                                               log_level="error"), daemon=True).start()
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="error")


if __name__ == "__main__":
    main()
