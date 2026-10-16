"""Install bundled skills and upgrade known stock files without overriding admin choices."""
from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
import tempfile

from ..skillpacks import parse_skill_pack_text
from ..skillassets import skill_members
from ..skill_layout import entry_path, member_path, migrate_library, entries
from .builtin_agents import ASSETS, IMAGE_QC_SKILL


def asset_path(root, relative):
    parts = relative.split("/", 1)
    return entry_path(root, parts[0]) if len(parts) == 1 else member_path(root, parts[0], parts[1])


def installation_key(filename: str) -> str:
    return "BUILTIN_SKILL_INSTALLED_" + filename


def _upgrade_stock_assets(store, library_dir: Path) -> bool:
    """Upgrade only exact known stock files, preserving customizations and deletions."""
    manifest = ASSETS / "stock-upgrades.json"
    if not manifest.is_file():
        return False
    changed = False
    upgrades = json.loads(manifest.read_text(encoding="utf-8"))
    sources = {relative: asset_path(ASSETS, relative) for relative in upgrades}
    known_sources = {source: upgrades[relative] for relative, source in sources.items()}
    for name in entries(ASSETS):
        for member, source in skill_members(ASSETS, name).items():
            alias = name + "/" + member
            if source in known_sources and alias not in upgrades:
                sources[alias], upgrades[alias] = source, known_sources[source]
    for relative, known in upgrades.items():
        source, target = sources[relative], asset_path(library_dir, relative)
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
    migrate_library(library_dir)
    installed = False
    for name, entry in entries(ASSETS).items():
        # This existing default has its own agent bootstrap and stock-upgrade policy.
        identity = name + ".md"
        if identity == IMAGE_QC_SKILL or store.config().get(installation_key(identity)) == "1":
            continue
        sources = {"SKILL.md": entry, **skill_members(ASSETS, name)}
        for relative, source in sources.items():
            target = member_path(library_dir, name, relative, create=True)
            target.parent.mkdir(parents=True, exist_ok=True)
            try:
                with target.open("xb") as output:
                    output.write(source.read_bytes())
            except FileExistsError:
                pass
        content = entry_path(library_dir, name).read_text(encoding="utf-8")
        if parse_skill_pack_text(content) is None:
            raise ValueError(f"默认技能格式无效，请检查 {entry.name}")
        if store.default_skill(identity) is None:
            store.upsert_default_skill(identity, content)
            # Visible in administration. Agent bootstrap may enable new dependencies.
            store.set_default_skill_enabled(identity, False)
        store.set_config({installation_key(identity): "1"})
        installed = True
    return _upgrade_stock_assets(store, library_dir) or installed
