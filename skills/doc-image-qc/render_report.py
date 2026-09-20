#!/usr/bin/env python
"""UMEKO 技能包脚本：doc-image-qc / render_report.py

【统一契约】（所有技能包脚本必须遵守）
- 输入：stdin 收一个 JSON 对象 {"args": {...}, "workdir": "<会话产物绝对路径>"}
- 输出：stdout 输出【一行】JSON：{"ok": true/false, "result": "...", "files": [...]}
        - result：给模型看的一段文字结论
        - files：产物文件列表（相对会话根的路径）
- 进度：stderr 可逐行输出进度文本（实时展示给用户），不计入结果
- 约束：不要读环境变量密钥、不要联网、不要写 workdir 之外的路径；
        超时（默认 60s）会被强制终止

本脚本：qc-report.json → qc-report.html（与被检 Markdown 同目录）
args: {"data_path": "<qc-report.json 的 Session 相对路径>",
       "doc_dir": "<被检 Markdown 所在的 Session 相对目录>"}
"""

from __future__ import annotations

import html
import json
import sys
from pathlib import Path


# ---------- 模板（与平台米纸绿墨风格一致） ----------

_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>图片质检报告 · {doc_name}</title>
<style>
  :root {{
    --paper: #f4f1e8; --panel: #fffdf7; --line: #d9d4c7;
    --ink: #21332d; --muted: #7a8a82; --accent: #087f68; --accent-dark: #056452;
    --pass: #087f68; --warn: #b8860b; --fail: #b3402a;
    --pass-bg: #edf7f3; --warn-bg: #faf3e0; --fail-bg: #f9ece9;
  }}
  * {{ box-sizing: border-box; margin: 0; }}
  body {{ background: var(--paper); color: var(--ink);
    font: 14px/1.65 "Inter", "Noto Sans SC", "Segoe UI", sans-serif; padding: 28px 20px 60px; }}
  .report {{ max-width: 1080px; margin: 0 auto; }}
  header {{ border-bottom: 2px solid var(--ink); padding-bottom: 16px; margin-bottom: 22px; }}
  .eyebrow {{ font: 700 11px/1 ui-monospace, monospace; letter-spacing: .18em;
    color: var(--accent); margin-bottom: 8px; }}
  h1 {{ font-size: 24px; font-weight: 700; letter-spacing: -.01em; }}
  .meta {{ display: flex; flex-wrap: wrap; gap: 6px 22px; margin-top: 10px;
    color: var(--muted); font-size: 12.5px; }}
  .meta b {{ color: var(--ink); font-weight: 600; }}
  .stats {{ display: grid; grid-template-columns: repeat(5, 1fr); gap: 12px; margin-bottom: 24px; }}
  .stat {{ background: var(--panel); border: 1px solid var(--line); border-radius: 10px;
    padding: 14px 16px; }}
  .stat .num {{ font-size: 26px; font-weight: 700; line-height: 1.2; }}
  .stat .label {{ color: var(--muted); font-size: 12px; margin-top: 2px; }}
  .stat.total .num {{ color: var(--ink); }}
  .stat.pass .num {{ color: var(--pass); }}
  .stat.warn .num {{ color: var(--warn); }}
  .stat.fail .num {{ color: var(--fail); }}
  .stat.other .num {{ color: var(--muted); }}
  .section {{ margin-bottom: 26px; }}
  .section > h2 {{ font-size: 16px; font-weight: 700; margin-bottom: 12px;
    padding-left: 10px; border-left: 3px solid var(--accent); }}
  .actions li {{ list-style: none; background: var(--panel); border: 1px solid var(--line);
    border-radius: 8px; padding: 10px 14px; margin-bottom: 8px; display: flex; gap: 10px; }}
  .actions .sev {{ flex: none; font-size: 11px; font-weight: 700; padding: 2px 8px;
    border-radius: 10px; margin-top: 2px; }}
  .sev.high {{ color: var(--fail); background: var(--fail-bg); }}
  .sev.mid {{ color: var(--warn); background: var(--warn-bg); }}
  .sev.low {{ color: var(--accent-dark); background: var(--pass-bg); }}
  .item {{ background: var(--panel); border: 1px solid var(--line); border-radius: 12px;
    padding: 16px 18px; margin-bottom: 14px; }}
  .item-head {{ display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }}
  .item-head .name {{ font: 600 14px ui-monospace, "Cascadia Code", monospace; }}
  .item-head .loc {{ color: var(--muted); font-size: 12px; }}
  .badge {{ font-size: 11px; font-weight: 700; padding: 2px 10px; border-radius: 10px; }}
  .badge.PASS {{ color: var(--pass); background: var(--pass-bg); border: 1px solid #087f6833; }}
  .badge.WARN {{ color: var(--warn); background: var(--warn-bg); border: 1px solid #b8860b33; }}
  .badge.FAIL {{ color: var(--fail); background: var(--fail-bg); border: 1px solid #b3402a33; }}
  .badge.MISSING, .badge.ERROR, .badge.SKIP {{ color: var(--muted); background: #f0ede4;
    border: 1px solid var(--line); }}
  .item-body {{ display: grid; grid-template-columns: 220px 1fr; gap: 16px; margin-top: 12px; }}
  @media (max-width: 720px) {{ .item-body {{ grid-template-columns: 1fr; }} }}
  .thumb {{ width: 220px; border: 1px solid var(--line); border-radius: 8px;
    background: #fff; padding: 6px; align-self: start; }}
  .thumb img {{ width: 100%; height: auto; border-radius: 4px; display: block; }}
  .thumb .noimg {{ color: var(--muted); font-size: 12px; text-align: center; padding: 28px 8px; }}
  .checks {{ display: grid; gap: 8px; align-content: start; }}
  .check {{ display: grid; grid-template-columns: 76px 1fr; gap: 8px; font-size: 13px; }}
  .check .k {{ color: var(--muted); }}
  .check .v.ok {{ color: var(--ink); }}
  .check .v.bad {{ color: var(--fail); font-weight: 600; }}
  .detail {{ margin-top: 4px; padding: 8px 12px; background: #f8f5ec; border-radius: 6px;
    font-size: 12.5px; color: #4a5a52; }}
  footer {{ margin-top: 34px; padding-top: 14px; border-top: 1px solid var(--line);
    color: var(--muted); font-size: 11.5px; display: flex; justify-content: space-between;
    flex-wrap: wrap; gap: 6px; }}
</style>
</head>
<body>
<div class="report">
  <header>
    <div class="eyebrow">IMAGE QC REPORT</div>
    <h1>图片质检报告 · {doc_name}</h1>
    <div class="meta">
      <span>源文档：<b>{document}</b></span>
      <span>检查时间：<b>{checked_at}</b></span>
      <span>视觉模型：<b>{vision_model}</b></span>
    </div>
  </header>
  {stats_html}
  {actions_html}
  {items_html}
  <footer>
    <span>UMEKO · doc-image-qc · 报告与源文档同级存放，图片为相对路径引用</span>
    <span>生成于 {checked_at} · 详尽数据见 qc-report.json</span>
  </footer>
</div>
</body>
</html>
"""

_SEV_ORDER = {"FAIL": "high", "WARN": "mid"}


def _esc(value):
    return html.escape(str(value or ""))


def _stats_html(counts):
    total = sum(counts.values())
    cells = [
        ('<div class="stat total"><div class="num">{}</div>'
         '<div class="label">图片总数</div></div>').format(total),
        ('<div class="stat pass"><div class="num">{}</div>'
         '<div class="label">PASS 通过</div></div>').format(counts.get("PASS", 0)),
        ('<div class="stat warn"><div class="num">{}</div>'
         '<div class="label">WARN 警告</div></div>').format(counts.get("WARN", 0)),
        ('<div class="stat fail"><div class="num">{}</div>'
         '<div class="label">FAIL 失败</div></div>').format(counts.get("FAIL", 0)),
        ('<div class="stat other"><div class="num">{}</div>'
         '<div class="label">缺失/跳过</div></div>').format(
            counts.get("MISSING", 0) + counts.get("ERROR", 0) + counts.get("SKIP", 0)),
    ]
    return '<div class="stats">{}</div>'.format("".join(cells))


def _actions_html(items):
    rows = []
    for item in items:
        status = item.get("status", "")
        if status not in _SEV_ORDER:
            continue
        sev = _SEV_ORDER[status]
        label = {"high": "高", "mid": "中"}[sev]
        text = item.get("detail") or item.get("consistency") or item.get("quality") or ""
        rows.append(
            '<li><span class="sev {sev}">{label}</span>'
            '<span><b>{image}</b>：{text}</span></li>'.format(
                sev=sev, label=label, image=_esc(item.get("image")), text=_esc(text)))
    if not rows:
        return ""
    return ('<div class="section"><h2>建议处理清单</h2>'
            '<ul class="actions">{}</ul></div>').format("".join(rows))


def _item_html(item):
    status = _esc(item.get("status", "ERROR"))
    image = _esc(item.get("image", ""))
    loc = _esc(item.get("loc", ""))
    if status in {"MISSING", "ERROR", "SKIP"}:
        thumb = '<div class="thumb"><div class="noimg">{}</div></div>'.format(
            "图片文件缺失" if status == "MISSING" else "未检查")
    else:
        # 不用 str.format（JS 花括号会打架），占位符替换
        thumb = ('<div class="thumb"><img src="{SRC}" alt="{SRC}" '
                 'onerror="this.replaceWith(Object.assign('
                 "document.createElement('div'),"
                 "{className:'noimg',textContent:'图片加载失败'}))\"></div>"
                 ).replace("{SRC}", image)
    checks = []
    # 新格式：checks 数组（按检查项维度，含编号/名称/状态/依据）；兼容旧三字段
    check_items = item.get("checks")
    if isinstance(check_items, list) and check_items:
        for c in check_items:
            cid = _esc(c.get("id", ""))
            name = _esc(c.get("name", ""))
            text = _esc(c.get("note", ""))
            st = _esc(c.get("status", ""))
            cls = "bad" if st in ("FAIL", "WARN") else "ok"
            checks.append(
                '<div class="check"><span class="k">{} {}</span>'
                '<span class="v {}">[{}] {}</span></div>'.format(
                    cid, name, cls, st, text))
    else:
        for key, label in (("consistency", "图文一致"), ("quality", "图片质量"),
                           ("compliance", "合规检查")):
            text = item.get(key)
            if not text:
                continue
            cls = "bad" if any(
                w in text for w in ("不一致", "不可读", "风险", "不符", "缺失", "模糊")
            ) else "ok"
            checks.append(
                '<div class="check"><span class="k">{}</span>'
                '<span class="v {}">{}</span></div>'.format(label, cls, _esc(text)))
    detail = item.get("detail")
    detail_html = '<div class="detail">{}</div>'.format(_esc(detail)) if detail else ""
    return (
        '<div class="item">'
        '<div class="item-head"><span class="badge {status}">{status}</span>'
        '<span class="name">{image}</span><span class="loc">{loc}</span></div>'
        '<div class="item-body">{thumb}<div class="checks">{checks}{detail}</div></div>'
        '</div>'
    ).format(status=status, image=image, loc=loc, thumb=thumb,
             checks="".join(checks), detail=detail_html)


def render_report_html(data):
    items = data.get("items", [])
    counts = {}
    for item in items:
        counts[item.get("status", "ERROR")] = counts.get(item.get("status", "ERROR"), 0) + 1
    document = str(data.get("document", ""))
    return _TEMPLATE.format(
        doc_name=_esc(Path(document).name or "未命名文档"),
        document=_esc(document),
        checked_at=_esc(data.get("checked_at", "")),
        vision_model=_esc(data.get("vision_model", "")),
        stats_html=_stats_html(counts),
        actions_html=_actions_html(items),
        items_html="".join(_item_html(i) for i in items) or
                   '<p class="noimg">没有检查项。</p>',
    )


def emit(obj):
    print(json.dumps(obj, ensure_ascii=False))


def main():
    payload = json.loads(sys.stdin.read() or "{}")
    args = payload.get("args", {})
    workdir = Path(payload.get("workdir", ".")).resolve()      # generate/（产物目录）
    session_root = Path(payload.get("session_root", workdir.parent)).resolve()
    data_path = args.get("data_path", "")
    doc_dir = args.get("doc_dir", "")

    if not data_path:
        emit({"ok": False, "result": "缺少 data_path 参数", "files": []})
        return
    # data_path 是 Session 相对路径（如 generate/qc-report.json），按 session_root 解析
    dp = Path(data_path)
    dp = dp if dp.is_absolute() else (session_root / dp)
    if not dp.is_file():
        emit({"ok": False, "result": f"数据文件不存在：{data_path}", "files": []})
        return
    try:
        data = json.loads(dp.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        emit({"ok": False, "result": f"JSON 解析失败：{e}", "files": []})
        return

    # 目标目录：被检 Markdown 所在目录（Session 相对，如 workspace/md），
    # 报告与数据放这里，图片相对引用直接生效
    out_dir = session_root
    if doc_dir:
        ddp = Path(doc_dir)
        out_dir = ddp if ddp.is_absolute() else (session_root / ddp)
    out_dir = out_dir if out_dir.is_dir() else workdir
    # JSON 拷贝到目标目录（数据与报告同处，交付完整）
    json_out = out_dir / "qc-report.json"
    json_out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print("已复制数据文件", file=sys.stderr)

    try:
        html_text = render_report_html(data)
    except Exception as e:
        emit({"ok": False, "result": f"渲染失败：{e}", "files": []})
        return
    html_out = out_dir / "qc-report.html"
    html_out.write_text(html_text, encoding="utf-8")
    counts = {}
    for item in data.get("items", []):
        counts[item.get("status", "ERROR")] = counts.get(item.get("status", "ERROR"), 0) + 1
    summary = "PASS {p} / WARN {w} / FAIL {f} / 其他 {o}".format(
        p=counts.get("PASS", 0), w=counts.get("WARN", 0), f=counts.get("FAIL", 0),
        o=counts.get("MISSING", 0) + counts.get("ERROR", 0) + counts.get("SKIP", 0))
    emit({
        "ok": True,
        "result": f"HTML 报告已生成（{summary}），位于 {html_out.name}",
        "files": [str(html_out.name), str(json_out.name)],
    })


if __name__ == "__main__":
    main()
