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

人类可读性要点：
- 逐项 checks[] 渲染：每个检查项独立徽章按自身 PASS/WARN/FAIL 着色（不做文本猜测）
- 逐图 × 检查项 verdict 矩阵总览
- 缩略图点击放大（lightbox）
- meta 容错：checked_at 缺失/异常显示"未记录"；vision_model 为工具名时显示"未记录"；
  footer 生成时间取脚本本地运行时刻
"""

from __future__ import annotations

import datetime
import html
import json
import re
import sys
import zipfile
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
  table.matrix {{ width: 100%; border-collapse: collapse; background: var(--panel);
    border: 1px solid var(--line); border-radius: 10px; overflow: hidden; font-size: 12.5px; }}
  table.matrix th, table.matrix td {{ border: 1px solid var(--line); padding: 7px 10px;
    text-align: center; }}
  table.matrix th {{ background: #efece2; font-weight: 600; }}
  table.matrix td.img {{ text-align: left; font: 600 12px ui-monospace, monospace; }}
  .cell {{ display: inline-block; min-width: 34px; padding: 1px 6px; border-radius: 8px;
    font-size: 11px; font-weight: 700; }}
  .cell.PASS {{ color: var(--pass); background: var(--pass-bg); }}
  .cell.WARN {{ color: var(--warn); background: var(--warn-bg); }}
  .cell.FAIL {{ color: var(--fail); background: var(--fail-bg); }}
  .cell.NA {{ color: var(--muted); background: #f0ede4; }}
  .item {{ background: var(--panel); border: 1px solid var(--line); border-radius: 12px;
    padding: 16px 18px; margin-bottom: 14px; }}
  .item-head {{ display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }}
  .item-head .name {{ font: 600 14px ui-monospace, "Cascadia Code", monospace; }}
  .item-head .loc {{ color: var(--muted); font-size: 12px; }}
  .badge {{ font-size: 11px; font-weight: 700; padding: 2px 10px; border-radius: 10px; }}
  .badge.PASS {{ color: var(--pass); background: var(--pass-bg); border: 1px solid #087f6833; }}
  .badge.WARN {{ color: var(--warn); background: var(--warn-bg); border: 1px solid #b8860b33; }}
  .badge.FAIL {{ color: var(--fail); background: var(--fail-bg); border: 1px solid #b3402a33; }}
  .badge.MISSING, .badge.ERROR, .badge.SKIP, .badge.NA {{ color: var(--muted); background: #f0ede4;
    border: 1px solid var(--line); }}
  .item-body {{ display: grid; grid-template-columns: 240px 1fr; gap: 16px; margin-top: 12px; }}
  @media (max-width: 720px) {{ .item-body {{ grid-template-columns: 1fr; }} }}
  .thumb {{ width: 240px; border: 1px solid var(--line); border-radius: 8px;
    background: #fff; padding: 6px; align-self: start; }}
  .thumb img {{ width: 100%; height: auto; border-radius: 4px; display: block; cursor: zoom-in; }}
  .thumb .noimg {{ color: var(--muted); font-size: 12px; text-align: center; padding: 28px 8px; }}
  .checks {{ display: grid; gap: 8px; align-content: start; }}
  .check {{ display: grid; grid-template-columns: auto 1fr; gap: 10px; font-size: 13px;
    align-items: start; }}
  .check .v {{ color: var(--ink); }}
  .check .v.bad {{ color: var(--fail); font-weight: 600; }}
  .check .v.warn {{ color: var(--warn); font-weight: 600; }}
  .cbadge {{ flex: none; font-size: 10.5px; font-weight: 700; padding: 1px 7px; border-radius: 8px;
    margin-top: 2px; white-space: nowrap; }}
  .cbadge.PASS {{ color: var(--pass); background: var(--pass-bg); }}
  .cbadge.WARN {{ color: var(--warn); background: var(--warn-bg); }}
  .cbadge.FAIL {{ color: var(--fail); background: var(--fail-bg); }}
  .cbadge.NA {{ color: var(--muted); background: #f0ede4; }}
  .detail {{ margin-top: 4px; padding: 8px 12px; background: #f8f5ec; border-radius: 6px;
    font-size: 12.5px; color: #4a5a52; }}
  footer {{ margin-top: 34px; padding-top: 14px; border-top: 1px solid var(--line);
    color: var(--muted); font-size: 11.5px; display: flex; justify-content: space-between;
    flex-wrap: wrap; gap: 6px; }}
  /* 筛选条 */
  .filters {{ position: sticky; top: 0; z-index: 20; display: flex; flex-wrap: wrap; gap: 10px;
    align-items: center; padding: 10px 14px; margin-bottom: 18px;
    background: var(--panel); border: 1px solid var(--line); border-radius: 10px;
    box-shadow: 0 4px 14px #26322e10; }}
  .filters .fgroup {{ display: flex; align-items: center; gap: 4px; }}
  .filters .flabel {{ font-size: 12px; color: var(--muted); margin-right: 2px; }}
  .fbtn {{ border: 1px solid var(--line); background: #fff; color: var(--ink);
    font: 600 12px/1 inherit; padding: 5px 12px; border-radius: 14px; cursor: pointer;
    transition: all .12s ease; }}
  .fbtn:hover {{ border-color: var(--accent); color: var(--accent-dark); }}
  .fbtn.on {{ background: var(--accent); border-color: var(--accent); color: #fff; }}
  .fbtn .cnt {{ font-weight: 400; opacity: .75; margin-left: 3px; font-size: 11px; }}
  .filters .spacer {{ flex: 1; }}
  .filters select {{ border: 1px solid var(--line); background: #fff; color: var(--ink);
    font: 12px inherit; padding: 5px 8px; border-radius: 8px; cursor: pointer; }}
  #filter-count {{ font-size: 12px; color: var(--muted); }}
  /* 建议清单折叠 */
  details.actions-wrap {{ background: transparent; border: 0; margin-bottom: 26px; }}
  details.actions-wrap > summary {{ list-style: none; cursor: pointer; font-size: 16px;
    font-weight: 700; margin-bottom: 12px; padding-left: 10px; border-left: 3px solid var(--accent);
    display: flex; align-items: center; gap: 8px; user-select: none; }}
  details.actions-wrap > summary::-webkit-details-marker {{ display: none; }}
  details.actions-wrap > summary .chev {{ transition: transform .15s ease; font-size: 12px; color: var(--muted); }}
  details.actions-wrap[open] > summary .chev {{ transform: rotate(90deg); }}
  details.actions-wrap > summary .n-badge {{ font: 700 11px/1 inherit; color: var(--fail);
    background: var(--fail-bg); border-radius: 10px; padding: 3px 9px; }}
  #lightbox {{ position: fixed; inset: 0; background: rgba(20,26,23,.82); display: none;
    align-items: center; justify-content: center; z-index: 99; cursor: zoom-out; }}
  #lightbox img {{ max-width: 94vw; max-height: 92vh; border-radius: 8px;
    box-shadow: 0 8px 40px rgba(0,0,0,.4); background: #fff; }}
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
  {filters_html}
  {actions_html}
  {matrix_html}
  {items_html}
  <p id="no-match" hidden style="text-align:center;color:var(--muted);padding:40px 0;">当前筛选条件下没有图片。</p>
  <footer>
    <span>UMEKO · doc-image-qc · 报告与源文档同级存放，图片为相对路径引用（点击缩略图放大）</span>
    <span>报告生成于 {generated_at} · 详尽数据见 qc-report.json</span>
  </footer>
</div>
<div id="lightbox" onclick="this.style.display='none'"><img id="lightbox-img" alt="放大查看"></div>
<script>
(function() {{
  // ---------- lightbox ----------
  document.addEventListener('click', function(e) {{
    var im = e.target.closest('.thumb img');
    if (im) {{
      document.getElementById('lightbox-img').src = im.src;
      document.getElementById('lightbox').style.display = 'flex';
    }}
  }});
  document.addEventListener('keydown', function(e) {{
    if (e.key === 'Escape') document.getElementById('lightbox').style.display = 'none';
  }});

  // ---------- 筛选 ----------
  var statusSel = 'all';           // all | PASS | WARN | FAIL | OTHER
  var checkSel = 'all';            // all | <check_id>
  var items = Array.prototype.slice.call(document.querySelectorAll('.item'));

  function applyFilters() {{
    var visible = 0;
    items.forEach(function(el) {{
      var okS = (statusSel === 'all') || (el.dataset.status === statusSel);
      var okC = (checkSel === 'all') || (el.dataset.checks.split(' ').indexOf(checkSel) >= 0);
      var show = okS && okC;
      el.hidden = !show;
      if (show) visible++;
    }});
    document.getElementById('no-match').hidden = visible > 0;
    document.getElementById('filter-count').textContent = visible + ' / ' + items.length;
    // 矩阵行同步隐藏（若有矩阵）
    document.querySelectorAll('table.matrix tbody tr').forEach(function(tr) {{
      var img = tr.getAttribute('data-img') || '';
      var el = items.filter(function(x) {{ return x.dataset.img === img; }})[0];
      tr.hidden = el ? el.hidden : false;
    }});
  }}

  // 状态按钮组（单选语义；再点一次 = 回到全部）
  document.querySelectorAll('.fbtn[data-st]').forEach(function(btn) {{
    btn.addEventListener('click', function() {{
      var v = btn.getAttribute('data-st');
      statusSel = (statusSel === v) ? 'all' : v;
      document.querySelectorAll('.fbtn[data-st]').forEach(function(b) {{
        b.classList.toggle('on', b.getAttribute('data-st') === statusSel);
      }});
      applyFilters();
    }});
  }});
  // 检查项下拉
  var checkDd = document.getElementById('check-filter');
  if (checkDd) checkDd.addEventListener('change', function() {{
    checkSel = checkDd.value;
    applyFilters();
  }});
  // 重置
  var resetBtn = document.getElementById('filter-reset');
  if (resetBtn) resetBtn.addEventListener('click', function() {{
    statusSel = 'all'; checkSel = 'all';
    document.querySelectorAll('.fbtn[data-st]').forEach(function(b) {{ b.classList.remove('on'); }});
    if (checkDd) checkDd.value = 'all';
    applyFilters();
  }});
}})();
</script>
</body>
</html>
"""

