"""Editable public Agent Card metadata with service-managed protocol fields."""
from __future__ import annotations

import json
from urllib.parse import urlsplit

from a2a import types as a2a
from google.protobuf.json_format import MessageToDict, ParseDict, ParseError

from .. import __version__
from ..skillpacks import parse_skill_pack_text

EDITABLE_FIELDS = ("name", "description", "version", "documentationUrl", "iconUrl", "provider")
MANAGED_FIELDS = ("supportedInterfaces", "capabilities", "defaultInputModes", "defaultOutputModes",
                  "securitySchemes", "securityRequirements", "skills")


class AgentCardConfig:
    def __init__(self, store):
        self.store = store

    @staticmethod
    def defaults() -> dict:
        return {"name": "UMEKO", "description": "文件处理与多智能体任务执行服务", "version": __version__,
                "documentationUrl": "https://umeiko.github.io/UmEkO/api/"}

    def dispatched_skills(self) -> list[dict]:
        """Read the same enabled DB copies that AgentService seeds into new sessions.

        Publish only frontmatter metadata; skill instructions and scripts stay private.
        The filename is a stable ID even when its displayed name/description changes.
        """
        skills = []
        for item in self.store.default_skills(enabled_only=True):
            pack = parse_skill_pack_text(item["content"])
            if pack is not None:
                skills.append({"id": item["name"], "name": pack.name,
                               "description": pack.description, "tags": [pack.name]})
        return skills

    def render(self, base: str, auth_mode: str) -> dict:
        saved = self.store.config().get("A2A_AGENT_CARD")
        metadata = {key: value for key, value in (json.loads(saved) if saved else self.defaults()).items()
                    if key in EDITABLE_FIELDS}
        value = {**metadata,
                 "skills": self.dispatched_skills(),
                 "supportedInterfaces": [{"url": base + "/a2a", "protocolBinding": "JSONRPC", "protocolVersion": "1.0"}],
                 "capabilities": {"streaming": True, "pushNotifications": False},
                 "defaultInputModes": ["text/plain", "application/octet-stream", "application/json"],
                 "defaultOutputModes": ["text/plain", "application/octet-stream"],
                 "securitySchemes": {"serviceBearer": {"httpAuthSecurityScheme": {"scheme": "bearer", "bearerFormat": "UMEKO service credential"}}},
                 "securityRequirements": [] if auth_mode == "anonymous" else [{"schemes": {"serviceBearer": {"list": []}}}]}
        result = MessageToDict(ParseDict(value, a2a.AgentCard()))
        # An empty catalogue still has the required skills array. Do not invent a
        # business capability when no skills are dispatched by this server.
        result.setdefault("skills", [])
        return result

    def save(self, card: dict, base: str, auth_mode: str) -> dict:
        unknown = set(card) - set(EDITABLE_FIELDS) - set(MANAGED_FIELDS)
        if unknown:
            raise ValueError("不支持的 Agent Card 字段：" + "、".join(sorted(unknown)))
        for field in ("name", "description", "version"):
            if not isinstance(card.get(field), str) or not card[field].strip():
                raise ValueError(f"{field} 须为非空文本")
        for field in ("documentationUrl", "iconUrl"):
            if field in card:
                self._validate_url(card[field], field)
        if "provider" in card:
            provider = card["provider"]
            if not isinstance(provider, dict) or not isinstance(provider.get("organization"), str) or not provider["organization"].strip():
                raise ValueError("提供方须填写组织名称和网址")
            self._validate_url(provider.get("url"), "提供方网址")
        try:
            normalized = MessageToDict(ParseDict(card, a2a.AgentCard()))
        except (ParseError, TypeError, ValueError) as exc:
            raise ValueError(f"Agent Card 格式不正确：{exc}") from exc
        current = self.render(base, auth_mode)
        for field in MANAGED_FIELDS:
            actual = normalized.get(field, []) if field == "skills" else normalized.get(field)
            if field in card and actual != current.get(field):
                if field == "skills":
                    raise ValueError("skills 与已启用的默认 Skill 自动同步，请在默认 Skill 页面维护；列表已变化时请重新读取")
                raise ValueError(f"{field} 由服务配置自动维护，请保留原值；配置有变化时请重新读取")
        metadata = {field: normalized[field] for field in EDITABLE_FIELDS if field in normalized}
        self.store.set_config({"A2A_AGENT_CARD": json.dumps(metadata, ensure_ascii=False)})
        return self.render(base, auth_mode)

    @staticmethod
    def _validate_url(value, field):
        if isinstance(value, str):
            try:
                parsed = urlsplit(value)
                if parsed.scheme in {"http", "https"} and parsed.hostname:
                    return
            except ValueError:
                pass
        raise ValueError(f"{field} 须为完整的 http:// 或 https:// 地址；不需要时可留空")
