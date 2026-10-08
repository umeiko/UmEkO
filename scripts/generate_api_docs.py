"""Generate public API documentation using isolated apps; never read .env or live data.

Usage: python scripts/generate_api_docs.py [--check]
The explicit supplements describe Request-body and middleware contracts that FastAPI
cannot infer. No model request, account bootstrap, or skill execution is performed.
"""
from __future__ import annotations

import argparse
import gc
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fastapi.routing import APIRoute
from umeko.config import ModelConfig, Settings
from umeko.server.app import create_app
from umeko.server.admin import create_admin_app
from umeko.server.models import EventView

METHODS = {"get", "post", "put", "patch", "delete", "head", "options"}
BINARY = {"type": "string", "format": "binary"}


def supplement(spec: dict, admin: bool) -> None:
    cookie = "umeko_admin" if admin else "umeko_auth"
    spec.setdefault("components", {}).setdefault("securitySchemes", {})[cookie] = {
        "type": "apiKey", "in": "cookie", "name": cookie,
        "description": "登录后保存 Cookie；当前实现不接受 Bearer Token。",
    }
    spec["servers"] = [{"url": "http://127.0.0.1:9000" if admin else "http://127.0.0.1:8000"}]
    public = {("/health", "get"), ("/admin/login", "post")} if admin else {
        ("/health", "get"), ("/v1/auth/login", "post"), ("/v1/auth/register", "post")}
    for path, operations in spec["paths"].items():
        for method, operation in operations.items():
            if method in METHODS:
                operation["security"] = [] if (path, method) in public else [{cookie: []}]
    if admin:
        return
    raw = {
        ("/v1/auth/avatar", "put"): "原始图片字节；支持 PNG/JPEG/WebP/GIF，最多 2 MiB。",
        ("/v1/sessions/{session_id}/files", "post"): "原始附件字节；filename 在查询参数中。",
        ("/v1/sessions/{session_id}/workspace/files", "post"): "原始文件字节；filename 与可选 path 在查询参数中。",
        ("/v1/sessions/{session_id}/client/{kind}", "post"): "UTF-8 技能文本；kind 只能为 skills。",
    }
    for (path, method), description in raw.items():
        media_type = "text/plain" if "client/" in path else "application/octet-stream"
        spec["paths"][path][method]["requestBody"] = {
            "required": True, "description": description,
            "content": {media_type: {"schema": BINARY}},
        }
    spec["paths"]["/v1/proxy/sessions"]["post"]["requestBody"] = {
        "required": True,
        "content": {"multipart/form-data": {"schema": {
            "type": "object", "required": ["prompt"], "properties": {
                "prompt": {"type": "string", "minLength": 1, "description": "去掉首尾空白后不能为空"},
                "skill": {"type": "string", "description": "可选的技能包名称"},
                "files": {"type": "array", "items": BINARY},
            },
        }}},
    }
    downloads = [
        "/v1/auth/avatar",
        "/v1/sessions/{session_id}/workspace/files/content",
        "/v1/sessions/{session_id}/workspace/files/raw/{file_path}",
        "/v1/sessions/{session_id}/workspace/files/download",
        "/v1/sessions/{session_id}/artifacts/{artifact_id}/content",
    ]
    for path in downloads:
        spec["paths"][path]["get"]["responses"]["200"] = {
            "description": "文件响应；实际 Content-Type 随文件类型变化，目录下载为 ZIP。",
            "content": {"application/octet-stream": {"schema": BINARY}},
        }
    spec["paths"]["/v1/runs/{run_id}/events"]["get"]["responses"]["200"] = {
        "description": "SSE：id / event / data 帧；data 为 EventView 的 JSON。",
        "content": {"text/event-stream": {"schema": {"type": "string"}}},
    }
    spec["components"]["schemas"]["EventView"] = EventView.model_json_schema()


def schemas_text(schema: dict) -> str:
    if "$ref" in schema:
        return schema["$ref"].rsplit("/", 1)[-1]
    if "anyOf" in schema or "oneOf" in schema:
        return " / ".join(schemas_text(s) for s in schema.get("anyOf", schema.get("oneOf", [])))
    if schema.get("type") == "array":
        return f"array<{schemas_text(schema.get('items', {}))}>"
    return schema.get("type", "任意 JSON")


