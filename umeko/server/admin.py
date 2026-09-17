"""管理面（L3）：独立 FastAPI app，仅监听管理端口，与用户面完全分离。

用户面 app 中不存在任何 /admin 路由——隐藏靠的是端口分离 + 回环/内网绑定，
而不是藏路径。管理页资源与 API 只由本 app 提供。

功能：用户管理（列表/新建/重置密码/角色/删除）、Session 管理（按用户列出/
删除，含内存态驱逐）、Provider/Model 配置（DB 覆盖层，改后驱逐全部在线
Session 即时生效）。
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

from ..config import Settings
from ..host.service import AgentService
from ..host.storage import Store
from ..runtime import app_dir
from ..skillpacks import parse_skill_pack_text

ADMIN_COOKIE = "umeko_admin"
STATIC_DIR = Path(__file__).parent / "static"
SECRET_MASK = "********"


class _Login(BaseModel):
    username: str
    password: str


class _UserCreate(BaseModel):
    username: str
    password: str
    role: str = "user"


class _PasswordSet(BaseModel):
    password: str


class _RoleSet(BaseModel):
    role: str


class _DefaultSkillIn(BaseModel):
    content: str = Field(min_length=1, max_length=200_000)


class _ProviderIn(BaseModel):
    name: str
    base_url: str
    api_key: str
    proxy: str | None = None


class _ProviderPatch(BaseModel):
    name: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    proxy: str | None = None


class _ModelIn(BaseModel):
    name: str
    vision: bool = False


class _ModelPatch(BaseModel):
    name: str | None = None
    vision: bool | None = None


class _ActiveModelIn(BaseModel):
    model_id: str


class _ImportIn(BaseModel):
    document: dict


def create_admin_app(settings: Settings, service: AgentService, store: Store) -> FastAPI:
    app = FastAPI(
        title="Umeko Admin",
        docs_url=None, redoc_url=None, openapi_url=None,  # 不暴露任何 API 文档
    )

    @app.middleware("http")
    async def authenticate_admin(request: Request, call_next):
        path = request.url.path
        if path.startswith("/admin/v1/"):
            user = store.user_for_token(request.cookies.get(ADMIN_COOKIE))
            if user is None or user.get("role") != "admin":
                return JSONResponse({"detail": "需要管理员登录"}, status_code=401)
            request.state.admin = user
        return await call_next(request)

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    def admin_page() -> HTMLResponse:
        return HTMLResponse((STATIC_DIR / "admin.html").read_text(encoding="utf-8"))

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok", "role": "admin"}

    @app.post("/admin/login")
    def login(payload: _Login, response: Response) -> dict:
        user = store.authenticate(payload.username, payload.password)
        if user is None or user.get("role") != "admin":
            raise HTTPException(401, "用户名或密码错误，或该账号不是管理员")
        response.set_cookie(
            ADMIN_COOKIE, store.issue_token(user["id"]),
            httponly=True, samesite="lax", secure=False, max_age=7 * 86400,
        )
        return {"id": user["id"], "username": user["username"]}

    @app.post("/admin/logout", status_code=204)
    def logout(request: Request, response: Response) -> None:
        store.revoke_token(request.cookies.get(ADMIN_COOKIE))
        response.delete_cookie(ADMIN_COOKIE)

    # ---------- 用户管理 ----------

    @app.get("/admin/v1/me")
    def me(request: Request) -> dict:
        return request.state.admin

    @app.get("/admin/v1/users")
    def users() -> list[dict]:
        return store.list_users()

    @app.post("/admin/v1/users", status_code=201)
    def create_user(payload: _UserCreate) -> dict:
        try:
            return store.create_user(payload.username, payload.password, payload.role)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.put("/admin/v1/users/{user_id}/password", status_code=204)
    def set_password(user_id: str, payload: _PasswordSet) -> None:
        try:
            store.set_password(user_id, payload.password)
        except KeyError as exc:
            raise HTTPException(404, "用户不存在") from exc
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.put("/admin/v1/users/{user_id}/role", status_code=204)
    def set_role(user_id: str, payload: _RoleSet) -> None:
        try:
            store.set_role(user_id, payload.role)
        except KeyError as exc:
            raise HTTPException(404, "用户不存在") from exc
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.delete("/admin/v1/users/{user_id}", status_code=204)
    def delete_user(user_id: str) -> None:
        try:
            service.delete_user_admin(user_id)
        except KeyError as exc:
            raise HTTPException(404, "用户不存在") from exc
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    # ---------- Session 管理 ----------

    @app.get("/admin/v1/users/{user_id}/sessions")
    def user_sessions(user_id: str) -> list[dict]:
        return service.admin_sessions(user_id)

    @app.delete("/admin/v1/sessions/{session_id}", status_code=204)
    def delete_session(session_id: str) -> None:
        try:
            service.delete_session_admin(session_id)
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from exc

    @app.post("/admin/v1/sessions/{session_id}/evict")
    def evict_session(session_id: str) -> dict:
        return {"evicted": service.evict_session(session_id)}

    # ---------- Provider / Model 注册表 ----------

    def _provider_view(p: dict, active_model_id: str | None) -> dict:
        return {
            "id": p["id"], "name": p["name"], "base_url": p["base_url"],
            "proxy": p["proxy"], "api_key": p["api_key"],  # 管理员可见完整 key
            "api_key_set": bool(p["api_key"]),
            "models": [
                {**m, "active": m["id"] == active_model_id} for m in p["models"]
            ],
        }

    @app.get("/admin/v1/providers")
    def list_providers() -> dict:
        active = store.active_model()
        active_id = active["model_id"] if active else None
        return {
            "providers": [
                _provider_view(p, active_id) for p in store.list_providers()
            ],
            "active_model_id": active_id,
            "effective": {
                "text_model": service.settings.text_model.name,
                "text_model_vision": service.settings.text_model_vision,
                "vision_model": (
                    service.settings.vision_model.name
                    if service.settings.vision_model else None
                ),
            },
        }

    @app.post("/admin/v1/providers", status_code=201)
    def create_provider(payload: _ProviderIn) -> dict:
        try:
            return store.create_provider(
                payload.name, payload.base_url, payload.api_key, payload.proxy
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.put("/admin/v1/providers/{provider_id}", status_code=204)
    def update_provider(provider_id: str, payload: _ProviderPatch) -> None:
        fields = payload.model_dump(exclude_none=True)
        if fields.get("api_key") == SECRET_MASK:
            fields.pop("api_key")  # 掩码原样提交 = 不修改
        try:
            store.update_provider(provider_id, **fields)
        except KeyError as exc:
            raise HTTPException(404, "Provider 不存在") from exc

    @app.delete("/admin/v1/providers/{provider_id}", status_code=204)
    def delete_provider(provider_id: str) -> None:
        try:
            store.delete_provider(provider_id)
        except KeyError as exc:
            raise HTTPException(404, "Provider 不存在") from exc

    @app.post("/admin/v1/providers/{provider_id}/models", status_code=201)
    def add_model(provider_id: str, payload: _ModelIn) -> dict:
        try:
            return store.add_model(provider_id, payload.name, payload.vision)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.put("/admin/v1/models/{model_id}", status_code=204)
    def update_model(model_id: str, payload: _ModelPatch) -> None:
        try:
            store.update_model(model_id, **payload.model_dump(exclude_none=True))
        except KeyError as exc:
            raise HTTPException(404, "模型不存在") from exc

    @app.delete("/admin/v1/models/{model_id}", status_code=204)
    def delete_model(model_id: str) -> None:
        try:
            store.delete_model(model_id)
        except KeyError as exc:
            raise HTTPException(404, "模型不存在") from exc

    @app.put("/admin/v1/active-model")
    def activate_model(payload: _ActiveModelIn) -> dict:
        """设为当前模型并全员生效（驱逐全部在线 Session）。"""
        try:
            store.set_active_model(payload.model_id)
        except KeyError as exc:
            raise HTTPException(404, "模型不存在") from exc
        return service.reload_config()

    @app.post("/admin/v1/providers/import")
    def import_providers(payload: _ImportIn) -> dict:
        """粘贴 JSON 批量导入；带 active 字段时一并激活并全员生效。"""
        try:
            result = store.import_providers(payload.document)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        if result.get("activated"):
            result["applied"] = service.reload_config()
        return result

    # ---------- 默认 Skill（管理员下发，出现在用户的 Skills 列表） ----------

    @app.get("/admin/v1/default-skills")
    def list_default_skills() -> dict:
        db_names = {item["name"] for item in store.default_skills()}
        # 服务器 skills/ 目录（仓库自带的技能库源文件）：管理员可一键导入，
        # 但不自动下发——是否给用户由管理员决定。
        library = []
        lib_dir = app_dir() / "skills"
        if lib_dir.is_dir():
            for f in sorted(lib_dir.glob("*.md")):
                try:
                    text = f.read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError):
                    continue
                if parse_skill_pack_text(text) is None:
                    continue
                library.append({
                    "name": f.name,
                    "size": len(text),
                    "imported": f.name in db_names,
                })
        return {
            "skills": [
                {"name": item["name"], "updated_at": item["updated_at"],
                 "size": len(item["content"]), "enabled": bool(item["enabled"])}
                for item in store.default_skills()
            ],
            "library": library,
        }

    @app.post("/admin/v1/default-skills/{name}/toggle")
    def toggle_default_skill(name: str) -> dict:
        """停用/启用：停用后不再下发到新 Session（已播种的不撤回）。"""
        content = store.default_skill(name)
        if content is None:
            raise HTTPException(404, "默认 Skill 不存在")
        current = next(
            (s for s in store.default_skills() if s["name"] == name), None
        )
        enabled = not (current["enabled"] if current else False)
        store.set_default_skill_enabled(name, enabled)
        return {"name": name, "enabled": enabled}

    @app.post("/admin/v1/default-skills/import/{name}", status_code=201)
    def import_default_skill(name: str) -> dict:
        """把服务器 skills/ 目录中的技能文件导入默认 Skill（导入后新 Session 生效）。"""
        clean = Path(name).name
        if clean != name or not clean.endswith(".md"):
            raise HTTPException(400, "名称必须是 xxx.md 形式（不带路径）")
        source = app_dir() / "skills" / clean
        if not source.is_file():
            raise HTTPException(404, f"技能库中不存在：{clean}")
        content = source.read_text(encoding="utf-8")
        try:
            service._validate_resource(content)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        store.upsert_default_skill(clean, content)
        return {"name": clean, "imported": True}

    @app.get("/admin/v1/default-skills/{name}")
    def get_default_skill(name: str) -> dict:
        content = store.default_skill(name)
        if content is None:
            raise HTTPException(404, "默认 Skill 不存在")
        return {"name": name, "content": content}

    @app.put("/admin/v1/default-skills/{name}", status_code=201)
    def upload_default_skill(name: str, payload: _DefaultSkillIn) -> dict:
        """上传/更新默认 Skill；对新 Session 生效（在线 Session 不回填）。"""
        clean = Path(name).name
        if not clean.endswith(".md") or clean != name or "/" in name or "\\" in name:
            raise HTTPException(400, "名称必须是 xxx.md 形式（不带路径）")
        try:
            service._validate_resource(payload.content)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        store.upsert_default_skill(name, payload.content)
        return {"name": name, "updated": True}

    @app.delete("/admin/v1/default-skills/{name}", status_code=204)
    def delete_default_skill(name: str) -> None:
        store.delete_default_skill(name)

    return app
