import asyncio
from dataclasses import replace
import json

import httpx2
import pytest
from fastapi.testclient import TestClient
from mcp.client import Client
from mcp.client.streamable_http import streamable_http_client

from umeko.server.admin import create_admin_app


@pytest.mark.parametrize("machine_app", ["", "/doc-master/consistency/image-text"], indirect=True)
def test_admin_disclosure_matches_official_client_and_requires_admin(machine_server):
    base, app, caller, _ = machine_server
    service, store = app.state.agent_service, app.state.store
    prefix = "/operations/umeko" if service.settings.base_path else ""
    settings = replace(service.settings, admin_base_path=prefix, public_url=base.removesuffix('/agent/fixture'))
    admin_app = create_admin_app(settings, service, store)
    administrator = store.create_user("disclosure-admin", "fixture-only-password", "admin")
    ordinary = store.create_user("disclosure-reader", "fixture-only-password")
    definition = app.state.fixture_agent
    endpoint = prefix + "/admin/v1/agents/" + definition["id"] + "/mcp"
    with TestClient(admin_app) as admin:
        assert admin.get(endpoint).status_code == 401
        admin.cookies.set("umeko_admin", store.issue_token(ordinary["id"]), path=prefix or "/")
        assert admin.get(endpoint).status_code == 401
        admin.cookies.clear()
        assert admin.post(prefix + "/admin/login", json={"username": administrator["username"],
                    "password": "fixture-only-password"}).status_code == 200
        data = admin.get(endpoint).json()
        assert data["endpoint"] == base + "/mcp"
        assert data["agent_id"] == definition["id"] and data["enabled"]
        assert data["auth_mode"] == "required"
        assert data["transport"] == "Streamable HTTP"
        assert {tool["name"] for tool in data["tools"]} == {
            "get_agent_info", "submit_task", "get_task", "list_file", "download_file", "cancel_task", "read_results",
        }
        async def actual_listing():
            async with httpx2.AsyncClient(headers={"Authorization": "Bearer " + caller["token"]}, trust_env=False) as transport:
                async with Client(streamable_http_client(base + "/mcp", http_client=transport), cache=None) as client:
                    def wire(items):
                        return [item.model_dump(mode="json", by_alias=True, exclude_none=True) for item in items]
                    return {"tools": wire((await client.list_tools()).tools),
                            "resources": wire((await client.list_resources()).resources),
                            "resourceTemplates": wire((await client.list_resource_templates()).resource_templates),
                            "prompts": wire((await client.list_prompts()).prompts)}
        actual = asyncio.run(actual_listing())
        for key in actual:
            assert data[key] == actual[key]
        submit = next(tool for tool in data["tools"] if tool["name"] == "submit_task")
        assert "prompt" in submit["inputSchema"]["required"]
        assert "ctx" not in submit["inputSchema"]["properties"]
        assert "model_id" not in submit["inputSchema"]["properties"]
        assert submit["outputSchema"] and submit["annotations"]["readOnlyHint"] is False
        assert data["resourceTemplates"] == []
        assert "fixture-key" not in json.dumps(data)
        assert "password_hash" not in json.dumps(data)
        assert service.task_service.snapshot()["counts"] == {}
        assert not service.sessions
        assert admin.get(prefix + "/admin/v1/agents/missing/mcp").status_code == 404
        service.identity_store.set_auth_mode("anonymous")
        service.agent_registry.save({**definition, "enabled": False}, definition["id"])
        disabled = admin.get(endpoint).json()
        assert disabled["enabled"] is False and disabled["auth_mode"] == "anonymous"
        assert disabled["tools"] == data["tools"]
        admin.post(prefix + "/admin/logout")
        assert admin.get(endpoint).status_code == 401
