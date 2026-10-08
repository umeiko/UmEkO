from copy import deepcopy
import json

import pytest
from fastapi.testclient import TestClient

from umeko.server.admin import create_admin_app
from umeko.server.agent_card import AgentCardConfig, EDITABLE_FIELDS

SKILL = "---\nname: image-qc\ndescription: 检查图片内容并生成报告\n---\nPRIVATE: internal instructions\n"


@pytest.mark.parametrize("machine_app", ["", "/doc-master/consistency/image-text"], indirect=True)
def test_card_admin_edit_public_response_and_persistence(machine_client):
    client, app, _, _ = machine_client
    service, store = app.state.agent_service, app.state.store
    store.upsert_default_skill("image-qc.md", SKILL)
    prefix = service.settings.base_path
    public = "http://127.0.0.1" + prefix
    admin_user = store.create_user("card-admin", "fixture-pass", "admin")
    admin_app = create_admin_app(service.settings, service, store, public_url=public)
    with TestClient(admin_app) as admin:
        assert admin.get("/admin/v1/agent-card").status_code == 401
        assert admin.put("/admin/v1/agent-card", json={"card": {}}).status_code == 401
        admin.cookies.set("umeko_admin", store.issue_token(admin_user["id"]))
        data = admin.get("/admin/v1/agent-card").json()
        original = client.get(prefix + "/.well-known/agent-card.json").json()
        assert data["card"] == original
        assert data["public_url"] == public + "/.well-known/agent-card.json"
        card = deepcopy(data["card"])
        card.update(name="Company Image QA", description="内部图像质检服务", iconUrl="https://example.internal/logo.svg",
                    provider={"organization": "QA Team", "url": "https://example.internal"})
        saved = admin.put("/admin/v1/agent-card", json={"card": card})
        assert saved.status_code == 200, saved.text
        published = client.get(prefix + "/.well-known/agent-card.json")
        assert published.headers["cache-control"] == "no-cache"
        assert published.json() == saved.json()["card"]
        assert AgentCardConfig(store).render(public, "required") == published.json()
        assert set(json.loads(store.config()["A2A_AGENT_CARD"])) <= set(EDITABLE_FIELDS)
        assert "skills" not in data["editable_fields"]
        assert published.json()["skills"] == [{"id": "image-qc.md", "name": "image-qc",
                                               "description": "检查图片内容并生成报告", "tags": ["image-qc"]}]
        assert "PRIVATE" not in published.text
        assert client.get(prefix + "/admin/v1/agent-card").status_code == 404
        service.identity_store.set_auth_mode("anonymous")
        anonymous = client.get(prefix + "/.well-known/agent-card.json").json()
        assert not anonymous.get("securityRequirements")
        assert anonymous["name"] == "Company Image QA"
        assert anonymous["supportedInterfaces"][0]["url"] == public + "/a2a"
        assert anonymous["capabilities"]["streaming"] is True


def test_card_rejects_invalid_metadata_and_false_protocol_claims(machine_client):
    client, app, _, _ = machine_client
    service, store = app.state.agent_service, app.state.store
    store.upsert_default_skill("image-qc.md", SKILL)
    admin_user = store.create_user("card-admin", "fixture-pass", "admin")
    admin_app = create_admin_app(service.settings, service, store, public_url="http://127.0.0.1")
    with TestClient(admin_app) as admin:
        admin.cookies.set("umeko_admin", store.issue_token(admin_user["id"]))
        original = admin.get("/admin/v1/agent-card").json()["card"]
        invalid = []
        for field, value in [("name", "  "), ("skills", []), ("unknown", True),
                             ("capabilities", {"streaming": True, "pushNotifications": True}),
                             ("supportedInterfaces", [{"url": "https://wrong.example/a2a", "protocolBinding": "JSONRPC", "protocolVersion": "1.0"}])]:
            card = deepcopy(original)
            card[field] = value
            invalid.append(card)
        duplicate = deepcopy(original)
        duplicate["skills"].append(deepcopy(duplicate["skills"][0]))
        invalid.append(duplicate)
        for field, value in [("provider", "wrong"), ("provider", {"organization": "Team"}),
                             ("iconUrl", "javascript:alert(1)"), ("documentationUrl", "/relative")]:
            malformed = deepcopy(original)
            malformed[field] = value
            invalid.append(malformed)
        for card in invalid:
            response = admin.put("/admin/v1/agent-card", json={"card": card})
            assert response.status_code == 400, response.text
            assert isinstance(response.json()["detail"], str)
            assert client.get("/.well-known/agent-card.json").json() == original
        assert "A2A_AGENT_CARD" not in store.config()
        # Metadata-only clients can omit the managed fields; the service fills them in.
        metadata = {key: value for key, value in original.items() if key in EDITABLE_FIELDS}
        metadata["description"] = "Updated metadata"
        assert admin.put("/admin/v1/agent-card", json={"card": metadata}).status_code == 200
        assert client.get("/.well-known/agent-card.json").json()["capabilities"]["streaming"] is True


