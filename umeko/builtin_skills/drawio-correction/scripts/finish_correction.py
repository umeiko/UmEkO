"""Validate the converted graph and reuse draw.io layout/style helpers without export."""
from __future__ import annotations

import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from correction_common import normalize_xml, session_path
from drawio_flow import apply_flow_layout, make_flow_grid
from drawio_style import apply_visuals, edge_visuals, load_style, verify_restyle, packaged_file
from drawio_xml import apply_font, extract_xml, sanitize_xml

SKILL_SCRIPT = {
    "description": "校验流程图修正结果，保护原 draw.io 的节点/连线语义，复用确定性布局、字体及风格参数，只交付 .drawio/XML。",
    "usage": "仅在 prepare_correction.py 门禁通过且一次转换已写入 source_path 后运行。沿用准备阶段的 job.json，不导出 PNG/SVG/PDF，不做图像复检。",
    "input_schema": {"type": "object", "additionalProperties": False, "required": ["manifest_path"], "properties": {
        "manifest_path": {"type": "string", "minLength": 1, "description": "门禁返回的 manifest_path"},
        "return_xml": {"type": "boolean", "default": False, "description": "用户明确要源码时才返回完整 XML，默认只返回文件路径"},
    }},
    "outputs": ["generate/<output_name>.drawio：可编辑单页流程图", "用户显式要求时，stdout JSON 的 xml 字段包含完整源码"],
    "example_args": {"manifest_path": "generate/approval-job.json"},
}


def finish(payload):
    args = payload["args"]
    root, workdir = Path(payload["session_root"]).resolve(), Path(payload["workdir"]).resolve()
    workdir.relative_to(root)
    manifest = json.loads(session_path(args["manifest_path"], root).read_text(encoding="utf-8"))
    name = manifest["output_name"]
    if not re.fullmatch(r"[\w-]{1,80}", name):
        raise ValueError("准备任务中的 output_name 无效")
    source = session_path(manifest["source_path"], root)
    if source.stat().st_size > 400_000:
        raise ValueError("转换后的 XML 过大，请精简流程")
    raw = sanitize_xml(source.read_text(encoding="utf-8-sig"))
    xml = normalize_xml(extract_xml(raw) or raw)
    reference_path = session_path(manifest["input_path"], root)
    if manifest["kind"] == "drawio":
        reference = normalize_xml(reference_path.read_text(encoding="utf-8"))
        verify_restyle(xml, reference)
    package = Path(__file__).resolve().parent
    config = json.loads(packaged_file(package, "config.json").read_text(encoding="utf-8"))
    style = load_style(manifest.get("style_path", ""), root, "flowchart", package)
    options = style["options"]
    grid = make_flow_grid(**{**config.get("layout", {}), **options.get("layout", {})})
    laid_out = apply_flow_layout(xml, grid=grid)
    laid_out = apply_visuals(laid_out, options, edge_visuals(xml))
    laid_out = apply_font(laid_out, options.get("font_family", config.get("font_family")),
                          str(options.get("font_size", config.get("font_size")) or ""))
    # Layout must never silently change labels, branch conditions or connectivity.
    verify_restyle(laid_out, xml)
    normalize_xml(laid_out)
    output = (workdir / f"{name}.drawio").resolve()
    output.relative_to(workdir)
    output.write_text(laid_out, encoding="utf-8")
    result = {"ok": True, "status": "completed", "result": "流程图修正完成；已校验结构并整理布局，未导出图片或执行视觉复检。",
              "files": [output.relative_to(root).as_posix()], "style_source": style["source"]}
    if args.get("return_xml", False):
        result["xml"] = laid_out
        result["result"] += "\n```xml\n" + laid_out + "\n```"
    return result


def main():
    try:
        result = finish(json.load(sys.stdin))
    except (ValueError, OSError, KeyError) as exc:
        result = {"ok": False, "status": "failed", "result": f"流程图修正校验失败：{exc}", "files": [],
                  "error": {"code": "correction_invalid", "message": str(exc),
                            "hint": "只修复已指出的 XML/结构问题；不要重新理解业务或反复执行相同输入"}}
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    sys.exit(main())
