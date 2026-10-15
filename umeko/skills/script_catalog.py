"""Read script contracts without importing or executing skill code."""
from __future__ import annotations

import json

from ..skillpacks import get_skill_pack, skill_packs_dir
from .script_runner import _resolve_script
from .script_contract import inspect_script

OUTPUT_SCHEMA = {
    "type": "object", "required": ["ok", "result"],
    "properties": {
        "ok": {"type": "boolean"}, "result": {"type": "string"},
        "files": {"type": "array", "items": {"type": "string"},
                  "description": "产物的会话相对路径；无产物时为空数组"},
    },
}


def _describe(pack: str, name: str) -> dict:
    item = inspect_script(_resolve_script(pack, name))
    if item["documentation"] == "declared":
        item.update(output_schema=OUTPUT_SCHEMA, invocation={
            "tool": "run_skill_script", "arguments": {
                "pack": pack, "script": name,
                "args": json.dumps(item["example_args"], ensure_ascii=False),
            },
        })
    return item


def list_skill_script(pack: str, script: str = "", offset: int = 0, limit: int = 20) -> str:
    """List a permitted package's scripts, or inspect one script's declared contract."""
    try:
        # Validate names before loading files, and use the same library as the runner.
        if not pack or pack == "." or any(c in pack for c in ("/", "\\", "..", ":")):
            raise ValueError("非法技能包名")
        try:
            get_skill_pack(pack)
        except ValueError:
            raise ValueError("未知技能包：" + pack) from None
        base = skill_packs_dir().resolve()
        folder = (base / pack).resolve()
        if folder != base / pack:
            raise ValueError("技能包目录不能是链接")
        if script:
            _resolve_script(pack, script)
            names = [script]
        else:
            names = sorted(p.name for p in folder.glob("*.py") if p.is_file())
        if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 20:
            raise ValueError("offset 须为非负整数，limit 须为 1–20")
        entries = []
        used_chars = 0
        for name in names[offset:offset + limit]:
            try:
                item = _describe(pack, name)
            except (ValueError, OSError):
                item = {"script": name, "documentation": "invalid", "warning": "脚本路径不可访问或越界"}
            size = len(json.dumps(item, ensure_ascii=False, indent=2))
            if entries and used_chars + size > 48000:
                break
            used_chars += size
            entries.append(item)
        return json.dumps({
            "pack": pack, "scripts": entries, "total": len(names),
            "next_offset": offset + len(entries) if offset + len(entries) < len(names) else None,
            "protocol": {
                "input": "run_skill_script 的 args 为 JSON 对象字符串；框架通过 stdin 注入 args、workdir 和 session_root，调用者不传服务器绝对路径。",
                "output": "stdout 最后一行是 JSON 结果，stderr 为诊断；工具返回 result、files 及失败说明。",
                "output_schema": OUTPUT_SCHEMA,
                "note": "本次仅静态读取元数据，不执行脚本、不保证运行环境或依赖可用。support_module 是辅助模块，不作为任务入口。",
            },
        }, ensure_ascii=False, indent=2)
    except (ValueError, OSError) as exc:
        return f"错误：{exc}"
