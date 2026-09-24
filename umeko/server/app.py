from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.background import BackgroundTask

from .. import __version__
from ..config import Settings
from ..host.profile import CLOUD_PROFILE, Profile
from ..host.service import AgentService, SessionState
from ..host.storage import Store
from ..runner import Run as RunState
from .models import (
    ArtifactView,
    AuthInput,
    ClientResourceGenerate,
    ClientResourceUpdate,
    ClientResourceView,
    ContextView,
    FileView,
    MessageView,
    ModelPrefsIn,
    ProxySessionView,
    ProxyStatusView,
    RunCreate,
    RunView,
    SessionCreate,
    SessionModelIn,
    SessionTitlePatch,
    SessionView,
    UserView,
    WorkspaceAttachmentCreate,
    WorkspaceEntryCreate,
    WorkspaceFileView,
    WorkspaceNode,
    ToolEventView,
    WorkspaceTransfer,
    WorkspaceExtract,
)

STATIC_DIR = Path(__file__).with_name("static")
MAX_AVATAR_BYTES = 2 * 1024 * 1024
AUTH_COOKIE = "umeko_auth"


def _avatar_media_type(content: bytes) -> str | None:
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if content.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if content.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if len(content) >= 12 and content.startswith(b"RIFF") and content[8:12] == b"WEBP":
        return "image/webp"
    return None


def _session_view(session: SessionState) -> SessionView:
    return SessionView(
        id=session.id,
        created_at=session.created_at,
        title=session.title,
    )


def _run_view(run: RunState, service: AgentService) -> RunView:
    return RunView(
        id=run.id,
        session_id=run.session_id,
        status=run.status,
        created_at=run.created_at,
        completed_at=run.completed_at,
        reply=service.web_text(run.session_id, run.reply),
        error=service.web_text(run.session_id, run.error),
    )


