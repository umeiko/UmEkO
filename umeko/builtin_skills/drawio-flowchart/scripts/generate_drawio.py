#!/usr/bin/env python
"""Standalone draw.io structure, layout, and optional image export."""
from __future__ import annotations

import html
import json
import logging
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET

# Also works when a frozen UmEkO executable invokes this file via runpy.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from drawio_arch import apply_layout
from drawio_flow import apply_flow_layout, make_flow_grid
from drawio_xml import apply_font, export_diagram, extract_xml, sanitize_xml
from drawio_style import load_style, edge_visuals, apply_visuals, verify_restyle, packaged_file

SKILL_SCRIPT = {
    "description": "校验 draw.io XML 结构、确定性布局并按需导出 PNG/SVG/PDF；不调用模型或执行图像复检。",
    "usage": "先生成完整 mxfile XML，推荐通过 source_path 传文件；也可传 xml 字符串。formats=[] 仅输出可编辑文件。PNG/SVG 使用管理员配置的网络或本地渲染器，PDF 使用本地 draw.io。",
    "input_schema": {"type": "object", "additionalProperties": False,
                     "anyOf": [{"required": ["source_path"]}, {"required": ["xml"]}], "properties": {
        "source_path": {"type": "string", "minLength": 1, "pattern": r"\S", "description": "已有 mxfile XML 的会话相对路径"},
        "xml": {"type": "string", "minLength": 1, "pattern": r"\S", "description": "完整 XML；与 source_path 同传时优先使用此值"},
        "output_name": {"type": "string", "minLength": 1, "maxLength": 80, "pattern": r"^[\w-]+$", "default": "flowchart", "description": "1–80 字符，不带路径或扩展名"},
        "diagram_type": {"type": "string", "enum": ["auto", "flowchart", "architecture"], "default": "auto"},
        "formats": {"type": "array", "items": {"type": "string", "enum": ["png", "svg", "pdf"]}, "default": ["png", "svg"]},
        "style_path": {"type": "string", "default": "", "description": "可选风格 Markdown 的会话相对路径"},
        "restyle_reference_path": {"type": "string", "description": "可选原始 draw.io 文件路径，用于校验换肤时业务结构未变"},
        "layout": {"type": "object", "additionalProperties": False, "properties": {
            "node_width": {"type": ["number", "null"], "exclusiveMinimum": 0},
            "node_height": {"type": ["number", "null"], "exclusiveMinimum": 0},
            "gap_x": {"type": ["number", "null"], "exclusiveMinimum": 0},
            "gap_y": {"type": ["number", "null"], "exclusiveMinimum": 0},
        }, "description": "可选流程布局覆盖项；尺寸和间距为正数，null 表示沿用默认"},
    }},
    "outputs": ["generate/<output_name>.drawio：可编辑图表", "generate/<output_name>.<png|svg|pdf>：成功导出的格式", "stdout JSON 另含 status、exports、errors、warnings、diagram_type、visual_review_performed；导出失败可能保留草稿，必须检查 ok/status"],
    "example_args": {"source_path": "generate/approval-source.xml", "output_name": "approval", "diagram_type": "flowchart", "formats": []},
}


def _label(cell):
    return re.sub(r"<[^>]+>", "", html.unescape(cell.get("value", ""))).strip()


def _terminal(cell, kind):
    """Terminal identity is structural; labels may retain business descriptions."""
    if cell.get("id", "").lower() == kind:
        return True
    pattern = r"^(?:开始|start)(?:\s|[:：]|$)" if kind == "start" else r"^(?:结束|终止|end)(?:\s|[:：]|$)"
    return bool(re.match(pattern, _label(cell), re.IGNORECASE))