def cell(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def reference(spec: dict, admin: bool) -> str:
    label = "管理" if admin else "用户"
    filename = "openapi-admin.json" if admin else "openapi-user.json"
    count = sum(method in METHODS for ops in spec["paths"].values() for method in ops)
    lines = [f"# {label}接口完整参考", "", "> 自动生成：请修改源码或生成器，不直接编辑本文件。", "",
             f"共 **{count}** 个 HTTP 操作。[下载 OpenAPI]({filename}) · [数据结构](schemas.md)", "",
             "路径为应用内部路由；带前缀部署时在公共 URL 前加 `UMEKO_BASE_PATH`。登录、原始字节体与 SSE 契约由生成器显式补充。", "",
             "泛型 `object` / 任意 JSON 表示源码尚未声明完整字段模型，请结合各专题指南。表中响应码来自 OpenAPI，不包含中间件产生的全部错误。", "",
             "## 接口索引", "", "| 方法 | 路径 | 操作 |", "| --- | --- | --- |"]
    for path, ops in spec["paths"].items():
        for method, op in ops.items():
            if method in METHODS:
                lines.append(f"| {method.upper()} | `{path}` | {cell(op.get('summary', ''))} |")
    for path, ops in spec["paths"].items():
        for method, op in ops.items():
            if method not in METHODS:
                continue
            lines += ["", f"## {method.upper()} {path}", "", op.get("summary", ""), "",
                      "认证：" + ("无须登录。" if not op["security"] else f"`{'umeko_admin' if admin else 'umeko_auth'}` Cookie。")]
            if op.get("description"):
                lines += ["", op["description"]]
            if op.get("parameters"):
                lines += ["", "| 参数 | 位置 | 必填 | 类型与约束 |", "| --- | --- | --- | --- |"]
                for parameter in op["parameters"]:
                    schema = parameter.get("schema", {})
                    details = json.dumps(schema, ensure_ascii=False, sort_keys=True)
                    lines.append(f"| `{parameter['name']}` | {parameter['in']} | {'是' if parameter.get('required') else '否'} | `{cell(details)}` |")
            if op.get("requestBody"):
                body = op["requestBody"]
                lines += ["", "请求体：" + ("必填。" if body.get("required") else "可选。")]
                if body.get("description"):
                    lines += ["", body["description"]]
                for media_type, content in body["content"].items():
                    lines += ["", f"`{media_type}` → `{schemas_text(content['schema'])}`"]
                    if "$ref" not in content["schema"]:
                        lines += ["", "```json", json.dumps(content["schema"], ensure_ascii=False, indent=2, sort_keys=True), "```"]
            lines += ["", "| 响应码 | 内容 |", "| --- | --- |"]
            for status, response in op.get("responses", {}).items():
                payload = "; ".join(f"{media}: {schemas_text(content.get('schema', {}))}" for media, content in response.get("content", {}).items())
                lines.append(f"| {status} | {cell(payload or response.get('description', '无响应体'))} |")
    return "\n".join(lines) + "\n"


def generate() -> dict[Path, str]:
    # TemporaryDirectory cleanup is confined to a verified workspace directory.
    temporary_root = ROOT / "smoke" / "api-docs.local"
    assert temporary_root.resolve().is_relative_to(ROOT)
    temporary_root.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=temporary_root) as folder:
        root = Path(folder)
        settings = Settings(ModelConfig("documentation-placeholder", "", "https://unconfigured.invalid/v1"))
        app = create_app(settings, data_root=root / "data", workspace_root=root / "output")
        service = app.state.agent_service
        try:
            admin = create_admin_app(settings, service, app.state.store)
            specs = {"user": app.openapi(), "admin": admin.openapi()}
            for name, instance in [("user", app), ("admin", admin)]:
                expected = {(route.path_format, method.lower()) for route in instance.routes
                            if isinstance(route, APIRoute) and route.include_in_schema
                            for method in route.methods}
                actual = {(path, method) for path, ops in specs[name]["paths"].items()
                          for method in ops if method in METHODS}
                if actual != expected:
                    raise RuntimeError(f"OpenAPI route coverage mismatch: {name}")
                supplement(specs[name], name == "admin")
        finally:
            service.run_manager.shutdown()
            gc.collect()  # close short-lived SQLite connections before Windows cleanup
    files = {}
    for name, spec in specs.items():
        files[ROOT / f"docs/api/openapi-{name}.json"] = json.dumps(spec, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
        files[ROOT / f"docs/api/reference-{name}.md"] = reference(spec, name == "admin")
    lines = ["# 数据结构", "", "> 自动生成：字段必填性、默认值、枚举与约束以以下 JSON Schema 为准。", "",
             "用户和管理服务各有独立模型。`$ref` 指向同一 OpenAPI 文件的 `components/schemas`；管理模型名称的下划线是源码中的名称。"]
    for name, spec in specs.items():
        lines += ["", "## " + ("用户服务" if name == "user" else "管理服务")]
        for key, value in sorted(spec["components"].get("schemas", {}).items()):
            lines += ["", f"### {key}", "", "```json", json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True), "```"]
    files[ROOT / "docs/api/schemas.md"] = "\n".join(lines) + "\n"
    return files


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    stale = []
    for path, content in generate().items():
        if args.check:
            if not path.exists() or path.read_text(encoding="utf-8") != content:
                stale.append(str(path.relative_to(ROOT)))
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8", newline="\n")
    if stale:
        print("API reference is out of date: " + ", ".join(stale))
        print("Run: python scripts/generate_api_docs.py")
        return 1
    print("API documentation checked." if args.check else "API documentation generated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
