"""Bound machine request bodies, including HTTP chunked uploads."""
from mcp.server.transport_security import RequestBodyLimitMiddleware


class MachineBodyLimitMiddleware:
    def __init__(self, app):
        self.app = app
        self.task_app = RequestBodyLimitMiddleware(app, 30 * 1024 * 1024)
        self.token_app = RequestBodyLimitMiddleware(app, 16 * 1024)

    async def __call__(self, scope, receive, send):
        path = scope.get("path", "")
        root = scope.get("root_path", "")
        if root and path.startswith(root + "/"):
            path = path[len(root):]
        target = self.app
        if scope["type"] == "http" and scope.get("method") == "POST":
            if path in {"/v1/tasks", "/a2a"}:
                target = self.task_app
            elif path == "/oauth/token":
                target = self.token_app
        await target(scope, receive, send)
