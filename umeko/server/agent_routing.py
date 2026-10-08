"""Resolve a dynamic agent prefix before the shared authentication and routes."""
import re

from starlette.responses import JSONResponse


def machine_path(path):
    return path in {"/mcp", "/a2a", "/v1/tasks", "/oauth/token", "/.well-known/agent-card.json",
                    "/.well-known/oauth-protected-resource/mcp", "/.well-known/oauth-authorization-server"} or path.startswith("/v1/tasks/")


def published_path(path):
    return "/agent/{agent_name}" + path if machine_path(path) else path


def publish_agent_schema(schema):
    """Describe the externally callable paths instead of internal SDK routes."""
    for path in list(schema["paths"]):
        if not machine_path(path):
            continue
        operations = schema["paths"].pop(path)
        for operation in operations.values():
            if isinstance(operation, dict):
                operation.setdefault("parameters", []).insert(0, {
                    "name": "agent_name", "in": "path", "required": True,
                    "description": "管理员配置的智能体访问路径名称（slug）",
                    "schema": {"type": "string", "pattern": "^[a-z0-9][a-z0-9-]{0,62}$"}})
        schema["paths"][published_path(path)] = operations
    return schema


class AgentRoutingMiddleware:
    def __init__(self, app, registry):
        self.app, self.registry = app, registry

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        root = scope.get("root_path", "")
        path = scope["path"]
        if root and path.startswith(root + "/"):
            path = path[len(root):]
        match = re.match(r"^/agent/([^/]+)(/.*)?$", path)
        if match:
            slug, rest = match.group(1), match.group(2) or "/"
            # Per-agent delivery exposes machine routes, not aliases for web/admin APIs.
            allowed = rest in {"/", "/health"} or machine_path(rest)
            try:
                definition = self.registry.by_slug(slug)
            except KeyError:
                definition = None
            if not allowed or definition is None:
                return await JSONResponse({"detail": "智能体不存在、已停用或入口无效"}, status_code=404)(scope, receive, send)
            scope = dict(scope)
            scope["state"] = {**scope.get("state", {}), "agent_definition": definition, "agent_path": "/agent/" + slug}
            scope["root_path"] = root + "/agent/" + slug
            scope["path"] = scope["root_path"] + rest
        elif machine_path(path) or path == "/agents" or path.startswith("/agents/"):
            return await JSONResponse({"detail": "请使用 /agent/<name>/ 下的智能体入口"}, status_code=404)(scope, receive, send)
        await self.app(scope, receive, send)
