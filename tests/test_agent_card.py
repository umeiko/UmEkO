from copy import deepcopy
import json

import pytest
from fastapi.testclient import TestClient

from umeko.server.admin import create_admin_app
from umeko.server.agent_card import AgentCardConfig, EDITABLE_FIELDS


@pytest.mark.parametrize("machine_app", ["", "/doc-master/consistency/image-text"], indirect=True)
def test_card_admin_edit_public_response_and_persistence(machine_client):
    client, app, _, _ = machine_client
    service, store = app.state.agent_service, app.state.store
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
        card["skills"][0].update(name="图像检查", description="检查图片内容", examples=["检查这张图片"])
        saved = admin.put("/admin/v1/agent-card", json={"card": card})
        assert saved.status_code == 200, saved.text
        published = client.get(prefix + "/.well-known/agent-card.json")
        assert published.headers["cache-control"] == "no-cache"
        assert published.json() == saved.json()["card"]
        assert AgentCardConfig(store).render(public, "required") == published.json()
        assert set(json.loads(store.config()["A2A_AGENT_CARD"])) <= set(EDITABLE_FIELDS)
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
        malformed = deepcopy(original)
        malformed["provider"] = "wrong"
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
