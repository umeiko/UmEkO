"""Web、CLI 与本地宿主共享的 Provider 配置解析与旧配置迁移。"""
from __future__ import annotations

import uuid
from dataclasses import replace

from ..config import ModelConfig, Settings, apply_overrides
from .storage import Store, _now

LEGACY_MODEL_KEYS = frozenset({
    "TEXT_MODEL_NAME", "TEXT_MODEL_API_KEY", "TEXT_MODEL_BASE_URL", "TEXT_MODEL_VISION",
    "VISION_MODEL_NAME", "VISION_MODEL_API_KEY", "VISION_MODEL_BASE_URL", "MODEL_PROXY",
})


def model_from_row(row: dict, defaults: ModelConfig) -> ModelConfig:
    return ModelConfig(row["model"], row["api_key"], row["base_url"],
                       proxy=row["proxy"] or None, ca_file=defaults.ca_file,
                       model_id=row.get("model_id"),
                       max_concurrent_requests=row.get("max_concurrent_requests", 0))


def deployment_defaults(settings: Settings) -> Settings:
    """加载自注册表的凭据不能成为删除 Provider 后的隐藏回退配置。"""
    if not settings.registry_managed:
        return settings  # 保留进程内显式注入 ModelConfig 的核心 API。
    return replace(settings, text_model=ModelConfig(
        "unconfigured", "", "https://invalid.unconfigured", ca_file=settings.text_model.ca_file
    ), vision_model=None, sub_model=None, text_model_vision=False, sub_model_vision=False)


def resolve_provider_settings(settings: Settings, store: Store) -> Settings:
    settings = apply_overrides(deployment_defaults(settings), store.config())
    active = store.active_model()
    if active is None:
        return settings
    text_model = model_from_row(active, settings.text_model)
    fallback = None if active["vision"] else store.first_vision_model(active["provider_id"])
    return replace(settings, text_model=text_model, text_model_vision=bool(active["vision"]),
                   vision_model=model_from_row(fallback, text_model) if fallback else None)


def migrate_legacy_models(store: Store, values: dict) -> int:
    """原子导入旧模型配置：按凭据复用 Provider，不覆盖既有凭据或激活选择。

    调用方只在成功后删除旧 .env 项；此函数也清除旧 DB 模型覆盖项。
    """
    values = {**values, **{k: v for k, v in store.config().items() if k in LEGACY_MODEL_KEYS}}
    models = []
    for role, vision in (("TEXT", False), ("VISION", True)):
        name, key, url = (str(values.get(f"{role}_MODEL_{suffix}") or "").strip()
                          for suffix in ("NAME", "API_KEY", "BASE_URL"))
        if not any((name, key, url)):
            continue
        if not all((name, key, url)):
            raise RuntimeError(f"旧 {role}_MODEL 配置不完整，迁移前请补全 NAME、API_KEY、BASE_URL")
        if role == "TEXT":
            vision = str(values.get("TEXT_MODEL_VISION", "")).lower() in {"1", "true", "yes"}
        models.append((role, name, key, url, vision))
    if not models:
        return 0
    proxy = str(values.get("MODEL_PROXY") or "").strip() or None
    with store.connect() as db:
        for role, name, key, url, vision in models:
            provider = db.execute(
                "SELECT id FROM providers WHERE base_url=? AND api_key=? AND COALESCE(proxy,'')=?",
                (url, key, proxy or ""),
            ).fetchone()
            if provider:
                pid = provider["id"]
            else:
                label = "legacy-env" if role == "TEXT" else "legacy-env-vision"
                candidate, suffix = label, 1
                while db.execute("SELECT id FROM providers WHERE name=?", (candidate,)).fetchone():
                    suffix += 1
                    candidate = f"{label}-{suffix}"
                pid = f"prv_{uuid.uuid4().hex}"
                db.execute("INSERT INTO providers VALUES (?,?,?,?,?,?)",
                           (pid, candidate, url, key, proxy, _now()))
            model = db.execute("SELECT id FROM provider_models WHERE provider_id=? AND name=?", (pid, name)).fetchone()
            mid = model["id"] if model else f"mdl_{uuid.uuid4().hex}"
            if not model:
                db.execute("INSERT INTO provider_models (id,provider_id,name,vision,created_at) VALUES (?,?,?,?,?)",
                           (mid, pid, name, int(vision), _now()))
            if role == "TEXT":
                db.execute("INSERT OR IGNORE INTO app_config VALUES ('ACTIVE_MODEL_ID', ?, ?)", (mid, _now()))
        db.executemany("DELETE FROM app_config WHERE key=?", [(k,) for k in LEGACY_MODEL_KEYS])
    return len(models)
