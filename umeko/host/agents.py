"""Persistent agent definitions over one shared runtime and skill catalogue."""
from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from urllib.parse import urlsplit

from .. import __version__
from ..skillpacks import parse_skill_pack_text


class AgentRegistry:
    def __init__(self, store):
        self.store = store
        with store.connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS agent_definitions (
                id TEXT PRIMARY KEY, slug TEXT UNIQUE NOT NULL, name TEXT NOT NULL,
                enabled INTEGER NOT NULL, definition_json TEXT NOT NULL,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL)""")

    @staticmethod
    def _view(row):
        value = json.loads(row["definition_json"])
        value.setdefault("default_vision_model_id", None)
        return {**value, "id": row["id"],
                "created_at": row["created_at"], "updated_at": row["updated_at"]}

    def list(self):
        with self.store.connect() as db:
            return [self._view(row) for row in db.execute("SELECT * FROM agent_definitions ORDER BY created_at,id")]

    def get(self, agent_id):
        with self.store.connect() as db:
            row = db.execute("SELECT * FROM agent_definitions WHERE id=?", (agent_id,)).fetchone()
        if row is None:
            raise KeyError("智能体不存在")
        return self._view(row)

    def by_slug(self, slug):
        with self.store.connect() as db:
            row = db.execute("SELECT * FROM agent_definitions WHERE slug=?", (slug,)).fetchone()
        if row is None or not row["enabled"]:
            raise KeyError("智能体不存在或已停用")
        return self._view(row)

    def save(self, value, agent_id=None):
        value = dict(value)
        slug = value.get("slug", "")
        if not isinstance(slug, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,62}", slug):
            raise ValueError("访问路径须为 1–63 位小写字母、数字或连字符")
        for key, label in [("name", "名称"), ("description", "介绍"), ("version", "版本")]:
            text = value.get(key, __version__ if key == "version" else "")
            if not isinstance(text, str) or not text.strip():
                raise ValueError("请填写智能体" + label)
            value[key] = text.strip()
        value.setdefault("system_prompt", "")
        value.setdefault("default_model_id", None)
        value.setdefault("default_vision_model_id", None)
        value.setdefault("skill_names", [])
        value.setdefault("enabled", True)
        if not isinstance(value["system_prompt"], str) or len(value["system_prompt"]) > 100_000:
            raise ValueError("工作指引须为文本，最多 100000 字符")
        if type(value["enabled"]) is not bool:
            raise ValueError("enabled 须为布尔值")
        names = value["skill_names"]
        available = {item["name"] for item in self.store.default_skills() if parse_skill_pack_text(item["content"])}
        if not isinstance(names, list) or any(not isinstance(name, str) or name not in available for name in names):
            raise ValueError("所选技能不存在或格式无效，请从默认 Skill 中选择")
        if len(names) != len(set(names)):
            raise ValueError("技能不能重复选择")
        if value["default_model_id"] and self.store.model_by_id(value["default_model_id"]) is None:
            raise ValueError("默认模型不存在")
        if value["default_vision_model_id"]:
            vision = self.store.model_by_id(value["default_vision_model_id"])
            if vision is None:
                raise ValueError("默认视觉模型不存在")
            if not vision["vision"]:
                raise ValueError("默认视觉模型须具备视觉能力，请先在 Provider / Model 中标记")
        for key in ("documentationUrl", "iconUrl"):
            if not value.get(key):
                value.pop(key, None)
            else:
                self._url(value[key], key)
        if value.get("provider"):
            provider = value["provider"]
            if not isinstance(provider, dict) or not isinstance(provider.get("organization"), str) or not provider["organization"].strip():
                raise ValueError("提供方须填写名称和网址")
            if set(provider) - {"organization", "url"}:
                raise ValueError("提供方只支持 organization 和 url 字段")
            self._url(provider.get("url"), "提供方网址")
            value["provider"] = {"organization": provider["organization"].strip(), "url": provider["url"]}
        else:
            value.pop("provider", None)
        if agent_id and self.get(agent_id)["slug"] != slug:
            raise ValueError("已有智能体的访问路径不能修改，避免调用方入口失效")
        stamp = datetime.now(timezone.utc).isoformat()
        agent_id = agent_id or "agt_" + uuid.uuid4().hex
        # Store only the definition, never IDs or timestamps supplied by a client.
        allowed = {"slug", "name", "description", "version", "system_prompt", "default_model_id", "default_vision_model_id", "skill_names", "enabled", "documentationUrl", "iconUrl", "provider"}
        value = {key: val for key, val in value.items() if key in allowed}
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            conflict = db.execute("SELECT id FROM agent_definitions WHERE slug=? AND id<>?", (slug, agent_id)).fetchone()
            if conflict:
                raise ValueError("访问路径已被其他智能体使用")
            db.execute("INSERT INTO agent_definitions VALUES(?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET "
                       "name=excluded.name,enabled=excluded.enabled,definition_json=excluded.definition_json,updated_at=excluded.updated_at",
                       (agent_id, slug, value["name"], int(value["enabled"]), json.dumps(value, ensure_ascii=False), stamp, stamp))
        return self.get(agent_id)

    def dispatched(self, definition):
        selected = set(definition["skill_names"])
        return [item for item in self.store.default_skills(enabled_only=True)
                if item["name"] in selected and parse_skill_pack_text(item["content"])]

    def snapshot(self, definition):
        return {**definition, "dispatched_skills": self.dispatched(definition)}

    def delete(self, agent_id):
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM agent_definitions WHERE id=?", (agent_id,)).fetchone() is None:
                raise KeyError("智能体不存在")
            if db.execute("SELECT 1 FROM service_tasks WHERE agent_id=? LIMIT 1", (agent_id,)).fetchone():
                raise ValueError("该智能体仍有保留任务，请先停用，待任务到期清理后再删除")
            db.execute("DELETE FROM agent_definitions WHERE id=?", (agent_id,))

    @staticmethod
    def _url(value, label):
        if isinstance(value, str):
            try:
                parsed = urlsplit(value)
                if parsed.scheme in {"http", "https"} and parsed.hostname:
                    return
            except ValueError:
                pass
        raise ValueError(label + "须为完整 HTTP / HTTPS 地址")