_SEV_ORDER = {"FAIL": "high", "WARN": "mid"}
_KNOWN_TOOL_NAMES = {"image_reasoning", "read_image"}


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


def _filters_html(counts, items):
    """筛选条：状态按钮组（按图级状态）+ 检查项下拉（按逐项 check_id）+ 重置 + 计数"""
    def st_count(k):
        return counts.get(k, 0)
    other = sum(v for k, v in counts.items()
                if k not in ("PASS", "WARN", "FAIL"))
    # 检查项选项（从 checks[] 收集，保持出现顺序）
    check_ids = []
    check_names = {}
    for item in items:
        for c in item.get("checks") or []:
            cid = str(c.get("id", ""))
            if cid and cid not in check_ids:
                check_ids.append(cid)
                check_names[cid] = str(c.get("name", ""))
    has_checks = bool(check_ids)
    buttons = [
        ('<button type="button" class="fbtn on" data-st="all">全部<span class="cnt">{}</span></button>'
         .format(sum(counts.values()))),
        ('<button type="button" class="fbtn" data-st="PASS" style="color:var(--pass)">通过<span class="cnt">{}</span></button>'
         .format(st_count("PASS"))),
        ('<button type="button" class="fbtn" data-st="WARN" style="color:var(--warn)">警告<span class="cnt">{}</span></button>'
         .format(st_count("WARN"))),
        ('<button type="button" class="fbtn" data-st="FAIL" style="color:var(--fail)">失败<span class="cnt">{}</span></button>'
         .format(st_count("FAIL"))),
    ]
    if other:
        buttons.append(
            '<button type="button" class="fbtn" data-st="OTHER">其他<span class="cnt">{}</span></button>'
            .format(other))
    check_dd = ""
    if has_checks:
        opts = ['<option value="all">全部检查项</option>']
        for cid in check_ids:
            opts.append('<option value="{cid}">{cid} · {name}</option>'.format(
                cid=_esc(cid), name=_esc(check_names[cid])))
        check_dd = ('<span class="flabel">检查项</span>'
                    '<select id="check-filter">{}</select>'.format("".join(opts)))
    return (
        '<div class="filters">'
        '<span class="flabel">状态</span>'
        '<div class="fgroup">{btns}</div>'
        '{check_dd}'
        '<span class="spacer"></span>'
        '<button type="button" class="fbtn" id="filter-reset">重置</button>'
        '<span id="filter-count">{n} / {n}</span>'
        '</div>'
    ).format(btns="".join(buttons), check_dd=check_dd, n=sum(counts.values()))


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
    n_fail = sum(1 for i in items if i.get("status") == "FAIL")
    return (
        '<details class="actions-wrap">'
        '<summary><span class="chev">▶</span>建议处理清单'
        '<span class="n-badge">{n} 项待处理</span></summary>'
        '<ul class="actions">{rows}</ul>'
        '</details>'
    ).format(n=n_fail + sum(1 for i in items if i.get("status") == "WARN"), rows="".join(rows))


