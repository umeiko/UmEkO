"""Build an editable draw.io design principle diagram from a bounded mechanism model."""

from __future__ import annotations

import json
from pathlib import Path
import re
import sys
from tempfile import NamedTemporaryFile
import xml.etree.ElementTree as ET


SKILL_SCRIPT = {
    "description": "校验机制模型与网格，生成可编辑 draw.io 原理图，按需导出图片。",
    "usage": "传入会话内的 JSON model_path。默认只生成 .drawio；传 formats=['png','svg'] 可同时导出两种图片。",
    "input_schema": {"type": "object", "additionalProperties": False,
                     "required": ["model_path"], "properties": {
        "model_path": {"type": "string", "minLength": 1, "maxLength": 300},
        "output_name": {"type": "string", "pattern": r"^[\w-]{1,80}$", "default": "principle"},
        "formats": {"type": "array", "maxItems": 2, "uniqueItems": True,
                    "items": {"enum": ["png", "svg"]}, "default": []},
    }},
    "outputs": ["generate/<output_name>.drawio", "按需导出 .png 和 .svg；files 仅列出成功产物，exports 和 errors 记录各格式结果"],
    "example_args": {"model_path": "generate/principle-model.json", "output_name": "principle"},
}

ROLES = {
    "input": ("#F0F6FF", "#7595BC"),
    "mechanism": ("#EEF8F7", "#448785"),
    "state": ("#F4F0FE", "#8D79B9"),
    "output": ("#EDF7EE", "#578659"),
}

RELATIONS = {
    "data": ("传递", "#415977", "0"),
    "control": ("控制", "#6750A4", "1"),
    "feedback": ("反馈", "#006D68", "1"),
    "fallback": ("保护／降级", "#A64B17", "1"),
}

ICONS = {
    "input": "shape=parallelogram;perimeter=parallelogramPerimeter;",
    "output": "shape=trapezoid;perimeter=trapezoidPerimeter;",
    "process": "shape=process;",
    "decision": "rhombus;",
    "storage": "shape=cylinder3;",
    "document": "shape=document;",
    "folder": "shape=folder;",
    "cloud": "cloud;",
    "measure": "ellipse;",
    "rule": "shape=hexagon;perimeter=hexagonPerimeter2;",
    "component": "shape=cube;",
    "trigger": "shape=step;",
    "note": "shape=note;",
    "card": "shape=card;",
}

CARD_WIDTH, CARD_HEIGHT = 212, 84
MARGIN, TOP = 48, 150
COLUMN_STEP, ROW_STEP = 328, 178
MAX_MODEL_BYTES = 64 * 1024


def _text(value, field, maximum):
    if not isinstance(value, str) or not 1 <= len(value.strip()) <= maximum:
        raise ValueError(f"{field} 必须为 1–{maximum} 字的单行文字")
    if re.search(r"[\x00-\x1f\ud800-\udfff\ufffe\uffff]", value):
        raise ValueError(f"{field} 含换行或 XML 无效字符")
    return value.strip()


def _object(value, field, required, optional=()):
    if not isinstance(value, dict) or not set(required) <= value.keys() or value.keys() - {*required, *optional}:
        raise ValueError(f"{field} 字段与机制图模型约定不符")
    return value


