"""Read script contracts without importing or executing skill code."""
from __future__ import annotations

import ast
import json

from ..skillpacks import get_skill_pack, skill_packs_dir
from .script_runner import _resolve_script

MAX_SOURCE_BYTES = 1024 * 1024
MAX_SPEC_CHARS = 16000
OUTPUT_SCHEMA = {
    "type": "object", "required": ["ok", "result"],
    "properties": {
        "ok": {"type": "boolean"}, "result": {"type": "string"},
        "files": {"type": "array", "items": {"type": "string"},
                  "description": "产物的会话相对路径；无产物时为空数组"},
    },
}


def _describe(pack: str, name: str) -> dict:
    target = _resolve_script(pack, name)
    item = {"script": name, "size_bytes": target.stat().st_size}
    try:
        with target.open("rb") as source:
            data = source.read(MAX_SOURCE_BYTES + 1)
        if len(data) > MAX_SOURCE_BYTES:
            raise ValueError("脚本超过 1 MiB，未解析；请拆分辅助模块或阅读技能文档")
        source_text = data.decode("utf-8-sig")
        tree = ast.parse(source_text)
        item["description"] = (ast.get_docstring(tree) or "未提供脚本说明")[:2000]
        spec_node = None
        for node in tree.body:
            targets = node.targets if isinstance(node, ast.Assign) else [node.target] if isinstance(node, ast.AnnAssign) else []
            if any(isinstance(t, ast.Name) and t.id == "SKILL_SCRIPT" for t in targets):
                if spec_node is not None:
                    raise ValueError("SKILL_SCRIPT 只能声明一次")
                spec_node = node.value
        if spec_node is not None:
            # literal_eval never evaluates calls, attribute access, imports or expressions.
            if len(ast.get_source_segment(source_text, spec_node) or "") > MAX_SPEC_CHARS:
                raise ValueError("SKILL_SCRIPT 说明过长")
            spec = ast.literal_eval(spec_node)
            if not isinstance(spec, dict):
                raise ValueError("SKILL_SCRIPT 必须是字典常量")
            for key, kind in {"description": str, "usage": str, "input_schema": dict,
                              "outputs": list, "example_args": dict}.items():
                if not isinstance(spec.get(key), kind):
                    raise ValueError(f"SKILL_SCRIPT.{key} 缺失或类型错误")
            if not all(isinstance(v, str) for v in spec["outputs"]):
                raise ValueError("SKILL_SCRIPT.outputs 必须是字符串数组")
            if spec["input_schema"].get("type") != "object":
                raise ValueError("input_schema 描述 args 对象，type 必须为 object")
            if len(json.dumps(spec, ensure_ascii=False, allow_nan=False)) > MAX_SPEC_CHARS:
                raise ValueError("SKILL_SCRIPT 说明过长")
            item.update({key: spec[key] for key in ("description", "usage", "input_schema", "outputs", "example_args")})
            item.update(documentation="declared", kind="script", output_schema=OUTPUT_SCHEMA,
                        invocation={"tool": "run_skill_script", "arguments": {
                            "pack": pack, "script": name,
                            "args": json.dumps(spec["example_args"], ensure_ascii=False),
                        }})
        else:
            # A guard identifies a likely entrypoint, not proof of the stdin/stdout contract.
            guarded = any(isinstance(n, ast.If) and any(
                isinstance(c, ast.Constant) and c.value == "__main__" for c in ast.walk(n.test)
            ) for n in tree.body)
            top_level_call = any(isinstance(n, ast.Expr) and isinstance(n.value, ast.Call) for n in tree.body)
            item.update(documentation="missing", kind="legacy_script" if guarded or top_level_call else "support_module",
                        input_schema=None, outputs=[],
                        warning="未声明 SKILL_SCRIPT，不能确认参数和输入输出协议；先 read_pack_file 查看源码或技能文档，不要猜测参数。")
    except (OSError, UnicodeError, SyntaxError, ValueError, TypeError, RecursionError) as exc:
        # Do not include parser source snippets, host paths or arbitrary executable expressions.
        item.update(documentation="invalid", warning="无法读取脚本契约，请检查 UTF-8、语法及 SKILL_SCRIPT 常量格式。")
        if isinstance(exc, ValueError) and not isinstance(exc, (UnicodeError, SyntaxError)):
            item["warning"] = "脚本契约不可用：" + str(exc)[:300] if str(exc).startswith(("脚本超过", "SKILL_SCRIPT", "input_schema")) else item["warning"]
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
