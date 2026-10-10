from pathlib import Path
import json
import ssl

import certifi
import pytest

from umeko.config import ModelConfig, Settings, load_settings, normalize_base_path
from umeko.host.configuration import LEGACY_MODEL_KEYS, migrate_legacy_models, resolve_provider_settings
from umeko.host.service import AgentService
from umeko.host.storage import Store
from umeko.llm import client as client_module


@pytest.fixture
def deployment_env(monkeypatch, tmp_path):
    for key in {*LEGACY_MODEL_KEYS, "UMEKO_DATA_ROOT", "UMEKO_BASE_PATH", "UMEKO_ADMIN_BASE_PATH", "UMEKO_PUBLIC_URL", "MODEL_CA_FILE",
                "TEXT_MODEL_CONTEXT_WINDOW", "MAX_TOOL_ITERATIONS", "MAX_SUBAGENT_TOOL_ITERATIONS"}:
        monkeypatch.delenv(key, raising=False)
    path = tmp_path / ".env"
    path.write_text("", encoding="utf-8")
    return path


@pytest.mark.parametrize("value, expected", [("", ""), ("/", ""), (" /doc-master/consistency/image-text/ ", "/doc-master/consistency/image-text"), ("/v1", "/v1")])
def test_prefix_normalization(value, expected):
    assert normalize_base_path(value) == expected


@pytest.mark.parametrize("value", ["relative", "https://example.com/app", "//host/app", "/a//b", "/a/../b", "/a/./b", "/a?x=1", "/a#b", "/a\\b", "/a space"])
def test_invalid_prefix_fails_early(value):
    with pytest.raises(RuntimeError, match="UMEKO_BASE_PATH"):
        normalize_base_path(value)


def test_admin_prefix_is_independent_and_process_env_takes_precedence(deployment_env, monkeypatch):
    deployment_env.write_text("UMEKO_BASE_PATH=/workbench\n", encoding="utf-8")
    assert load_settings(deployment_env).admin_base_path == ""
    deployment_env.write_text("UMEKO_BASE_PATH=/workbench\nUMEKO_ADMIN_BASE_PATH=/file-admin/\n", encoding="utf-8")
    assert load_settings(deployment_env).admin_base_path == "/file-admin"
    monkeypatch.setenv("UMEKO_ADMIN_BASE_PATH", "/operations/umeko/")
    settings = load_settings(deployment_env)
    assert settings.admin_base_path == "/operations/umeko" and settings.base_path == "/workbench"
    monkeypatch.setenv("UMEKO_ADMIN_BASE_PATH", "https://company.internal/admin")
    with pytest.raises(RuntimeError, match="UMEKO_ADMIN_BASE_PATH"):
        load_settings(deployment_env)


def test_legacy_models_move_to_shared_registry_once(deployment_env, monkeypatch):
    deployment_env.write_text("TEXT_MODEL_NAME=old\nTEXT_MODEL_BASE_URL=https://old.test/v1\nTEXT_MODEL_API_KEY=old-key\nVISION_MODEL_NAME=vision\nVISION_MODEL_BASE_URL=https://vision.test/v1\nVISION_MODEL_API_KEY=vision-key\n", encoding="utf-8")
    settings = load_settings(deployment_env)
    store = Store(Path(settings.data_root) / "umeko.db")
    assert settings.text_model.name == "old"
    assert settings.vision_model.name == "vision"
    assert len(store.list_providers()) == 2
    provider = store.create_provider("new", "https://new.test/v1", "new-key")
    model = store.add_model(provider["id"], "new", vision=True)
    store.set_active_model(model["id"])
    monkeypatch.setenv("TEXT_MODEL_API_KEY", "obsolete-key")
    updated = load_settings(deployment_env)
    assert updated.text_model.api_key == "new-key"
    assert updated.text_model_vision is True and updated.vision_model is None
    store.delete_provider(provider["id"])
    assert load_settings(deployment_env).text_model.name == "unconfigured"
    assert len(store.list_providers()) == 2  # no obsolete env fallback or re-import


def test_migration_preserves_existing_provider_and_active_selection(tmp_path):
    store = Store(tmp_path / "db")
    p = store.create_provider("existing", "https://existing.test", "keep-key")
    m = store.add_model(p["id"], "keep")
    store.set_active_model(m["id"])
    values = {"TEXT_MODEL_NAME": "old", "TEXT_MODEL_API_KEY": "old-key", "TEXT_MODEL_BASE_URL": "https://old.test"}
    assert migrate_legacy_models(store, values) == 1
    assert migrate_legacy_models(store, values) == 1
    assert len(store.list_providers()) == 2
    assert store.active_model()["model_id"] == m["id"]
    assert store.active_model()["api_key"] == "keep-key"
    with pytest.raises(RuntimeError, match="不完整"):
        migrate_legacy_models(store, {**values, "VISION_MODEL_NAME": "incomplete"})
    assert len(store.list_providers()) == 2


