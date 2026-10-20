"""Official MCP and A2A SDK adapters over the shared durable task service."""
from __future__ import annotations

import asyncio
import base64
import json
from urllib.parse import urlsplit
from typing import Annotated, Any
from fastapi import Request
from fastapi.responses import JSONResponse

from a2a import types as a2a
from a2a.server.context import ServerCallContext
from a2a.server.request_handlers import RequestHandler
from a2a.server.routes import ServerCallContextBuilder, create_jsonrpc_routes
from a2a.utils.errors import (
    InvalidParamsError, PushNotificationNotSupportedError, TaskNotCancelableError,
    TaskNotFoundError, UnsupportedOperationError,
)
from google.protobuf.json_format import MessageToDict, ParseDict
from google.protobuf.struct_pb2 import Value
from mcp.server import MCPServer
from mcp.server.mcpserver import Context
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import CallToolResult, TextContent, ToolAnnotations

from .. import __version__
from ..host.tasks import TERMINAL
from ..host.task_input import MAX_MESSAGE_PARTS, MAX_PROMPT_CHARS, TaskInputError
from .task_api import TaskFileInput, caller_ip, public_base, task_view

def _mcp_call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except (ValueError, KeyError, PermissionError) as exc:
        raise ToolError(str(exc)) from exc


