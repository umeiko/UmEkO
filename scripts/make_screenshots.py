"""README 截图生成：登录页 / 工作台（带对话与工具调用）/ 管理控制台。"""

from __future__ import annotations

import json
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8000"
ADMIN = "http://127.0.0.1:9000"
OUT = Path(__file__).resolve().parents[1] / "docs" / "screenshots"
OUT.mkdir(parents=True, exist_ok=True)
VIEW = {"width": 1440, "height": 900}


def api(path: str, cookie: str = "", payload: dict | None = None, method: str = "GET"):
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={"Content-Type": "application/json", **({"Cookie": cookie} if cookie else {})},
        method=method,
    )
    resp = urllib.request.urlopen(req)
    set_cookie = resp.headers.get("Set-Cookie", "").split(";")[0]
    return set_cookie, json.loads(resp.read() or b"{}")


def main() -> None:
    # 准备演示数据：登录 demo，建 session、造文件
    cookie, _ = api("/v1/auth/login", payload={"username": "demo", "password": "demo12345"}, method="POST")
    _, session = api("/v1/sessions", cookie, {}, method="POST")
    sid = session["id"]
    # 演示文件：让文件树和预览不空
    demo_files = {
        "workspace/quarterly-report.md": "# Q3 Report\n\n- revenue: +12%\n- churn: 2.1%\n",
        "workspace/architecture.md": "# Architecture notes\n\nFour-layer kernel.\n",
        "workspace/metrics.csv": "date,mau,retention\n2026-07,12400,0.41\n2026-08,13950,0.44\n",
    }
    import urllib.parse
    for rel, content in demo_files.items():
        name = urllib.parse.quote(Path(rel).name)
        req = urllib.request.Request(
            f"{BASE}/v1/sessions/{sid}/workspace/files?filename={name}",
            data=content.encode(), headers={"Content-Type": "application/octet-stream", "Cookie": cookie},
            method="POST",
        )
        urllib.request.urlopen(req)
    api(f"/v1/sessions/{sid}/title", cookie, {"title": "Quarterly report analysis"}, method="PATCH")

    with sync_playwright() as p:
        browser = p.chromium.launch()

        # ---- 1. 登录页 ----
        ctx = browser.new_context(viewport=VIEW, device_scale_factor=2)
        page = ctx.new_page()
        page.goto(BASE, wait_until="networkidle")
        time.sleep(1.2)
        page.screenshot(path=OUT / "login.png")
        ctx.close()

        # ---- 2. 工作台 ----
        ctx = browser.new_context(viewport=VIEW, device_scale_factor=2)
        page = ctx.new_page()
        page.add_init_script(f"localStorage.setItem('umeko:last-session', '{sid}');")
        page.goto(BASE, wait_until="networkidle")
        page.wait_for_timeout(800)
        if page.locator("#auth-dialog[open]").count():
            page.fill("#auth-username", "demo")
            page.fill("#auth-password", "demo12345")
            page.click("#auth-form button.attach-button")
            page.wait_for_timeout(2500)
        # 展开文件树根目录，让演示文件可见
        for summary in page.locator(".tree-dir > summary").all():
            summary.click()
            page.wait_for_timeout(250)
        page.wait_for_timeout(800)
        page.screenshot(path=OUT / "workspace.png")
        ctx.close()

        # ---- 3. 管理控制台 ----
        ctx = browser.new_context(viewport=VIEW, device_scale_factor=2)
        page = ctx.new_page()
        page.goto(ADMIN + '/?t=' + str(int(time.time())), wait_until="networkidle")
        page.wait_for_timeout(800)
        if page.locator("#login").is_visible():
            import os
            page.fill("#l-user", os.environ.get("UMEKO_SHOT_USER", "admin"))
            page.fill("#l-pass", os.environ.get("UMEKO_SHOT_PASS", "admin"))
            page.click("#login button.attach-button")
            page.wait_for_timeout(2000)
        time.sleep(1)
        # 切到 Provider/Model 页签更有代表性
        try:
            page.click("#tab-config")
            page.wait_for_timeout(1200)
        except Exception:
            pass
        # 演示化：遮蔽真实网关地址，换成示例 URL
        page.evaluate(
            """
            () => {
              document.querySelectorAll('.p-sub').forEach(el => {
                const text = el.textContent;
                const idx = text.indexOf('apigateway');
                if (idx >= 0) {
                  el.textContent = 'https://api.example.com/v1 · 1 个模型';
                }
              });
            }
            """
        )
        page.wait_for_timeout(300)
        page.wait_for_timeout(300)
        print('P-SUB 文本:', page.evaluate("""() => Array.from(document.querySelectorAll('.p-sub')).map(e => e.textContent)"""))
        page.screenshot(path=OUT / "admin.png")
        ctx.close()

        browser.close()

    # 清理演示 session
    req = urllib.request.Request(f"{BASE}/v1/sessions/{sid}", headers={"Cookie": cookie}, method="DELETE")
    urllib.request.urlopen(req)
    print("截图完成:", [p.name for p in OUT.glob("*.png")])


if __name__ == "__main__":
    main()
