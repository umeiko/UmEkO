"""端到端质检实测：造 session + 图 + 文档，发起 doc-image-qc 流水线。"""

import json
import time
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw

BASE = "http://127.0.0.1:8000"
TMP = Path(r"C:\Users\admin\AppData\Local\Temp")


def api(path, cookie="", payload=None, method="GET", data=None, ctype="application/json"):
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(payload).encode() if payload is not None else data,
        headers={"Content-Type": ctype, **({"Cookie": cookie} if cookie else {})},
        method=method,
    )
    resp = urllib.request.urlopen(req)
    return resp.headers.get("Set-Cookie", "").split(";")[0], json.loads(resp.read() or b"{}")


def main():
    cookie, _ = api("/v1/auth/login", payload={"username": "demo", "password": "demo12345"}, method="POST")
    _, session = api("/v1/sessions", cookie, {}, method="POST")
    sid = session["id"]
    print("SID:", sid)

    # 造图
    img = Image.new("RGB", (400, 200), "white")
    d = ImageDraw.Draw(img)
    d.rectangle([20, 60, 120, 140], outline="black", width=2)
    d.text((40, 90), "Client", fill="black")
    d.rectangle([280, 60, 380, 140], outline="black", width=2)
    d.text((300, 90), "Server", fill="black")
    d.line([120, 100, 280, 100], fill="black", width=2)
    arch = TMP / "qc-arch.png"
    img.save(arch)

    img2 = Image.new("RGB", (400, 100), "#1e1e1e")
    d2 = ImageDraw.Draw(img2)
    d2.text((10, 10), r"PS C:\proj> python app.py", fill="white")
    d2.text((10, 40), "Server running on port 8000", fill="lightgreen")
    term = TMP / "qc-term.png"
    img2.save(term)

    for f in (arch, term):
        api(f"/v1/sessions/{sid}/workspace/files?filename={f.name}", cookie,
            data=f.read_bytes(), ctype="application/octet-stream", method="POST")

    doc = (
        "# 系统设计文档\n\n"
        "## 架构\n系统采用客户端-服务端架构，如图1所示：\n\n"
        "![系统架构图](qc-arch.png)\n\n"
        "图1 展示了 Client 通过网络连接 Server 的整体结构。\n\n"
        "## 部署\n启动命令截图如下：\n\n"
        "![终端截图](qc-term.png)\n\n"
        "截图显示服务在 8000 端口启动。\n"
    )
    api(f"/v1/sessions/{sid}/workspace/files?filename=design-doc.md", cookie,
        data=doc.encode(), ctype="text/markdown", method="POST")
    print("素材就绪")

    # 发起质检（引用 skill）
    prompt = (
        "use_skill doc-image-qc 然后按其指引，"
        "对 workspace/design-doc.md 执行图片质检流水线，"
        "完成后给我统计结论。"
    )
    payload = json.dumps({"input": prompt}).encode()
    req = urllib.request.Request(
        f"{BASE}/v1/sessions/{sid}/runs", data=payload,
        headers={"Content-Type": "application/json", "Cookie": cookie}, method="POST")
    run = json.loads(urllib.request.urlopen(req).read())
    print("run:", run["id"], run["status"])

    # 轮询 tool_events 看流水线进展
    for i in range(30):
        time.sleep(15)
        try:
            req = urllib.request.Request(f"{BASE}/v1/sessions/{sid}/tool-events",
                                         headers={"Cookie": cookie})
            events = json.loads(urllib.request.urlopen(req).read())
            print(f"[{i*15}s] 事件数: {len(events)} | 最近:",
                  [f"{e['agent']}/{e['name']}" for e in events[-3:]])
        except Exception as e:
            print("poll error:", e)
        # 查活跃 run
        try:
            req = urllib.request.Request(f"{BASE}/v1/sessions/{sid}/active-run",
                                         headers={"Cookie": cookie})
            active = json.loads(urllib.request.urlopen(req).read())
            if active is None:
                print("run 已结束")
                break
        except Exception:
            pass

    # 消息与产物
    _, msgs = api(f"/v1/sessions/{sid}/messages", cookie)
    print("\n== 最后一条 assistant ==")
    for m in reversed(msgs):
        if m["role"] == "assistant":
            print(m["content"][:600])
            break

    # 产物文件
    import sqlite3
    from umeko.runtime import app_dir
    # 直接从文件系统找 qc-*.md
    root = Path(r"D:\Users\admin\Desktop\文档图像质检Agent\UmEkO\server_data\users")
    for name in ("qc-manifest.md", "qc-report.md", "qc-summary.md"):
        hits = list(root.rglob(name))
        for h in hits:
            if sid in str(h):
                print(f"\n== {name} ({h.stat().st_size}B) ==")
                print(h.read_text(encoding="utf-8")[:500])

    # 清理
    api(f"/v1/sessions/{sid}", cookie, method="DELETE")
    print("\n测试 session 已清理")


if __name__ == "__main__":
    main()
