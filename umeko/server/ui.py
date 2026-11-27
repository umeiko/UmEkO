"""Load a frontend release independently of its source or build tools."""

from html import escape
from pathlib import Path

from fastapi import HTTPException
from fastapi.staticfiles import StaticFiles

UI_DIR = Path(__file__).with_name("static") / "ui"


def ui_directory(settings) -> Path | None:
    if not settings.serve_ui:
        return None
    directory = Path(settings.ui_dir).expanduser().resolve() if settings.ui_dir else UI_DIR
    for entry in ("index.html", "admin.html"):
        if not (directory / entry).is_file():
            raise RuntimeError(f"前端成品缺少 {entry}，请检查 UMEKO_UI_DIR 或设置 UMEKO_SERVE_UI=false")
    if not (directory / "assets").is_dir():
        raise RuntimeError("前端成品缺少 assets 目录，请检查 UMEKO_UI_DIR")
    return directory


def mount_ui(app, directory: Path | None) -> None:
    if directory is not None:
        app.mount("/static/ui", StaticFiles(directory=directory), name="ui")


def render_ui(entry: str, base_path: str = "", *, temporary_path: str = "", guide_url: str = "",
              directory: Path | None = UI_DIR) -> str:
    if directory is None:
        raise HTTPException(404, "此服务仅提供 API")
    template = (directory / entry).read_text(encoding="utf-8")
    prefix = escape(base_path, quote=True)
    rendered = template.replace("__UMEKO_BASE_PATH__", prefix).replace(
        '="./assets/', f'="{prefix}/static/ui/assets/'
    )
    rendered = rendered.replace(
        "</head>", '<meta name="umeko-guide-url" content="'
        + escape(guide_url or base_path + "/guide/", quote=True) + '"></head>'
    )
    if temporary_path:
        rendered = rendered.replace("</head>", '<meta name="umeko-temporary-path" content="' + escape(temporary_path, quote=True) + '"></head>')
    return rendered