def test_card_skills_follow_actual_dispatch_and_keep_instructions_private(machine_client):
    client, app, _, _ = machine_client
    service, store = app.state.agent_service, app.state.store
    admin_user = store.create_user("catalogue-admin", "fixture-pass", "admin")
    admin_app = create_admin_app(service.settings, service, store, public_url="http://127.0.0.1")
    with TestClient(admin_app) as admin:
        admin.cookies.set("umeko_admin", store.issue_token(admin_user["id"]))
        assert client.get("/.well-known/agent-card.json").json()["skills"] == []
        # Preserve earlier Card metadata, but ignore its separately maintained skills.
        legacy = {**AgentCardConfig.defaults(), "name": "Existing custom name",
                  "skills": [{"id": "legacy", "name": "Old claim", "description": "Old", "tags": ["old"]}]}
        store.set_config({"A2A_AGENT_CARD": json.dumps(legacy)})
        empty = client.get("/.well-known/agent-card.json").json()
        assert empty["name"] == "Existing custom name" and empty["skills"] == []
        metadata = {key: value for key, value in empty.items() if key in EDITABLE_FIELDS}
        assert admin.put("/admin/v1/agent-card", json={"card": metadata}).status_code == 200
        assert "skills" not in json.loads(store.config()["A2A_AGENT_CARD"])

        assert admin.put("/admin/v1/default-skills/image-qc.md", json={"content": SKILL}).status_code == 201
        second = "---\nname: report\ndescription: 整理结果\n---\nPRIVATE report instructions\n"
        assert admin.put("/admin/v1/default-skills/report.md", json={"content": second}).status_code == 201
        card = client.get("/.well-known/agent-card.json").json()
        assert {s["id"] for s in card["skills"]} == {"image-qc.md", "report.md"}
        assert "PRIVATE" not in json.dumps(card)
        session = service.create_session(user_id=admin_user["id"])
        assert {p.name for p in (session.root / "client" / "skills").glob("*.md")} == {s["id"] for s in card["skills"]}
        updated = SKILL.replace("name: image-qc", "name: renamed-qc").replace("检查图片内容并生成报告", "最新能力说明")
        assert admin.put("/admin/v1/default-skills/image-qc.md", json={"content": updated}).status_code == 201
        changed = client.get("/.well-known/agent-card.json").json()["skills"][0]
        assert changed["id"] == "image-qc.md" and changed["name"] == "renamed-qc"
        assert changed["description"] == "最新能力说明"
        assert admin.post("/admin/v1/default-skills/report.md/toggle").json()["enabled"] is False
        assert [s["id"] for s in client.get("/.well-known/agent-card.json").json()["skills"]] == ["image-qc.md"]
        # Old sessions retain their dispatched copy; a new session uses the new catalogue.
        assert (session.root / "client" / "skills" / "report.md").exists()
        newer = service.create_session(user_id=admin_user["id"])
        assert [p.name for p in (newer.root / "client" / "skills").glob("*.md")] == ["image-qc.md"]
        assert (newer.root / "client" / "skills" / "image-qc.md").read_text(encoding="utf-8") == updated
        assert admin.delete("/admin/v1/default-skills/image-qc.md").status_code == 204
        store.upsert_default_skill("invalid.md", "No valid frontmatter")
        assert client.get("/.well-known/agent-card.json").json()["skills"] == []
