"""Editable public Agent Card metadata with service-managed protocol fields."""
from __future__ import annotations

import json

from a2a import types as a2a
from google.protobuf.json_format import MessageToDict, ParseDict, ParseError

from .. import __version__

EDITABLE_FIELDS = ("name", "description", "version", "documentationUrl", "iconUrl", "provider", "skills")
MANAGED_FIELDS = ("supportedInterfaces", "capabilities", "defaultInputModes", "defaultOutputModes",
                  "securitySchemes", "securityRequirements")


class AgentCardConfig:
    def __init__(self, store):
        self.store = store

    @staticmethod
    def defaults() -> dict:
        return {"name": "UMEKO", "description": "文件处理与多智能体任务执行服务", "version": __version__,
                "documentationUrl": "https://umeiko.github.io/UmEkO/api/",
                "skills": [{"id": "file_task", "name": "文件任务", "description": "按要求处理文本、图像和文件，返回结果与报告",
                            "tags": ["files", "documents", "images"], "examples": ["检查附件内容并生成报告"]}]}

    def render(self, base: str, auth_mode: str) -> dict:
        saved = self.store.config().get("A2A_AGENT_CARD")
        metadata = json.loads(saved) if saved else self.defaults()
        value = {**metadata,
                 "supportedInterfaces": [{"url": base + "/a2a", "protocolBinding": "JSONRPC", "protocolVersion": "1.0"}],
                 "capabilities": {"streaming": True, "pushNotifications": False},
                 "defaultInputModes": ["text/plain", "application/octet-stream", "application/json"],
                 "defaultOutputModes": ["text/plain", "application/octet-stream"],
                 "securitySchemes": {"serviceBearer": {"httpAuthSecurityScheme": {"scheme": "bearer", "bearerFormat": "UMEKO service credential"}}},
                 "securityRequirements": [] if auth_mode == "anonymous" else [{"schemes": {"serviceBearer": {"list": []}}}]}
        return MessageToDict(ParseDict(value, a2a.AgentCard()))

    def save(self, card: dict, base: str, auth_mode: str) -> dict:
        unknown = set(card) - set(EDITABLE_FIELDS) - set(MANAGED_FIELDS)
        if unknown:
            raise ValueError("不支持的 Agent Card 字段：" + "、".join(sorted(unknown)))
        for field in ("name", "description", "version"):
            if not isinstance(card.get(field), str) or not card[field].strip():
                raise ValueError(f"{field} 须为非空文本")
        skills = card.get("skills")
        if not isinstance(skills, list) or not skills:
            raise ValueError("skills 须包含至少一项技能")
        ids = set()
        for index, skill in enumerate(skills, 1):
            if not isinstance(skill, dict):
                raise ValueError(f"第 {index} 项技能须为 JSON 对象")
            for field in ("id", "name", "description"):
                if not isinstance(skill.get(field), str) or not skill[field].strip():
                    raise ValueError(f"第 {index} 项技能的 {field} 须为非空文本")
            if skill["id"] in ids:
                raise ValueError("技能 id 不能重复：" + skill["id"])
            ids.add(skill["id"])
            if not isinstance(skill.get("tags"), list) or any(not isinstance(tag, str) for tag in skill["tags"]):
                raise ValueError(f"第 {index} 项技能的 tags 须为文本数组")
        try:
            normalized = MessageToDict(ParseDict(card, a2a.AgentCard()))
        except (ParseError, TypeError, ValueError) as exc:
            raise ValueError(f"Agent Card 格式不正确：{exc}") from exc
        current = self.render(base, auth_mode)
        for field in MANAGED_FIELDS:
            if field in card and normalized.get(field) != current.get(field):
                raise ValueError(f"{field} 由服务配置自动维护，请保留原值；配置有变化时请重新读取")
        metadata = {field: normalized[field] for field in EDITABLE_FIELDS if field in normalized}
        self.store.set_config({"A2A_AGENT_CARD": json.dumps(metadata, ensure_ascii=False)})
        return self.render(base, auth_mode)