def _mcp_server(settings, tasks):
    server = MCPServer("UMEKO", version=__version__, instructions=(
        "先 get_agent_info 了解当前智能体，再 submit_task 提交任务，使用 get_task 查询状态。"
        "用 submit_task 返回的 task_id 查询本次执行；结束后 read_results 获取自然语言结果和 Agent 选择的最终文件清单。"
        "按清单的 file_id 调用 download_file 下载，文件夹为 ZIP；list_file 可逐层查看其他任务文件。"
        "取消用 cancel_task。主模型和视觉模型由管理员配置，调用方不能选择。"
        "prompt 可写需求和普通 HTTP/HTTPS 下载链接，禁止把文件 base64 或 data URL 塞进正文；文件字节使用 files 的 name/content_base64。"
        "输入被拒绝时不要原样或拆段重试，应按错误提示修正附件结构，不能上传时通知用户。"
        "提交成功后立即把 workspace_url 作为可点击链接交给用户，邀请其打开临时工作台查看进度、文件与继续同一会话。"
        "若回复说明缺少必要图片、文档或需要人工处理，立即提供真实 workspace_url 和待补事项，邀请用户进入工作台处理；"
        "不要一直 get_task 等待补传文件，后续通过工作台或其会话 REST 接口继续。"
        "链接等同本会话访问凭据，请仅交给预期使用者。"))
    def principal(ctx):
        return ctx.request_context.request.state.principal

    @server.prompt(name="task_lifecycle", title="任务提交、查询与文件下载契约")
    def task_lifecycle() -> str:
        """首次接入时读取：用最少步骤完成本 MCP 的任务提交、状态查询、文件下载和人工接续。"""
        return """按以下契约使用当前 Agent 的 MCP：
1. 可先 get_agent_info 了解能力。submit_task(prompt=用户需求, files=可选附件) 提交一次，保存返回的 task_id 和 workspace_url。
   files 使用 name/content_base64，不传服务器路径；prompt 可写需求和普通 HTTP/HTTPS 下载链接，不放 base64、data URL 或伪装成文字的附件 JSON。
   提交成功后立即把真实 workspace_url 作为可点击链接交给用户，说明可实时查看进度、文件和工具记录，任务结束后可继续同一会话。
   输入被拒绝时不要原样或拆段重试，按错误提示修正；无法上传时向用户说明需要附件。模型由管理员配置，不传 model_id。本服务不提供模型列表或任务列表。
2. 提交成功不等于执行完成。只用这次返回的 task_id 调用 get_task；不能用固定 agent_id 替代。
   queued/running/cancelling 时隔几秒查询，避免密集轮询和重复提交；重试同一次提交时复用 idempotency_key。
3. completed 时调用 read_results(task_id)，ready=true 后交付 text，并按 files 中的 file_id 调用 download_file(task_id, file_id) 获取下载链接。
   files 是 Agent 明确提交并由平台校验的最终文件清单，可能为空；不把整个目录的文件当成最终成果。
   需要查看其他任务文件时用 list_file(task_id)，传 directory_id=文件夹的file_id 可逐层查看直接子项。
   文件下载保持原内容，文件夹自动打包 ZIP。需要凭据模式下，GET 下载链接携带相同服务凭据；不要把 file_id 当作 task_id。
4. failed/cancelled 时说明 error 或停止状态；停止正在执行的任务用 cancel_task(task_id)，不要把失败当作成功。
5. 回复说缺少必要资料或需要人工处理时，把真实 workspace_url 和待补事项交给用户，请其在临时工作台继续同一会话；不要空等补传或自动重提。
6. 只访问当前 Agent、当前调用方、本次 task_id 的信息。下载序号在该任务内有效；不存在或类型变化时重新 list_file，不猜路径或序号。
7. 节点有生命周期：workspace_state=expired 或下载返回过期时，原回复可能仍能查询，文件和工作台已不可访问。
   说明过期情况；用户要求重做时才重新提交。workspace_url 是会话访问凭据，只交给预期使用者。
   临时工作台续聊后，可用同一 task_id 再 read_results 获取最新通过校验的结果；不要重复提交原任务。"""

    @server.tool(structured_output=True, annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=False))
    def get_agent_info(ctx: Context) -> dict[str, Any]:
        """读取当前路径所对应智能体的公开介绍和技能，不包含工作指引与模型密钥。"""
        request = ctx.request_context.request
        return tasks.service.agent_card.render(public_base(settings, request), tasks.service.identity_store.auth_mode(),
                                               request.state.agent_definition)

    @server.tool(structured_output=True, annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=True))
    async def submit_task(prompt: str, ctx: Context, files: list[TaskFileInput] | None = None,
                          idempotency_key: str | None = None) -> Annotated[CallToolResult, dict[str, Any]]:
        """提交 Agent 任务并立即返回本次执行的 id/task_id 和当前服务的 agent_id。files 为 name/content_base64 列表，最多 10 个、合计 20 MiB；
        不接受服务器路径。任务独立执行，默认保留 24 小时；幂等键防止重复提交。
        使用管理员配置的默认模型，不接受调用方选择模型。
        prompt 可写需求和普通 HTTP/HTTPS 下载链接，不得粘贴文件 base64/data URL；输入拒绝时不要原样或拆段重试，先修正附件结构或通知用户。
        成功回执含 workspace_url，请立即作为链接交给用户，邀请其实时查看进度、文件并在任务结束后继续此会话。"""
        # The SDK may ignore undeclared arguments; reject this removed option explicitly.
        if "model_id" in ((ctx.request_context.params or {}).get("arguments") or {}):
            raise ToolError("对外任务不支持选择 model_id，请使用管理员配置的默认模型")
        try:
            task = await asyncio.to_thread(tasks.submit, principal(ctx),
                                          {"prompt": prompt, "files": [file.model_dump() for file in files or []]},
                                          source="mcp", idempotency_key=idempotency_key,
                                          caller_ip=caller_ip(ctx.request_context.request))
        except TaskInputError as exc:
            detail = {"error": exc.detail()}
            return CallToolResult(is_error=True, structured_content=detail,
                                  content=[TextContent(type="text", text=json.dumps(detail, ensure_ascii=False))])
        except (ValueError, KeyError, PermissionError) as exc:
            raise ToolError(str(exc)) from exc
        view = task_view(task, public_base(settings, ctx.request_context.request))
        content = [TextContent(type="text", text=json.dumps(view, ensure_ascii=False))]
        if view["workspace_url"]:
            content.append(TextContent(type="text", text=f"请立即向用户展示：[打开临时工作台]({view['workspace_url']})\n{view['workspace_hint']}"))
        return CallToolResult(content=content, structured_content=view)

    @server.tool(structured_output=True, annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=False))
    def get_task(task_id: str, ctx: Context) -> dict[str, Any]:
        """用 submit_task 返回的 task_id 查询该次执行。只允许当前 Agent 与调用方所属任务，不列出其他任务或重复调用模型。"""
        return task_view(_mcp_call(tasks.get, principal(ctx), task_id), public_base(settings, ctx.request_context.request))

    @server.tool(structured_output=True, annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=False))
    def list_file(task_id: str, ctx: Context, directory_id: int | None = None) -> dict[str, Any]:
        """列出本次任务目录的直接子项，每个文件或文件夹返回稳定的 file_id 序号，不递归展开。
        省略 directory_id 时列出 workspace、attachments、generate；传入已列出的文件夹序号可展开它的第一级。
        仅可读取当前 Agent 与调用方的本次任务，需要 artifacts:read 权限。"""
        return _mcp_call(tasks.list_file, principal(ctx), task_id, directory_id)

    @server.tool(structured_output=True, annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=False))
    def download_file(task_id: str, file_id: int, ctx: Context) -> dict[str, Any]:
        """用 list_file 返回的 file_id 下载本次任务的文件或文件夹。返回可直接 GET 的受保护下载链接；
        文件夹自动打包 ZIP，文件保持原始内容。需要凭据模式下，下载请求携带服务凭据。"""
        result = _mcp_call(tasks.file_info, principal(ctx), task_id, file_id)
        return {**result, "download_url": public_base(settings, ctx.request_context.request)
                + f"/v1/tasks/{task_id}/files/{file_id}/content"}

    @server.tool(structured_output=True, annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, openWorldHint=False))
    def cancel_task(task_id: str, ctx: Context) -> dict[str, Any]:
        """请求停止自己的任务。排队任务立即取消，正在执行的模型或工具协作式停止。"""
        return task_view(_mcp_call(tasks.cancel, principal(ctx), task_id), public_base(settings, ctx.request_context.request))

    @server.tool(structured_output=True, annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=False))
    def read_results(task_id: str, ctx: Context) -> dict[str, Any]:
        """读取本次 Agent 最后通过校验的结果 JSON：text 是自然语言结论，files 是 Agent 选择的最终交付件。
        文件项包含 file_id，可直接交给 download_file；不读取文件内容，不自动扫描目录挑选产物。
        ready=false 表示未产生结构化结果，结合 status/error 判断；节点过期后仍可读取保留的结果元数据。"""
        return _mcp_call(tasks.read_results, principal(ctx), task_id)

    return server


