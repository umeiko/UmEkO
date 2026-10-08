"""Serve the bundled Vue entries with a runtime deployment prefix."""

from html import escape
from pathlib import Path

UI_DIR = Path(__file__).with_name("static") / "ui"


def render_ui(entry: str, base_path: str = "") -> str:
    template = (UI_DIR / entry).read_text(encoding="utf-8")
    prefix = escape(base_path, quote=True)
    return template.replace("__UMEKO_BASE_PATH__", prefix).replace(
        '="./assets/', f'="{prefix}/static/ui/assets/'
    )