def _validate(model):
    _object(model, "model", ("title", "principle", "nodes", "layout", "relations"), ("basis",))
    title = _text(model["title"], "title", 40)
    principle = _text(model["principle"], "principle", 90)
    basis = _text(model["basis"], "basis", 90) if "basis" in model else ""
    if not isinstance(model["nodes"], list) or not 2 <= len(model["nodes"]) <= 12:
        raise ValueError("nodes 需要 2–12 个节点")
    if not isinstance(model["relations"], list) or not 1 <= len(model["relations"]) <= 20:
        raise ValueError("relations 需要 1–20 条关系")
    nodes = {}
    for index, node in enumerate(model["nodes"]):
        field = f"nodes[{index}]"
        _object(node, field, ("id", "label", "role"), ("detail", "icon", "assumed"))
        node_id = _text(node["id"], f"{field}.id", 32)
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,31}", node_id) or node_id in nodes:
            raise ValueError(f"{field}.id 格式无效或重复")
        role = _text(node["role"], f"{field}.role", 16)
        icon = _text(node["icon"], f"{field}.icon", 16) if "icon" in node else None
        if role not in ROLES or (icon is not None and icon not in ICONS):
            raise ValueError(f"{field} 的角色或图标键未收录")
        if "assumed" in node and type(node["assumed"]) is not bool:
            raise ValueError(f"{field}.assumed 必须为布尔值")
        nodes[node_id] = {
            "label": _text(node["label"], f"{field}.label", 18),
            "detail": _text(node["detail"], f"{field}.detail", 28) if "detail" in node else "",
            "role": role, "icon": icon, "assumed": node.get("assumed", False),
        }
    layout = _object(model["layout"], "layout", nodes)
    occupied = set()
    for index, (node_id, slot) in enumerate(layout.items()):
        if (not isinstance(slot, list) or len(slot) != 2 or any(type(n) is not int for n in slot)
                or not (0 <= slot[0] <= 4 and 0 <= slot[1] <= 3)):
            raise ValueError(f"layout 的第 {index + 1} 个槽位须为有效的 [列, 行]")
        if tuple(slot) in occupied:
            raise ValueError("layout 存在重复槽位")
        occupied.add(tuple(slot))
        nodes[node_id]["position"] = (MARGIN + slot[0] * COLUMN_STEP, TOP + slot[1] * ROW_STEP)
    edges = []
    endpoints = set()
    pairs = set()
    for index, relation in enumerate(model["relations"]):
        field = f"relations[{index}]"
        _object(relation, field, ("source", "target", "label", "kind"))
        source = _text(relation["source"], f"{field}.source", 32)
        target = _text(relation["target"], f"{field}.target", 32)
        kind = _text(relation["kind"], f"{field}.kind", 16)
        if source not in nodes or target not in nodes or source == target or (source, target) in pairs:
            raise ValueError(f"{field} 端点缺失、自连或重复")
        if kind not in RELATIONS:
            raise ValueError(f"{field}.kind 未收录")
        endpoints.update((source, target))
        pairs.add((source, target))
        edges.append((source, target, _text(relation["label"], f"{field}.label", 12), kind))
    if endpoints != nodes.keys():
        raise ValueError("存在未接入任何关系的节点，可连接到机制或将其移入依据说明")
    return title, principle, basis, nodes, edges


def _vertex(root, cell_id, label, style, box, parent="1"):
    cell = ET.SubElement(root, "mxCell", id=cell_id, value=label, style=style, vertex="1", parent=parent)
    geometry = {key: str(value) for key, value in zip(("x", "y", "width", "height"), box)}
    ET.SubElement(cell, "mxGeometry", geometry, **{"as": "geometry"})


def _ports(sx, sy, tx, ty):
    if sx != tx:
        return (1, 0.5, 0, 0.5) if sx < tx else (0, 0.5, 1, 0.5)
    return (0.5, 1, 0.5, 0) if sy < ty else (0.5, 0, 0.5, 1)


def _feedback_leg(x, y, fraction, right, nodes, corridor):
    port = x + CARD_WIDTH * fraction
    if not any(node["position"][0] == x and node["position"][1] > y for node in nodes.values()):
        return [(port, corridor)]
    gap_x = x + CARD_WIDTH + 20 if right else x - 20
    gap_y = y + CARD_HEIGHT + 20
    return [(port, gap_y), (gap_x, gap_y), (gap_x, corridor)]


