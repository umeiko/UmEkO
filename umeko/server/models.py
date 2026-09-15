from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class SessionCreate(BaseModel):
    """通用基座的 Session 没有领域配置；保留模型以便未来扩展。"""


class SessionView(BaseModel):
    id: str
    created_at: str
    title: str = "未命名会话"
    model_override_id: str | None = None


class ModelPrefsIn(BaseModel):
    """用户角色级模型偏好；None = 跟随默认（管理员配置的当前模型）。"""

    main_model_id: str | None = None
    sub_model_id: str | None = None
    vision_model_id: str | None = None


class SessionModelIn(BaseModel):
    """会话级主模型覆盖；None = 清除覆盖。"""

    model_id: str | None = None


class AuthInput(BaseModel):
    username: str = Field(min_length=3, max_length=80)
    password: str = Field(min_length=8, max_length=256)


class UserView(BaseModel):
    id: str
    username: str
    avatar_url: str | None = None


class ContextView(BaseModel):
    used_tokens: int
    message_tokens: int
    tool_tokens: int
    limit_tokens: int
    # True = used_tokens 以供应商 usage.prompt_tokens 为锚（精确口径）
    exact: bool = False
    percent: float
    message_count: int
    compressed: bool = False
    before_tokens: int | None = None
    reason: str | None = None
    cleared: bool = False


class SessionTitlePatch(BaseModel):
    title: str = Field(min_length=1, max_length=80)


class MessageView(BaseModel):
    role: Literal["user", "assistant"]
    content: str
    attachments: list[str] = Field(default_factory=list)
    created_at: str


class ToolEventView(BaseModel):
    agent: str = "main"
    name: str
    arguments: str | None = None
    result: str | None = None
    created_at: str


class RunCreate(BaseModel):
    input: str = Field(min_length=1)
    attachments: list[str] = Field(default_factory=list)


class RunView(BaseModel):
    id: str
    session_id: str
    status: Literal["queued", "running", "cancelling", "completed", "failed", "cancelled"]
    created_at: str
    completed_at: str | None = None
    reply: str | None = None
    error: str | None = None


class EventView(BaseModel):
    id: int
    run_id: str
    session_id: str
    type: str
    timestamp: str
    data: dict[str, Any]


class FileView(BaseModel):
    id: str
    filename: str
    size: int


class WorkspaceFileView(BaseModel):
    path: str
    filename: str
    size: int


class WorkspaceAttachmentCreate(BaseModel):
    path: str = Field(min_length=1)


class WorkspaceEntryCreate(BaseModel):
    path: str = Field(min_length=1, max_length=500)
    type: Literal["file", "directory"]


class WorkspaceTransfer(BaseModel):
    source: str = Field(min_length=1, max_length=500)
    target: str = Field(min_length=1, max_length=500)
    operation: Literal["copy", "move"]


class WorkspaceExtract(BaseModel):
    path: str = Field(min_length=1, max_length=500)


class ArtifactView(BaseModel):
    id: str
    name: str
    kind: str
    size: int
    download_url: str


class WorkspaceNode(BaseModel):
    name: str
    path: str
    type: Literal["directory", "file"]
    size: int | None = None
    children: list["WorkspaceNode"] = Field(default_factory=list)
    truncated: bool = False
    virtual: bool = False


class ClientResourceView(BaseModel):
    kind: Literal["skills"]
    name: str
    mounted: bool
    builtin: bool
    content: str | None = None


class ClientResourceUpdate(BaseModel):
    content: str | None = None
    mounted: bool | None = None


class ClientResourceGenerate(BaseModel):
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
