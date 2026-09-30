"""Use production config/Provider resolution with an isolated, fake-model registry."""
import os
import time
from pathlib import Path

from fastapi import HTTPException, Request

from umeko import events
from umeko.config import load_settings
from umeko.host.storage import Store
from umeko.server.app import create_app


def create_lab_app():
    root = Path(os.environ["UMEKO_LAB_RUNTIME"])
    data = root / os.environ.get("UMEKO_LAB_DATA_NAME", "data")
    store = Store(data / "umeko.db")
    if not store.list_providers():
        store.import_providers({"providers": [{
            "name": "lab", "base_url": os.environ.get("UMEKO_LAB_MODEL_URL", "https://localhost:19443/v1"),
            "api_key": "local-test-only", "models": [{"name": "lab-model", "vision": False}],
        }], "active": "lab/lab-model"})
    settings = load_settings(root / "lab.env", data_root=data)
    app = create_app(settings, workspace_root=data / "output")

    @app.post("/v1/__lab/sessions/{session_id}/stream-fixture", status_code=202)
    def stream_fixture(session_id: str, request: Request):
        service = app.state.agent_service
        if app.state.store.session(session_id, request.state.user["id"]) is None:
            raise HTTPException(404, "Unknown lab session")
        run = service.run_manager.create(session_id)

        def work():
            run.emit(events.RUN_STARTED)
            for text in ("LOCAL_", "STREAM_", "OK"):
                time.sleep(0.4)
                run.emit(events.ASSISTANT_DELTA, text=text)
            run.finish("completed", reply="LOCAL_STREAM_OK")

        service.run_manager.submit(run, work)
        return {"id": run.id, "fixture": True}

    return app
