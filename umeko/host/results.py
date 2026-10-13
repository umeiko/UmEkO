"""Final result contract for machine sessions, independent of providers and skills."""
from __future__ import annotations

import json
import re

MACHINE_RESULTS_PROMPT = """

机器任务的最终结果契约：
你最后的回复必须是一个 JSON 对象，不在 JSON 外添加文字：
{"text":"给用户的自然语言结果，可包含 Markdown、公式和必要说明", "files":[{"path":"generate/最终文件.ext", "description":"这份最终交付件的用途"}]}
text 必须是非空字符串，按用户的语言和详略要求回答。files 必须是数组，由你明确选择本次的最终交付件。
没有文件产物时 files=[]；不要为了满足格式而创建多余文件。缺少必要资料时，也按这个格式说明缺失项和补齐步骤。
path 必须是已经存在的会话相对路径，只能位于 generate/ 或 workspace/，可以是文件或用于整体交付的文件夹。
仅列最终文件，不列源材料、草稿、规则文件或中间文件，除非用户明确要求交付它们。
不要填写文件序号、主机绝对路径、下载网址或 Base64；平台会校验路径并为下载分配 file_id。
description 是简短用途说明，可省略。只使用 text/files 以及文件项的 path/description 字段。
工具调用和任务处理照常进行；这个契约规定最后回复的结构，适用于当前任务及临时工作台的后续回复。
"""


def parse_final_result(reply: str | None) -> dict:
    value = (reply or "").strip()
    fenced = re.fullmatch(r"```(?:json)?\s*\n?(.*?)\s*```", value, re.S)
    if fenced:
        value = fenced.group(1)
    try:
        result = json.loads(value)
    except (ValueError, TypeError) as exc:
        raise ValueError("Agent 最后回复必须为包含 text 和 files 的结果 JSON；未登记最终产物") from exc
    if not isinstance(result, dict) or set(result) != {"text", "files"}:
        raise ValueError("结果 JSON 只能包含 text 和 files 字段")
    if not isinstance(result["text"], str) or not result["text"].strip() or not isinstance(result["files"], list):
        raise ValueError("结果 text 必须为非空文本，files 必须为数组")
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
