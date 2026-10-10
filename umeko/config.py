"""部署配置从 dotenv 加载，模型配置从共享 Provider 注册表解析。

基座只保留通用项：双模型配置、上下文窗口、子 Agent 回合上限。
领域配置（渲染、引擎、领域开关等）由各领域项目在自己的 Settings 中扩展。
"""

from __future__ import annotations

import os
import re
import ssl
from dataclasses import dataclass, replace
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import dotenv_values, load_dotenv

from . import runtime


@dataclass(frozen=True)
class ModelConfig:
    """单个模型的 OpenAI 兼容 API 配置。"""

    name: str
    api_key: str
    base_url: str
    # 模型 API 代理。None 表示直连；LLM 客户端始终忽略系统代理环境变量。
    proxy: str | None = None
    # 在默认信任库之外追加的公司 CA（PEM）；不关闭证书校验。
    ca_file: str | None = None
    # 注册表模型 ID：同一模型的所有客户端共用并发额度；0 表示不限制。
    model_id: str | None = None
    max_concurrent_requests: int = 0


@dataclass(frozen=True)
class Settings:
    text_model: ModelConfig
    # 主 Agent 上下文窗口，用于 UI 占用估算与压缩提示。不同兼容端点无法统一
    # 返回精确 tokenizer 结果，因此这里只作为容量参考，不参与供应商计费。
    context_window: int = 128000
    # 多模态（视觉）模型；None = 未配置——image_reasoning/ocr_image 工具不可用
    vision_model: ModelConfig | None = None
    text_model_vision: bool = False  # 文本（主）模型是否具备原生多模态能力
    # 子 Agent（文件子 Agent / Skill 生成 Agent）独立模型；None = 跟随主模型。
    # 由用户级模型偏好解析得出，不来自 .env。
    sub_model: ModelConfig | None = None
    sub_model_vision: bool = False  # 子 Agent 模型是否具备原生多模态能力
    # 文件子 Agent 允许的 function-calling 回合数；一回合可包含多个工具调用。
    # 图片质检在部分兼容端点上会退化为每回合只调用一个工具，因此默认高于主 Agent。
    max_subagent_tool_iterations: int = 24
    # 主 Agent 单次请求允许的 function-calling 回合数
    max_tool_iterations: int = 8
    # 浏览器入口路径；空字符串表示部署在域名根目录。修改后重启。
    base_path: str = ""
    data_root: str = "server_data"
    # load_settings 使用持久化 Provider；直接构造 Settings 仍支持显式注入模型。
    registry_managed: bool = False
    public_url: str = ""
    task_workers: int = 4
    task_queue_limit: int = 100
    task_caller_limit: int = 20
    task_retention_seconds: int = 86400
    task_timeout_seconds: int = 3600
    # 管理面独立入口前缀；不继承用户面的 base_path。留空表示管理端口根路径。
    admin_base_path: str = ""


def normalize_base_path(value: str, setting_name: str = "UMEKO_BASE_PATH") -> str:
    value = value.strip()
    if value in {"", "/"}:
        return ""
    value = value.rstrip("/")
    if (not re.fullmatch(r"(?:/[A-Za-z0-9._~-]+)+", value)
            or any(part in {".", ".."} for part in value.split("/"))):
        raise RuntimeError(
            f"{setting_name} 必须是 /doc-master/consistency/image-text 这样的路径，"
            "不含域名、查询参数、空格或 . / .. 路径段。"
        )
    return value


def _load_model_ca(env_path: Path) -> str | None:
    value = (os.getenv("MODEL_CA_FILE") or "").strip()
    if not value:
        return None
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = env_path.resolve().parent / path
    try:
        # 启动即报错，避免直到提问时才发现证书文件缺失或格式错误。
        ssl.create_default_context().load_verify_locations(cafile=str(path))
    except (OSError, ssl.SSLError) as exc:
        raise RuntimeError(f"MODEL_CA_FILE 无法加载 CA 证书：{path} ({exc})") from exc
    return str(path.resolve())


def normalize_public_url(value: str, base_path: str) -> str:
    value = value.strip().rstrip("/")
    if not value:
        return ""
    parsed = urlsplit(value)
    if (parsed.scheme not in {"http", "https"} or not parsed.netloc
            or parsed.username or parsed.password or parsed.query or parsed.fragment
            or parsed.path != base_path):
        raise RuntimeError("UMEKO_PUBLIC_URL 必须是外部完整服务地址，路径须与 UMEKO_BASE_PATH 一致")
    return value


def model_config_unconfigured(settings) -> bool:
    """主模型是否为占位配置（无 .env 启动）。"""
    tm = settings.text_model
    return not tm.api_key or "unconfigured" in tm.base_url