async def mcp_disclosure(settings, tasks):
    """Use the same SDK registrations as tools/list, without calling tools or HTTP."""
    server = _mcp_server(settings, tasks)
    tools, resources, templates, prompts = await asyncio.gather(
        server.list_tools(), server.list_resources(), server.list_resource_templates(), server.list_prompts(),
    )
    def wire(items):
        return [item.model_dump(mode="json", by_alias=True, exclude_none=True) for item in items]
    return {"server": {"name": server.name, "version": server.version, "instructions": server.instructions},
            "transport": "Streamable HTTP", "tools": wire(tools), "resources": wire(resources),
            "resourceTemplates": wire(templates), "prompts": wire(prompts)}


def build_mcp(settings, tasks):
    server = _mcp_server(settings, tasks)
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
        view = task_view(record, base)
        if view["workspace_url"]:
            status_text = ((record["error"] + "\n\n") if record["error"] else "")
            status_text += f"[打开临时工作台]({view['workspace_url']})\n{view['workspace_hint']}"
            task.status.message.CopyFrom(a2a.Message(message_id=record["id"] + "-status", role=a2a.Role.ROLE_AGENT,
                                                     parts=[a2a.Part(text=status_text)]))
        ParseDict({"expiresAt": record["expires_at"], "source": record["source"], "agentId": record["agent_id"],
                   "workspaceExpiresAt": record.get("workspace_expires_at"), "workspaceState": record.get("workspace_state"),
                   "workspaceUrl": view["workspace_url"], "workspaceHint": view["workspace_hint"]}, task.metadata)
        if include_artifacts:
            if record["reply"]:
                task.artifacts.append(a2a.Artifact(artifact_id="response", name="Agent response", parts=[a2a.Part(text=record["reply"])]))
                with self.tasks.store.connect() as db:
                    result = db.execute("SELECT result_json FROM service_tasks WHERE id=?", (record["id"],)).fetchone()
                if result and result["result_json"]:
                    task.artifacts[-1].parts.append(a2a.Part(data=ParseDict(json.loads(result["result_json"]), Value())))
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
        if len(message.parts) > MAX_MESSAGE_PARTS:
            exc = TaskInputError("TOO_MANY_PARTS", "消息最多包含 64 个 Part；请合并需求文本并通过文件 Part 上传附件。", "message.parts")
            raise InvalidParamsError(str(exc), data=exc.detail())
        prompt, files, urls, text_length, url_length, file_bytes = [], [], [], 0, 0, 0
        url_label = "用户的请求还附带了这些url："
        for part in message.parts:
            kind = part.WhichOneof("content")
            if kind in {"text", "data"}:
                text = part.text if kind == "text" else json.dumps(MessageToDict(part.data), ensure_ascii=False)
                text_length += len(text) + bool(prompt)
                prompt.append(text)
            elif kind == "raw":
                file_bytes += len(part.raw)
                files.append({"name": part.filename or "attachment.bin", "content_base64": base64.b64encode(part.raw).decode()})
            elif kind == "url":
                if not part.url.strip():
                    exc = TaskInputError("INVALID_URL", "url Part 须包含非空链接；也可直接在 text 中描述链接。", "message.parts")
                    raise InvalidParamsError(str(exc), data=exc.detail())
                # Pass links to the Agent as user input; the protocol neither
                # fetches URLs nor copies other tasks' artifacts into this task.
                url_length += len(part.url) + (2 if urls else len(url_label))
                urls.append(part.url)
            else:
                raise InvalidParamsError("不支持的消息 Part")
            if text_length + url_length + bool(prompt and urls) > MAX_PROMPT_CHARS:
                exc = TaskInputError("PROMPT_TOO_LARGE", "所有 text、data 和 url Part 合计最多 200000 字符；文件内容请通过 raw Part 上传。", "message.parts")
                raise InvalidParamsError(str(exc), data=exc.detail())
            if len(files) > 10 or file_bytes > 20 * 1024 * 1024:
                exc = TaskInputError("INVALID_FILES", "最多上传 10 个文件，总大小不超过 20 MiB。", "message.parts")
                raise InvalidParamsError(str(exc), data=exc.detail())
        if urls:
            prompt.append(url_label + "; ".join(urls))
        options = MessageToDict(params.metadata).get("umeko", {})
        if not isinstance(options, dict):
            raise InvalidParamsError("metadata.umeko 须为对象")
        if "model_id" in options:
            raise InvalidParamsError("对外任务不支持选择 model_id，请使用管理员配置的默认模型")
        try:
            record = await asyncio.to_thread(self.tasks.submit, context.state["principal"],
                {"prompt": "\n".join(prompt), "files": files}, source="a2a",
                context_id=message.context_id or None, idempotency_key=options.get("idempotency_key") or "a2a:" + message.message_id,
                message_id=message.message_id, caller_ip=context.state.get("caller_ip"))
            return record
        except TaskInputError as exc:
            raise InvalidParamsError(str(exc), data=exc.detail()) from exc
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
        raise UnsupportedOperationError("不提供任务列表，请使用提交时返回的任务 ID 调用 GetTask")

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
        value = tasks.service.agent_card.render(base, tasks.service.identity_store.auth_mode(),
                                               request.state.agent_definition)
        return JSONResponse(value, headers={"Cache-Control": "no-cache"})
    app.add_api_route("/.well-known/agent-card.json", card, methods=["GET"], tags=["A2A"])
    app.router.routes.extend(create_jsonrpc_routes(A2AHandler(tasks), rpc_url="/a2a",
                                                   context_builder=A2AContextBuilder(settings)))
