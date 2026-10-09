"""Capture the real UI with an isolated English demo; no .env or model calls.

Run with a Python environment containing the server extra and Playwright:
    python scripts/make_screenshots.py
    python scripts/make_screenshots.py --output path/to/screenshots
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import socket
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Prefer this checkout even when the environment has another Umeko installation.
sys.path.insert(0, str(ROOT))
VIEW = {"width": 1440, "height": 960}
PROMPT = (
    "Review the Q3 report against metrics.csv and the release notes. "
    "Check the figures, flag anything that needs attention, and save a review."
)
SOURCE = """# Q3 product report

Revenue increased from $2.40M to $2.688M (+12%). Monthly active users grew
from 12,800 to 14,400 (+12.5%). Customer retention remained at 92%.

## Release readiness

- Reporting dashboard: ready
- Data export: ready
- Renewal assumptions: owner still to be assigned
"""
METRICS = "quarter,revenue_usd,active_users,retention\nQ2,2400000,12800,0.92\nQ3,2688000,14400,0.92\n"
REVIEW = """# Q3 report review

**Ready with one follow-up** · 3 source files reviewed

## Validation

| Check | Result | Evidence |
| --- | --- | --- |
| Revenue growth | Pass | +12.0% |
| Active users | Pass | +12.5% |
| Retention | Pass | 92%, unchanged |
| Renewal owner | Follow-up | Not assigned |

## Reproducible check

```python
previous, current = 2_400_000, 2_688_000
growth = (current / previous - 1) * 100
print(f"Revenue growth: {growth:.1f}%")
```

## Before publishing

1. Assign an owner for renewal assumptions.
2. Confirm the assumptions with the finance team.

Source: `q3-report.md`, `metrics.csv`, `release-notes.md`.
"""
REPLY = """### Review complete

**The figures are consistent.** Revenue grew **12%**, active users rose **12.5%**, and retention stayed at **92%**.

- Checked the report against the source metrics and release notes.
- **One follow-up:** assign an owner for renewal assumptions.
- Saved a readable review and a machine-readable checklist.

