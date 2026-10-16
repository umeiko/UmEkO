"""Bounded input gate shared by the correction preparation and final validation."""
from __future__ import annotations

import base64
from pathlib import Path
import re
from urllib.parse import unquote
import xml.etree.ElementTree as ET
import zlib

from generate_drawio import validate_structure

MAX_XML = 100_000
MAX_NODES = 60
MAX_EDGES = 120


class Rejected(ValueError):
    pass


def session_path(value, root, *, exists=True):
    path = Path(value)
    if path.is_absolute() or not path.parts or path.parts[0] not in {"workspace", "attachments", "generate"}:
        raise ValueError("路径必须位于本次会话的 workspace/attachments/generate")
    target = (root / path).resolve()
    target.relative_to(root)
    if exists and not target.is_file():
        raise ValueError("输入文件不存在，请提供本次会话中实际存在的文件")
    return target


def unfence(text):
    match = re.fullmatch(r"\s*```([^\n]*)\n(.*?)\n```\s*", text, re.S)
    if match and match.group(1).strip().lower() not in {"", "mermaid", "xml", "drawio", "md", "markdown", "text"}:
        raise Rejected("不接收其他编程语言代码，请提供流程图源码")
    return (match.group(2) if match else text).strip()


def normalize_xml(text):
    if len(text) > MAX_XML or "<!DOCTYPE" in text.upper() or "<!ENTITY" in text.upper():
        raise Rejected("XML 超过 100,000 字符或包含不支持的实体声明")
    try:
        root = ET.fromstring(text)
        if root.tag == "mxGraphModel":
            model = root
            root = ET.Element("mxfile")
            ET.SubElement(root, "diagram", {"name": "Flowchart"}).append(model)
        if root.tag != "mxfile" or len(root.findall("diagram")) != 1:
            raise Rejected("快速修正只接收单页 draw.io XML")
        diagram = root.find("diagram")
        if diagram.find("mxGraphModel") is None and diagram.text:
            compressed = base64.b64decode(diagram.text.strip(), validate=True)
            decoder = zlib.decompressobj(-15)
            decoded = decoder.decompress(compressed, MAX_XML + 1)
            if len(decoded) > MAX_XML or not decoder.eof or decoder.unused_data:
                raise Rejected("压缩图表过大或数据不完整")
            model_text = unquote(decoded.decode("utf-8"))
            if "<!DOCTYPE" in model_text.upper() or "<!ENTITY" in model_text.upper():
                raise Rejected("XML 不支持实体声明")
            diagram.text = None
            diagram.append(ET.fromstring(model_text))
        xml = ET.tostring(root, encoding="unicode")
        nodes, edges = validate_structure(xml, "architecture")
        if not 2 <= nodes <= MAX_NODES or not 1 <= edges <= MAX_EDGES:
            raise Rejected(f"快速修正支持 2–{MAX_NODES} 个节点、1–{MAX_EDGES} 条连线")
        if any(c.get("parent") != "1" for c in root.iter("mxCell") if c.get("vertex") == "1" or c.get("edge") == "1"):
            raise Rejected("暂不接收含分组或嵌套容器的 XML，请提供单层流程图")
        return xml
    except Rejected:
        raise
    except (ET.ParseError, ValueError, zlib.error) as exc:
        raise Rejected("draw.io XML 无法解析或节点/连线结构无效；请提供有效的单页源码") from exc


def classify(text):
    text = unfence(text)
    if not text:
        raise Rejected("未取得流程图源码或简短流程描述")
    if text.startswith("<"):
        return "drawio", normalize_xml(text)
    if "```" in text:
        raise Rejected("请只提供一个流程源码块，不混入其他代码块")
    lines = [line for line in text.splitlines() if line.strip() and not line.lstrip().startswith("%%")]
    header = lines[0].strip() if lines else ""
    if re.match(r"^(?:flowchart|graph)\s+(?:TB|TD|BT|LR|RL)\b", header):
        if len(text) > 8_000 or len(lines) > 120:
            raise Rejected("Mermaid 超过快速修正上限：8,000 字符或 120 行")
        if not re.search(r"-->|---|==>|-\.->|--\s+[^\n]+?\s+-->", text):
            raise Rejected("Mermaid 中未找到流程连线")
        if len(re.findall(r"-->|---|==>|-\.->", text)) > MAX_EDGES:
            raise Rejected("Mermaid 连线过多，请拆成较小流程")
        return "mermaid", text
    if re.match(r"^(?:sequenceDiagram|classDiagram|stateDiagram|erDiagram|journey|gantt|pie|mindmap|timeline|quadrantChart|xychart|sankey|block-beta|packet|architecture)\b", header):
        raise Rejected("仅接收 Mermaid 流程图 flowchart/graph，不接收其他图型")
    if len(text) > 2_000 or len(lines) > 30:
        raise Rejected("Markdown 流程描述需精简到 2,000 字符、30 行以内；长需求文档请使用流程图生成智能体")
    if "```" in text or re.search(r"!\[[^]]*\]\(|<img\b|https?://", text, re.I):
        raise Rejected("图片、网页链接及其他代码不属于可直接修正的流程源码")
    ordered = re.findall(r"(?m)^\s*\d+[.)、]\s*\S.*", text)
    arrows = re.search(r"\S\s*(?:→|->(?!>)|-->)(?!>)\s*\S", text)
    if len(ordered) >= 2 or arrows:
        return "markdown", text
    raise Rejected("未识别出明确的流程步骤或流转关系；请提供 Mermaid、draw.io XML，或用编号/箭头写成简短流程")
