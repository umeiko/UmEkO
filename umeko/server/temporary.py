"""Capability-scoped browser workspaces over the existing session routes."""
import asyncio
import json
import re

from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, StreamingResponse

from .ui import render_ui

EXPIRED = {"detail": "该节点已过期，请重新申请", "code": "temporary_workspace_expired"}
PRIVATE = {"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"}


def session_revision(store, sid):
    with store.connect() as db:
        row = db.execute("SELECT COUNT(*) AS count,COALESCE(MAX(id),0) AS last_id FROM messages WHERE session_id=?", (sid,)).fetchone()
    return {"message_count": row["count"], "message_id": row["last_id"]}


class TemporaryWorkspaceMiddleware:
    def __init__(self, app, tasks, base_path, guide_url=""):
        self.app, self.tasks, self.base_path = app, tasks, base_path
        self.guide_url = guide_url

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        root = scope.get("root_path", "")
        path = scope["path"]
        if root and path.startswith(root + "/"):
            path = path[len(root):]
        match = re.fullmatch(r"/TMP/([A-Za-z0-9_-]{1,128})(/.*)?", path)
        if not match:
            return await self.app(scope, receive, send)
        token, rest = match.group(1), match.group(2) or "/"
        method = scope["method"]
        if rest == "/" and method == "GET":
            return await HTMLResponse(render_ui("index.html", self.base_path, temporary_path="/TMP/" + token, guide_url=self.guide_url), headers=PRIVATE)(scope, receive, send)
        task = self.tasks.temporary_workspace(token)
        if task is None:
            return await JSONResponse(EXPIRED, status_code=410, headers=PRIVATE)(scope, receive, send)
        snapshot, sid = task["snapshot"], task["session_id"]
        if rest == "/v1/temporary" and method == "GET" or rest == "/v1/temporary/activity" and method == "POST":
            task = self.tasks.open_workspace(token, activity=method == "POST")
            if task is None:
                return await JSONResponse(EXPIRED, status_code=410, headers=PRIVATE)(scope, receive, send)
            state = self.tasks.service.sessions.get(sid)
            active = state.active_run_holder["run"] if state else None
            busy = not task["completed_at"] or (active and not active.finished)
            deadline = min(task["expires_at"], task["workspace_expires_at"]) if task["workspace_expires_at"] else task["expires_at"]
            return await JSONResponse({"state": "ready" if sid and (task["run_id"] or task["completed_at"]) else "pending", "task_id": task["id"],
                                       "session_id": sid, "agent_name": snapshot.get("name", "Agent"),
                                       "status": task["status"], "expires_at": None if busy else deadline,
                                       "idle_seconds": self.tasks.settings.tmp_idle_seconds}, headers=PRIVATE)(scope, receive, send)
        if not sid:
            return await JSONResponse({"detail": "临时工作台正在准备", "code": "temporary_workspace_pending"}, status_code=409, headers=PRIVATE)(scope, receive, send)
        service, store = self.tasks.service, self.tasks.store
        if rest == "/v1/temporary/events" and method == "GET":
            request = Request(scope, receive)
            async def changes():
                previous, cursor = None, 0
                while not await request.is_disconnected():
                    if self.tasks.temporary_workspace(token) is None:
                        yield 'event: session.expired\ndata: {}\n\n'
                        return
                    state = service.sessions.get(sid)
                    run = state.active_run_holder["run"] if state else None
                    active = run if run and not run.finished else None
                    update = {**session_revision(store, sid), "run_id": active.id if active else None}
                    if update != previous:
                        previous, cursor = update, cursor + 1
                        yield f'id: {cursor}\nevent: session.changed\ndata: {json.dumps(update)}\n\n'
                    else:
                        yield ': keep-alive\n\n'
                    await asyncio.sleep(.5)
            return await StreamingResponse(changes(), media_type="text/event-stream",
                                           headers={**PRIVATE, "X-Accel-Buffering": "no"})(scope, receive, send)
        if rest == "/v1/sessions" and method == "GET":
            return await JSONResponse([store.session_by_id(sid)], headers=PRIVATE)(scope, receive, send)
        if rest == "/v1/models" and method == "GET":
            record = store.session_by_id(sid)
            active = store.active_model()
            model_id = record.get("model_override_id") or (active or {}).get("model_id")
            model = store.model_by_id(model_id) if model_id else None
            providers = [{"id": "agent", "name": snapshot.get("name", "Agent"), "models": [
                {"id": model_id, "name": model["model"], "vision": bool(model["vision"])}]}] if model else []
            return await JSONResponse({"providers": providers, "active_model_id": model_id, "prefs": {}}, headers=PRIVATE)(scope, receive, send)
        prefix = "/v1/sessions/" + sid
        allowed = False
        if rest == prefix or rest.startswith(prefix + "/"):
            suffix = rest[len(prefix):]
            allowed = (
                method == "GET" and (suffix in {"", "/messages", "/tool-events", "/context", "/active-run", "/workspace/tree", "/artifacts",
                                                "/workspace/files/content", "/workspace/files/download"}
                                     or suffix.startswith("/workspace/files/raw/")
                                     or re.fullmatch(r"/artifacts/[^/]+/content", suffix))
                or method == "POST" and suffix in {"/runs", "/files", "/files/from-workspace", "/workspace/files", "/workspace/entries",
                                                   "/workspace/transfer", "/workspace/extract", "/context/compact", "/context/clear", "/chat/clear"}
                or method == "DELETE" and suffix == "/workspace/entries"
            )
            skills = {item["name"] for item in snapshot.get("dispatched_skills", [])}
            if method == "GET" and suffix == "/client/skills":
                resources = [item for item in service.client_resources(sid, "skills") if item["name"] in skills]
                return await JSONResponse(resources, headers=PRIVATE)(scope, receive, send)
            if method == "GET" and suffix.startswith("/client/skills/"):
                allowed = suffix[len("/client/skills/"):] in skills
            if method == "GET" and suffix.startswith("/skill-files/"):
                parts = suffix[len("/skill-files/"):].split("/", 1)
                allowed = len(parts) == 2 and parts[0] + ".md" in skills
        run_match = re.fullmatch(r"/v1/runs/([^/]+)(/events|/cancel)?", rest)
        if run_match:
            run = service.runs.get(run_match.group(1))
            if run is None or run.session_id != sid:
                return await JSONResponse({"detail": "运行不存在或无权访问"}, status_code=404, headers=PRIVATE)(scope, receive, send)
            allowed = method == "GET" and run_match.group(2) != "/cancel" or method == "POST" and run_match.group(2) == "/cancel"
        if not allowed:
            return await JSONResponse({"detail": "临时工作台仅允许访问本会话，模型与技能由智能体配置", "code": "temporary_workspace_restricted"}, status_code=403, headers=PRIVATE)(scope, receive, send)
        scope = dict(scope)
        scope["root_path"] = root + "/TMP/" + token
        scope["path"] = scope["root_path"] + rest
        scope["state"] = {**scope.get("state", {}), "temporary_task": task,
                          "temporary_user": {"id": task["user_id"]}}
        async def private_send(message):
            if message["type"] == "http.response.start":
                message = {**message, "headers": [*message.get("headers", []), (b"cache-control", b"no-store"), (b"referrer-policy", b"no-referrer")]}
            await send(message)
        await self.app(scope, receive, private_send)
