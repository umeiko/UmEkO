"""Official MCP and A2A SDK adapters over the shared durable task service."""
from __future__ import annotations

import asyncio
import base64
import json
from datetime import timezone
from urllib.parse import urlsplit
from typing import Any
from fastapi import Request

from a2a import types as a2a
from a2a.server.context import ServerCallContext
from a2a.server.request_handlers import RequestHandler
from a2a.server.routes import ServerCallContextBuilder, create_jsonrpc_routes
from a2a.utils.errors import (
    InvalidParamsError, PushNotificationNotSupportedError, TaskNotCancelableError,
    TaskNotFoundError, UnsupportedOperationError,
)
from google.protobuf.json_format import MessageToDict, ParseDict
from mcp.server import MCPServer
from mcp.server.mcpserver import Context
from mcp.server.mcpserver.exceptions import ToolError, ResourceError
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations

from .. import __version__
from ..host.identities import require_scope
from ..host.tasks import TERMINAL
from .task_api import caller_ip, public_base, task_view

MAX_INLINE_ARTIFACT = 256 * 1024


def _mcp_call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except (ValueError, KeyError, PermissionError) as exc:
        raise ToolError(str(exc)) from exc


def build_mcp(settings, tasks):
    server = MCPServer("UMEKO", version=__version__, instructions=(
        "先 submit_task 提交文件处理任务，使用 get_task 查询状态。"
        "完成后使用 read_artifact 读取产物；取消用 cancel_task。"))
    def principal(ctx):
        return ctx.request_context.request.state.principal

    @server.tool(structured_output=True, annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=False))
    def list_models(ctx: Context) -> dict[str, Any]:
        """列出可选模型 ID 与名称，不包含模型地址或密钥。未指定模型时使用管理员默认模型。"""
        _mcp_call(require_scope, principal(ctx), "tasks:create")
        active = tasks.store.active_model()
        return {"default_model_id": active["model_id"] if active else None,
                "models": [{"id": m["id"], "name": m["name"], "vision": m["vision"], "provider": p["name"]}
                           for p in tasks.store.list_providers() for m in p["models"]]}

    @server.tool(structured_output=True, annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=True))
    async def submit_task(prompt: str, ctx: Context, files: list[dict[str, str]] | None = None,
                          model_id: str | None = None, idempotency_key: str | None = None) -> dict[str, Any]:
        """提交 Agent 任务并立即返回任务 ID。files 为 name/content_base64 列表，最多 10 个、合计 20 MiB；
        不接受服务器路径。任务独立执行，默认保留 24 小时；幂等键防止重复提交。"""
        task = await asyncio.to_thread(_mcp_call, tasks.submit, principal(ctx),
                                      {"prompt": prompt, "files": files or [], "model_id": model_id},
                                      source="mcp", idempotency_key=idempotency_key,
                                      caller_ip=caller_ip(ctx.request_context.request))
        return task_view(task, public_base(settings, ctx.request_context.request))

    @server.tool(structured_output=True, annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=False))
    def get_task(task_id: str, ctx: Context) -> dict[str, Any]:
        """查询自己的任务进度、结果、到期时间及产物。只读取持久化状态，不重复调用模型。"""
        return task_view(_mcp_call(tasks.get, principal(ctx), task_id), public_base(settings, ctx.request_context.request))

    @server.tool(structured_output=True, annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=False))
    def list_tasks(ctx: Context, limit: int = 50, offset: int = 0) -> dict[str, Any]:
        """列出当前凭据所属账号的任务。最多返回 100 条，可用 offset 翻页。"""
        result = _mcp_call(tasks.list, principal(ctx), limit=limit, offset=offset)
        return {**result, "tasks": [task_view(t, public_base(settings, ctx.request_context.request)) for t in result["tasks"]]}

    @server.tool(structured_output=True, annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, openWorldHint=False))
    def cancel_task(task_id: str, ctx: Context) -> dict[str, Any]:
        """请求停止自己的任务。排队任务立即取消，正在执行的模型或工具协作式停止。"""
        return _mcp_call(tasks.cancel, principal(ctx), task_id)

    @server.tool(structured_output=True, annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=False))
    def read_artifact(task_id: str, artifact_id: str, ctx: Context) -> dict[str, Any]:
        """读取自己任务的产物，最多 256 KiB；文本返回 text，二进制返回 content_base64。
        更大的产物请使用 get_task 返回的下载地址；需要凭据模式下附带服务凭据。"""
        path, media_type = _mcp_call(tasks.artifact, principal(ctx), task_id, artifact_id)
        if path.stat().st_size > MAX_INLINE_ARTIFACT:
            raise ToolError("产物超过 256 KiB，请使用受保护的 HTTP 下载入口")
        content = path.read_bytes()
        try:
            if media_type.startswith("text/") or media_type in {"application/json", "image/svg+xml"}:
                return {"name": path.name, "media_type": media_type, "text": content.decode("utf-8")}
        except UnicodeDecodeError:
            pass
        return {"name": path.name, "media_type": media_type, "content_base64": base64.b64encode(content).decode()}

    @server.resource("umeko://tasks/{task_id}/artifacts/{artifact_id}", mime_type="application/octet-stream")
    def artifact_resource(task_id: str, artifact_id: str, ctx: Context) -> bytes:
        try:
            path, _ = tasks.artifact(principal(ctx), task_id, artifact_id)
        except (KeyError, PermissionError) as exc:
            raise ResourceError(str(exc)) from exc
        if path.stat().st_size > MAX_INLINE_ARTIFACT:
            raise ResourceError("产物超过 256 KiB，请使用受保护的 HTTP 下载入口")
        return path.read_bytes()

    hosts = ["127.0.0.1", "127.0.0.1:*", "localhost", "localhost:*", "[::1]", "[::1]:*"]
    origins = ["http://127.0.0.1:*", "http://localhost:*", "http://[::1]:*"]
    if settings.public_url:
        parsed = urlsplit(settings.public_url)
        hosts.append(parsed.netloc)
        origins.append(parsed.scheme + "://" + parsed.netloc)
    http_app = server.streamable_http_app(
        streamable_http_path="/mcp", stateless_http=True, json_response=True,
        max_request_body_size=30 * 1024 * 1024,
        transport_security=TransportSecuritySettings(allowed_hosts=hosts, allowed_origins=origins))
    return server, http_app