def test_relative_ca_and_process_env_precedence(deployment_env, monkeypatch):
    ca = deployment_env.parent / "company.pem"
    ca.write_bytes(Path(certifi.where()).read_bytes())
    deployment_env.write_text("MODEL_CA_FILE=company.pem\nUMEKO_BASE_PATH=/file\n", encoding="utf-8")
    monkeypatch.setenv("UMEKO_BASE_PATH", "/process/")
    settings = load_settings(deployment_env)
    assert settings.base_path == "/process"
    assert settings.text_model.ca_file == str(ca.resolve())
    monkeypatch.setenv("MODEL_CA_FILE", "missing.pem")
    with pytest.raises(RuntimeError, match="MODEL_CA_FILE"):
        load_settings(deployment_env)


def test_provider_switches_keep_ca_and_use_each_providers_proxy(tmp_path):
    store = Store(tmp_path / "db")
    p1 = store.create_provider("proxy", "https://one.test", "one-key", "http://localhost:7890")
    p2 = store.create_provider("direct", "https://two.test", "two-key")
    m1 = store.add_model(p1["id"], "one")
    m2 = store.add_model(p2["id"], "two")
    v = store.add_model(p2["id"], "vision", True)
    store.set_active_model(m1["id"])
    user = store.create_user("person", "password")
    store.set_user_model_prefs(user["id"], main_model_id=m2["id"], sub_model_id=m1["id"], vision_model_id=v["id"])
    base = Settings(ModelConfig("unconfigured", "", "https://invalid.unconfigured", ca_file="company.pem"), registry_managed=True)
    service = AgentService(base, tmp_path / "data", tmp_path / "output", store=store)
    try:
        effective = service.effective_settings_for(user["id"])
        assert all(model.ca_file == "company.pem" for model in (effective.text_model, effective.sub_model, effective.vision_model))
        assert effective.text_model.proxy is None
        assert effective.sub_model.proxy == "http://localhost:7890"
        store.set_active_model(m2["id"])
        assert service.effective_settings_for("").text_model.name == "two"
        service.reload_config()
        assert service.settings.text_model.ca_file == "company.pem"
        store.delete_provider(p2["id"])
        assert resolve_provider_settings(service.settings, store).text_model.name == "unconfigured"
    finally:
        service.run_manager.shutdown()


def test_custom_ca_transport_keeps_hostname_and_certificate_verification(monkeypatch):
    captured = {}
    monkeypatch.setattr(client_module, "DefaultHttpxClient", lambda **kw: captured.update(kw) or object())
    monkeypatch.setattr(client_module, "OpenAI", lambda **kw: object())
    model = ModelConfig("test", "key", "https://test/v1", ca_file=certifi.where())
    client_module.LLMClient(model)._get_client()
    assert captured["trust_env"] is False
    assert isinstance(captured["verify"], ssl.SSLContext)
    assert captured["verify"].verify_mode == ssl.CERT_REQUIRED
    assert captured["verify"].check_hostname is True


def test_cli_import_and_migration_use_same_store_without_exposing_keys(deployment_env, monkeypatch, capsys):
    from umeko.cli import main
    from dotenv import dotenv_values
    deployment_env.write_text("TEXT_MODEL_NAME=old\nTEXT_MODEL_API_KEY=old-secret\nTEXT_MODEL_BASE_URL=https://old.test\nUMEKO_ADMIN_PASSWORD=keep-admin\n", encoding="utf-8")
    document = deployment_env.parent / "providers.local"
    document.write_text(json.dumps({"providers": [{"name": "cli", "base_url": "https://cli.test", "api_key": "cli-secret", "models": [{"name": "new"}]}], "active": "cli/new"}), encoding="utf-8")
    def command(*args):
        monkeypatch.setattr("sys.argv", ["umeko.cli", "--env", str(deployment_env), "providers", *args])
        main()
    command("import", str(document))
    assert load_settings(deployment_env).text_model.name == "new"
    command("list")
    output = capsys.readouterr().out
    assert "cli-secret" not in output and "old-secret" not in output
    assert "new" in output
    command("migrate-env", "--remove")
    values = dotenv_values(deployment_env)
    assert not LEGACY_MODEL_KEYS.intersection(values)
    assert values["UMEKO_ADMIN_PASSWORD"] == "keep-admin"
    assert load_settings(deployment_env).text_model.api_key == "cli-secret"
