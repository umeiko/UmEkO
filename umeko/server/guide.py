"""The packaged, offline user handbook; separate from developer API explorers."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.requests import Request
from starlette.responses import RedirectResponse


GUIDE_DIR = Path(__file__).with_name("static") / "guide"


def guide_url(public_url: str | None, base_path: str = "") -> str:
    """Use the configured user public base, or the current surface's prefix."""
    return (public_url.rstrip("/") if public_url else base_path) + "/guide/"


def add_guide(app: FastAPI) -> None:
    @app.get("/guide", include_in_schema=False)
    def guide_redirect(request: Request):
        return RedirectResponse(request.url.replace(path=request.url.path + "/"))

    # All generated links are relative, so one build serves either runtime prefix.
    app.mount("/guide", StaticFiles(directory=GUIDE_DIR, html=True, check_dir=False), name="guide")
