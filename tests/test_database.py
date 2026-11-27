import sys

import pytest

from umeko.cli import main
from umeko.config import load_settings
from umeko.host.configuration import LEGACY_MODEL_KEYS
from umeko.host.service import AgentService
from umeko.host.storage import Store


def test_configured_database_is_shared_by_cli_and_host(tmp_path, monkeypatch, capsys, test_database_url):
    for key in LEGACY_MODEL_KEYS | {"UMEKO_BASE_PATH", "UMEKO_ADMIN_BASE_PATH", "UMEKO_PUBLIC_URL", "MODEL_CA_FILE"}:
        monkeypatch.delenv(key, raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text("UMEKO_DATABASE_URL=\n", encoding="utf-8")
    monkeypatch.setenv("UMEKO_DATABASE_URL", test_database_url or "")
    monkeypatch.setenv("TEXT_MODEL_NAME", "database-fixture-model")
    monkeypatch.setenv("TEXT_MODEL_API_KEY", "synthetic-provider-key")
    monkeypatch.setenv("TEXT_MODEL_BASE_URL", "https://models.example.invalid/v1")
    data_root = tmp_path / "data"
    settings = load_settings(env_file, data_root)
    assert settings.text_model.name == "database-fixture-model"
    service = AgentService(settings, data_root)
    try:
        assert service.store.backend == ("postgresql" if test_database_url else "sqlite")
        assert (data_root / "umeko.db").exists() == (test_database_url is None)
        monkeypatch.setattr(sys, "argv", ["umeko", "--env", str(env_file), "--data-root", str(data_root), "providers", "list"])
        main()
        output = capsys.readouterr().out
        assert settings.text_model.name in output
        assert "synthetic-provider-key" not in output
        if test_database_url:
            assert test_database_url not in output + repr(settings)
    finally:
        service.run_manager.shutdown()


def test_accounts_history_and_files_survive_store_reopen(tmp_path, test_database_url):
    path = tmp_path / "umeko.db"
    store = Store(path, database_url=test_database_url)
    uid = store.create_user("CaseUser", "synthetic-password")["id"]
    with pytest.raises(ValueError, match="用户名已存在"):
        store.create_user("caseuser", "synthetic-password")
    assert store.authenticate("CASEUSER", "synthetic-password")["id"] == uid
    avatar = b"\x00\xf0\xff"
    store.set_user_avatar(uid, avatar, "image/png")
    token = store.issue_token(uid)
    store.save_session("source", uid, "Source")
    store.add_message("source", "user", "100% ready?")
    store.add_message("source", "assistant", "Yes")
    event = store.add_tool_event("source", "main", "read_document")
    store.complete_tool_event(event, "Synthetic result")
    attachment = tmp_path / "attachment.txt"
    attachment.write_text("synthetic input", encoding="utf-8")
    store.add_session_file("source", "file_original", attachment)
    store.clone_session("source", "clone", uid, "Clone")

    reopened = Store(path, database_url=test_database_url)
    assert reopened.user_for_token(token)["id"] == uid
    assert reopened.user_avatar(uid) == (avatar, "image/png")
    assert reopened.list_users()[0]["session_count"] == 2
    assert [row["content"] for row in reopened.messages("clone")] == ["100% ready?", "Yes"]
    assert reopened.tool_events("source")[0]["result"] == "Synthetic result"
    cloned_files = reopened.session_files("clone")
    assert "file_original" not in cloned_files
    assert list(cloned_files.values()) == [attachment]
    assert reopened.database_bytes() > 0
    reopened.delete_session("source", uid)
    assert reopened.messages("source") == reopened.tool_events("source") == []


def test_invalid_database_url_cannot_fall_back_to_sqlite(tmp_path):
    path = tmp_path / "umeko.db"
    with pytest.raises(ValueError, match="UMEKO_DATABASE_URL") as err:
        Store(path, database_url="invalid://synthetic-credential@db.example.invalid/umeko")
    assert "synthetic-credential" not in str(err.value)
    assert not path.exists()
