"""REST tasks and OAuth client credentials for machine clients."""
from __future__ import annotations

import asyncio
import base64
import json
from urllib.parse import unquote

from fastapi import HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from ..host.identities import SCOPES
from ..host.tasks import IdempotencyConflict, QueueFull, TERMINAL


class TaskFileInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=200)
    content_base64: str = Field(max_length=28_000_000)


class TaskCreateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prompt: str = Field(min_length=1, max_length=200_000)
    model_id: str | None = None
    files: list[TaskFileInput] = Field(default_factory=list, max_length=10)


def public_base(settings, request: Request) -> str:
    return settings.public_url or str(request.base_url).rstrip("/")


def task_view(task: dict, base: str) -> dict:
    return {**task, "artifacts": [{**a, "download_url": base + f"/v1/tasks/{task['id']}/artifacts/{a['id']}/content",
                                  "resource_uri": f"umeko://tasks/{task['id']}/artifacts/{a['id']}"}
                                 for a in task["artifacts"]]}


def api_error(exc):
    if isinstance(exc, PermissionError):
        return HTTPException(403, str(exc))
    if isinstance(exc, KeyError):
        return HTTPException(404, str(exc))
    if isinstance(exc, QueueFull):
        return HTTPException(429, str(exc), headers={"Retry-After": "5"})
    return HTTPException(409 if isinstance(exc, IdempotencyConflict) else 400, str(exc))


def add_task_routes(app, settings, tasks, identities):
    @app.post("/v1/tasks", status_code=202, tags=["machine tasks"])
    def submit_task(payload: TaskCreateInput, request: Request) -> dict:
        try:
            task = tasks.submit(request.state.principal, payload.model_dump(),
                                idempotency_key=request.headers.get("Idempotency-Key"))
            return task_view(task, public_base(settings, request))
        except (KeyError, ValueError, PermissionError) as exc:
            raise api_error(exc) from exc

    @app.get("/v1/tasks", tags=["machine tasks"])
    def list_tasks(request: Request, limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0)) -> dict:
        try:
            result = tasks.list(request.state.principal, limit=limit, offset=offset)
            return {**result, "tasks": [task_view(t, public_base(settings, request)) for t in result["tasks"]]}
        except PermissionError as exc:
            raise api_error(exc) from exc

    @app.get("/v1/tasks/{task_id}", tags=["machine tasks"])
    def get_task(task_id: str, request: Request) -> dict:
        try:
            return task_view(tasks.get(request.state.principal, task_id), public_base(settings, request))
        except (KeyError, PermissionError) as exc:
            raise api_error(exc) from exc

    @app.post("/v1/tasks/{task_id}/cancel", tags=["machine tasks"])
    def cancel_task(task_id: str, request: Request) -> dict:
        try:
            return task_view(tasks.cancel(request.state.principal, task_id), public_base(settings, request))
        except (KeyError, PermissionError) as exc:
            raise api_error(exc) from exc

    @app.get("/v1/tasks/{task_id}/events", tags=["machine tasks"])
    async def task_events(task_id: str, request: Request, after: int = Query(0, ge=0)):
        try:
            tasks.get(request.state.principal, task_id)
            cursor = max(after, int(request.headers.get("Last-Event-ID", "0")))
        except (KeyError, ValueError, PermissionError) as exc:
            raise api_error(exc) from exc
        async def stream():
            nonlocal cursor
            while not await request.is_disconnected():
                try:
                    for event in tasks.events(request.state.principal, task_id, cursor):
                        cursor = event["id"]
                        yield f"id: {cursor}\nevent: {event['type']}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
                    if tasks.get(request.state.principal, task_id)["status"] in TERMINAL:
                        break
                except (KeyError, PermissionError):
                    break
                yield ": keepalive\n\n"
                await asyncio.sleep(1)
        return StreamingResponse(stream(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    @app.get("/v1/tasks/{task_id}/artifacts/{artifact_id}/content", tags=["machine tasks"])
    def download_artifact(task_id: str, artifact_id: str, request: Request):
        try:
            path, media_type = tasks.artifact(request.state.principal, task_id, artifact_id)
            return FileResponse(path, media_type=media_type, filename=path.name, headers={"Cache-Control": "private, no-store"})
        except (KeyError, PermissionError) as exc:
            raise api_error(exc) from exc

    def resource_metadata(request):
        base = public_base(settings, request)
        return {"resource": base + "/mcp", "authorization_servers": [base],
                "scopes_supported": sorted(SCOPES), "bearer_methods_supported": ["header"]}

    @app.get("/.well-known/oauth-protected-resource/mcp", tags=["machine auth"])
    def oauth_resource(request: Request) -> dict:
        return resource_metadata(request)

    @app.get("/.well-known/oauth-authorization-server", tags=["machine auth"])
    def oauth_server(request: Request) -> dict:
        base = public_base(settings, request)
        return {"issuer": base, "token_endpoint": base + "/oauth/token", "response_types_supported": [],
                "grant_types_supported": ["client_credentials"], "token_endpoint_auth_methods_supported": ["client_secret_post", "client_secret_basic"],
                "scopes_supported": sorted(SCOPES)}

    @app.post("/oauth/token", tags=["machine auth"])
    async def oauth_token(request: Request):
        form = await request.form()
        if form.get("grant_type") != "client_credentials":
            return JSONResponse({"error": "unsupported_grant_type"}, status_code=400)
        client_id, secret = form.get("client_id", ""), form.get("client_secret", "")
        if not isinstance(client_id, str) or not isinstance(secret, str):
            return JSONResponse({"error": "invalid_client"}, status_code=401)
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Basic "):
            try:
                client_id, secret = [unquote(s) for s in base64.b64decode(auth[6:], validate=True).decode().split(":", 1)]
            except (ValueError, UnicodeError):
                return JSONResponse({"error": "invalid_client"}, status_code=401)
        resource = form.get("resource", public_base(settings, request) + "/mcp")
        allowed = {public_base(settings, request) + p for p in ["/mcp", "/a2a", "/v1/tasks"]}
        if not isinstance(resource, str) or resource not in allowed:
            return JSONResponse({"error": "invalid_target"}, status_code=400)
        account = identities.authenticate(secret)
        scopes = str(form.get("scope") or " ".join(account["scopes"] if account else [])).split()
        try:
            token = identities.issue_access_token(client_id, secret, resource, scopes)
            return JSONResponse(token, headers={"Cache-Control": "no-store", "Pragma": "no-cache"})
        except PermissionError:
            return JSONResponse({"error": "invalid_client"}, status_code=401)
        except ValueError as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
