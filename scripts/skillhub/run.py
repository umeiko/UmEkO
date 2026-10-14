"""Run the preserved UmEkO skill scripts from any local Agent host (stdlib only)."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys


SCRIPTS = {
    "prepare_drawio.py": "drawio-flowchart",
    "generate_drawio.py": "drawio-flowchart",
    "render_report.py": "doc-image-qc",
}


def diagnostic(value):
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    return str(value or "").strip()[-4000:]


def script_result(completed):
    """A nonzero exit must retain a valid failure JSON and its actual output files."""
    try:
        lines = completed.stdout.strip().splitlines()
        result = json.loads(lines[-1])
        if not isinstance(result, dict) or not isinstance(result.get("ok"), bool):
            raise ValueError("脚本未返回有效的 JSON 结果")
    except (ValueError, IndexError):
        result = {"ok": False, "status": "failed", "result": "脚本未返回有效的 JSON 结果", "files": []}
        if completed.stdout.strip():
            result["result"] += "\nstdout 尾部：" + diagnostic(completed.stdout)
    if completed.returncode:
        if result["ok"]:
            result["ok"], result["status"] = False, "failed"
        result["exit_code"] = completed.returncode
        result["result"] = f"脚本退出码 {completed.returncode}：" + str(result.get("result", ""))
    if not result["ok"] and completed.stderr:
        result["stderr"] = diagnostic(completed.stderr)
        result["result"] = str(result.get("result", "")) + "\nstderr 尾部：" + result["stderr"]
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="运行本包的确定性脚本，不调用模型")
    parser.add_argument("script", choices=SCRIPTS)
    parser.add_argument("--root", type=Path, required=True, help="本次任务目录")
    args_group = parser.add_mutually_exclusive_group(required=True)
    args_group.add_argument("--args-file", type=Path, help="UTF-8 JSON 参数对象的文件路径")
    args_group.add_argument("--args", help="JSON 参数对象；长参数建议使用 --args-file")
    options = parser.parse_args()
    try:
        root = options.root.resolve(strict=True)
        if not root.is_dir():
            raise ValueError("任务根目录必须是已存在的目录")
        arguments = json.loads(options.args_file.read_text(encoding="utf-8-sig")
                               if options.args_file else options.args)
        if not isinstance(arguments, dict):
            raise ValueError("脚本参数必须是 JSON 对象")
        script = Path(__file__).resolve().parents[1] / SCRIPTS[options.script] / options.script
        if not script.is_file():
            raise ValueError("本技能包未包含所选脚本")
        workdir = root / "generate"
        workdir.resolve().relative_to(root)
        workdir.mkdir(exist_ok=True)
        payload = {"args": arguments, "session_root": str(root), "workdir": str(workdir)}
        completed = subprocess.run(
            [sys.executable, "-X", "utf8", str(script)],
            input=json.dumps(payload, ensure_ascii=False), text=True, encoding="utf-8",
            capture_output=True, timeout=120,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if completed.stderr:
            print(completed.stderr, file=sys.stderr, end="")
        result = script_result(completed)
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        result = {"ok": False, "result": str(exc), "files": []}
        if isinstance(exc, subprocess.TimeoutExpired):
            result["stderr"] = diagnostic(exc.stderr)
            if result["stderr"]:
                result["result"] += "\nstderr 尾部：" + result["stderr"]
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    sys.exit(main())
