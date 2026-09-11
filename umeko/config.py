"""配置加载：dotenv 读取文本模型与多模态模型的独立 API 配置。

基座只保留通用项：双模型配置、上下文窗口、子 Agent 回合上限。
领域配置（渲染、引擎、领域开关等）由各领域项目在自己的 Settings 中扩展。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, replace
from pathlib import Path

from dotenv import load_dotenv

from . import runtime


@dataclass(frozen=True)
class ModelConfig:
    """单个模型的 OpenAI 兼容 API 配置。"""

    name: str
    api_key: str
    base_url: str
    # 模型 API 代理。None 表示直连；LLM 客户端始终忽略系统代理环境变量。
    proxy: str | None = None


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


def _require(key: str) -> str:
    value = os.getenv(key)
    if not value:
        raise RuntimeError(
            f"缺少环境变量 {key}，请复制 .env.example 为 .env 并填写配置。"
        )
    return value


def _load_vision_model(proxy: str | None = None) -> ModelConfig | None:
    """视觉模型可选：三项配置齐全才加载，否则返回 None。"""
    name = os.getenv("VISION_MODEL_NAME")
    api_key = os.getenv("VISION_MODEL_API_KEY")
    base_url = os.getenv("VISION_MODEL_BASE_URL")
    if name and api_key and base_url:
        return ModelConfig(name=name, api_key=api_key, base_url=base_url, proxy=proxy)
    return None


def load_settings(env_path: str | Path | None = None) -> Settings:
    if env_path is None:
        # 冻结（离线包）时优先读 exe 旁边的 .env，其次 CWD；源码运行维持 ./.env
        candidates = (
            [runtime.app_dir() / ".env", Path(".env")]
            if runtime.is_frozen()
            else [Path(".env")]
        )
        env_path = next((p for p in candidates if p.is_file()), candidates[-1])
    load_dotenv(env_path)
    model_proxy = (os.getenv("MODEL_PROXY") or "").strip() or None
    return Settings(
        text_model=ModelConfig(
            name=_require("TEXT_MODEL_NAME"),
            api_key=_require("TEXT_MODEL_API_KEY"),
            base_url=_require("TEXT_MODEL_BASE_URL"),
            proxy=model_proxy,
        ),
        context_window=max(1, int(os.getenv("TEXT_MODEL_CONTEXT_WINDOW", "128000"))),
        vision_model=_load_vision_model(model_proxy),
        text_model_vision=os.getenv("TEXT_MODEL_VISION", "").lower()
        in ("1", "true", "yes"),
        max_subagent_tool_iterations=max(
            1, int(os.getenv("MAX_SUBAGENT_TOOL_ITERATIONS", "24"))
        ),
        max_tool_iterations=max(1, int(os.getenv("MAX_TOOL_ITERATIONS", "8"))),
    )


# ---- 管理面可在线修改的配置键（存 Store.app_config，优先级高于 .env） ----

CONFIGURABLE_KEYS = (
    "TEXT_MODEL_NAME", "TEXT_MODEL_API_KEY", "TEXT_MODEL_BASE_URL",
    "TEXT_MODEL_VISION", "TEXT_MODEL_CONTEXT_WINDOW",
    "VISION_MODEL_NAME", "VISION_MODEL_API_KEY", "VISION_MODEL_BASE_URL",
    "MODEL_PROXY",
)
SECRET_KEYS = frozenset({"TEXT_MODEL_API_KEY", "VISION_MODEL_API_KEY"})


def apply_overrides(settings: Settings, overrides: dict[str, str]) -> Settings:
    """把 DB 覆盖层应用到 Settings（frozen dataclass，返回新实例）。

    视觉模型三项必须齐全才生效；覆盖不完整时保持原状，避免半个配置把
    在线服务打挂。
    """
    o = {
        k: str(v).strip()
        for k, v in overrides.items()
        if k in CONFIGURABLE_KEYS and str(v).strip()
    }
    if not o:
        return settings
    proxy = o.get("MODEL_PROXY", settings.text_model.proxy)
    text_model = replace(
        settings.text_model,
        name=o.get("TEXT_MODEL_NAME", settings.text_model.name),
        api_key=o.get("TEXT_MODEL_API_KEY", settings.text_model.api_key),
        base_url=o.get("TEXT_MODEL_BASE_URL", settings.text_model.base_url),
        proxy=proxy,
    )
    vision = settings.vision_model
    v_name = o.get("VISION_MODEL_NAME", vision.name if vision else None)
    v_key = o.get("VISION_MODEL_API_KEY", vision.api_key if vision else None)
    v_url = o.get("VISION_MODEL_BASE_URL", vision.base_url if vision else None)
    if v_name and v_key and v_url:
        vision = ModelConfig(name=v_name, api_key=v_key, base_url=v_url, proxy=proxy)
    try:
        context_window = int(o.get("TEXT_MODEL_CONTEXT_WINDOW", settings.context_window))
    except (TypeError, ValueError):
        context_window = settings.context_window
    vision_flag = o.get("TEXT_MODEL_VISION")
    return replace(
        settings,
        text_model=text_model,
        vision_model=vision,
        context_window=max(1, context_window),
        text_model_vision=(
            settings.text_model_vision
            if vision_flag is None
            else vision_flag.lower() in ("1", "true", "yes")
        ),
    )
