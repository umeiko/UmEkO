import base64
import json
import time

import pytest
from fastapi.testclient import TestClient

from umeko.agent import UmekoAgent
from umeko.config import ModelConfig, Settings
from umeko.host.agents import AgentRegistry
from umeko.host.builtin_agents import (
    BUILTIN_SERVICE_AGENTS, FLOW_CHART_SLUG, FLOW_CORRECTION_SLUG, IMAGE_REASONING_SLUG,
    agent_installation_key, install_builtin_agents,
)
from umeko.host.storage import Store
from umeko.skill_layout import entries, entry_path
from umeko.llm import LLMClient
from umeko.server.admin import create_admin_app
from umeko.server.app import create_app

PNG = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/lXcAAAAASUVORK5CYII="


def app_for(tmp_path, user_prefix="", admin_prefix=""):
    settings = Settings(ModelConfig("fixture", "fixture-key", "https://unused.invalid"),
                        base_path=user_prefix, admin_base_path=admin_prefix)
    return create_app(settings, data_root=tmp_path / "data", workspace_root=tmp_path / "out")


@pytest.mark.parametrize("user_prefix,admin_prefix", [("", ""), ("/teams/umeko", "/operations/admin")])
def test_new_defaults_discovery_admin_and_skill_isolation(tmp_path, user_prefix, admin_prefix):
    app = app_for(tmp_path, user_prefix, admin_prefix)
    service, store = app.state.agent_service, app.state.store
    owner = store.create_user("defaults-admin", "fixture-pass", "admin")
    with TestClient(app) as user, TestClient(create_admin_app(service.settings, service, store)) as admin:
        assert admin.get(admin_prefix + "/admin/v1/agents").status_code == 401
        assert admin.post(admin_prefix + "/admin/login", json={"username": owner["username"], "password": "fixture-pass"}).status_code == 200
        listed = admin.get(admin_prefix + "/admin/v1/agents").json()["agents"]
        assert {FLOW_CHART_SLUG, IMAGE_REASONING_SLUG} <= {item["slug"] for item in listed}
        for expected in BUILTIN_SERVICE_AGENTS:
            definition = service.agent_registry.by_slug(expected["slug"])
            assert definition["name"] == expected["name"]
            assert definition["default_model_id"] is None
            assert definition["default_vision_model_id"] is None
            base = user_prefix + "/agent/" + expected["slug"]
            response = user.get(base + "/.well-known/agent-card.json")
            assert response.status_code == 200
            card = response.json()
            assert card["supportedInterfaces"][0]["url"].endswith(base + "/a2a")
            assert [skill["id"] for skill in card["skills"]] == expected["skill_names"]
            assert expected["system_prompt"] not in response.text
            session = service.create_session(user_id=owner["id"], agent_snapshot=service.agent_registry.snapshot(definition))
            try:
                assert {name + ".md" for name in entries(session.root / "client/skills")} == set(expected["skill_names"])
            finally:
                service.evict_session(session.id)
            store.set_default_skill_enabled(expected["skill_names"][0], False)
            assert user.get(base + "/.well-known/agent-card.json").json()["skills"] == []
        assert admin.post(admin_prefix + "/admin/logout").status_code == 204
        assert admin.get(admin_prefix + "/admin/v1/agents").status_code == 401


@pytest.mark.parametrize("slug,skill", [(FLOW_CHART_SLUG, "drawio-flowchart.md"), (IMAGE_REASONING_SLUG, "image-reasoning.md"),
                                       (FLOW_CORRECTION_SLUG, "drawio-correction.md")])