def create_app(
    settings: Settings,
    data_root: str | Path = "server_data",
    workspace_root: str | Path = "output",
    profile: Profile = CLOUD_PROFILE,
    command_runner=None,
) -> FastAPI:
    app = FastAPI(
        title="Umeko API",
        version=__version__,
        description=(
            "Umeko 通用 Agent 基座的服务化 API。用户、Session 与对话历史保存在 SQLite；"
            "附件与产物保存在用户与 Session 隔离的服务端目录。"
        ),
    )
    store = Store(Path(data_root) / "umeko.db")
    service = AgentService(
        settings, data_root, workspace_root=workspace_root, store=store,
        profile=profile, command_runner=command_runner,
    )
    app.state.agent_service = service
    app.state.store = store
    app.state.profile = profile
    # 本地场景：所有请求都落在隐式单用户上，免登录直达工作台
    local_user = None if profile.auth_enabled else store.ensure_local_user()
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.middleware("http")
    async def authenticate_request(request: Request, call_next):
        path = request.url.path
        public = path in {"/", "/health", "/openapi.json", "/v1/auth/register", "/v1/auth/login"} or path.startswith("/static/")
        user = (
            store.user_for_token(request.cookies.get(AUTH_COOKIE))
            if profile.auth_enabled else local_user
        )
        request.state.user = user
        if path.startswith("/v1/") and not public and user is None:
            return JSONResponse({"detail": "请先登录"}, status_code=401)
        match = re.match(r"/v1/sessions/([^/]+)", path)
        if match and user and store.session(match.group(1), user["id"]) is None:
            return JSONResponse({"detail": "Session 不存在或无权访问"}, status_code=404)
        return await call_next(request)

    def get_session(session_id: str) -> SessionState:
        try:
            return service.get_session(session_id)
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from exc

    def get_run(run_id: str) -> RunState:
        try:
            return service.get_run(run_id)
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from exc

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    def web_app() -> HTMLResponse:
        return HTMLResponse((STATIC_DIR / "index.html").read_text(encoding="utf-8"))

    @app.get("/health", tags=["system"])
    def health() -> dict:
        return {"status": "ok"}

    @app.post("/v1/auth/register", response_model=UserView, status_code=201, tags=["auth"])
    def register(payload: AuthInput, response: Response) -> UserView:
        try:
            user = store.create_user(payload.username, payload.password)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        response.set_cookie(AUTH_COOKIE, store.issue_token(user["id"]), httponly=True,
                            samesite="lax", secure=False, max_age=14 * 86400)
        return UserView(**user)

    @app.post("/v1/auth/login", response_model=UserView, tags=["auth"])
    def login(payload: AuthInput, response: Response) -> UserView:
        user = store.authenticate(payload.username, payload.password)
        if not user:
            raise HTTPException(401, "用户名或密码错误")
        response.set_cookie(AUTH_COOKIE, store.issue_token(user["id"]), httponly=True,
                            samesite="lax", secure=False, max_age=14 * 86400)
        return UserView(**user)

    @app.get("/v1/auth/me", response_model=UserView, tags=["auth"])
    def me(request: Request) -> UserView:
        return UserView(**request.state.user)

    @app.get("/v1/auth/avatar", tags=["auth"])
    def avatar(request: Request) -> Response:
        stored = store.user_avatar(request.state.user["id"])
        if stored is None:
            raise HTTPException(404, "尚未设置头像")
        content, media_type = stored
        return Response(
            content=content,
            media_type=media_type,
            headers={"Cache-Control": "private, no-store"},
        )

    @app.put("/v1/auth/avatar", response_model=UserView, tags=["auth"])
    async def update_avatar(request: Request) -> UserView:
        content = await request.body()
        if not content:
            raise HTTPException(400, "头像文件不能为空")
        if len(content) > MAX_AVATAR_BYTES:
            raise HTTPException(413, "头像不能超过 2 MB")
        media_type = _avatar_media_type(content)
        if media_type is None:
            raise HTTPException(400, "头像仅支持 PNG、JPEG、WebP 或 GIF")
        store.set_user_avatar(request.state.user["id"], content, media_type)
        return UserView(
            id=request.state.user["id"],
            username=request.state.user["username"],
            avatar_url="/v1/auth/avatar",
        )

    @app.delete("/v1/auth/avatar", response_model=UserView, tags=["auth"])
    def delete_avatar(request: Request) -> UserView:
        store.set_user_avatar(request.state.user["id"], None)
        return UserView(
            id=request.state.user["id"],
            username=request.state.user["username"],
            avatar_url=None,
        )

    @app.post("/v1/auth/logout", status_code=204, tags=["auth"])
    def logout(request: Request, response: Response) -> None:
        store.revoke_token(request.cookies.get(AUTH_COOKIE))
        response.delete_cookie(AUTH_COOKIE)

    # ---------- 模型选择（用户面：只读注册表 + 个人偏好 + 会话覆盖） ----------

    @app.get("/v1/models", tags=["models"])
    def available_models(request: Request) -> dict:
        """管理员配置的可用模型清单（不含凭据）+ 全局默认 + 我的偏好。"""
        active = store.active_model()
        return {
            "providers": [
                {
                    "id": p["id"], "name": p["name"],
                    "models": [
                        {"id": m["id"], "name": m["name"], "vision": m["vision"]}
                        for m in p["models"]
                    ],
                }
                for p in store.list_providers()
            ],
            "active_model_id": active["model_id"] if active else None,
            "prefs": store.user_model_prefs(request.state.user["id"]),
        }

    @app.put("/v1/auth/model-prefs", tags=["models"])
    def set_model_prefs(payload: ModelPrefsIn, request: Request) -> dict:
        try:
            return store.set_user_model_prefs(
                request.state.user["id"],
                main_model_id=payload.main_model_id,
                sub_model_id=payload.sub_model_id,
                vision_model_id=payload.vision_model_id,
            )
        except KeyError as exc:
            raise HTTPException(404, "模型不存在或已被管理员移除") from exc
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.put("/v1/sessions/{session_id}/model", status_code=204, tags=["models"])
    def set_session_model(session_id: str, payload: SessionModelIn) -> None:
        try:
            store.set_session_model_override(session_id, payload.model_id)
        except KeyError as exc:
            raise HTTPException(404, "模型不存在或已被管理员移除") from exc

    @app.get(
        "/v1/sessions/{session_id}/workspace/tree",
        response_model=list[WorkspaceNode],
        tags=["workspace"],
    )
    def workspace_tree(session_id: str, filter: str = "") -> list[WorkspaceNode]:
        try:
            nodes = [
                WorkspaceNode(**node)
                for node in service.workspace_tree(session_id, filter=filter)
            ]
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        return nodes

    @app.get(
        "/v1/sessions/{session_id}/client/{kind}",
        response_model=list[ClientResourceView],
        tags=["client resources"],
    )
    def list_client_resources(session_id: str, kind: str) -> list[ClientResourceView]:
        get_session(session_id)
        try:
            return [ClientResourceView(**item) for item in service.client_resources(session_id, kind)]
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.get(
        "/v1/sessions/{session_id}/client/{kind}/{name}",
        response_model=ClientResourceView,
        tags=["client resources"],
    )
    def read_client_resource(session_id: str, kind: str, name: str) -> ClientResourceView:
        session = get_session(session_id)
        try:
            path, mounted = service.client_resource(session_id, kind, name)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        except FileNotFoundError as exc:
            raise HTTPException(404, f"资源不存在：{name}") from exc
        return ClientResourceView(
            kind=kind, name=path.name, mounted=mounted,
            builtin=path.name in session.builtin_resources[kind],
            content=path.read_text(encoding="utf-8"),
        )

    @app.post(
        "/v1/sessions/{session_id}/client/{kind}",
        response_model=ClientResourceView,
        status_code=201,
        tags=["client resources"],
    )
    async def create_client_resource(
        session_id: str, kind: str, request: Request, filename: str = Query(min_length=1)
    ) -> ClientResourceView:
        session = get_session(session_id)
        if session.lock.locked():
            raise HTTPException(409, "会话正在执行 Run，暂时不能修改挂载资源")
        try:
            content = (await request.body()).decode("utf-8")
            return ClientResourceView(**service.create_client_resource(
                session_id, kind, filename, content
            ))
        except UnicodeDecodeError as exc:
            raise HTTPException(400, "资源文件必须使用 UTF-8 编码") from exc
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.post(
        "/v1/sessions/{session_id}/client/{kind}/generate",
        response_model=ClientResourceView,
        status_code=201,
        tags=["client resources"],
    )
    def generate_client_resource(
        session_id: str, kind: str, payload: ClientResourceGenerate
    ) -> ClientResourceView:
        session = get_session(session_id)
        if session.lock.locked():
            raise HTTPException(409, "会话正在执行 Run，暂时不能生成资源")
        try:
            return ClientResourceView(**service.generate_client_resource(
                session_id, kind, payload.name, payload.description
            ))
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.patch(
        "/v1/sessions/{session_id}/client/{kind}/{name}",
        response_model=ClientResourceView,
        tags=["client resources"],
    )
    def update_client_resource(
        session_id: str, kind: str, name: str, payload: ClientResourceUpdate
    ) -> ClientResourceView:
        session = get_session(session_id)
        if session.lock.locked():
            raise HTTPException(409, "会话正在执行 Run，暂时不能修改挂载资源")
        try:
            return ClientResourceView(**service.update_client_resource(
                session_id, kind, name, content=payload.content, mounted=payload.mounted
            ))
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        except FileNotFoundError as exc:
            raise HTTPException(404, f"资源不存在：{name}") from exc

    @app.delete(
        "/v1/sessions/{session_id}/client/{kind}/{name}",
        status_code=204,
        tags=["client resources"],
    )
    def delete_client_resource(session_id: str, kind: str, name: str) -> None:
        session = get_session(session_id)
        if session.lock.locked():
            raise HTTPException(409, "会话正在执行 Run，暂时不能修改挂载资源")
        try:
            service.delete_client_resource(session_id, kind, name)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        except FileNotFoundError as exc:
            raise HTTPException(404, f"资源不存在：{name}") from exc

    @app.get("/v1/sessions/{session_id}/workspace/files/content", tags=["workspace"])
    def workspace_file(session_id: str, path: str = Query(min_length=1)):
        try:
            file_path = service.workspace_file(session_id, path)
        except ValueError as exc:
            raise HTTPException(403, str(exc)) from exc
        except FileNotFoundError as exc:
            raise HTTPException(404, f"文件不存在：{path}") from exc
        return FileResponse(file_path, media_type=None)

    @app.get(
        "/v1/sessions/{session_id}/workspace/files/raw/{file_path:path}",
        tags=["workspace"],
    )
    def workspace_file_raw(session_id: str, file_path: str):
        """路径式文件访问：URL 自带位置信息，HTML 内的相对路径引用（图片/CSS）
        可被浏览器正确解析。用于 HTML 报告等产物的整页渲染（新标签页打开）。"""
        try:
            resolved = service.workspace_file(session_id, file_path)
        except ValueError as exc:
            raise HTTPException(403, str(exc)) from exc
        except FileNotFoundError as exc:
            raise HTTPException(404, f"文件不存在：{file_path}") from exc
        return FileResponse(resolved, media_type=None)

    @app.get("/v1/sessions/{session_id}/workspace/files/download", tags=["workspace"])
    def download_workspace_file(session_id: str, path: str = Query(min_length=1)):
        try:
            download_path, temporary = service.workspace_download(session_id, path)
        except ValueError as exc:
            raise HTTPException(403, str(exc)) from exc
        except FileNotFoundError as exc:
            raise HTTPException(404, f"文件或目录不存在：{path}") from exc
        if temporary:
            source_name = Path(path.replace("\\", "/")).name or "directory"
            return FileResponse(
                download_path,
                filename=f"{source_name}.zip",
                media_type="application/zip",
                background=BackgroundTask(download_path.unlink, missing_ok=True),
            )
        return FileResponse(
            download_path,
            filename=download_path.name,
            media_type="application/octet-stream",
        )

    @app.post(
        "/v1/sessions/{session_id}/workspace/entries",
        response_model=WorkspaceFileView,
        status_code=201,
        tags=["workspace"],
    )
    def create_workspace_entry(session_id: str, payload: WorkspaceEntryCreate) -> WorkspaceFileView:
        session = get_session(session_id)
        if session.lock.locked():
            raise HTTPException(409, "Session 正在运行，暂时不能修改文件")
        try:
            path = service.create_workspace_entry(session_id, payload.path, payload.type)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        return WorkspaceFileView(path=path.relative_to(session.root).as_posix(), filename=path.name,
                                 size=path.stat().st_size if path.is_file() else 0)

    @app.post(
        "/v1/sessions/{session_id}/workspace/transfer",
        response_model=WorkspaceFileView,
        tags=["workspace"],
    )
    def transfer_workspace_entry(session_id: str, payload: WorkspaceTransfer) -> WorkspaceFileView:
        session = get_session(session_id)
        if session.lock.locked():
            raise HTTPException(409, "Session 正在运行，暂时不能修改文件")
        try:
            path = service.transfer_workspace_entry(
                session_id, payload.source, payload.target, payload.operation
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        except FileNotFoundError as exc:
            raise HTTPException(404, "源文件或目录不存在") from exc
        return WorkspaceFileView(path=path.relative_to(session.root).as_posix(), filename=path.name,
                                 size=path.stat().st_size if path.is_file() else 0)

    @app.delete("/v1/sessions/{session_id}/workspace/entries", status_code=204, tags=["workspace"])
    def delete_workspace_entry(session_id: str, path: str = Query(min_length=1)) -> None:
        session = get_session(session_id)
        if session.lock.locked():
            raise HTTPException(409, "Session 正在运行，暂时不能修改文件")
        try:
            service.delete_workspace_entry(session_id, path)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        except FileNotFoundError as exc:
            raise HTTPException(404, f"文件或目录不存在：{path}") from exc

    @app.post(
        "/v1/sessions/{session_id}/workspace/extract",
        response_model=WorkspaceFileView,
        tags=["workspace"],
    )
    def extract_workspace_archive(session_id: str, payload: WorkspaceExtract) -> WorkspaceFileView:
        session = get_session(session_id)
        if session.lock.locked():
            raise HTTPException(409, "Session 正在运行，暂时不能修改文件")
        try:
            target = service.extract_archive(session_id, payload.path)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        except FileNotFoundError as exc:
            raise HTTPException(404, "压缩包不存在") from exc
        return WorkspaceFileView(
            path=target.relative_to(session.root).as_posix(),
            filename=target.name,
            size=sum(f.stat().st_size for f in target.rglob("*") if f.is_file()),
        )

    @app.post(
        "/v1/sessions/{session_id}/workspace/files",
        response_model=WorkspaceFileView,
        status_code=201,
        tags=["workspace"],
    )
    async def upload_workspace_file(
        session_id: str, request: Request,
        filename: str = Query(min_length=1),
        path: str = Query(default=""),
    ) -> WorkspaceFileView:
        content = await request.body()
        if not content:
            raise HTTPException(400, "文件内容不能为空")
        try:
            saved = service.save_workspace_file(
                session_id, filename, content, relative_dir=path
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        except FileNotFoundError as exc:
            raise HTTPException(400, f"目标目录不存在：{path}") from exc
        return WorkspaceFileView(
            path=saved.relative_to(get_session(session_id).root).as_posix(),
            filename=saved.name,
            size=saved.stat().st_size,
        )

    @app.get("/v1/sessions", tags=["sessions"])
    def list_sessions(request: Request) -> list[dict]:
        return store.sessions(request.state.user["id"])

    @app.post("/v1/sessions", response_model=SessionView, status_code=201, tags=["sessions"])
    def create_session(payload: SessionCreate, request: Request) -> SessionView:
        session = service.create_session(user_id=request.state.user["id"])
        return _session_view(session)

    @app.patch("/v1/sessions/{session_id}/title", status_code=204, tags=["sessions"])
    def rename_session(session_id: str, payload: SessionTitlePatch, request: Request) -> None:
        store.rename_session(session_id, request.state.user["id"], payload.title)
        if session_id in service.sessions:
            service.sessions[session_id].title = payload.title.strip()

    @app.delete("/v1/sessions/{session_id}", status_code=204, tags=["sessions"])
    def delete_session(session_id: str, request: Request) -> None:
        session = service.sessions.get(session_id)
        if session and session.lock.locked():
            raise HTTPException(409, "Session 正在运行")
        store.delete_session(session_id, request.state.user["id"])
        service.sessions.pop(session_id, None)
        if session and session.root.is_dir():
            import shutil
            shutil.rmtree(session.root)

    @app.get("/v1/sessions/{session_id}/messages", response_model=list[MessageView], tags=["sessions"])
    def session_messages(session_id: str) -> list[MessageView]:
        get_session(session_id)
        rows = store.messages(session_id)
        return [MessageView(role=row["role"], content=(
                                service.web_text(session_id, row["content"])
                                if row["role"] == "assistant" else row["content"]
                            ),
                            attachments=json.loads(row["attachments"]), created_at=row["created_at"])
                for row in rows]

    @app.get(
        "/v1/sessions/{session_id}/tool-events",
        response_model=list[ToolEventView],
        tags=["sessions"],
    )
    def session_tool_events(session_id: str) -> list[ToolEventView]:
        get_session(session_id)
        return [
            ToolEventView(
                agent=row["agent"], name=row["name"],
                arguments=row["arguments"], result=row["result"],
                created_at=row["created_at"],
            )
            for row in store.tool_events(session_id)
        ]

    @app.get(
        "/v1/sessions/{session_id}/context",
        response_model=ContextView,
        tags=["sessions"],
    )
    def session_context(session_id: str) -> ContextView:
        return ContextView(**service.context_stats(session_id))

    @app.post(
        "/v1/sessions/{session_id}/context/compact",
        response_model=ContextView,
        tags=["sessions"],
    )
    def compact_session_context(session_id: str) -> ContextView:
        try:
            return ContextView(**service.compact_context(session_id))
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.post(
        "/v1/sessions/{session_id}/context/clear",
        response_model=ContextView,
        tags=["sessions"],
    )
    def clear_session_context(session_id: str) -> ContextView:
        try:
            return ContextView(**service.clear_context(session_id))
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.post(
        "/v1/sessions/{session_id}/chat/clear",
        response_model=SessionView,
        tags=["sessions"],
    )
    def clear_session_chat(session_id: str, request: Request) -> SessionView:
        """清空聊天记录与上下文（文件、Skill 挂载保留）。"""
        try:
            service.clear_chat(session_id)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        view = _session_view(get_session(session_id))
        record = store.session_by_id(session_id)
        view.model_override_id = (record or {}).get("model_override_id")
        return view

    @app.post(
        "/v1/sessions/{session_id}/clone",
        response_model=SessionView,
        status_code=201,
        tags=["sessions"],
    )
    def clone_session(session_id: str, request: Request) -> SessionView:
        """复制会话：文件目录、当前上下文、聊天记录与 Skill 挂载全部带走。"""
        try:
            state = service.clone_session(session_id, request.state.user["id"])
        except KeyError as exc:
            raise HTTPException(404, "Session 不存在或无权访问") from exc
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        view = _session_view(state)
        record = store.session_by_id(state.id)
        view.model_override_id = (record or {}).get("model_override_id")
        return view

    @app.get("/v1/sessions/{session_id}", response_model=SessionView, tags=["sessions"])
    def read_session(session_id: str) -> SessionView:
        view = _session_view(get_session(session_id))
        record = store.session_by_id(session_id)
        view.model_override_id = (record or {}).get("model_override_id")
        return view

    @app.post(
        "/v1/sessions/{session_id}/runs",
        response_model=RunView,
        status_code=202,
        tags=["runs"],
    )
    def create_run(session_id: str, payload: RunCreate) -> RunView:
        get_session(session_id)
        try:
            run = service.create_run(session_id, payload.input, payload.attachments)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        return _run_view(run, service)

    @app.get("/v1/runs/{run_id}", response_model=RunView, tags=["runs"])
    def read_run(run_id: str, request: Request) -> RunView:
        run = get_run(run_id)
        if store.session(run.session_id, request.state.user["id"]) is None:
            raise HTTPException(404, "Run 不存在或无权访问")
        return _run_view(run, service)

    @app.get(
        "/v1/sessions/{session_id}/active-run",
        response_model=RunView | None,
        tags=["runs"],
    )
    def active_run(session_id: str) -> RunView | None:
        run = service.active_run(session_id)
        return _run_view(run, service) if run else None

    @app.post("/v1/runs/{run_id}/cancel", response_model=RunView, tags=["runs"])
    def cancel_run(run_id: str, request: Request) -> RunView:
        run = get_run(run_id)
        if store.session(run.session_id, request.state.user["id"]) is None:
            raise HTTPException(404, "Run 不存在或无权访问")
        return _run_view(service.cancel_run(run_id), service)

    @app.get("/v1/runs/{run_id}/events", tags=["runs"])
    async def stream_events(
        run_id: str,
        request: Request,
        last_event_id: int | None = Header(default=None, alias="Last-Event-ID"),
        after: int = Query(default=0, ge=0),
    ) -> StreamingResponse:
        run = get_run(run_id)
        if store.session(run.session_id, request.state.user["id"]) is None:
            raise HTTPException(404, "Run 不存在或无权访问")
        cursor = last_event_id if last_event_id is not None else after

        async def generate():
            nonlocal cursor
            while True:
                if await request.is_disconnected():
                    return
                events = run.events_after(cursor)
                for event in events:
                    cursor = event["id"]

                    def web_value(value):
                        if isinstance(value, str):
                            return service.web_text(run.session_id, value)
                        if isinstance(value, list):
                            return [web_value(item) for item in value]
                        if isinstance(value, dict):
                            return {key: web_value(item) for key, item in value.items()}
                        return value

                    payload = json.dumps(web_value(event), ensure_ascii=False)
                    yield f"id: {event['id']}\nevent: {event['type']}\ndata: {payload}\n\n"
                if run.status in {"completed", "failed", "cancelled"} and not run.events_after(cursor):
                    return
                yield ": keep-alive\n\n"
                await asyncio.sleep(0.25)

        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.post(
        "/v1/sessions/{session_id}/files",
        response_model=FileView,
        status_code=201,
        tags=["files"],
    )
    async def upload_file(
        session_id: str, request: Request, filename: str = Query(min_length=1)
    ) -> FileView:
        get_session(session_id)
        content = await request.body()
        if not content:
            raise HTTPException(400, "文件内容不能为空")
        try:
            file_id, path = service.save_file(session_id, filename, content)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        return FileView(id=file_id, filename=Path(filename).name, size=path.stat().st_size)

    @app.post(
        "/v1/sessions/{session_id}/files/from-workspace",
        response_model=FileView,
        status_code=201,
        tags=["files"],
    )
    def attach_workspace_file(
        session_id: str, payload: WorkspaceAttachmentCreate
    ) -> FileView:
        get_session(session_id)
        try:
            file_id, path = service.attach_workspace_file(session_id, payload.path)
        except ValueError as exc:
            raise HTTPException(403, str(exc)) from exc
        except FileNotFoundError as exc:
            raise HTTPException(404, f"文件不存在：{payload.path}") from exc
        return FileView(id=file_id, filename=path.name, size=path.stat().st_size)

    @app.get(
        "/v1/sessions/{session_id}/artifacts",
        response_model=list[ArtifactView],
        tags=["artifacts"],
    )
    def list_artifacts(session_id: str) -> list[ArtifactView]:
        get_session(session_id)
        return [ArtifactView(**{k: v for k, v in item.items() if not k.startswith("_")})
                for item in service.artifacts(session_id)]

    @app.get(
        "/v1/sessions/{session_id}/artifacts/{artifact_id}/content",
        tags=["artifacts"],
    )
    def download_artifact(session_id: str, artifact_id: str):
        get_session(session_id)
        try:
            path, media_type = service.artifact(session_id, artifact_id)
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from exc
        return FileResponse(path, media_type=media_type, filename=path.name)

    # ---------- One-shot 代理调用 API（外部 Agent 集成） ----------
    # 用途：外部程序化调用（如同事的截图 Agent 借用质检能力）。
    # 创建会话 → 存文件 → 挂 Skill → 起任务，一次请求完成；
    # 轮询状态接口拿最终回复与产物下载地址。
    # 权限遵循现有登录态：Bearer/Cookie 均可（走 authenticate_request 中间件）。

    @app.post(
        "/v1/proxy/sessions",
        response_model=ProxySessionView,
        status_code=201,
        tags=["proxy"],
    )
    async def create_proxy_session(request: Request) -> ProxySessionView:
        """一步创建会话并启动任务。

       multipart/form-data 字段：
        - prompt: str（必填）发给 Agent 的指令
        - skill: str（可选）要挂载的技能包名（须在 default_skills 或服务器 skills/ 中）
        - files: list[UploadFile]（可选）随任务附带的文件（zip/png/md…），存入 workspace
        """
        user = request.state.user
        if user is None:
            raise HTTPException(401, "请先登录")
        form = await request.form()
        prompt = str(form.get("prompt") or "").strip()
        if not prompt:
            raise HTTPException(400, "prompt 不能为空")
        skill_name = str(form.get("skill") or "").strip()

        session = service.create_session(user_id=user["id"], title=prompt[:28] or "API 调用")

        # 可选：挂载指定 Skill（写入 client/skills/ 并注册资源）
        if skill_name:
            content = None
            for item in store.default_skills():
                if item["name"] == skill_name:
                    content = item["content"]
                    break
            if content is None:
                lib_dir = service._skills_library_dir()
                lib_file = lib_dir / f"{skill_name}.md"
                if lib_file.is_file():
                    content = lib_file.read_text(encoding="utf-8")
            if content is None:
                raise HTTPException(404, f"Skill 不存在：{skill_name}")
            from ..skillpacks import parse_skill_pack_text

            dest = session.root / "client" / "skills" / f"{skill_name}.md"
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(content, encoding="utf-8")
            if parse_skill_pack_text(content) is not None:
                session.mounted_resources["skills"].add(dest.name)
                store.set_resource_mount(session.id, "skills", dest.name, True)

        # 保存上传文件到 workspace
        saved_paths: list[str] = []
        for upload in form.getlist("files"):
            data = await upload.read()
            if not data:
                continue
            try:
                saved = service.save_workspace_file(
                    session.id, upload.filename or "upload.bin", data
                )
            except ValueError as exc:
                raise HTTPException(400, str(exc)) from exc
            saved_paths.append(saved.relative_to(session.root).as_posix())

        file_note = (
            "\n\n随任务附带的文件（已存入 workspace）：\n" + "\n".join(saved_paths)
            if saved_paths else ""
        )
        try:
            run = service.create_run(session.id, prompt + file_note, [])
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        return ProxySessionView(
            session_id=session.id,
            run_id=run.id,
            skill=skill_name or None,
            files=saved_paths,
        )

    @app.get("/v1/proxy/sessions/{session_id}", response_model=ProxyStatusView, tags=["proxy"])
    def proxy_session_status(session_id: str, request: Request) -> ProxyStatusView:
        """查询任务状态。

        - running：progress 给出当前阶段（最近工具调用/推理中）
        - completed：reply 为文字结论；result 内联 qc-report.json 的结构化结果；
          artifacts 只列交付物（qc-report-*.zip/html/json），中间产物不列。
        """
        session = get_session(session_id)
        # 状态判定：优先活跃 Run；否则看最后一条 assistant 消息是否存在
        active = service.active_run(session_id)
        last_run = session.active_run_holder["run"]
        if active is not None:
            run_status, run_id = active.status, active.id
        elif last_run is not None:
            run_status, run_id = last_run.status, last_run.id
        else:
            run_status, run_id = "unknown", None
        reply = ""
        messages = store.messages(session_id)
        if run_status in {"completed", "unknown"}:
            for m in reversed(messages):
                if m["role"] == "assistant":
                    reply = service.web_text(session_id, m["content"] or "") or ""
                    break
            if run_status == "unknown" and reply:
                run_status = "completed"
        # 阶段信息：running 时从最近工具事件提取
        progress = ""
        if run_status in {"queued", "running"}:
            events = store.tool_events(session_id)
            if events:
                last = events[-1]
                tool = last.get("name", "")
                if tool == "image_reasoning":
                    progress = "正在图像推理（视觉模型分析图片）"
                elif tool == "delegate_task":
                    progress = "已派发子 Agent 处理"
                elif tool == "run_skill_script":
                    progress = "正在渲染质检报告"
                elif tool in {"read_pack_file", "read_document", "list_dir", "find_files", "grep_files"}:
                    progress = f"正在读取资料（{tool}）"
                elif tool in {"write_file", "write_working_doc"}:
                    progress = "正在落盘中间结论"
                elif tool == "archive_tool":
                    progress = "正在解压压缩包"
                else:
                    progress = f"正在调用 {tool}"
            else:
                progress = "模型推理中"
        # 结构化结果：completed 时内联 qc-report.json
        result = None
        if run_status == "completed":
            for p in sorted((session.root / "generate").glob("qc-report*.json"),
                            key=lambda x: x.stat().st_mtime, reverse=True):
                try:
                    result = json.loads(p.read_text(encoding="utf-8"))
                    break
                except (json.JSONDecodeError, UnicodeDecodeError):
                    continue
        # 产物只列交付物（报告三件套），中间产物不列
        artifacts = [
            ArtifactView(**{k: v for k, v in item.items() if not k.startswith("_")})
            for item in service.artifacts(session_id)
            if re.search(r"generate/qc-report[^/]*\.(zip|html|json)$", item["name"])
        ]
        return ProxyStatusView(
            session_id=session_id,
            run_id=run_id,
            status=run_status,
            reply=reply,
            progress=progress,
            result=result,
            artifacts=artifacts,
        )

    return app
