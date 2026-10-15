"""run_skill_script：技能包自带脚本的通用受限执行器（框架机制，无领域知识）。

技能包结构约定：
    skills/<pack-name>.md            提示词（现有机制）
    skills/<pack-name>/<script>.py   包内脚本（本工具可执行）

脚本契约（管理员面板可下载模板）：
    stdin  : {"args": {...}, "workdir": "<Session 产物目录绝对路径>",
              "session_root": "<Session 根绝对路径>"}
    stdout : 一行 JSON {"ok": bool, "result": "给模型的结论", "files": [...]}
    stderr : 进度文本（结束后尾行透传给工具卡片，失败诊断同时返回模型）

沙箱约束：
    - 只能执行技能库目录内、且包名与 .md 同名的子目录下的 .py（防穿越）
    - 独立子进程（venv 同解释器），默认 60s 超时强杀（取消请求也强杀）
    - stdout 只保留最后一行（结果）；stderr 保留尾部若干行
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from pathlib import Path
from typing import Callable

from ..cancellation import CancelCheck
from ..skillpacks import skill_packs_dir

DEFAULT_TIMEOUT = 60  # 秒；硬上限由调用方传入
MAX_DIAGNOSTIC_CHARS = 4000


def _tail(value: str) -> str:
    return value.strip()[-MAX_DIAGNOSTIC_CHARS:]


def _script_result(out: str, err: str, code: int, *, timed_out: int | None = None) -> str:
    """Keep failure evidence in the model's tool result, not only UI progress events."""
    lines = [line for line in out.strip().splitlines() if line.strip()]
    stderr = _tail(err)

    def failure(message):
        return (f"错误：{message}\n脚本退出码：{code}"
                + (f"\nstdout 尾部：{_tail(out)}" if out.strip() else "")
                + (f"\nstderr 尾部：{stderr}" if stderr else ""))

    if timed_out is not None:
        return failure(f"脚本执行超时（>{timed_out}s），已强制终止。请根据下方诊断检查脚本和运行环境。")
    if not lines:
        return failure("脚本无输出")
    try:
        result = json.loads(lines[-1])
    except (json.JSONDecodeError, TypeError):
        return failure("脚本输出不符合契约（最后一行须为 JSON 对象）")
    if not isinstance(result, dict) or not isinstance(result.get("ok"), bool):
        return failure("脚本结果须为 JSON 对象，ok 须为布尔值")
    files = result.get("files", [])
    if files is None:
        files = []
    if not isinstance(files, list) or any(not isinstance(path, str) for path in files):
        return failure("脚本结果 files 须为文件路径数组")
    ok = result["ok"] and code == 0
    text = str(result.get("result") or "脚本未提供结果说明")
    if not ok:
        label = "脚本部分失败" if result.get("status") == "partial" else "脚本报告失败"
        text = f"错误：{label}（退出码 {code}）：{text}"
    for key in ("error", "errors", "warnings"):
        value = result.get(key)
        if value:
            if isinstance(value, list) and all(isinstance(item, str) for item in value):
                detail = "；".join(item for item in value if item not in text)
            else:
                detail = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
            # Some scripts already include warnings in their summary; retain new evidence only.
            if detail and detail not in text:
                text += f"\n{key}：{_tail(detail)}"
    if stderr and not ok:
        text += f"\nstderr 尾部：{stderr}"
    if files:
        text += "\n产物文件：" + "、".join(files)
    return text


def _resolve_script(pack: str, script: str) -> Path:
    """解析并校验脚本路径：必须在 skills/<pack>/<script>.py 且防穿越。"""
    if not pack or not script:
        raise ValueError("pack 与 script 不能为空")
    if pack == "." or any(c in pack for c in ("/", "\\", "..", ":")):
        raise ValueError(f"非法技能包名：{pack}")
    script_name = Path(script).name  # 去掉任何路径成分
    if script_name != script or any(c in script for c in ("/", "\\", ":")) or not script_name.endswith(".py"):
        raise ValueError(f"非法脚本名（须为 xxx.py，不带路径）：{script}")
    base = skill_packs_dir().resolve()
    folder = base / pack
    candidate = (folder / script_name).resolve()
    if folder.resolve() != folder or candidate != folder / script_name:
        raise ValueError("脚本路径越界或包含链接")
    if not candidate.is_file():
        available = sorted(p.name for p in (base / pack).glob("*.py")) if (base / pack).is_dir() else []
        raise ValueError(
            f"脚本不存在：{pack}/{script_name}"
            + (f"（可用：{'、'.join(available)}）" if available else f"（技能包 {pack} 无脚本目录）")
        )
    return candidate


def run_skill_script(
    pack: str,
    script: str,
    args: str = "",
    workdir: Path | None = None,
    session_root: Path | None = None,
    timeout: int = DEFAULT_TIMEOUT,
    should_cancel: CancelCheck = None,
    on_progress: Callable[[str], None] | None = None,
) -> str:
    """执行脚本，将结果、退出码与失败诊断一起返回给模型。"""
    try:
        target = _resolve_script(pack, script)
    except ValueError as e:
        return f"错误：{e}"
    try:
        args_obj = json.loads(args) if args.strip() else {}
    except json.JSONDecodeError as e:
        return f"错误：args 不是合法 JSON：{e}"
    payload = {
        "args": args_obj,
        "workdir": str(workdir or Path(".")),
        "session_root": str(session_root or (workdir or Path(".")).parent),
    }
    cancelled = {"flag": False}

    try:
        command = ([sys.executable, "--run-skill-script", pack, script]
                   if getattr(sys, "frozen", False) else [sys.executable, str(target)])
        proc = subprocess.Popen(
            command,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace",
            # Match the UTF-8 JSON contract on Windows as well as Unix.
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except OSError as e:
        return f"错误：无法启动脚本进程：{e}"

    def _watch_cancel() -> None:
        # 取消轮询：模型会话点停止 → 杀脚本进程
        import time
        while proc.poll() is None:
            if should_cancel is not None and should_cancel():
                cancelled["flag"] = True
                proc.kill()
                return
            time.sleep(0.2)

    watcher = threading.Thread(target=_watch_cancel, daemon=True)
    watcher.start()
    timed_out = None
    try:
        out, err = proc.communicate(
            input=json.dumps(payload, ensure_ascii=False),
            timeout=max(1, int(timeout)),
        )
    except subprocess.TimeoutExpired:
        proc.kill()
        out, err = proc.communicate()
        timed_out = timeout
    watcher.join(timeout=1)

    if cancelled["flag"]:
        return "错误：脚本已被用户取消。"
    # stderr → 进度透传（尾行）
    for line in (err or "").strip().splitlines()[-5:]:
        if on_progress is not None and line.strip():
            on_progress(line.strip())
    return _script_result(out or "", err or "", proc.returncode, timed_out=timed_out)
