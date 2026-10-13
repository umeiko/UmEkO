#!/usr/bin/env python
"""Stage package rules and a bounded task for the existing file sub-agent."""
from __future__ import annotations

import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from drawio_style import load_style


def prepare(payload):
    args = payload.get("args", {})
    if not isinstance(args, dict):
        raise ValueError("args 必须为对象")
    session_root = Path(payload["session_root"]).resolve()
    workdir = Path(payload["workdir"]).resolve()
    workdir.relative_to(session_root)
    name = args.get("output_name", "flowchart")
    if not isinstance(name, str) or not re.fullmatch(r"[\w-]{1,80}", name):
        raise ValueError("output_name 不带路径或扩展名，限文字、数字、下划线和连字符")
    diagram_type = args.get("diagram_type", "auto")
    if diagram_type not in {"auto", "flowchart", "architecture"}:
        raise ValueError("diagram_type 只能是 auto、flowchart 或 architecture")
    request = args.get("request", "")
    documents = args.get("document_paths", [])
    if not isinstance(request, str) or len(request) > 4000:
        raise ValueError("request 为简短需求，最多 4000 字；长文档请传 document_paths")
    if not isinstance(documents, list) or len(documents) > 30:
        raise ValueError("document_paths 为数组，最多 30 个会话文件路径")
    for item in documents:
        if not isinstance(item, str):
            raise ValueError("文档路径必须为字符串")
        path = Path(item)
        if path.is_absolute() or not path.parts or path.parts[0] not in {"workspace", "attachments", "generate"}:
            raise ValueError("文档路径须为当前会话内的相对路径")
        resolved = (session_root / path).resolve()
        resolved.relative_to(session_root)
        if not resolved.is_file():
            raise ValueError(f"输入文档不存在：{item}")
    package = Path(__file__).resolve().parent
    config = json.loads((package / "config.json").read_text(encoding="utf-8"))
    style_path = args.get("style_path", "")
    workdir.mkdir(parents=True, exist_ok=True)
    rule_path = workdir / f"{name}-rules.md"
    task_path = workdir / f"{name}-task.md"
    source_path = workdir / f"{name}-source.xml"
    outline_path = workdir / f"{name}-outline.md"

    def relative(path):
        path.resolve().relative_to(workdir)
        return path.relative_to(session_root).as_posix()

    kinds = ["flowchart", "architecture"] if diagram_type == "auto" else [diagram_type]
    rules_paths = {}
    style_name = ""
    relative(task_path)
    for index, kind in enumerate(kinds):
        current_rule = rule_path if index == 0 else workdir / f"{name}-{kind}-rules.md"
        rules_paths[kind] = relative(current_rule)
        style = load_style(style_path, session_root, kind, package)
        style_name = style["name"]
        rule = (package / ("flowchart.md" if kind == "flowchart" else "architecture.md")).read_text(encoding="utf-8")
        rule += "\n\n## 本次选用风格（视觉要求优先于默认配色，业务含义与结构规范仍须保留）\n\n"
        rule += style["instructions"]
        rule += "\n\n## 当前生效视觉配置\n\n"
        visual = {**config, **style["options"]}
        fields = ("font_family", "font_size", "background", "edge_color", "edge_width")
        effective = {k: visual.get(k) for k in fields}
        if kind == "flowchart":
            effective["layout"] = {**config.get("layout", {}), **style["options"].get("layout", {})}
        else:
            effective["architecture_grid"] = {"component_width": 180, "component_height": 60,
                                               "columns": 4, "gap": 20, "title_height": 30}
        rule += json.dumps(effective, ensure_ascii=False, indent=2)
        current_rule.write_text(rule, encoding="utf-8")
    task = (package / "delegation.md").read_text(encoding="utf-8")
    task += "\n\n## 本次任务\n\n" + json.dumps({
        "request": request, "document_paths": documents, "diagram_type": diagram_type,
        "rules_path": relative(rule_path), "outline_path": relative(outline_path),
        "rules_paths": rules_paths,
        "source_path": relative(source_path),
        "style_path": style_path, "style_name": style_name,
    }, ensure_ascii=False, indent=2)
    task_path.write_text(task, encoding="utf-8")
    delegation_task = (
        f"读取 {relative(task_path)} 并执行里面的单个文件任务：若图型为 auto，先依据需求判断是流程流转还是系统组成，再读取对应 rules_paths 的规范；"
        f"将简要作图清单写入 {relative(outline_path)}，完整 XML 写入 {relative(source_path)}。"
        "最终只返回这两个路径、图型、节点/分支摘要及未解决问题，最多 500 字，不返回原文或 XML。"
        "不要执行绘图脚本或图像复检，主 Agent 负责运行脚本。"
    )
    return {"ok": True, "result": delegation_task,
            "files": [relative(task_path), *rules_paths.values()],
            "source_path": relative(source_path), "outline_path": relative(outline_path), "style_path": style_path}


def main():
    try:
        result = prepare(json.load(sys.stdin))
    except Exception as exc:
        result = {"ok": False, "result": f"委派准备失败：{exc}", "files": []}
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    main()
