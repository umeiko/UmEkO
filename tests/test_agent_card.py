import json

import pytest
from fastapi.testclient import TestClient

from umeko.server.admin import create_admin_app
from umeko.server.agent_card import AgentCards

SKILL = "---\nname: image-qc\ndescription: 检查图片内容并生成报告\n---\nPRIVATE: internal instructions\n"


@pytest.mark.parametrize("machine_app", ["", "/doc-master/consistency/image-text"], indirect=True)
def test_agent_card_metadata_public_response_and_persistence(machine_client):
    client, app, _, _ = machine_client
    service, store = app.state.agent_service, app.state.store
    store.upsert_default_skill("image-qc.md", SKILL)
    definition = service.agent_registry.save({**app.state.fixture_agent, "skill_names": ["image-qc.md"]}, app.state.fixture_agent["id"])
    public = "http://127.0.0.1" + service.settings.base_path + "/agent/fixture"
    path = "/admin/v1/agents/" + definition["id"]
    admin_user = store.create_user("card-admin", "fixture-pass", "admin")
    admin_app = create_admin_app(service.settings, service, store, public_url="http://127.0.0.1" + service.settings.base_path)
    with TestClient(admin_app) as admin:
        assert admin.get(path + "/card").status_code == 401
        admin.cookies.set("umeko_admin", store.issue_token(admin_user["id"]))
        assert admin.get(path + "/card").json()["public_url"] == public + "/.well-known/agent-card.json"
        value = {key: definition[key] for key in ["slug", "name", "description", "version", "skill_names"]}
        value.update(name="Company Image QA", description="内部图像质检服务", iconUrl="https://example.internal/logo.svg", provider={"organization": "QA Team", "url": "https://example.internal"})
        saved = admin.put(path, json=value)
        assert saved.status_code == 200, saved.text
        published = client.get(public + "/.well-known/agent-card.json")
        assert published.headers["cache-control"] == "no-cache"
        assert admin.get(path + "/card").json()["card"] == published.json()
        assert AgentCards(store).render(public, "required", service.agent_registry.get(definition["id"])) == published.json()
        assert published.json()["skills"] == [{"id": "image-qc.md", "name": "image-qc", "description": "检查图片内容并生成报告", "tags": ["image-qc"]}]
        assert "PRIVATE" not in published.text
        service.identity_store.set_auth_mode("anonymous")
        anonymous = client.get(public + "/.well-known/agent-card.json").json()
        assert not anonymous.get("securityRequirements")
        assert anonymous["name"] == "Company Image QA"
        assert anonymous["supportedInterfaces"][0]["url"] == public + "/a2a"
        assert anonymous["capabilities"]["streaming"] is True


def test_agent_definition_rejects_false_card_claims(machine_client):
    client, app, _, _ = machine_client
    service, store = app.state.agent_service, app.state.store
    definition = app.state.fixture_agent
    admin_user = store.create_user("card-admin", "fixture-pass", "admin")
    admin_app = create_admin_app(service.settings, service, store)
    path = "/admin/v1/agents/" + definition["id"]
    value = {key: definition[key] for key in ["slug", "name", "description", "version", "skill_names"]}
    with TestClient(admin_app) as admin:
        admin.cookies.set("umeko_admin", store.issue_token(admin_user["id"]))
        original = client.get("/agent/fixture/.well-known/agent-card.json").json()
        for field, val in [("name", "  "), ("provider", {"organization": "Team"}), ("iconUrl", "javascript:alert(1)"), ("documentationUrl", "/relative")]:
            assert admin.put(path, json={**value, field: val}).status_code == 400
        for field, val in [("skills", []), ("unknown", True), ("capabilities", {"pushNotifications": True}), ("supportedInterfaces", [])]:
            assert admin.put(path, json={**value, field: val}).status_code == 422
        assert client.get("/agent/fixture/.well-known/agent-card.json").json() == original
        assert admin.get("/admin/v1/agent-card").status_code == 404
        assert admin.put("/admin/v1/agent-card", json={"card": original}).status_code == 404


def test_agent_card_skills_match_dispatch_and_keep_instructions_private(machine_client):
    client, app, _, _ = machine_client
    service, store = app.state.agent_service, app.state.store
    definition = app.state.fixture_agent
    public = "/agent/fixture/.well-known/agent-card.json"
    assert client.get(public).json()["skills"] == []
    store.upsert_default_skill("image-qc.md", SKILL)
    store.upsert_default_skill("report.md", "---\nname: report\ndescription: 整理结果\n---\nPRIVATE report instructions")
    definition = service.agent_registry.save({**definition, "skill_names": ["image-qc.md", "report.md"]}, definition["id"])
    card = client.get(public).json()
    assert {s["id"] for s in card["skills"]} == {"image-qc.md", "report.md"}
    assert "PRIVATE" not in json.dumps(card)
    owner = store.create_user("catalogue-admin", "fixture-pass", "admin")["id"]
    session = service.create_session(user_id=owner, agent_snapshot=service.agent_registry.snapshot(definition))
    assert {p.name for p in (session.root / "client" / "skills").glob("*.md")} == {s["id"] for s in card["skills"]}
    updated = SKILL.replace("name: image-qc", "name: renamed-qc").replace("检查图片内容并生成报告", "最新能力说明")
    store.upsert_default_skill("image-qc.md", updated)
    changed = client.get(public).json()["skills"][0]
    assert changed["id"] == "image-qc.md" and changed["name"] == "renamed-qc"
    store.set_default_skill_enabled("report.md", False)
    assert [s["id"] for s in client.get(public).json()["skills"]] == ["image-qc.md"]
    assert (session.root / "client" / "skills" / "report.md").exists()
    newer = service.create_session(user_id=owner, agent_snapshot=service.agent_registry.snapshot(definition))
    assert [p.name for p in (newer.root / "client" / "skills").glob("*.md")] == ["image-qc.md"]
    assert (newer.root / "client" / "skills" / "image-qc.md").read_text(encoding="utf-8") == updated
