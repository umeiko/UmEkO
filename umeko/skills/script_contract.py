"""Static script descriptions and input validation, shared by discovery and execution."""
from __future__ import annotations

import ast
import json
from itertools import islice
from pathlib import Path

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError
from referencing import Registry
from referencing.exceptions import Unresolvable

MAX_SOURCE_BYTES = 1024 * 1024
MAX_SPEC_CHARS = 16000


def inspect_script(target: Path) -> dict:
    item = {"script": target.name}
    try:
        item["size_bytes"] = target.stat().st_size
        with target.open("rb") as source:
            data = source.read(MAX_SOURCE_BYTES + 1)
        if len(data) > MAX_SOURCE_BYTES:
            raise ValueError("脚本超过 1 MiB，未解析；请拆分辅助模块或阅读技能文档")
        source_text = data.decode("utf-8-sig")
        tree = ast.parse(source_text)
        item["description"] = (ast.get_docstring(tree) or "未提供脚本说明")[:2000]
        declarations = []
        for node in tree.body:
            targets = node.targets if isinstance(node, ast.Assign) else [node.target] if isinstance(node, ast.AnnAssign) else []
            if any(isinstance(t, ast.Name) and t.id == "SKILL_SCRIPT" for t in targets):
                declarations.append(node.value)
        if not declarations:
            guarded = any(isinstance(n, ast.If) and any(
                isinstance(c, ast.Constant) and c.value == "__main__" for c in ast.walk(n.test)
            ) for n in tree.body)
            top_level_call = any(isinstance(n, ast.Expr) and isinstance(n.value, ast.Call) for n in tree.body)
            return {**item, "documentation": "missing", "kind": "legacy_script" if guarded or top_level_call else "support_module",
                    "input_schema": None, "outputs": [],
                    "warning": "未声明 SKILL_SCRIPT，不能确认参数和输入输出协议；先 read_pack_file 查看源码或技能文档，不要猜测参数。"}
        if len(declarations) != 1 or declarations[0] is None:
            raise ValueError("SKILL_SCRIPT 必须声明为一个字典常量，且只能声明一次")
        if len(ast.get_source_segment(source_text, declarations[0]) or "") > MAX_SPEC_CHARS:
            raise ValueError("SKILL_SCRIPT 说明过长")
        spec = ast.literal_eval(declarations[0])
        if not isinstance(spec, dict):
            raise ValueError("SKILL_SCRIPT 必须是字典常量")
        fields = {"description": str, "usage": str, "input_schema": dict, "outputs": list, "example_args": dict}
        for key, kind in fields.items():
            if not isinstance(spec.get(key), kind):
                raise ValueError(f"SKILL_SCRIPT.{key} 缺失或类型错误")
        if not all(isinstance(v, str) for v in spec["outputs"]):
            raise ValueError("SKILL_SCRIPT.outputs 必须是字符串数组")
        if spec["input_schema"].get("type") != "object":
            raise ValueError("input_schema 描述 args 对象，type 必须为 object")
        if len(json.dumps(spec, ensure_ascii=False, allow_nan=False)) > MAX_SPEC_CHARS:
            raise ValueError("SKILL_SCRIPT 说明过长")
        Draft202012Validator.check_schema(spec["input_schema"])
        return {**item, **{key: spec[key] for key in fields}, "documentation": "declared", "kind": "script"}
    except SchemaError as exc:
        location = ".".join(str(part) for part in exc.absolute_path)[:200]
        return {**item, "documentation": "invalid", "error_code": "SCRIPT_CONTRACT_INVALID",
                "warning": f"SKILL_SCRIPT.input_schema 不符合 JSON Schema：{location or '(根节点)'}；请管理员修正脚本声明。"}
    except SyntaxError as exc:
        return {**item, "documentation": "invalid", "error_code": "SCRIPT_SYNTAX_ERROR",
                "warning": f"脚本 Python 语法错误（第 {exc.lineno} 行）：{exc.msg}；请管理员修正脚本。"}
    except OSError as exc:
        return {**item, "documentation": "invalid", "error_code": "SCRIPT_SOURCE_UNREADABLE",
                "warning": f"无法读取脚本源码（{type(exc).__name__}）；请管理员检查文件读取权限和存储状态。"}
    except UnicodeError:
        return {**item, "documentation": "invalid", "error_code": "SCRIPT_SOURCE_ENCODING",
                "warning": "脚本源码无法按 UTF-8 解码；请管理员修正文件编码。"}
    except (ValueError, TypeError, RecursionError) as exc:
        detail = "无法读取脚本契约，请检查 UTF-8 及 SKILL_SCRIPT 字典常量格式。"
        if str(exc).startswith(("脚本超过", "SKILL_SCRIPT", "input_schema")):
            detail = str(exc)[:300]
        return {**item, "documentation": "invalid", "error_code": "SCRIPT_CONTRACT_INVALID", "warning": detail}


def value_type(value) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "array"
    if isinstance(value, str):
        return "string"
    return "number"


def _field(path) -> str:
    return "args" + "".join(f"[{part}]" if isinstance(part, int) else "." + str(part)[:100] for part in path)


def argument_issues(schema: dict, arguments: dict) -> list[str]:
    # Empty registry disables remote $ref retrieval; local #/$defs references still work.
    validator = Draft202012Validator(schema, registry=Registry())
    try:
        errors = list(islice(validator.iter_errors(arguments), 6))
    except Unresolvable as exc:
        raise ValueError("input_schema 引用无法解析；仅支持包内声明的本地引用，请管理员修正。") from exc
    except RecursionError as exc:
        raise ValueError("参数或 input_schema 嵌套过深，无法完成校验；请简化数据或契约。") from exc
    issues = []
    for error in errors[:5]:
        field = _field(error.absolute_path)
        if error.validator == "required":
            missing = [key for key in error.validator_value if key not in error.instance]
            issues.append("缺少必填参数：" + "、".join(_field([*error.absolute_path, key]) for key in missing[:5]))
        elif error.validator == "type":
            issues.append(f"{field}：期望 {error.validator_value}，实际为 {value_type(error.instance)}")
        elif error.validator == "additionalProperties":
            # Do not echo parameter values (which may contain credentials or large XML).
            known = error.schema.get("properties", {})
            extras = sorted(set(error.instance) - set(known)) if not error.schema.get("patternProperties") else []
            suffix = "（未知字段：" + "、".join(str(k)[:80] for k in extras[:5]) + "）" if extras else ""
            issues.append(f"{field}：不接受未声明的参数{suffix}；可用字段：" + "、".join(known)[:300])
        elif error.validator == "enum":
            issues.append(f"{field}：取值不在允许范围；允许：" + json.dumps(error.validator_value, ensure_ascii=False)[:300])
        elif error.validator in {"anyOf", "oneOf"}:
            choices = [branch.get("required", []) if isinstance(branch, dict) else [] for branch in error.validator_value]
            if choices and all(choices):
                label = "或".join(" + ".join(_field([*error.absolute_path, key]) for key in choice) for choice in choices)
                issues.append(f"{field}：须提供 {label} 中的{'一组' if error.validator == 'oneOf' else '至少一组'}，并满足对应参数格式")
            else:
                issues.append(f"{field}：不符合脚本声明的 {error.validator} 参数组合")
        else:
            expected = json.dumps(error.validator_value, ensure_ascii=False)[:200]
            issues.append(f"{field}：不满足 {error.validator} 约束（要求 {expected}）")
    if len(errors) > 5:
        issues.append("仅列出前 5 项错误，请修正后重试。")
    return issues