def resolve_env_path(env_path: str | Path | None = None) -> Path:
    if env_path is None:
        # 冻结（离线包）时优先读 exe 旁边的 .env，其次 CWD；源码运行维持 ./.env
        candidates = (
            [runtime.app_dir() / ".env", Path(".env")]
            if runtime.is_frozen()
            else [Path(".env")]
        )
        env_path = next((p for p in candidates if p.is_file()), candidates[-1])
    return Path(env_path)


def load_settings(env_path: str | Path | None = None, data_root: str | Path | None = None) -> Settings:
    env_path = resolve_env_path(env_path)
    load_dotenv(env_path)
    model_ca = _load_model_ca(Path(env_path))
    root = Path(data_root) if data_root is not None else Path(os.getenv("UMEKO_DATA_ROOT") or "server_data")
    if data_root is None and not root.is_absolute():
        root = Path(env_path).resolve().parent / root
    settings = Settings(
        text_model=ModelConfig("unconfigured", "", "https://invalid.unconfigured", ca_file=model_ca),
        context_window=max(1, int(os.getenv("TEXT_MODEL_CONTEXT_WINDOW", "128000"))),
        base_path=normalize_base_path(os.getenv("UMEKO_BASE_PATH", "")),
        admin_base_path=normalize_base_path(os.getenv("UMEKO_ADMIN_BASE_PATH", ""), "UMEKO_ADMIN_BASE_PATH"),
        data_root=str(root.resolve()),
        registry_managed=True,
        max_subagent_tool_iterations=max(
            1, int(os.getenv("MAX_SUBAGENT_TOOL_ITERATIONS", "24"))
        ),
        max_tool_iterations=max(1, int(os.getenv("MAX_TOOL_ITERATIONS", "32"))),
        public_url=normalize_public_url(os.getenv("UMEKO_PUBLIC_URL", ""),
                                        normalize_base_path(os.getenv("UMEKO_BASE_PATH", ""))),
        task_workers=max(1, int(os.getenv("UMEKO_TASK_WORKERS", "4"))),
        task_queue_limit=max(1, int(os.getenv("UMEKO_TASK_QUEUE_LIMIT", "100"))),
        task_caller_limit=max(1, int(os.getenv("UMEKO_TASK_CALLER_LIMIT", "20"))),
        task_retention_seconds=max(60, int(os.getenv("UMEKO_TASK_RETENTION_SECONDS", "86400"))),
        task_timeout_seconds=max(1, int(os.getenv("UMEKO_TASK_TIMEOUT_SECONDS", "3600"))),
    )
    from .host.configuration import LEGACY_MODEL_KEYS, migrate_legacy_models, resolve_provider_settings
    from .host.storage import Store

    store = Store(root / "umeko.db")
    # 旧安装首次迁移；注册表已有配置时，不再读取 .env 凭据作为运行时回退。
    if store.config().get("LEGACY_MODEL_CONFIG_MIGRATED") != "1":
        legacy = {k: os.getenv(k, v) for k, v in dotenv_values(env_path).items() if k in LEGACY_MODEL_KEYS}
        legacy.update({k: os.environ[k] for k in LEGACY_MODEL_KEYS if k in os.environ})
        migrate_legacy_models(store, legacy)
        store.set_config({"LEGACY_MODEL_CONFIG_MIGRATED": "1"})
    return resolve_provider_settings(settings, store)


# ---- 管理面可在线修改的配置键（存 Store.app_config，优先级高于 .env） ----

CONFIGURABLE_KEYS = (
    "TEXT_MODEL_CONTEXT_WINDOW", "MAX_TOOL_ITERATIONS",
)
SECRET_KEYS = frozenset()


def apply_overrides(settings: Settings, overrides: dict[str, str]) -> Settings:
    """把 DB 覆盖层应用到 Settings（frozen dataclass，返回新实例）。

    地址、密钥、代理与视觉能力仅来自 Provider 注册表。
    """
    o = {
        k: str(v).strip()
        for k, v in overrides.items()
        if k in CONFIGURABLE_KEYS and str(v).strip()
    }
    if not o:
        return settings
    try:
        context_window = int(o.get("TEXT_MODEL_CONTEXT_WINDOW", settings.context_window))
    except (TypeError, ValueError):
        context_window = settings.context_window
    result = replace(
        settings,
        context_window=max(1, context_window),
    )
    # 主 Agent 最大工具轮次：0 = 无限（管理面可配）
    mti = o.get("MAX_TOOL_ITERATIONS")
    if mti is not None:
        try:
            result = replace(result, max_tool_iterations=max(0, int(mti)))
        except ValueError:
            pass  # 非法值忽略，保持原设置
    return result