def validate_structure(xml_text, diagram_type):
    if "<!DOCTYPE" in xml_text.upper() or "<!ENTITY" in xml_text.upper():
        raise ValueError("不支持 XML DTD/实体声明")
    root = ET.fromstring(xml_text)
    diagrams = root.findall("diagram")
    if root.tag != "mxfile" or len(diagrams) != 1:
        raise ValueError("必须是包含一个未压缩 diagram 的 mxfile XML")
    cells = root.find("diagram/mxGraphModel/root")
    if cells is None:
        raise ValueError("缺少 diagram/mxGraphModel/root（不支持压缩 XML）")
    by_id = {}
    for cell in cells:
        if cell.tag != "mxCell" or not cell.get("id") or cell.get("id") in by_id:
            raise ValueError("所有单元必须为带唯一非空 id 的 mxCell")
        by_id[cell.get("id")] = cell
    if "0" not in by_id or "1" not in by_id or by_id["1"].get("parent") != "0":
        raise ValueError('必须包含 id="0" 及 parent="0" 的 id="1" 根单元')
    vertices = {i: c for i, c in by_id.items() if c.get("vertex") == "1"}
    edges = [c for c in cells if c.get("edge") == "1"]
    if not vertices:
        raise ValueError("图表没有节点")
    for i, c in by_id.items():
        if i != "0" and c.get("parent") not in by_id:
            raise ValueError(f"节点 {i} 的 parent 不存在")
        visited = {i}
        parent = c.get("parent")
        while parent:
            if parent in visited:
                raise ValueError(f"节点 {i} 的容器层次存在循环")
            visited.add(parent)
            parent = by_id[parent].get("parent")
    outgoing = {i: [] for i in vertices}
    incoming = {i: [] for i in vertices}
    for edge in edges:
        source, target = edge.get("source"), edge.get("target")
        if source not in vertices or target not in vertices:
            raise ValueError(f"连线 {edge.get('id')} 的 source/target 必须指向已有节点")
        outgoing[source].append(edge)
        incoming[target].append(edge)
    if diagram_type == "architecture":
        return len(vertices), len(edges)
    if not edges:
        raise ValueError("流程图没有连线")
    if any(c.get("parent") != "1" for c in [*vertices.values(), *edges]):
        raise ValueError('流程图所有节点和连线的 parent 必须是 "1"')
    starts = {i for i, c in vertices.items() if _terminal(c, "start")}
    ends = {i for i, c in vertices.items() if _terminal(c, "end")}
    if len(starts) != 1 or not ends:
        raise ValueError("流程图必须有一个开始节点和至少一个结束节点")
    if any(incoming[i] for i in starts) or any(outgoing[i] for i in ends):
        raise ValueError("开始不能有入边，结束不能有出边")
    for i, cell in vertices.items():
        if "rhombus" in cell.get("style", ""):
            if len(outgoing[i]) < 2 or any(not _label(e) for e in outgoing[i]):
                raise ValueError(f"判断节点 {i} 必须有至少两条带标签的出边")

    def reachable(initial, links, endpoint):
        seen, pending = set(initial), list(initial)
        while pending:
            for edge in links[pending.pop()]:
                node = edge.get(endpoint)
                if node not in seen:
                    seen.add(node)
                    pending.append(node)
        return seen

    if reachable(starts, outgoing, "target") != set(vertices):
        raise ValueError("存在从开始节点不可达的步骤")
    if reachable(ends, incoming, "source") != set(vertices):
        raise ValueError("存在无法通向结束节点的步骤")
    return len(vertices), len(edges)


def _source(args, session_root):
    if "xml" in args:
        if not isinstance(args["xml"], str):
            raise ValueError("xml 必须是字符串")
        return args["xml"]
    relative = Path(args.get("source_path", ""))
    if relative.is_absolute() or not relative.parts or relative.parts[0] not in {"generate", "workspace", "attachments"}:
        raise ValueError("source_path 必须是会话内 generate/workspace/attachments 下的相对路径")
    source = (session_root / relative).resolve()
    try:
        source.relative_to(session_root)
    except ValueError as exc:
        raise ValueError("参数 source_path 越出当前会话目录") from exc
    if not source.is_file():
        raise ValueError(f"参数 source_path 指向的输入文件不存在或不是文件：{relative.as_posix()}")
    if source.stat().st_size > 1_000_000:
        raise ValueError("XML 输入超过 1 MB")
    return source.read_text(encoding="utf-8")


