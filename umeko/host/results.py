"""Machine-only answer submission, independent of providers and domain skills."""
from __future__ import annotations

import json
import os
from pathlib import Path, PurePosixPath
import stat

from ..skills import Skill, ToolResult
from .file_manifest import _linked

MACHINE_RESULTS_PROMPT = """

[机器任务答案提交]
本次是外部 Agent 调用的机器任务。完成任务时，必须调用 submit_results 提交最终答案与产物清单。
将完整的自然语言结果（可含 Markdown、公式、必要说明）填写到 text；files 填你明确选择的最终交付件。
没有文件时 files=[]，不要为了满足格式而创建多余文件。缺少必要资料时，也用该工具说明缺失项和补齐步骤。
用户需求中的普通 HTTP/HTTPS 文件链接可以按需用 download_url 尝试下载，不要求所有资料都预先上传为附件。
下载或处理失败后，由你判断材料是否必需、是否有明确可行的修正办法，以及已有资料是否足以继续；一次工具错误不代表整项任务必须失败。
确认关键材料无法取得或处理、任务因此不能继续时，及时调用 submit_results 结束本轮，说明阻塞原因、缺失材料、已完成部分及补齐步骤。
不要空等文件、反复轮询或重复无效的下载/处理方法；不能把下载失败或未检查当作完成、通过。
请外层 Agent 将任务响应中的真实 workspace_url（A2A 为 metadata.workspaceUrl）交给用户，邀请进入临时工作台补充资料或接续任务。
上下文中没有真实工作台链接时，只说明从上述响应字段获取，不编造 URL。若仅缺可选资料，继续完成可执行部分并说明限制。
每个文件项的 path 必须是已经存在的会话相对路径，只能位于 generate/ 或 workspace/，可为文件或整体交付的文件夹。
description 是可选的简短用途说明。不要填写文件序号、服务器绝对路径、下载网址或 Base64。
只选择最终交付件，不自动加入源材料、草稿、规则或中间文件，除非用户明确要求交付它们。
工具会校验答案和文件路径：返回 ok=false 时根据错误修正后重试；只有提交成功才完成本轮。
提交成功会直接结束本轮，不需要再写一段回复；结束前请完成所有必要的文件操作。
不要把最终聊天回复强制写成 JSON；最终答案通过 tool call 的参数提交，平台会分配下载 file_id。
本契约也适用于本机器任务临时工作台的后续对话。普通会话没有这个工具。
"""

SUBMISSION_REMINDER = """[系统：机器任务提交提醒]
本轮尚未通过 submit_results 成功提交答案。请用该工具提交已完成的自然语言答案及最终文件清单。
没有文件时 files=[]；如之前提交失败，按工具反馈修正。不要再用普通回复或独立 JSON 代替工具调用。
"""


def validate_result(result: dict) -> dict:
    if not isinstance(result, dict) or set(result) != {"text", "files"}:
        raise ValueError("提交参数只能包含 text 和 files")
    if not isinstance(result["text"], str) or not result["text"].strip() or not isinstance(result["files"], list):
        raise ValueError("text 必须为非空文本，files 必须为数组")
    files = []
    seen = set()
    for index, item in enumerate(result["files"], 1):
        if (not isinstance(item, dict) or set(item) - {"path", "description"}
                or not isinstance(item.get("path"), str) or not item["path"].strip()
                or not isinstance(item.get("description", ""), str)):
            raise ValueError(f"最终文件清单第 {index} 项需要 path 和可选 description")
        path = item["path"]
        if path in seen:
            raise ValueError(f"最终文件清单第 {index} 项路径重复")
        seen.add(path)
        files.append({"path": path, "description": item.get("description", "")})
    return {"text": result["text"], "files": files}


def verify_result_files(result: dict, root: Path) -> list:
    """Check every entry before publishing anything; never read or infer file contents."""
    verified, seen = [], set()
    for index, item in enumerate(result["files"], 1):
        relative = item["path"]
        parts = PurePosixPath(relative).parts
        if (not parts or parts[0] not in {"generate", "workspace"} or PurePosixPath(relative).is_absolute()
                or any(part in {".", ".."} for part in relative.split("/"))
                or any(char in relative for char in ("\\", ":", "\x00"))):
            raise ValueError(f"最终文件清单第 {index} 项须为 generate/ 或 workspace/ 内的会话相对路径")
        try:
            path = root
            if _linked(root.lstat()):
                raise ValueError("目录不可读取")
            for part in parts:
                path = path / part
                if _linked(path.lstat()) or not path.resolve().is_relative_to(root):
                    raise ValueError("文件不可读取")
            info = path.lstat()
            kind = "directory" if stat.S_ISDIR(info.st_mode) else "file" if stat.S_ISREG(info.st_mode) else None
            if kind is None:
                raise ValueError("文件类型不可读取")
        except (OSError, ValueError) as exc:
            raise ValueError(f"最终文件清单第 {index} 项不存在或不可读取；请先生成实际文件再提交") from exc
        identity = os.path.normcase(str(path))
        if identity in seen:
            raise ValueError(f"最终文件清单第 {index} 项与已有文件重复")
        seen.add(identity)
        verified.append((item, path, kind, info))
    return verified


class ResultSubmission:
    """One validated submission per run; no chat-text parsing and no cross-run reuse."""

    def __init__(self, root: Path):
        self.root = root
        self.run_id: str | None = None
        self.result: dict | None = None

    def begin_run(self, run_id: str) -> None:
        self.run_id, self.result = run_id, None

    def for_run(self, run_id: str) -> dict:
        if self.run_id != run_id or self.result is None:
            raise ValueError("Agent 未通过 submit_results 成功提交本轮答案，请重试任务")
        return self.result

    def submit(self, text, files) -> ToolResult:
        try:
            if self.run_id is None:
                raise ValueError("当前没有正在执行的机器任务")
            result = validate_result({"text": text, "files": files})
            verify_result_files(result, self.root)
        except ValueError as exc:
            return ToolResult(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        self.result = result
        return ToolResult(json.dumps({"ok": True, "message": "最终答案已提交，本轮结束。",
                                      "file_count": len(result["files"])}, ensure_ascii=False),
                          final_reply=result["text"])

    def tool(self) -> Skill:
        return Skill(
            name="submit_results",
            description="提交本机器任务的最终自然语言答案与实际产物清单。校验通过后直接完成本轮；校验失败时修正参数再调用。没有文件时传 files=[]。",
            parameters={"type": "object", "additionalProperties": False,
                        "properties": {"text": {"type": "string", "minLength": 1,
                            "description": "给用户的完整自然语言结果，可含 Markdown 和公式"},
                            "files": {"type": "array", "description": "明确选定的最终交付件，无产物时为空数组",
                                "items": {"type": "object", "additionalProperties": False,
                                    "properties": {"path": {"type": "string", "minLength": 1,
                                        "description": "已存在的 generate/ 或 workspace/ 下的会话相对路径，文件或文件夹"},
                                        "description": {"type": "string", "description": "产物用途，可省略"}},
                                    "required": ["path"]}}}, "required": ["text", "files"]},
            handler=self.submit,
        )
