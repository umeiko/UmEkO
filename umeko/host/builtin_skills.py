"""Install bundled skills and upgrade known stock files without overriding admin choices."""
from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
import tempfile

from ..skillpacks import parse_skill_pack_text
from .builtin_agents import ASSETS, IMAGE_QC_SKILL


def installation_key(filename: str) -> str:
    return "BUILTIN_SKILL_INSTALLED_" + filename


def _upgrade_stock_assets(store, library_dir: Path) -> bool:
    """Upgrade only exact known stock files, preserving customizations and deletions."""
    manifest = ASSETS / "stock-upgrades.json"
    if not manifest.is_file():
        return False
    changed = False
    for relative, known in json.loads(manifest.read_text(encoding="utf-8")).items():
        source, target = ASSETS / relative, library_dir / relative
        entry = Path(relative).name if len(Path(relative).parts) == 1 else Path(relative).parts[0] + ".md"
        if store.config().get(installation_key(entry)) != "1" or store.default_skill(entry) is None:
            continue
        if not source.is_file() or not target.is_file() or target.is_symlink():
            continue
        if not source.resolve().is_relative_to(ASSETS.resolve()) or not target.resolve().is_relative_to(library_dir.resolve()):
            continue
        old, new = target.read_bytes(), source.read_bytes()
        stock = {hashlib.sha256(old).hexdigest(), hashlib.sha256(old.replace(b"\r\n", b"\n")).hexdigest()}
        if old != new and stock.intersection(known):
            temporary = None
            try:
                with tempfile.NamedTemporaryFile(dir=target.parent, prefix=".skill-upgrade-", delete=False) as output:
                    temporary = Path(output.name)
                    output.write(new)
                temporary.replace(target)
            except OSError:
                logging.getLogger(__name__).warning("Could not upgrade stock skill asset %s", relative, exc_info=True)
                continue
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)
            changed = True
        elif old != new:
            continue
        if relative == entry:
            content = store.default_skill(entry)
            latest = new.decode("utf-8").replace("\r\n", "\n")
            content_hashes = {hashlib.sha256(content.encode("utf-8")).hexdigest(),
                              hashlib.sha256(content.replace("\r\n", "\n").encode("utf-8")).hexdigest()}
            if content != latest and content_hashes.intersection(known):
                store.upsert_default_skill(entry, latest)
                changed = True
    return changed


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
    return _upgrade_stock_assets(store, library_dir) or installed