def _edge(root, index, source, target, label, kind, nodes, bottom, feedback_row):
    sx, sy = nodes[source]["position"]
    tx, ty = nodes[target]["position"]
    _, color, dashed = RELATIONS[kind]
    ports = _ports(sx, sy, tx, ty)
    points = []
    if kind == "feedback":
        ports = (0.75, 1, 0.25, 1)
        corridor = bottom + 44 + feedback_row * 36
        outgoing = _feedback_leg(sx, sy, ports[0], sx >= tx, nodes, corridor)
        incoming = _feedback_leg(tx, ty, ports[2], sx < tx, nodes, corridor)
        points = outgoing + list(reversed(incoming))
    exit_x, exit_y, entry_x, entry_y = ports
    style = ("edgeStyle=orthogonalEdgeStyle;rounded=0;html=0;endArrow=block;endFill=1;"
             "fontSize=12;labelBackgroundColor=#FFFFFF;strokeWidth=2;"
             f"strokeColor={color};fontColor={color};dashed={dashed};"
             f"exitX={exit_x};exitY={exit_y};entryX={entry_x};entryY={entry_y};")
    cell = ET.SubElement(root, "mxCell", id=f"edge-{index}", value=label, style=style, parent="1",
                         edge="1", source=f"node-{source}", target=f"node-{target}")
    geometry = ET.SubElement(cell, "mxGeometry", relative="1", **{"as": "geometry"})
    if points:
        array = ET.SubElement(geometry, "Array", **{"as": "points"})
        for x, y in points:
            ET.SubElement(array, "mxPoint", x=str(x), y=str(y))


def build_diagram(model):
    title, principle, basis, nodes, edges = _validate(model)
    bottom = max(node["position"][1] for node in nodes.values()) + CARD_HEIGHT
    width = max(768, max(node["position"][0] for node in nodes.values()) + CARD_WIDTH + MARGIN)
    feedback_count = sum(edge[3] == "feedback" for edge in edges)
    legend_y = bottom + 58 + feedback_count * 36
    mxfile = ET.Element("mxfile")
    diagram = ET.SubElement(mxfile, "diagram", id="principle", name="设计原理")
    graph = ET.SubElement(diagram, "mxGraphModel", grid="0", page="1", pageScale="1", background="#FFFFFF",
                          pageWidth=str(width), pageHeight=str(legend_y + 96))
    root = ET.SubElement(graph, "root")
    ET.SubElement(root, "mxCell", id="0")
    ET.SubElement(root, "mxCell", id="1", parent="0")
    text_style = "text;align=left;verticalAlign=middle;whiteSpace=wrap;html=0;spacing=0;"
    _vertex(root, "title", title, text_style + "fontSize=28;fontStyle=1;fontColor=#17283F;",
            (MARGIN, 28, width - 2 * MARGIN, 40))
    _vertex(root, "principle", principle, text_style + "fontSize=17;fontColor=#425772;",
            (MARGIN, 76, width - 2 * MARGIN, 56))

    for node_id, node in nodes.items():
        x, y = node["position"]
        fill, stroke = ROLES[node["role"]]
        icon = node["icon"]
        style = ("rounded=1;arcSize=12;whiteSpace=wrap;html=0;align=left;verticalAlign=middle;"
                 f"spacingLeft={47 if icon else 14};spacingRight=12;fontSize=14;strokeWidth=1.5;"
                 f"fontColor=#17283F;fillColor={fill};strokeColor={stroke};")
        label = node["label"]
        if node["assumed"]:
            label += "〔待验证〕"
            style += "dashed=1;"
        if node["detail"]:
            label += "\n" + node["detail"]
        _vertex(root, f"node-{node_id}", label, style, (x, y, CARD_WIDTH, CARD_HEIGHT))
        if icon:
            _vertex(root, f"icon-{node_id}", "", ICONS[icon] + f"fillColor=#FFFFFF;strokeColor={stroke};strokeWidth=2;",
                    (14, 29, 24, 24), f"node-{node_id}")

    feedback_row = 0
    for index, (source, target, label, kind) in enumerate(edges):
        _edge(root, index, source, target, label, kind, nodes, bottom, feedback_row)
        feedback_row += kind == "feedback"

    used = {edge[3] for edge in edges}
    legend = [(name, color, dashed) for key, (name, color, dashed) in RELATIONS.items() if key in used]
    for index, (name, color, dashed) in enumerate(legend):
        marker = "┄" if dashed == "1" else "━"
        _vertex(root, f"legend-{index}", f"{marker}  {name}", text_style + f"fontSize=13;fontColor={color};",
                (MARGIN + index * 126, legend_y, 118, 23))
    if basis:
        _vertex(root, "basis", f"依据或条件  {basis}", text_style + "fontSize=12;fontColor=#536579;",
                (MARGIN, legend_y + 30, width - 2 * MARGIN, 42))
    return ET.tostring(mxfile, encoding="unicode")