STATES = {"queued": a2a.TaskState.TASK_STATE_SUBMITTED, "running": a2a.TaskState.TASK_STATE_WORKING,
          "cancelling": a2a.TaskState.TASK_STATE_WORKING, "completed": a2a.TaskState.TASK_STATE_COMPLETED,
          "failed": a2a.TaskState.TASK_STATE_FAILED, "cancelled": a2a.TaskState.TASK_STATE_CANCELED}


class A2AContextBuilder(ServerCallContextBuilder):
    def __init__(self, settings):
        self.settings = settings

    def build(self, request):
        return ServerCallContext(state={"principal": request.state.principal,
                                        "headers": dict(request.headers),
                                        "caller_ip": caller_ip(request),
                                        "base": public_base(self.settings, request)})


class A2AHandler(RequestHandler):
    def __init__(self, tasks):
        self.tasks = tasks

    def _task(self, record, base, history_length=None, include_artifacts=True):
        if history_length is not None and history_length < 0:
            raise InvalidParamsError("historyLength 不能为负数")
        status = a2a.TaskStatus(state=STATES[record["status"]])
        status.timestamp.FromJsonString(record["updated_at"])
        if record["error"]:
            status.message.CopyFrom(a2a.Message(message_id=record["id"] + "-status", role=a2a.Role.ROLE_AGENT,
                                                parts=[a2a.Part(text=record["error"])]))
        task = a2a.Task(id=record["id"], context_id=record["context_id"], status=status)
        ParseDict({"expiresAt": record["expires_at"], "source": record["source"]}, task.metadata)
        if include_artifacts:
            if record["reply"]:
                task.artifacts.append(a2a.Artifact(artifact_id="response", name="Agent response", parts=[a2a.Part(text=record["reply"])]))
            for artifact in task_view(record, base)["artifacts"]:
                task.artifacts.append(a2a.Artifact(artifact_id=artifact["id"], name=artifact["name"],
                    parts=[a2a.Part(url=artifact["download_url"], filename=artifact["name"], media_type=artifact["media_type"])]))
        if history_length != 0:
            with self.tasks.store.connect() as db:
                row = db.execute("SELECT input_json FROM service_tasks WHERE id=?", (record["id"],)).fetchone()
            payload = json.loads(row["input_json"])
            history = [a2a.Message(message_id=payload.get("message_id", record["id"] + "-input"),
                                   context_id=record["context_id"], task_id=record["id"], role=a2a.Role.ROLE_USER,
                                   parts=[a2a.Part(text=payload["prompt"])])]
            if record["reply"]:
                history.append(a2a.Message(message_id=record["id"] + "-reply", context_id=record["context_id"],
                                            task_id=record["id"], role=a2a.Role.ROLE_AGENT, parts=[a2a.Part(text=record["reply"])]))
            task.history.extend(history[-history_length:] if history_length is not None else history)
        return task

    def _get(self, context, task_id):
        try:
            return self.tasks.get(context.state["principal"], task_id)
        except KeyError as exc:
            raise TaskNotFoundError() from exc
        except PermissionError as exc:
            raise InvalidParamsError(str(exc)) from exc

    async def _submit(self, params, context):
        message = params.message
        if message.role != a2a.Role.ROLE_USER or not message.message_id or len(message.message_id) > 150:
            raise InvalidParamsError("需要用户 Message 与长度不超过 150 的 messageId")
        if message.task_id:
            self._get(context, message.task_id)
            raise UnsupportedOperationError("现有任务不接受补充输入；请提交新的任务")
        if params.configuration.HasField("task_push_notification_config"):
            raise PushNotificationNotSupportedError()
        if params.configuration.HasField("history_length") and params.configuration.history_length < 0:
            raise InvalidParamsError("historyLength 不能为负数")
        if params.configuration.accepted_output_modes and not any(
                m in {"text/plain", "application/octet-stream", "text/*", "*/*"} for m in params.configuration.accepted_output_modes):
            raise InvalidParamsError("需要接受 text/plain 输出")
        prompt, files = [], []
        for part in message.parts:
            kind = part.WhichOneof("content")
            if kind == "text":
                prompt.append(part.text)
            elif kind == "data":
                prompt.append(json.dumps(MessageToDict(part.data), ensure_ascii=False))
            elif kind == "raw":
                files.append({"name": part.filename or "attachment.bin", "content_base64": base64.b64encode(part.raw).decode()})
            elif kind == "url":
                # Only our authenticated artifact references are accepted; no arbitrary URL fetching.
                base = context.state["base"] + "/v1/tasks/"
                if not part.url.startswith(base):
                    raise InvalidParamsError("文件 URL 仅接受当前 UMEKO 的任务产物；其他文件请使用 raw/base64")
                pieces = part.url[len(base):].split("/")
                if len(pieces) != 4 or pieces[1] != "artifacts" or pieces[3] != "content":
                    raise InvalidParamsError("产物 URL 无效")
                try:
                    path, _ = self.tasks.artifact(context.state["principal"], pieces[0], pieces[2])
                    if path.stat().st_size > 20 * 1024 * 1024:
                        raise ValueError("文件超过 20 MiB")
                    files.append({"name": part.filename or path.name, "content_base64": base64.b64encode(path.read_bytes()).decode()})
                except (KeyError, PermissionError, ValueError) as exc:
                    raise InvalidParamsError(str(exc)) from exc
            else:
                raise InvalidParamsError("不支持的消息 Part")
        options = MessageToDict(params.metadata).get("umeko", {})
        if not isinstance(options, dict):
            raise InvalidParamsError("metadata.umeko 须为对象")
        try:
            record = await asyncio.to_thread(self.tasks.submit, context.state["principal"],
                {"prompt": "\n".join(prompt), "files": files, "model_id": options.get("model_id")}, source="a2a",
                context_id=message.context_id or None, idempotency_key=options.get("idempotency_key") or "a2a:" + message.message_id,
                message_id=message.message_id, caller_ip=context.state.get("caller_ip"))
            return record
        except KeyError as exc:
            raise TaskNotFoundError(str(exc)) from exc
        except (ValueError, PermissionError) as exc:
            raise InvalidParamsError(str(exc), data={"retryAfter": 5} if "队列" in str(exc) else None) from exc

    async def on_message_send(self, params, context):
        record = await self._submit(params, context)
        if not params.configuration.return_immediately:
            while record["status"] not in TERMINAL:
                await asyncio.sleep(0.2)
                record = self._get(context, record["id"])
        length = params.configuration.history_length if params.configuration.HasField("history_length") else None
        return self._task(record, context.state["base"], length)

    async def on_get_task(self, params, context):
        length = params.history_length if params.HasField("history_length") else None
        return self._task(self._get(context, params.id), context.state["base"], length)

    async def on_cancel_task(self, params, context):
        record = self._get(context, params.id)
        if record["status"] in TERMINAL:
            raise TaskNotCancelableError()
        try:
            record = self.tasks.cancel(context.state["principal"], params.id)
        except PermissionError as exc:
            raise InvalidParamsError(str(exc)) from exc
        return self._task(record, context.state["base"])

    async def on_list_tasks(self, params, context):
        try:
            offset = int(params.page_token or "0")
            if offset < 0:
                raise ValueError()
            if params.page_size < 0 or params.page_size > 100:
                raise ValueError()
            states = None if params.status == a2a.TaskState.TASK_STATE_UNSPECIFIED else [k for k, v in STATES.items() if v == params.status]
            updated_after = None
            if params.HasField("status_timestamp_after"):
                updated_after = params.status_timestamp_after.ToDatetime(tzinfo=timezone.utc).isoformat()
            result = self.tasks.list(context.state["principal"], limit=params.page_size or 50, offset=offset,
                                     context_id=params.context_id or None, status=states, updated_after=updated_after)
        except (ValueError, PermissionError) as exc:
            raise InvalidParamsError("分页或权限无效") from exc
        length = params.history_length if params.HasField("history_length") else None
        include = params.include_artifacts if params.HasField("include_artifacts") else True
        next_offset = offset + len(result["tasks"])
        return a2a.ListTasksResponse(tasks=[self._task(r, context.state["base"], length, include) for r in result["tasks"]],
             total_size=result["total"], page_size=len(result["tasks"]),
             next_page_token=str(next_offset) if next_offset < result["total"] else "")

    async def _stream(self, record, context):
        yield self._task(record, context.state["base"])
        cursor, emitted, state = 0, False, record["status"]
        while True:
            record = self._get(context, record["id"])
            for event in self.tasks.events(context.state["principal"], record["id"], cursor):
                cursor = event["id"]
                if event["type"] == "assistant.delta" and event["data"].get("text"):
                    yield a2a.TaskArtifactUpdateEvent(task_id=record["id"], context_id=record["context_id"],
                        artifact=a2a.Artifact(artifact_id="response", name="Agent response", parts=[a2a.Part(text=event["data"]["text"])]),
                        append=emitted, last_chunk=False)
                    emitted = True
            if record["status"] in TERMINAL:
                # Replace accumulated partial text with the authoritative final reply.
                final = self._task(record, context.state["base"])
                for artifact in final.artifacts:
                    yield a2a.TaskArtifactUpdateEvent(task_id=record["id"], context_id=record["context_id"],
                                                     artifact=artifact, append=False, last_chunk=True)
                yield a2a.TaskStatusUpdateEvent(task_id=record["id"], context_id=record["context_id"], status=final.status)
                return
            if state != record["status"]:
                state = record["status"]
                yield a2a.TaskStatusUpdateEvent(task_id=record["id"], context_id=record["context_id"],
                                                status=self._task(record, context.state["base"], 0, False).status)
            await asyncio.sleep(0.2)

    async def on_message_send_stream(self, params, context):
        record = await self._submit(params, context)
        async for event in self._stream(record, context):
            yield event

    async def on_subscribe_to_task(self, params, context):
        record = self._get(context, params.id)
        if record["status"] in TERMINAL:
            raise UnsupportedOperationError("任务已结束，请使用 GetTask 查询结果")
        async for event in self._stream(record, context):
            yield event

    async def _no_push(self, params, context):
        raise PushNotificationNotSupportedError()

    on_create_task_push_notification_config = _no_push
    on_get_task_push_notification_config = _no_push
    on_list_task_push_notification_configs = _no_push
    on_delete_task_push_notification_config = _no_push

    async def on_get_extended_agent_card(self, params, context):
        raise UnsupportedOperationError("使用公开 Agent Card")


