"""Install bundled skills once without creating agents or overriding admin choices."""
from __future__ import annotations

from pathlib import Path

from ..skillpacks import parse_skill_pack_text
from .builtin_agents import ASSETS, IMAGE_QC_SKILL


def installation_key(filename: str) -> str:
    return "BUILTIN_SKILL_INSTALLED_" + filename


def install_builtin_skills(store, library_dir: Path) -> bool:
    """Discover packages from bundled files; no domain tools or agent registrations."""
    installed = False
    for entry in sorted(ASSETS.glob("*.md")):
        # This existing default has its own agent bootstrap and stock-upgrade policy.
        if entry.name == IMAGE_QC_SKILL or store.config().get(installation_key(entry.name)) == "1":
            continue
        sources = [entry, *sorted((ASSETS / entry.stem).rglob("*"))]
        for source in sources:
            if not source.is_file() or "__pycache__" in source.parts:
                continue
            target = library_dir / source.relative_to(ASSETS)
            target.parent.mkdir(parents=True, exist_ok=True)
            try:
                with target.open("xb") as output:
                    output.write(source.read_bytes())
            except FileExistsError:
                pass
        content = (library_dir / entry.name).read_text(encoding="utf-8")
        if parse_skill_pack_text(content) is None:
            raise ValueError(f"默认技能格式无效，请检查 {entry.name}")
        if store.default_skill(entry.name) is None:
            store.upsert_default_skill(entry.name, content)
            # Visible in administration. Agent bootstrap may enable new dependencies.
            store.set_default_skill_enabled(entry.name, False)
        store.set_config({installation_key(entry.name): "1"})
        installed = True
    return installed
