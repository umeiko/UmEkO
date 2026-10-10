import json

import pytest
from fastapi.testclient import TestClient

from umeko.config import ModelConfig, Settings
from umeko.server.admin import create_admin_app
from umeko.server.agent_card import AgentCards
from umeko.server.app import create_app

SKILL = "---\nname: image-qc\ndescription: 检查图片内容并生成报告\n---\nPRIVATE: internal instructions\n"


@pytest.mark.parametrize("prefix", ["", "/doc-master/consistency/image-text"])
@pytest.mark.parametrize("explicit_public_url", [False, True])
def test_protocol_discovery_and_oauth_preserve_service_and_agent_prefixes(tmp_path, prefix, explicit_public_url):
    public_url = "https://company.internal" + prefix if explicit_public_url else ""
    settings = Settings(ModelConfig("fixture", "key", "https://unused.invalid"), base_path=prefix,
                        admin_base_path="/operations/umeko", public_url=public_url)
    app = create_app(settings, data_root=tmp_path / "data", workspace_root=tmp_path / "output")
    service = app.state.agent_service
    definition = service.agent_registry.save({"slug": "prefix-test", "name": "Prefix test",
                                              "description": "Protocol deployment test", "skill_names": []})
    route = prefix + "/agent/" + definition["slug"]
    base = (public_url or "http://127.0.0.1" + prefix) + "/agent/" + definition["slug"]
    account = service.identity_store.create("test-client", ["tasks:read", "tasks:create", "tasks:cancel"])
    with TestClient(app, base_url="http://127.0.0.1") as client:
        discovery = client.get(route + "/").json()
        assert {key: discovery[key] for key in ("agent_card", "a2a", "mcp", "tasks")} == {
            "agent_card": base + "/.well-known/agent-card.json", "a2a": base + "/a2a",
            "mcp": base + "/mcp", "tasks": base + "/v1/tasks"}
        assert client.get(route + "/.well-known/agent-card.json").json()["supportedInterfaces"][0]["url"] == base + "/a2a"
        unauthorized = client.post(route + "/mcp", json={})
        assert unauthorized.status_code == 401
        assert unauthorized.headers["www-authenticate"] == (
            'Bearer resource_metadata="' + base + '/.well-known/oauth-protected-resource/mcp"')
        resource = client.get(route + "/.well-known/oauth-protected-resource/mcp").json()
        assert resource["resource"] == base + "/mcp" and resource["authorization_servers"] == [base]
        authorization = client.get(route + "/.well-known/oauth-authorization-server").json()
        assert authorization["issuer"] == base and authorization["token_endpoint"] == base + "/oauth/token"
        for target in ("/mcp", "/a2a", "/v1/tasks"):
            token = client.post(route + "/oauth/token", data={"grant_type": "client_credentials",
                                "client_id": account["id"], "client_secret": account["token"], "resource": base + target})
            assert token.status_code == 200
            bearer = {"Authorization": "Bearer " + token.json()["access_token"]}
            assert client.get(route + "/v1/tasks", headers=bearer).status_code == (200 if target == "/v1/tasks" else 401)
        if prefix:
            missing_prefix = client.post(route + "/oauth/token", data={"grant_type": "client_credentials",
                                         "client_id": account["id"], "client_secret": account["token"],
                                         "resource": base.replace(prefix, "", 1) + "/mcp"})
            assert missing_prefix.status_code == 400 and missing_prefix.json()["error"] == "invalid_target"


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