def test_upgrade_preserves_existing_disabled_dependency_and_custom_agent(tmp_path, slug, skill):
    store = Store(tmp_path / "data/umeko.db")
    store.upsert_default_skill(skill, f"---\nname: {skill[:-3]}\ndescription: custom\n---\nCustom instructions")
    store.set_default_skill_enabled(skill, False)
    app = app_for(tmp_path)
    registry = app.state.agent_service.agent_registry
    library = app.state.agent_service._skills_library_dir()
    definition = next(item for item in registry.list() if item["slug"] == slug)
    assert definition["enabled"] is False
    assert not next(item for item in store.default_skills() if item["name"] == skill)["enabled"]
    customized = registry.save({**definition, "name": "Custom name", "system_prompt": "Custom prompt"}, definition["id"])
    assert not install_builtin_agents(registry, library)
    assert registry.get(definition["id"]) == customized
    registry.delete(definition["id"])
    store.delete_default_skill(skill)
    entry_path(library, skill).unlink()
    assert not install_builtin_agents(registry, library)
    assert slug not in {item["slug"] for item in registry.list()}
    assert store.default_skill(skill) is None and not entry_path(library, skill).exists()
    assert store.config()[agent_installation_key(slug)] == "1"


def test_upgrade_keeps_existing_same_slug_definitions(tmp_path):
    store = Store(tmp_path / "db.sqlite")
    registry = AgentRegistry(store)
    before = [registry.save({"slug": definition["slug"], "name": "Existing", "description": "custom",
                             "system_prompt": "Already configured", "skill_names": [], "enabled": False})
              for definition in BUILTIN_SERVICE_AGENTS]
    assert install_builtin_agents(registry, tmp_path / "library")
    assert [registry.get(item["id"]) for item in before] == before


@pytest.mark.parametrize("prefix", ["", "/teams/umeko"])
@pytest.mark.parametrize("count", [1, 5])
def test_image_reasoning_tasks_accept_images_and_open_prompt(tmp_path, monkeypatch, prefix, count):
    app = app_for(tmp_path, prefix)
    service, store = app.state.agent_service, app.state.store
    provider = store.create_provider("fixture", "https://unused.invalid", "fixture-key")
    main = store.add_model(provider["id"], "fixture-main")
    vision = store.add_model(provider["id"], "fixture-vision", True)
    store.set_active_model(main["id"])
    definition = service.agent_registry.by_slug(IMAGE_REASONING_SLUG)
    service.agent_registry.save({**definition, "default_vision_model_id": vision["id"]}, definition["id"])
    app.state.identity_store.set_auth_mode("anonymous")
    question = "请综合图片中的条件解这道几何题，并说明哪些条件还不足；也可以给出不同假设下的结论。"
    calls = []

    def visual_chat(llm, messages, image_paths, **kwargs):
        assert messages == [{"role": "user", "content": question}]
        assert len(image_paths) == count
        assert all(path.read_bytes() == base64.b64decode(PNG) for path in image_paths)
        calls.append(llm._model.model_id)
        return "fixture answer with image evidence"

    def chat(agent, prompt, images=None):
        assert question in prompt
        assert images and len(images) == count
        instructions = agent._skills["use_skill"].handler(name="image-reasoning")
        assert instructions and "错误" not in instructions
        answer = agent._skills["image_reasoning"].handler(prompt=question, image_paths=[str(path) for path in images])
        agent._skills["submit_results"].handler(text=answer, files=[])
        return answer

    monkeypatch.setattr(LLMClient, "chat_with_images_stream", visual_chat)
    monkeypatch.setattr(UmekoAgent, "chat", chat)
    with TestClient(app) as client:
        base = prefix + "/agent/" + IMAGE_REASONING_SLUG + "/v1/tasks"
        response = client.post(base, json={"prompt": question, "files": [
            {"name": f"image-{index}.png", "content_base64": PNG} for index in range(count)]})
        assert response.status_code == 202, response.text
        for _ in range(200):
            result = client.get(base + "/" + response.json()["id"]).json()
            if result["status"] in {"completed", "failed", "cancelled"}:
                break
            time.sleep(.02)
        assert result["status"] == "completed", json.dumps(result)
        assert result["reply"] == "fixture answer with image evidence"
    assert calls == [vision["id"]]