def _write_output(path, data):
    temporary = None
    try:
        with NamedTemporaryFile(dir=path.parent, prefix=".principle-", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(data)
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def generate(payload):
    args = _object(payload.get("args"), "args", ("model_path",), ("output_name", "formats"))
    root = Path(payload["session_root"]).resolve()
    workdir = Path(payload["workdir"]).resolve()
    if not workdir.is_relative_to(root):
        raise ValueError("workdir 不在会话目录内")
    name = args.get("output_name", "principle")
    if not isinstance(name, str) or not re.fullmatch(r"[\w-]{1,80}", name):
        raise ValueError("output_name 只能包含文字、数字、下划线和连字符")
    formats = args.get("formats", [])
    if (not isinstance(formats, list) or len(formats) > 2 or any(fmt not in ("png", "svg") for fmt in formats)
            or len(set(formats)) != len(formats)):
        raise ValueError("formats 必须为 png/svg 的无重复数组")
    value = args["model_path"]
    if not isinstance(value, str) or len(value) > 300:
        raise ValueError("model_path 必须为会话内的 JSON 相对路径")
    relative = Path(value)
    if (relative.anchor or not relative.parts or ".." in relative.parts
            or relative.parts[0] not in {"workspace", "attachments", "generate"}
            or relative.suffix.lower() != ".json"):
        raise ValueError("model_path 必须为会话内的 JSON 相对路径")
    source = (root / relative).resolve()
    if not source.is_relative_to(root) or not source.is_file():
        raise ValueError("model_path 必须指向会话内的普通 JSON 文件")
    with source.open("rb") as stream:
        data = stream.read(MAX_MODEL_BYTES + 1)
    if len(data) > MAX_MODEL_BYTES:
        raise ValueError("模型超过 64 KiB")
    xml = build_diagram(json.loads(data.decode("utf-8-sig")))
    workdir.mkdir(parents=True, exist_ok=True)
    output = workdir / f"{name}.drawio"
    _write_output(output, xml.encode("utf-8"))
    files = [output.relative_to(root).as_posix()]
    images, exports, errors, warnings = [], [], [], []
    if formats:
        from drawio_xml import export_diagram

        config_path = Path(__file__).resolve().parents[1] / "assets/config.json"
        images, exports, errors, warnings = export_diagram(output, root, formats, config_path, python_fallback=True)
    files.extend(images)
    warnings.extend(dict.fromkeys(error["message"] for error in errors))
    message = "已生成可编辑设计原理图。"
    if warnings:
        message += " " + "；".join(warnings)
    return {"ok": not errors, "status": "partial" if errors else "completed", "result": message,
            "files": files, "exports": exports, "errors": errors, "warnings": warnings}


def main():
    try:
        result = generate(json.load(sys.stdin))
    except (KeyError, ValueError, OSError, RecursionError) as exc:
        detail = "无法读取或写入会话文件" if isinstance(exc, OSError) else str(exc)[:300]
        result = {"ok": False, "status": "failed", "result": f"原理图模型校验失败。{detail}", "files": []}
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    for stream in (sys.stdin, sys.stdout):
        stream.reconfigure(encoding="utf-8")
    sys.exit(main())