def _matrix_html(items):
    """逐图 × 检查项 verdict 矩阵（有 checks[] 时生成）"""
    col_ids = []
    col_names = {}
    for item in items:
        for c in item.get("checks") or []:
            cid = str(c.get("id", ""))
            if cid and cid not in col_ids:
                col_ids.append(cid)
                col_names[cid] = str(c.get("name", ""))
    if not col_ids:
        return ""
    head = ('<tr><th style="text-align:left">图片</th>' +
            "".join('<th title="{}">{}</th>'.format(_esc(col_names[c]), _esc(c))
                    for c in col_ids) + "</tr>")
    rows = []
    for item in items:
        cells = {str(c.get("id", "")): str(c.get("status", "NA"))
                 for c in item.get("checks") or []}
        tds = []
        for cid in col_ids:
            st = cells.get(cid, "NA")
            if st not in ("PASS", "WARN", "FAIL"):
                st = "NA"
            tds.append('<td><span class="cell {st}">{st}</span></td>'.format(st=st))
        rows.append('<tr data-img="{}"><td class="img">{}</td>{}</tr>'.format(
            _esc(item.get("image", "")), _esc(item.get("image", "")), "".join(tds)))
    return ('<div class="section"><h2>逐图 × 检查项 判定矩阵</h2>'
            '<table class="matrix">{}{}</table></div>').format(head, "".join(rows))


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
    # 新格式：checks 数组（按检查项维度，含编号/名称/状态/依据）——徽章逐项着色
    check_items = item.get("checks")
    if isinstance(check_items, list) and check_items:
        for c in check_items:
            cid = _esc(c.get("id", ""))
            name = _esc(c.get("name", ""))
            text = _esc(c.get("note", ""))
            st = _esc(c.get("status", "")) or "NA"
            st_cls = st if st in ("PASS", "WARN", "FAIL", "NA") else "NA"
            v_cls = {"FAIL": "bad", "WARN": "warn"}.get(st, "")
            checks.append(
                '<div class="check"><span class="cbadge {st_cls}">{cid} {st}</span>'
                '<span class="v {v_cls}"><b>{name}</b>　{text}</span></div>'.format(
                    st_cls=st_cls, cid=cid, st=st, v_cls=v_cls, name=name, text=text))
    else:
        # 兼容旧三字段：无逐项状态，不做关键词猜测，中性渲染
        for key, label in (("consistency", "图文一致"), ("quality", "图片质量"),
                           ("compliance", "合规检查")):
            text = item.get(key)
            if not text:
                continue
            checks.append(
                '<div class="check"><span class="cbadge NA">{}</span>'
                '<span class="v">{}</span></div>'.format(label, _esc(text)))
    detail = item.get("detail")
    detail_html = '<div class="detail">{}</div>'.format(_esc(detail)) if detail else ""
    # 筛选 data 属性：图级状态 + 覆盖的检查项 id 列表
    raw_status = str(item.get("status", "ERROR"))
    status_key = raw_status if raw_status in ("PASS", "WARN", "FAIL") else "OTHER"
    raw_checks = item.get("checks")
    cids = " ".join(str(c.get("id", "")) for c in raw_checks) if isinstance(raw_checks, list) else ""
    return (
        '<div class="item" data-status="{sk}" data-checks="{cids}" data-img="{img}">'
        '<div class="item-head"><span class="badge {status}">{status}</span>'
        '<span class="name">{image}</span><span class="loc">{loc}</span></div>'
        '<div class="item-body">{thumb}<div class="checks">{checks}{detail}</div></div>'
        '</div>'
    ).format(sk=status_key, cids=_esc(cids), img=image, status=status, image=image, loc=loc,
             thumb=thumb, checks="".join(checks), detail=detail_html)


