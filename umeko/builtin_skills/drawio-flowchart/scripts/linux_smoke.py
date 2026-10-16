"""Model-free Linux acceptance: delegated preparation and both native diagram exports."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import xml.etree.ElementTree as ET


def main() -> None:
    parser = argparse.ArgumentParser(description="隔离目录内验证 Linux draw.io 绘图，不调用模型")
    parser.add_argument("--root", type=Path, default=Path("/work"))
    parser.add_argument("--font-family", default="Noto Sans CJK SC", help="必须是容器实际安装的字体 family")
    options = parser.parse_args()
    root = options.root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    for directory in ("attachments", "generate", "workspace"):
        (root / directory).mkdir(exist_ok=True)
    package = Path(__file__).resolve().parent
    runner = package.parent / "scripts" / "run.py"

    def run(script, arguments):
        argument_file = root / "workspace" / f"{script}.json"
        argument_file.write_text(json.dumps(arguments, ensure_ascii=False), encoding="utf-8")
        process = subprocess.run([sys.executable, str(runner), script, "--root", str(root),
                                  "--args-file", str(argument_file)],
                                 capture_output=True, text=True, encoding="utf-8", timeout=120)
        result = json.loads(process.stdout)
        if process.returncode or not result.get("ok") or result.get("warnings"):
            raise RuntimeError(f"{script}: {result}; {process.stderr}")
        return result

    (root / "attachments/request.md").write_text("中文流程：开始、审核、通过或退回、结束。", encoding="utf-8")
    # The distribution does not ship the original proprietary font. Use an installed
    # open font explicitly for this fixture; leave the original default style intact.
    style = (package.parent / "references/style.md").read_text(encoding="utf-8")
    style = re.sub(r"\A---\n", "---\nfont_family: " + json.dumps(options.font_family, ensure_ascii=False)
                   + "\nfont_size: 10.5\n", style, count=1)
    style_path = root / "attachments/linux-style.md"
    style_path.write_text(style, encoding="utf-8")
    font = subprocess.run(["fc-match", "-f", "%{family}", options.font_family], capture_output=True,
                          text=True, encoding="utf-8", check=True).stdout
    if options.font_family not in font:
        raise RuntimeError(f"测试字体未安装：{font}")
    prepared = run("prepare_drawio.py", {"document_paths": ["attachments/request.md"],
                   "diagram_type": "auto", "output_name": "linux", "style_path": "attachments/linux-style.md"})
    if not all((root / path).is_file() for path in prepared["files"]):
        raise RuntimeError("委派任务或规则文件未生成")
    records = []
    for kind in ("flowchart", "architecture"):
        rules = (package / f"{kind}.md").read_text(encoding="utf-8")
        examples = re.findall(r"```xml\n(.*?)```", rules, re.S)
        xml = next((example for example in examples if "rhombus" in example), examples[0])
        source = root / "generate" / f"{kind}-source.xml"
        source.write_text(xml, encoding="utf-8")
        result = run("generate_drawio.py", {"source_path": source.relative_to(root).as_posix(),
                     "output_name": kind, "diagram_type": kind, "formats": ["png", "svg", "pdf"],
                     "style_path": "attachments/linux-style.md"})
        if result["visual_review_performed"] or len(result["files"]) != 4:
            raise RuntimeError("导出结果不完整或发生自动视觉复检")
        produced = {}
        for relative in result["files"]:
            path = root / relative
            data = path.read_bytes()
            if path.suffix == ".png" and not data.startswith(b"\x89PNG\r\n\x1a\n"):
                raise RuntimeError("PNG 文件头错误")
            if path.suffix == ".pdf" and not data.startswith(b"%PDF-"):
                raise RuntimeError("PDF 文件头错误")
            if path.suffix == ".svg":
                ET.fromstring(data)
            if path.suffix == ".drawio":
                cells = ET.fromstring(data).iter("mxCell")
                if not all(f"fontFamily={options.font_family}" in c.get("style", "")
                           for c in cells if c.get("vertex") == "1"):
                    raise RuntimeError("配置字体未应用到节点")
            produced[relative] = len(data)
        records.append({"diagram_type": kind, "files": produced})
    # Prove the helper refuses a missing renderer instead of reporting success.
    missing = subprocess.run([str(Path("/usr/local/bin/drawio-headless")), "--help"],
                             env={**os.environ, "DRAWIO_BINARY": "/missing/drawio"},
                             capture_output=True, text=True)
    if not missing.returncode or "missing" not in missing.stderr:
        raise RuntimeError("缺少渲染器时没有正确失败")
    failure_file = root / "workspace/export-failure.json"
    failure_file.write_text(json.dumps({"source_path": "generate/flowchart-source.xml", "formats": ["png"],
                                       "output_name": "failure", "style_path": "attachments/linux-style.md"}), encoding="utf-8")
    for renderer, expected in (("/missing/drawio", "renderer_unavailable"),
                               ("/usr/local/bin/drawio-headless", "export_failed")):
        failure = subprocess.run([sys.executable, str(runner), "generate_drawio.py", "--root", str(root),
                                  "--args-file", str(failure_file)],
                                 env={**os.environ, "UMEKO_DRAWIO_PATH": renderer, "DRAWIO_BINARY": "/missing/drawio"},
                                 capture_output=True, text=True, encoding="utf-8", timeout=30)
        body = json.loads(failure.stdout)
        if (failure.returncode != 1 or body["ok"] or body.get("status") != "partial"
                or body["errors"][0]["code"] != expected or not body["errors"][0]["message"]
                or body["files"] != ["generate/failure.drawio"] or (root / "generate/failure.png").exists()):
            raise RuntimeError(f"导出失败没有完整返回诊断与草稿：{body}")
    summary = {"ok": True, "font": font, "prepared": prepared["files"], "diagrams": records,
               "visual_review_performed": False, "missing_renderer_rejected": True,
               "export_failure_diagnostics_retained": True}
    (root / "generate/linux-smoke.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
