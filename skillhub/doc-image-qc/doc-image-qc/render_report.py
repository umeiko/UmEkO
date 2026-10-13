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

本脚本：qc-report.json → generate/ 下的 HTML、JSON 与自包含 ZIP
args: {"data_path": "<qc-report.json 的 Session 相对路径>",
       "doc_dir": "<被检 Markdown 所在的 Session 相对目录>"}

人类可读性要点：
- 逐项 checks[] 渲染：每个检查项独立徽章按自身 PASS/WARN/FAIL 着色（不做文本猜测）
- 逐图 × 检查项 verdict 矩阵总览
- 矩阵直接展示编号与名称，检查范围从同包 checks.md 读取并写入离线报告
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
from urllib.parse import quote


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
  .matrix-scroll {{ overflow-x: auto; margin-bottom: 12px; }}
  table.matrix {{ width: 100%; border-collapse: collapse; background: var(--panel);
    border: 1px solid var(--line); border-radius: 10px; overflow: hidden; font-size: 12.5px; }}
  table.matrix th, table.matrix td {{ border: 1px solid var(--line); padding: 7px 10px;
    text-align: center; }}
  table.matrix th {{ background: #efece2; font-weight: 600; }}
  table.matrix th .check-id {{ display: block; color: var(--accent); }}
  table.matrix th .check-name {{ display: block; min-width: 7em; }}
  table.matrix td.img {{ text-align: left; font: 600 12px ui-monospace, monospace; }}
  .matrix-note {{ color: #4a5a52; margin-bottom: 10px; }}
  .check-legend {{ background: var(--panel); border: 1px solid var(--line);
    border-radius: 10px; padding: 14px 16px; }}
  .check-legend > summary {{ cursor: pointer; font-weight: 600; }}
  .check-legend dl {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 14px 24px; margin-top: 14px; }}
  .check-legend dt {{ font-weight: 600; }}
  .check-legend dt code {{ color: var(--accent); margin-right: 6px; }}
  .check-legend .group {{ color: var(--muted); font-size: 12px; margin-left: 8px;
    font-weight: 400; }}
  .check-legend dd {{ color: #4a5a52; margin-top: 3px; overflow-wrap: anywhere; }}
  .asset-warning {{ background: var(--warn-bg); border: 1px solid #b8860b55;
    border-radius: 10px; padding: 14px 16px; margin-bottom: 22px; }}
  .asset-warning h2 {{ font-size: 16px; }}
  .asset-warning ul {{ padding-left: 22px; overflow-wrap: anywhere; }}
  @media (max-width: 720px) {{ .check-legend dl {{ grid-template-columns: 1fr; }} }}
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
  {assets_html}
  {actions_html}
  {matrix_html}
  {items_html}
  <p id="no-match" hidden style="text-align:center;color:var(--muted);padding:40px 0;">当前筛选条件下没有图片。</p>
  <footer>
    <span>UMEKO · doc-image-qc · ZIP 解压后打开 HTML，图片按会话目录结构随报告打包（点击缩略图放大）</span>
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
    document.querySelectorAll('table.matrix tbody tr').forEach(function(tr, index) {{
      var el = items[index];
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


def _plain(value):
    """清单表格中的少量 Markdown 标记转为纯文本，输出时再统一 HTML 转义。"""
    return value.replace("\\|", "|").replace("**", "").replace("`", "").strip()


def _check_catalog():
    """与执行检查共用技能包清单，不在渲染器中另写一套编号定义。"""
    try:
        text = Path(__file__).with_name("checks.md").read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError):
        return {}
    catalog = {}
    group = ""
    for line in text.splitlines():
        if line.startswith("## "):
            group = _plain(line[3:])
        if not line.strip().startswith("|"):
            continue
        cells = [_plain(cell) for cell in re.split(r"(?<!\\)\|", line.strip().strip("|"))]
        if len(cells) < 3 or not re.fullmatch(r"[A-Za-z]+\d+", cells[0]):
            continue
        catalog[cells[0]] = {
            "name": cells[1], "description": cells[2], "group": group,
            "remark": cells[3] if len(cells) > 3 else "",
        }
    return catalog


def _check_definitions(items):
    """只解释本报告出现的编号，保留报告中的名称及自定义检查说明。"""
    catalog = _check_catalog()
    definitions = {}
    for item in items:
        for check in item.get("checks") or []:
            cid = str(check.get("id") or "").strip()
            if not cid:
                continue
            definition = definitions.setdefault(cid, {"name": "", "description": "", **catalog.get(cid, {})})
            for field in ("name", "description"):
                value = str(check.get(field) or "").strip()
                if value:
                    definition[field] = value
    for definition in definitions.values():
        definition["name"] = definition["name"] or "未命名检查项"
        definition["description"] = definition["description"] or "未提供检查范围，请参阅下方该项的检查依据。"
    return definitions


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


def _filters_html(counts, items, definitions):
    """筛选条：状态按钮组（按图级状态）+ 检查项下拉（按逐项 check_id）+ 重置 + 计数"""
    def st_count(k):
        return counts.get(k, 0)
    other = sum(v for k, v in counts.items()
                if k not in ("PASS", "WARN", "FAIL"))
    has_checks = bool(definitions)
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
        for cid, definition in definitions.items():
            opts.append('<option value="{cid}">{cid} · {name}</option>'.format(
                cid=_esc(cid), name=_esc(definition["name"])))
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


def _matrix_html(items, definitions):
    """逐图 × 检查项 verdict 矩阵（有 checks[] 时生成）"""
    col_ids = list(definitions)
    if not col_ids:
        return ""
    head = ('<thead><tr><th scope="col" style="text-align:left">图片</th>' +
            "".join('<th scope="col"><span class="check-id">{}</span>'
                    '<span class="check-name">{}</span></th>'.format(
                        _esc(cid), _esc(definitions[cid]["name"]))
                    for cid in col_ids) + "</tr></thead>")
    rows = []
    for item in items:
        cells = {str(c.get("id") or "").strip(): str(c.get("status", "NA"))
                 for c in item.get("checks") or []}
        tds = []
        for cid in col_ids:
            if cid not in cells:
                tds.append('<td><span class="cell absent">—</span></td>')
                continue
            st = cells[cid]
            if st not in ("PASS", "WARN", "FAIL"):
                st = "NA"
            tds.append('<td><span class="cell {st}">{st}</span></td>'.format(st=st))
        rows.append('<tr data-img="{}"><td class="img">{}</td>{}</tr>'.format(
            _esc(item.get("image", "")), _esc(item.get("image", "")), "".join(tds)))
    legend = []
    for cid, definition in definitions.items():
        group = ('<span class="group">{}</span>'.format(_esc(definition["group"]))
                 if definition.get("group") else "")
        remark = ('<br>补充：{}'.format(_esc(definition["remark"]))
                  if definition.get("remark") else "")
        legend.append('<div><dt><code>{cid}</code>{name}{group}</dt>'
                      '<dd>{description}{remark}</dd></div>'.format(
                          cid=_esc(cid), name=_esc(definition["name"]), group=group,
                          description=_esc(definition["description"]), remark=remark))
    return (
        '<div class="section"><h2>逐图 × 检查项 判定矩阵</h2>'
        '<p class="matrix-note">每行是一张图片，每列是一项检查。编号用于对应检查清单，'
        '字母区分类别，数字是类别内的序号，不是评分。</p>'
        '<div class="matrix-scroll"><table class="matrix">{head}<tbody>{rows}</tbody></table></div>'
        '<p class="matrix-note">PASS：通过；WARN：已确认的轻微问题；FAIL：未通过；'
        'NA：未检查（如缺少必要参照）；—：本图未列入该项检查。'
        'NA 和 — 均不表示通过，具体原因见逐图检查依据。</p>'
        '<details class="check-legend" open><summary>检查项说明 · {n} 项</summary>'
        '<dl>{legend}</dl></details></div>'
    ).format(head=head, rows="".join(rows), n=len(definitions), legend="".join(legend))


def _item_html(item, definitions, missing_images):
    status = _esc(item.get("status", "ERROR"))
    image = _esc(item.get("image", ""))
    loc = _esc(item.get("loc", ""))
    missing_reason = missing_images.get(str(item.get("image", "")))
    if missing_reason or status in {"MISSING", "ERROR", "SKIP"}:
        thumb = '<div class="thumb"><div class="noimg">{}</div></div>'.format(
            _esc("图片未打包：" + missing_reason) if missing_reason else
            "图片文件缺失" if status == "MISSING" else "未检查")
    else:
        # 不用 str.format（JS 花括号会打架），占位符替换
        thumb = ('<div class="thumb"><img src="{SRC}" alt="{ALT}" '
                 'onerror="this.replaceWith(Object.assign('
                 "document.createElement('div'),"
                 "{className:'noimg',textContent:'图片加载失败'}))\"></div>"
                 ).replace("{SRC}", _esc(_image_url(str(item.get("image", ""))))).replace("{ALT}", image)
    checks = []
    # 新格式：checks 数组（按检查项维度，含编号/名称/状态/依据）——徽章逐项着色
    check_items = item.get("checks")
    if isinstance(check_items, list) and check_items:
        for c in check_items:
            raw_cid = str(c.get("id") or "").strip()
            cid = _esc(raw_cid)
            name = _esc(c.get("name") or definitions.get(raw_cid, {}).get("name", ""))
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
    cids = " ".join(str(c.get("id") or "").strip() for c in raw_checks) if isinstance(raw_checks, list) else ""
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
    missing = data.get("packaging", {}).get("missing_images", [])
    missing_images = {entry["image"]: entry["reason"] for entry in missing}
    definitions = _check_definitions(items)
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
        filters_html=_filters_html(counts, items, definitions),
        assets_html=(
            '<div class="asset-warning"><h2>图片未完整打包 · {} 张</h2>'
            '<p>以下图片未包含在 ZIP 中，请补齐文件或修正路径后重新生成报告。</p><ul>{}</ul></div>'
        ).format(len(missing), "".join('<li><b>{}</b>：{}</li>'.format(
            _esc(entry["image"]), _esc(entry["reason"])) for entry in missing)) if missing else "",
        actions_html=_actions_html(items),
        matrix_html=_matrix_html(items, definitions),
        items_html="".join(_item_html(i, definitions, missing_images) for i in items) or
                   '<p class="noimg">没有检查项。</p>',
    )


def _is_remote(src):
    return src.lower().startswith(("http://", "https://", "data:"))


def _image_url(src):
    return src if _is_remote(src) else quote(src, safe="/")


def _rewrite_src_for_generate(html_text, assets):
    """ZIP 图片均使用会话相对路径，generate/ 的预览在同一路径前加 ../。"""
    for src in assets:
        html_text = html_text.replace('src="{}"'.format(_esc(_image_url(src))),
                                      'src="{}"'.format(_esc(_image_url("../" + src))))
    return html_text


def _session_path(path, session_root, *, allow_root=False):
    target = (session_root / path).resolve()
    relative = target.relative_to(session_root)
    if not relative.parts and allow_root:
        return target
    if not relative.parts or relative.parts[0] not in {"workspace", "attachments", "generate"}:
        raise ValueError("只能读取当前会话的 workspace、attachments 或 generate 目录")
    return target


def _prepare_images(data, doc_dir, session_root):
    """解析两种图片基址，规范为会话相对路径，避免同名文件冲突和越界打包。"""
    assets = {}
    missing = {}
    items = []
    for original in data.get("items", []):
        item = dict(original)
        src = str(item.get("image", "")).strip()
        if not src or _is_remote(src):
            items.append(item)
            continue
        try:
            path = Path(src.replace("\\", "/"))
            # 附件及其他显式 Session 路径不应拼到 Markdown 的 doc_dir 下。
            session_relative = path.parts and path.parts[0] in {"workspace", "attachments", "generate"}
            base = session_root if session_relative or path.is_absolute() else doc_dir
            if base == session_root and len(path.parts) == 1 and not session_relative:
                base = session_root / "attachments"
            resolved = _session_path(base / path, session_root)
            # 兼容旧报告只写粘贴附件的文件名：仅按精确文件名查附件，不做全目录猜测。
            if not resolved.is_file() and len(path.parts) == 1:
                attachment = _session_path(session_root / "attachments" / path, session_root)
                if attachment.is_file():
                    resolved = attachment
            canonical = resolved.relative_to(session_root).as_posix()
            item["image"] = canonical
            if canonical != src and not path.is_absolute():
                item.setdefault("source_image", src)
            if resolved.is_file():
                assets[canonical] = resolved
            else:
                missing[canonical] = "文件不存在"
        except (ValueError, OSError):
            missing[src] = "路径无效或超出当前会话的文件目录"
        items.append(item)
    report = {**data, "items": items, "packaging": {
        "packed_images": len(assets),
        "missing_images": [{"image": src, "reason": reason} for src, reason in missing.items()],
    }}
    return report, assets


def _pack_zip(zip_path, html_text, data, assets):
    """自包含 ZIP：HTML + JSON + 解析成功的文档配图及附件，统一保持会话目录结构。"""
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("qc-report.html", html_text)
        zf.writestr("qc-report.json", json.dumps(data, ensure_ascii=False, indent=2))
        for relative, path in assets.items():
            zf.write(path, relative)


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
    try:
        _session_path(workdir, session_root)
        if workdir != (session_root / "generate"):
            raise ValueError("报告只能写入当前会话的 generate 目录")
        dp = _session_path(Path(data_path), session_root)
        doc_dir_abs = _session_path(Path(doc_dir or "."), session_root, allow_root=True)
        if not doc_dir_abs.is_dir():
            raise ValueError("文档目录不存在")
    except (ValueError, OSError) as exc:
        emit({"ok": False, "result": f"路径无效：{exc}", "files": []})
        return
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

    try:
        data, assets = _prepare_images(data, doc_dir_abs, session_root)
        html_text = render_report_html(data)
    except Exception as e:
        emit({"ok": False, "result": f"渲染失败：{e}", "files": []})
        return

    # ---- generate/ 交付区（唯一产物位置）：HTML + JSON + 自包含 ZIP ----
    doc_stem = re.sub(r'[\\/:*?"<>|]+', "_", Path(document := str(data.get("document", ""))).stem) or "report"
    gen_files: list[str] = []
    try:
        gen_html = workdir / f"qc-report-{doc_stem}.html"
        gen_html.write_text(_rewrite_src_for_generate(html_text, assets), encoding="utf-8")
        gen_json = workdir / f"qc-report-{doc_stem}.json"
        gen_json.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        zip_path = workdir / f"qc-report-{doc_stem}.zip"
        _pack_zip(zip_path, html_text, data, assets)
        packed = len(assets)
        skipped = len(data["packaging"]["missing_images"])
        gen_files = [gen_html.name, gen_json.name, zip_path.name]
        print(f"generate 交付：{gen_html.name} / {gen_json.name} / {zip_path.name}"
              f"（ZIP 内图片 {packed} 张{f'，跳过 {skipped} 张' if skipped else ''}）", file=sys.stderr)
    except Exception as e:
        emit({"ok": False, "result": f"generate 产物写入失败：{e}", "files": []})
        return
    counts = {}
    for item in data.get("items", []):
        counts[item.get("status", "ERROR")] = counts.get(item.get("status", "ERROR"), 0) + 1
    summary = "PASS {p} / WARN {w} / FAIL {f} / 其他 {o}".format(
        p=counts.get("PASS", 0), w=counts.get("WARN", 0), f=counts.get("FAIL", 0),
        o=counts.get("MISSING", 0) + counts.get("ERROR", 0) + counts.get("SKIP", 0))
    emit({
        "ok": True,
        "result": f"HTML 报告已生成（{summary}），产物全部位于 generate/："
                  + "、".join(gen_files)
                  + ("。注意：以下图片未打包：" + "；".join(
                      entry["image"] + "（" + entry["reason"] + "）"
                      for entry in data["packaging"]["missing_images"]) if skipped else ""),
        "files": [f"generate/{n}" for n in gen_files],
    })


if __name__ == "__main__":
    # The tool runner exchanges UTF-8 JSON even on Windows with a legacy console code page.
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    main()