def _clean_meta(data):
    checked_at = str(data.get("checked_at", "")).strip()
    if not checked_at or not re.search(r"\d{4}[-/]\d{1,2}[-/]\d{1,2}", checked_at):
        checked_at = "未记录"
    vision = str(data.get("vision_model", "")).strip()
    if not vision or vision in _KNOWN_TOOL_NAMES:
        vision = "未记录"
    return checked_at, vision


def render_report_html(data):
    items = data.get("items", [])
    counts = {}
    for item in items:
        counts[item.get("status", "ERROR")] = counts.get(item.get("status", "ERROR"), 0) + 1
    document = str(data.get("document", ""))
    checked_at, vision = _clean_meta(data)
    generated_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    return _TEMPLATE.format(
        doc_name=_esc(Path(document).name or "未命名文档"),
        document=_esc(document),
        checked_at=_esc(checked_at),
        vision_model=_esc(vision),
        generated_at=generated_at,
        stats_html=_stats_html(counts),
        filters_html=_filters_html(counts, items),
        actions_html=_actions_html(items),
        matrix_html=_matrix_html(items),
        items_html="".join(_item_html(i) for i in items) or
                   '<p class="noimg">没有检查项。</p>',
    )


def _iter_local_images(data):
    """items 里引用的本地图片相对路径（跳过外链与越界路径）"""
    for item in data.get("items", []):
        src = str(item.get("image", "")).strip()
        if not src or src.lower().startswith(("http://", "https://", "data:")):
            continue
        rel = Path(src)
        if rel.is_absolute() or ".." in rel.parts:
            continue
        yield src