def add_a2a_routes(app, settings, tasks):
    async def card(request: Request):
        base = public_base(settings, request)
        value = {"name": "UMEKO", "description": "文件处理与多智能体任务执行服务", "version": __version__,
                 "documentationUrl": "https://umeiko.github.io/UmEkO/api/",
                 "supportedInterfaces": [{"url": base + "/a2a", "protocolBinding": "JSONRPC", "protocolVersion": "1.0"}],
                 "capabilities": {"streaming": True, "pushNotifications": False},
                 "defaultInputModes": ["text/plain", "application/octet-stream", "application/json"],
                 "defaultOutputModes": ["text/plain", "application/octet-stream"],
                 "securitySchemes": {"serviceBearer": {"httpAuthSecurityScheme": {"scheme": "bearer", "bearerFormat": "UMEKO service credential"}}},
                 "securityRequirements": [] if tasks.service.identity_store.auth_mode() == "anonymous" else [{"schemes": {"serviceBearer": {"list": []}}}],
                 "skills": [{"id": "file_task", "name": "文件任务", "description": "按要求处理文本、图像和文件，返回结果与报告",
                             "tags": ["files", "documents", "images"], "examples": ["检查附件内容并生成报告"]}]}
        return MessageToDict(ParseDict(value, a2a.AgentCard()))
    app.add_api_route("/.well-known/agent-card.json", card, methods=["GET"], tags=["A2A"])
    app.router.routes.extend(create_jsonrpc_routes(A2AHandler(tasks), rpc_url="/a2a",
                                                   context_builder=A2AContextBuilder(settings)))
