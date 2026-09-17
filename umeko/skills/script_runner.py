"""run_skill_script：技能包自带脚本的通用受限执行器（框架机制，无领域知识）。

技能包结构约定：
    skills/<pack-name>.md            提示词（现有机制）
    skills/<pack-name>/<script>.py   包内脚本（本工具可执行）

脚本契约（管理员面板可下载模板）：
    stdin  : {"args": {...}, "workdir": "<Session 产物目录绝对路径>",
              "session_root": "<Session 根绝对路径>"}
    stdout : 一行 JSON {"ok": bool, "result": "给模型的结论", "files": [...]}
    stderr : 逐行进度文本（实时透传给用户工具卡片）

沙箱约束：
    - 只能执行技能库目录内、且包名与 .md 同名的子目录下的 .py（防穿越）
    - 独立子进程（venv 同解释器），默认 60s 超时强杀（取消请求也强杀）
    - stdout 只保留最后一行（结果）；stderr 保留尾部若干行
"""

from __future__ import annotations

import json
import subprocess
import sys
import threading
from pathlib import Path
from typing import Callable

from ..cancellation import CancelCheck
from ..skillpacks import skill_packs_dir

DEFAULT_TIMEOUT = 60  # 秒；硬上限由调用方传入


def _resolve_script(pack: str, script: str) -> Path:
    """解析并校验脚本路径：必须在 skills/<pack>/<script>.py 且防穿越。"""
    if not pack or not script:
        raise ValueError("pack 与 script 不能为空")
    if "/" in pack or "\\" in pack or ".." in pack:
        raise ValueError(f"非法技能包名：{pack}")
    script_name = Path(script).name  # 去掉任何路径成分
    if script_name != script or not script_name.endswith(".py"):
        raise ValueError(f"非法脚本名（须为 xxx.py，不带路径）：{script}")
    base = skill_packs_dir().resolve()
    candidate = (base / pack / script_name).resolve()
    try:
        candidate.relative_to(base)
    except ValueError as e:
        raise ValueError("脚本路径越界") from e
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
    """执行技能包脚本，返回给模型的文本（stdout 最后一行 JSON 的 result）。"""
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
        proc = subprocess.Popen(
            [sys.executable, str(target)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace",
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
    try:
        out, err = proc.communicate(
            input=json.dumps(payload, ensure_ascii=False),
            timeout=max(1, int(timeout)),
        )
    except subprocess.TimeoutExpired:
        proc.kill()
        out, err = proc.communicate()
        return (
            f"错误：脚本执行超时（>{timeout}s），已强制终止。"
            "请检查脚本内是否有死循环，或让管理员在面板调大超时。"
        )
    watcher.join(timeout=1)

    if cancelled["flag"]:
        return "错误：脚本已被用户取消。"
    # stderr → 进度透传（尾行）
    for line in (err or "").strip().splitlines()[-5:]:
        if on_progress is not None and line.strip():
            on_progress(line.strip())
    # stdout 最后一行 = 结果 JSON
    lines = [ln for ln in (out or "").strip().splitlines() if ln.strip()]
    if not lines:
        return f"错误：脚本无输出（stderr 尾部：{(err or '').strip()[-300:]}）"
    try:
        result = json.loads(lines[-1])
        ok = bool(result.get("ok"))
        text = str(result.get("result", ""))
        files = result.get("files") or []
        suffix = f"\n产物文件：{'、'.join(str(f) for f in files)}" if files else ""
        return (text if ok else f"脚本报告失败：{text}") + suffix
    except (json.JSONDecodeError, TypeError):
        return f"脚本输出不符合契约（最后一行须为 JSON）：{lines[-1][:300]}"
