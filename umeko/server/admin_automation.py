"""Public instructions, never credentials; operations use the existing admin gate."""
import hashlib
from pathlib import Path

from fastapi import HTTPException
from fastapi.responses import FileResponse

from .. import __version__
from .admin_contract import install_admin_contract

SKILL_ROOT = Path(__file__).with_name("admin_skill")
SKILL_ARCHIVE = Path(__file__).with_name("admin_skill.zip")
SKILL_FILES = (
    "SKILL.md", "scripts/admin_api.py", "references/api.md",
    "references/platform.md", "references/configuration.md", "references/agent-publishing.md",
    "references/api-reference.md", "references/openapi-admin.json", "references/schemas.md",
)


def add_admin_automation(app, base_path):
    @app.get("/admin/automation", include_in_schema=False)
    def automation_manifest():
        return {"name": "umeko-server-admin", "format": "agent-skills", "version": __version__,
                "openapi": base_path + "/admin/v1/openapi.json", "authentication": "administrator-cookie",
                "archive": {"url": base_path + "/admin/automation/skill.zip",
                            "filename": "umeko-server-admin.zip", "size": SKILL_ARCHIVE.stat().st_size,
                            "sha256": hashlib.sha256(SKILL_ARCHIVE.read_bytes()).hexdigest()},
                "files": [{"path": name, "url": base_path + "/admin/automation/skill/" + name,
                           "size": (SKILL_ROOT / name).stat().st_size,
                           "sha256": hashlib.sha256((SKILL_ROOT / name).read_bytes()).hexdigest()}
                          for name in SKILL_FILES]}

    @app.get("/admin/automation/skill.zip", include_in_schema=False)
    def automation_skill_archive():
        return FileResponse(SKILL_ARCHIVE, media_type="application/zip", filename="umeko-server-admin.zip",
                            headers={"Cache-Control": "no-cache"})

    @app.get("/admin/automation/skill/{member:path}", include_in_schema=False)
    def automation_skill_file(member: str):
        if member not in SKILL_FILES:
            raise HTTPException(404, "管理 Skill 文件不存在")
        return FileResponse(SKILL_ROOT / member, media_type="text/plain; charset=utf-8",
                            filename=Path(member).name, headers={"Cache-Control": "no-cache"})

    @app.get("/admin/v1/openapi.json", tags=["admin automation"])
    def admin_schema() -> dict:
        return app.openapi()

    install_admin_contract(app, base_path)