def _config():
    config = json.loads(packaged_file(Path(__file__).resolve().parent, "config.json").read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        raise ValueError("config.json 必须为对象")
    return config


def architecture_edges(xml_text):
    """Native edges for explicitly requested architecture dependencies."""
    root = ET.fromstring(xml_text)
    for cell in root.iter("mxCell"):
        if cell.get("edge") != "1":
            continue
        for geometry in cell.findall("mxGeometry"):
            cell.remove(geometry)
        ET.SubElement(cell, "mxGeometry", {"relative": "1", "as": "geometry"})
        parts = [p for p in cell.get("style", "").split(";") if p and p.split("=", 1)[0] != "edgeStyle"]
        cell.set("style", "edgeStyle=orthogonalEdgeStyle;" + ";".join(parts) + ";")
    return ET.tostring(root, encoding="unicode", xml_declaration=True)


def generate(payload):
    args = payload.get("args", {})
    if not isinstance(args, dict):
        raise ValueError("args 必须是对象")
    workdir = Path(payload["workdir"]).resolve()
    session_root = Path(payload["session_root"]).resolve()
    workdir.relative_to(session_root)
    name = args.get("output_name", "flowchart")
    if not isinstance(name, str) or not re.fullmatch(r"[\w-]{1,80}", name):
        raise ValueError("output_name 须为 1–80 个文字、数字、下划线或连字符，不带路径/扩展名")
    diagram_type = args.get("diagram_type", "auto")
    if diagram_type not in {"auto", "flowchart", "architecture"}:
        raise ValueError("diagram_type 只能是 auto、flowchart 或 architecture")
    formats = args.get("formats", ["png", "svg"])
    if not isinstance(formats, list) or any(f not in ("png", "svg", "pdf") for f in formats):
        raise ValueError("formats 必须是 png/svg/pdf 的数组；空数组仅生成 .drawio")
    formats = list(dict.fromkeys(formats))
    raw = _source(args, session_root)
    if len(raw) > 1_000_000 or "<!DOCTYPE" in raw.upper() or "<!ENTITY" in raw.upper():
        raise ValueError("XML 过大或含不支持的 DTD/实体声明")
    xml = sanitize_xml(extract_xml(raw))
    if not xml:
        raise ValueError("未找到完整的 mxfile XML")
    if diagram_type == "auto":
        cells = list(ET.fromstring(xml).iter("mxCell"))
        diagram_type = "architecture" if (any(c.get("vertex") == "1" and c.get("parent") != "1" for c in cells)
                                           or not any(c.get("edge") == "1" for c in cells)) else "flowchart"
    nodes, edges = validate_structure(xml, diagram_type)
    if args.get("restyle_reference_path"):
        reference = sanitize_xml(extract_xml(_source({"source_path": args["restyle_reference_path"]}, session_root)))
        verify_restyle(xml, reference)
    config = _config()
    style = load_style(args.get("style_path", ""), session_root, diagram_type, Path(__file__).resolve().parent)
    visuals = edge_visuals(xml)
    options = style["options"]
    if diagram_type == "flowchart":
        layout = args.get("layout", {})
        if not isinstance(layout, dict) or not isinstance(config.get("layout", {}), dict):
            raise ValueError("layout 必须为对象")
        grid = make_flow_grid(**{**config.get("layout", {}), **options.get("layout", {}), **layout})
        xml = apply_flow_layout(xml, grid=grid)
    else:
        xml = architecture_edges(apply_layout(xml))
    xml = apply_visuals(xml, options, visuals)
    xml = apply_font(xml, options.get("font_family", config.get("font_family")),
                     str(options.get("font_size", config.get("font_size")) or ""))
    workdir.mkdir(parents=True, exist_ok=True)
    source = workdir / f"{name}.drawio"
    source.resolve().relative_to(workdir)
    source.write_text(xml, encoding="utf-8")
    files = [source.relative_to(session_root).as_posix()]
    images, exports, errors, warnings = export_diagram(source, session_root, formats, config)
    files.extend(images)
    result = f"draw.io 已生成：{nodes} 个节点、{edges} 条连线，结构校验与布局完成；未执行图像复检。"
    warnings.extend(error["message"] for error in errors)
    if errors:
        result = "图片导出未完成，已保留可编辑 .drawio 草稿。" + result + " " + "；".join(warnings)
    return {"ok": not errors, "status": "partial" if errors else "completed", "result": result, "files": files,
            "exports": exports, "errors": errors, "warnings": warnings,
            "diagram_type": diagram_type, "visual_review_performed": False}


def main():
    try:
        result = generate(json.load(sys.stdin))
    except Exception as exc:
        result = {"ok": False, "status": "failed", "result": f"draw.io 生成失败：{exc}", "files": []}
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    logging.basicConfig(stream=sys.stderr, level=logging.WARNING)
    sys.exit(main())