def _rewrite_src_for_generate(html_text, data, doc_dir_rel):
    """generate/ 副本：图片引用改写为 ../<doc_dir>/<img>（raw 端点按会话相对路径解析）"""
    if not doc_dir_rel:
        return html_text
    prefix = "../" + doc_dir_rel.rstrip("/") + "/"
    for src in _iter_local_images(data):
        html_text = html_text.replace('src="{}"'.format(_esc(src)),
                                      'src="{}{}"'.format(prefix, _esc(src)))
    return html_text


def _pack_zip(zip_path, html_text, data, out_dir):
    """自包含 ZIP：HTML（保持原始相对引用）+ JSON + 全部本地图片（保持相对结构）"""
    packed = skipped = 0
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("qc-report.html", html_text)
        zf.writestr("qc-report.json", json.dumps(data, ensure_ascii=False, indent=2))
        seen = set()
        for src in _iter_local_images(data):
            arc = Path(src).as_posix()
            if arc in seen:
                continue
            seen.add(arc)
            fp = out_dir / src
            if fp.is_file():
                zf.write(fp, arc)
                packed += 1
            else:
                skipped += 1
    return packed, skipped


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

    # 文档目录：只读（图片从这里取，用于打包 ZIP 与 HTML 相对引用），
    # 不向文档目录写任何产物——所有输出只落 generate/
    doc_dir_abs = session_root
    if doc_dir:
        ddp = Path(doc_dir)
        doc_dir_abs = ddp if ddp.is_absolute() else (session_root / ddp)
    doc_dir_abs = doc_dir_abs if doc_dir_abs.is_dir() else workdir

    try:
        html_text = render_report_html(data)
    except Exception as e:
        emit({"ok": False, "result": f"渲染失败：{e}", "files": []})
        return

    # ---- generate/ 交付区（唯一产物位置）：HTML + JSON + 自包含 ZIP ----
    doc_stem = re.sub(r'[\\/:*?"<>|]+', "_", Path(document := str(data.get("document", ""))).stem) or "report"
    gen_files: list[str] = []
    doc_dir_rel = ""
    if doc_dir:
        doc_dir_rel = Path(doc_dir).as_posix().strip("/")
    try:
        gen_html = workdir / f"qc-report-{doc_stem}.html"
        gen_html.write_text(_rewrite_src_for_generate(html_text, data, doc_dir_rel), encoding="utf-8")
        gen_json = workdir / f"qc-report-{doc_stem}.json"
        gen_json.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        zip_path = workdir / f"qc-report-{doc_stem}.zip"
        packed, skipped = _pack_zip(zip_path, html_text, data, doc_dir_abs)
        gen_files = [gen_html.name, gen_json.name, zip_path.name]
        print(f"generate 交付：{gen_html.name} / {gen_json.name} / {zip_path.name}"
              f"（ZIP 内图片 {packed} 张{f'，跳过 {skipped} 张' if skipped else ''}）", file=sys.stderr)
    except Exception as e:
        print(f"generate 交付失败：{e}", file=sys.stderr)
    counts = {}
    for item in data.get("items", []):
        counts[item.get("status", "ERROR")] = counts.get(item.get("status", "ERROR"), 0) + 1
    summary = "PASS {p} / WARN {w} / FAIL {f} / 其他 {o}".format(
        p=counts.get("PASS", 0), w=counts.get("WARN", 0), f=counts.get("FAIL", 0),
        o=counts.get("MISSING", 0) + counts.get("ERROR", 0) + counts.get("SKIP", 0))
    if not gen_files:
        emit({"ok": False, "result": f"generate 产物写入失败：{getattr(e, 'args', ['未知错误'])[0] if isinstance(e, Exception) else '未知错误'}", "files": []})
        return
    emit({
        "ok": True,
        "result": f"HTML 报告已生成（{summary}），产物全部位于 generate/："
                  + "、".join(gen_files),
        "files": [f"generate/{n}" for n in gen_files],
    })


if __name__ == "__main__":
    main()