[Open review](workspace-file:generate%2Freview.md) · [Open checklist](workspace-file:generate%2Fchecklist.json)
"""


def free_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def demo_apps(directory: Path, port: int):
    # Set the skill library before importing the host, and never load_settings().
    os.environ["UMEKO_SKILL_DIR"] = str(directory / "skills")
    from umeko.config import ModelConfig, Settings
    from umeko.server.admin import create_admin_app
    from umeko.server.app import create_app

    settings = Settings(ModelConfig("demo-text", "offline-demo", "https://example.invalid/v1"))
    app = create_app(settings, data_root=directory / "data", workspace_root=directory / "output")
    service, store = app.state.agent_service, app.state.store
    password = secrets.token_urlsafe(24)
    user = store.create_user("alex", password)
    store.create_user("demo-admin", password, role="admin")
    provider = store.create_provider("Demo provider", "https://example.invalid/v1", "offline-demo")
    text = store.add_model(provider["id"], "demo-text", max_concurrent_requests=4)
    store.add_model(provider["id"], "demo-vision", vision=True, max_concurrent_requests=2)
    store.set_active_model(text["id"])
    service.reload_config()
    session = service.create_session(user_id=user["id"], title="Q3 report review")
    for name, content in {
        "q3-report.md": SOURCE,
        "metrics.csv": METRICS,
        "release-notes.md": "# Release notes\n\nDashboard and data export are ready.\nRenewal assumptions need an owner.\n",
    }.items():
        (session.root / "workspace" / name).write_text(content, encoding="utf-8")

    def execute(state, run, user_input, paths):
        """Deterministic demo events through the real persistence and SSE paths."""
        with state.lock:
            run.status = "running"
            run.emit("run.started")
            try:
                checklist = json.dumps({"status": "follow-up", "revenue_growth_pct": 12.0,
                                        "active_user_growth_pct": 12.5,
                                        "follow_up": "Assign renewal owner"}, indent=2)
                tools = [
                    ("read_document", {"path": "workspace/q3-report.md"}, SOURCE),
                    ("read_document", {"path": "workspace/metrics.csv"}, METRICS),
                    ("read_document", {"path": "workspace/release-notes.md"}, "Renewal owner not assigned."),
                    ("write_file", {"path": "generate/review.md"}, "Saved generate/review.md"),
                    ("write_file", {"path": "generate/checklist.json"}, "Saved generate/checklist.json"),
                ]
                for name, params, result in tools:
                    arguments = json.dumps(params)
                    event = store.add_tool_event(state.id, "main", name,
                                                 arguments=json.dumps(arguments), run_id=run.id)
                    run.emit("tool.started", name=name, arguments=arguments)
                    time.sleep(.15)
                    if params["path"] == "generate/review.md":
                        (state.root / params["path"]).write_text(REVIEW, encoding="utf-8")
                    elif params["path"] == "generate/checklist.json":
                        (state.root / params["path"]).write_text(checklist, encoding="utf-8")
                    store.complete_tool_event(event, json.dumps(result))
                    run.emit("tool.completed", name=name, result=result)
                for start in range(0, len(REPLY), 100):
                    run.emit("assistant.delta", text=REPLY[start:start + 100])
                    time.sleep(.1)
                store.add_message(state.id, "assistant", REPLY)
                run.finish("completed", reply=REPLY)
            except Exception as exc:
                run.finish("failed", error=str(exc))
            finally:
                state.active_run_holder["run"] = None

    service._execute_run = execute
    admin = create_admin_app(settings, service, store, public_url=f"http://127.0.0.1:{port}")
    return app, admin, session.id, password


def capture(directory: Path, output: Path) -> None:
    import uvicorn
    from playwright.sync_api import sync_playwright

    port, admin_port = free_port(), free_port()
    app, admin, session_id, password = demo_apps(directory, port)
    servers = [uvicorn.Server(uvicorn.Config(application, host="127.0.0.1", port=p,
                                           log_level="error"))
               for application, p in ((app, port), (admin, admin_port))]
    threads = [threading.Thread(target=server.run, daemon=True) for server in servers]
    try:
        for thread in threads:
            thread.start()
        deadline = time.monotonic() + 20
        while not all(server.started for server in servers):
            if time.monotonic() > deadline or not all(thread.is_alive() for thread in threads):
                raise RuntimeError("Demo server did not start")
            time.sleep(.1)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            context = browser.new_context(viewport=VIEW, device_scale_factor=2, locale="en-US")
            context.add_init_script(
                "localStorage.setItem('umeko:locale', 'en');"
                "localStorage.setItem('umeko:theme', 'dark');"
                f"localStorage.setItem('umeko:last-session', {json.dumps(session_id)});"
            )
            page = context.new_page()
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(f"http://127.0.0.1:{port}/")
            page.locator("#auth-dialog[open]").wait_for()
            page.screenshot(path=output / "login.png")
            page.locator("#auth-username").fill("alex")
            page.locator("#auth-password").fill(password)
            page.locator("#auth-form button[type=submit]").click()
            page.locator("#status-dot.ready").wait_for()
            page.locator("#prompt").fill(PROMPT)
            page.locator("#send").click()
            page.locator("#messages").get_by_text("Review complete", exact=True).wait_for()
            page.locator("#stop").wait_for(state="hidden")
            # Replay the persisted conversation, which also omits the empty-session greeting.
            page.reload()
            page.locator("#status-dot.ready").wait_for()
            page.locator('.tree-file[data-path="generate/review.md"]').click()
            page.locator("#markdown-view h1").get_by_text("Q3 report review", exact=True).wait_for()
            # Use the same resize controls available to users, with space for both panels.
            page.locator("#left-resizer").focus()
            for _ in range(2):
                page.keyboard.press("ArrowLeft")
            page.locator("#right-resizer").focus()
            for _ in range(9):
                page.keyboard.press("ArrowRight")
            page.mouse.click(800, 30)
            page.locator("#messages").evaluate("el => { el.scrollTop = 0; }")
            page.evaluate("document.fonts.ready")
            assert page.locator("html").get_attribute("lang") == "en"
            assert page.locator("#send").inner_text() == "Send"
            assert page.locator(".workbench-label").inner_text() == "Workbench"
            assert page.locator(".tool-history-list .agent-action").count() == 5
            assert page.locator("#markdown-view pre code").count() == 1
            assert not errors, errors
            for theme, name in (("dark", "workspace.png"), ("light", "workspace-light.png")):
                if page.locator("html").get_attribute("data-theme") != theme:
                    page.locator("[data-theme-toggle]").first.click()
                page.wait_for_timeout(250)
                page.screenshot(path=output / name)

            admin_page = context.new_page()
            admin_page.goto(f"http://127.0.0.1:{admin_port}/")
            admin_page.locator("#l-user").fill("demo-admin")
            admin_page.locator("#l-pass").fill(password)
            admin_page.locator(".login-card button.primary").click()
            admin_page.locator("#tab-providers").click()
            admin_page.locator("#pd-name").wait_for()
            admin_page.get_by_text("demo-vision", exact=True).wait_for()
            admin_page.evaluate("document.fonts.ready")
            admin_page.screenshot(path=output / "admin.png")
            context.close()
            browser.close()
    finally:
        for server in servers:
            server.should_exit = True
        for thread in threads:
            if thread.is_alive():
                thread.join(timeout=10)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "docs" / "screenshots")
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="umeko-showcase-") as directory:
        capture(Path(directory), output)
    print("Captured: workspace.png, workspace-light.png, admin.png, login.png")


if __name__ == "__main__":
    main()
