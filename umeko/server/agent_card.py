"""Generate each configured Agent Card from the execution skill catalogue."""
from __future__ import annotations

from a2a import types as a2a
from google.protobuf.json_format import MessageToDict, ParseDict

from ..skillpacks import parse_skill_pack_text
from .task_api import task_results_url

EDITABLE_FIELDS = ("name", "description", "version", "documentationUrl", "iconUrl", "provider")


class AgentCards:
    def __init__(self, store):
        self.store = store

    def dispatched_skills(self, definition) -> list[dict]:
        """Read the same enabled DB copies that AgentService seeds into new sessions.

        Publish only frontmatter metadata; skill instructions and scripts stay private.
        The filename is a stable ID even when its displayed name/description changes.
        """
        skills = []
        for item in self.store.default_skills(enabled_only=True):
            if item["name"] not in definition["skill_names"]:
                continue
            pack = parse_skill_pack_text(item["content"])
            if pack is not None:
                skills.append({"id": item["name"], "name": pack.name,
                               "description": pack.description, "tags": [pack.name]})
        return skills

    def render(self, base: str, auth_mode: str, definition) -> dict:
        metadata = {key: value for key, value in definition.items() if key in EDITABLE_FIELDS}
        value = {**metadata,
                 "skills": self.dispatched_skills(definition),
                 "supportedInterfaces": [{"url": base + "/a2a", "protocolBinding": "JSONRPC", "protocolVersion": "1.0"}],
                 "capabilities": {"streaming": True, "pushNotifications": False, "extensions": [{
                     "uri": "urn:umeko:a2a:task-results:v1",
                     "description": "read_results: When GetTask is completed, deliver the response text and files "
                                    "from artifacts directly to the user. No workspace navigation or extra HTTP read is required. "
                                    "For the latest validated result, including temporary workspace continuations, "
                                    "GET Task.metadata.resultsUrl. This optional REST read returns ready, text and files; "
                                    "the caller reads it programmatically, not by asking the user to open the URL. "
                                    "It does not create a task or invoke a model. OAuth tokens must target oauthResource.",
                     "required": False,
                     "params": {"method": "GET", "urlTemplate": task_results_url(base, "{task_id}"),
                                "taskMetadataField": "resultsUrl", "requiredScope": "tasks:read",
                                "oauthResource": base + "/v1/tasks"},
                 }]},
                 "defaultInputModes": ["text/plain", "application/octet-stream", "application/json"],
                 "defaultOutputModes": ["text/plain", "application/octet-stream"],
                 "securitySchemes": {"serviceBearer": {"httpAuthSecurityScheme": {"scheme": "bearer", "bearerFormat": "UMEKO service credential"}}},
                 "securityRequirements": [] if auth_mode == "anonymous" else [{"schemes": {"serviceBearer": {"list": []}}}]}
        result = MessageToDict(ParseDict(value, a2a.AgentCard()))
        # An empty catalogue still has the required skills array. Do not invent a
        # business capability when no skills are dispatched by this server.
        result.setdefault("skills", [])
        return result
