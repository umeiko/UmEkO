"""Skill-local Markdown style selection and deterministic visual overrides."""
from __future__ import annotations

from pathlib import Path
import re
import xml.etree.ElementTree as ET

EDGE_KEYS = {"strokeColor", "strokeWidth", "dashed", "dashPattern", "fontColor",
             "endArrow", "endFill", "startArrow", "startFill", "opacity"}


def packaged_file(package, name):
    legacy = package / name
    if legacy.is_file():
        return legacy
    root = package.parent if package.name == "scripts" else package
    return root / ("references" if name.endswith(".md") else "assets") / name


def session_file(value, root):
    if not isinstance(value, str):
        raise ValueError("style_path 必须为会话相对路径字符串")
    path = Path(value)
    if path.is_absolute() or not path.parts or path.parts[0] not in {"workspace", "attachments", "generate"}:
        raise ValueError("style_path 须位于当前会话的 workspace/attachments/generate")
    target = (root / path).resolve()
    target.relative_to(root)
    if not target.is_file() or target.suffix.lower() != ".md":
        raise ValueError("风格文件必须是存在的 Markdown 文件")
    if target.stat().st_size > 100_000:
        raise ValueError("风格文件超过 100 KB")
    return target


def _color(value):
    if not re.fullmatch(r"#[0-9a-fA-F]{3,8}|[a-zA-Z]+", value):
        raise ValueError("background/edge_color 须为十六进制颜色或颜色名称")
    return value


def load_style(style_path, root, diagram_type, package):
    source = session_file(style_path, root) if style_path else packaged_file(package, "style.md")
    text = source.read_text(encoding="utf-8")
    meta, body = {}, text
    match = re.match(r"\A---\s*\n(.*?)\n---\s*\n(.*)\Z", text, re.S)
    if match:
        for line in match.group(1).splitlines():
            key, separator, value = line.partition(":")
            if separator:
                meta[key.strip()] = value.strip().strip("'\"")
        body = match.group(2)
    # Keep common guidance and only the relevant native diagram section.
    parts = re.split(r"(?m)(^## .*$)", body)
    selected = [parts[0].strip()]
    for index in range(1, len(parts), 2):
        heading, content = parts[index], parts[index + 1]
        tagged = re.match(r"##\s+\[([^]]+)\]\s*(.*)", heading)
        if tagged:
            if tagged.group(1) == "drawio:" + diagram_type:
                selected.append("## " + (tagged.group(2) or "图型风格") + "\n" + content.strip())
        else:
            selected.append(heading + "\n" + content.strip())
    options = {}
    for key in ("background", "edge_color"):
        if meta.get(key):
            options[key] = _color(meta[key])
    for key in ("font_size", "edge_width"):
        if meta.get(key):
            value = float(meta[key])
            if not 0 < value <= 100:
                raise ValueError(f"{key} 须大于 0 且不超过 100")
            options[key] = meta[key]
    if meta.get("font_family"):
        if any(c in meta["font_family"] for c in ";=<>\r\n"):
            raise ValueError("font_family 包含非法样式分隔符")
        options["font_family"] = meta["font_family"]
    if meta.get("layout"):
        layout = {}
        for item in meta["layout"].split(","):
            key, separator, value = item.strip().partition("=")
            if not separator or key not in {"node_width", "node_height", "gap_x", "gap_y"}:
                raise ValueError("风格 layout 仅支持 node_width/node_height/gap_x/gap_y")
            layout[key] = float(value)
            if not 1 <= layout[key] <= 10000:
                raise ValueError("layout 尺寸须在 1–10000 之间")
        options["layout"] = layout
    return {"instructions": "\n\n".join(p for p in selected if p), "options": options,
            "name": meta.get("name", source.stem), "source": style_path or "包内 style.md"}


def edge_visuals(xml_text):
    return {cell.get("id"): {key: value for item in cell.get("style", "").split(";")
                             if "=" in item for key, value in [item.split("=", 1)] if key in EDGE_KEYS}
            for cell in ET.fromstring(xml_text).iter("mxCell") if cell.get("edge") == "1"}


def apply_visuals(xml_text, options, original_edges):
    root = ET.fromstring(xml_text)
    model = root.find("diagram/mxGraphModel")
    if options.get("background"):
        model.set("background", options["background"])
    for cell in root.iter("mxCell"):
        if cell.get("edge") != "1":
            continue
        props = dict(original_edges.get(cell.get("id"), {}))
        if options.get("edge_color"):
            props["strokeColor"] = options["edge_color"]
        if options.get("edge_width"):
            props["strokeWidth"] = options["edge_width"]
        # Override visual properties only; keep all computed routing and geometry.
        parts = [p for p in cell.get("style", "").split(";") if p and p.split("=", 1)[0] not in props]
        cell.set("style", ";".join(parts + [f"{k}={v}" for k, v in props.items()]) + ";")
    return ET.tostring(root, encoding="unicode", xml_declaration=True)


def verify_restyle(xml_text, reference):
    def signature(xml):
        root = ET.fromstring(xml)
        return {cell.get("id"): tuple(cell.get(k) for k in
                ("value", "parent", "vertex", "edge", "source", "target")) for cell in root.iter("mxCell")}

    if signature(xml_text) != signature(reference):
        raise ValueError("仅换风格不得修改节点 ID、文字、层次、连线端点或分支标签")
