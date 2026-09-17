"""拖拽/右键菜单实测：Playwright 模拟文件拖入目录、检查菜单禁用态与 hover。"""

from __future__ import annotations

import json
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8000"


def api(path, cookie="", payload=None, method="GET"):
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={"Content-Type": "application/json", **({"Cookie": cookie} if cookie else {})},
        method=method,
    )
    resp = urllib.request.urlopen(req)
    return resp.headers.get("Set-Cookie", "").split(";")[0], json.loads(resp.read() or b"{}")


def main():
    cookie, _ = api("/v1/auth/login", payload={"username": "demo", "password": "demo12345"}, method="POST")
    _, session = api("/v1/sessions", cookie, {}, method="POST")
    sid = session["id"]
    # 造子目录 + 一个文件
    api(f"/v1/sessions/{sid}/workspace/entries", cookie, {"path": "workspace/target-dir", "type": "directory"}, "POST")
    req = urllib.request.Request(
        f"{BASE}/v1/sessions/{sid}/workspace/files?filename=note.txt",
        data=b"hi", headers={"Content-Type": "text/plain", "Cookie": cookie}, method="POST")
    urllib.request.urlopen(req)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()
        errors = []
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.add_init_script(f"localStorage.setItem('umeko:last-session', '{sid}');")
        page.goto(BASE, wait_until="networkidle")
        page.wait_for_timeout(1200)
        if page.locator("#auth-dialog[open]").count():
            page.fill("#auth-username", "demo")
            page.fill("#auth-password", "demo12345")
            page.click("#auth-form button.attach-button")
            page.wait_for_timeout(2500)

        # 展开树：JS 直接展开所有 details（避免 click toggle 竞态）
        page.evaluate("() => document.querySelectorAll('.file-tree details.tree-dir').forEach(d => d.open = true)")
        page.wait_for_timeout(800)

        # 1. 内部拖拽：note.txt → target-dir
        src = page.locator(".tree-file", has_text="note.txt").first
        dst = page.locator(".tree-dir > summary", has_text="target-dir").first
        src.hover()
        page.wait_for_timeout(200)
        src.drag_to(dst)
        page.wait_for_timeout(1500)
        moved = page.locator(".tree-dir > summary", has_text="target-dir").first
        moved.click()
        page.wait_for_timeout(600)
        in_dir = page.locator(".tree-file", has_text="note.txt").count()
        print(f"1. 内部拖拽 note.txt → target-dir: {'OK' if in_dir else 'FAIL'}")

        # 2. hover 高亮检查
        summary = page.locator(".tree-dir > summary", has_text="target-dir").first
        summary.hover()
        page.wait_for_timeout(300)
        bg = summary.evaluate("el => getComputedStyle(el).backgroundColor")
        print(f"2. 目录 hover 背景: {bg}（非 transparent=有高亮）")

        # 3. 右键子目录 → 删除按钮是否禁用
        summary.click(button="right")
        page.wait_for_timeout(500)
        disabled = page.locator("#file-context-menu button[data-file-action='delete']").is_disabled()
        print(f"3. 子目录右键删除禁用: {disabled}（False=可删，正确）")
        page.keyboard.press("Escape")

        # 4. 右键 workspace 根 → 删除应禁用
        root_summary = page.locator(".tree-dir > summary", has_text="workspace").first
        root_summary.click(button="right")
        page.wait_for_timeout(500)
        disabled_root = page.locator("#file-context-menu button[data-file-action='delete']").is_disabled()
        print(f"4. 根目录右键删除禁用: {disabled_root}（True=正确保护）")
        page.keyboard.press("Escape")

        # 5. 外部文件拖入（DataTransfer 模拟）
        dropped = page.evaluate("""
        async () => {
          const summary = [...document.querySelectorAll('.tree-dir > summary')]
            .find(s => s.textContent.includes('target-dir'));
          if (!summary) return 'no-summary';
          const dt = new DataTransfer();
          const file = new File(['dropped-content'], 'dropped.txt', {type: 'text/plain'});
          dt.items.add(file);
          summary.dispatchEvent(new DragEvent('dragover', {dataTransfer: dt, bubbles: true, cancelable: true}));
          summary.dispatchEvent(new DragEvent('drop', {dataTransfer: dt, bubbles: true, cancelable: true}));
          return 'dispatched';
        }
        """)
        page.wait_for_timeout(2000)
        ok = page.locator(".tree-file", has_text="dropped.txt").count()
        print(f"5. 外部文件模拟拖入 target-dir: dispatch={dropped}, 出现在树上: {bool(ok)}")

        if errors:
            print("Console errors:", errors[:3])
        browser.close()

    api(f"/v1/sessions/{sid}", cookie, method="DELETE")


if __name__ == "__main__":
    main()
