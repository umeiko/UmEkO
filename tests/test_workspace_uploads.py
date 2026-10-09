from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from umeko.config import ModelConfig, Settings
from umeko.server.app import create_app


@pytest.mark.parametrize("prefix", ["", "/doc-master/consistency/image-text"])
def test_upload_destinations_and_file_boundaries(tmp_path, prefix):
    app = create_app(
        Settings(
            ModelConfig("fixture", "unused-key", "http://unused.invalid"),
            base_path=prefix,
        ),
        data_root=tmp_path / "data",
        workspace_root=tmp_path / "output",
    )
    with TestClient(app) as client:
        client.post(
            prefix + "/v1/auth/register",
            json={"username": "file-owner", "password": "fixture-pass"},
        ).raise_for_status()
        sid = client.post(prefix + "/v1/sessions", json={}).json()["id"]
        base = prefix + f"/v1/sessions/{sid}/workspace"
        root = app.state.agent_service.get_session(sid).root
        for directory in ("workspace", "attachments", "generate"):
            response = client.post(
                base + "/files",
                params={"filename": "from-desktop.txt", "path": directory},
                content=b"desktop content",
            )
            assert response.status_code == 201, response.text
            assert response.json()["path"] == directory + "/from-desktop.txt"
            assert (root / response.json()["path"]).read_bytes() == b"desktop content"
        response = client.post(
            base + "/files", params={"filename": "default.txt"}, content=b"default folder"
        )
        assert response.status_code == 201
        assert response.json()["path"] == "workspace/default.txt"
        client.post(
            base + "/entries", json={"path": "generate/reports", "type": "directory"}
        ).raise_for_status()
        response = client.post(
            base + "/files",
            params={"filename": "nested.txt", "path": "generate/reports"},
            content=b"nested",
        )
        assert response.status_code == 201
        assert response.json()["path"] == "generate/reports/nested.txt"
        # Existing files are preserved and duplicate uploads get a different name.
        response = client.post(
            base + "/files",
            params={"filename": "from-desktop.txt", "path": "attachments"},
            content=b"second version",
        )
        assert response.status_code == 201
        assert response.json()["path"] == "attachments/from-desktop_1.txt"
        assert (root / "attachments/from-desktop.txt").read_bytes() == b"desktop content"
        for directory in ("../outside", "client", "generate/missing", "workspace/default.txt"):
            response = client.post(
                base + "/files",
                params={"filename": "blocked.txt", "path": directory},
                content=b"not saved",
            )
            assert response.status_code == 400, response.text
        for directory in ("workspace", "attachments", "generate"):
            assert client.delete(base + "/entries", params={"path": directory}).status_code == 400
            assert (root / directory).is_dir()
        # A second cookie jar uses the already-running app lifespan.
        other = TestClient(app)
        try:
            other.post(
                prefix + "/v1/auth/register",
                json={"username": "other-owner", "password": "fixture-pass"},
            ).raise_for_status()
            response = other.post(
                base + "/files",
                params={"filename": "blocked.txt", "path": "generate"},
                content=b"not saved",
            )
            assert response.status_code == 404
            assert not (root / "generate/blocked.txt").exists()
        finally:
            other.close()
