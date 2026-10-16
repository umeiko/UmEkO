"""Resolve shared bundled resources into self-contained, editable skill packages."""
from __future__ import annotations

import json
from pathlib import Path
from .skill_layout import category, member_path


def skill_members(root: Path, name: str) -> dict[str, Path]:
    """Return package-relative names and sources; sharing never grants another skill."""
    root = root.resolve()
    package = root / name
    members = {path.relative_to(package).as_posix(): path for path in sorted(package.rglob("*"))
               if path.is_file() and path.name != "SKILL.md" and "__pycache__" not in path.parts and path.suffix not in {".pyc", ".pyo"}}
    manifest = root / "shared-assets.json"
    shared = json.loads(manifest.read_text(encoding="utf-8")).get(name, {}) if manifest.is_file() else {}
    for dependency, filenames in shared.items():
        for filename in filenames:
            source = member_path(root, dependency, filename)
            relative = source.relative_to(root / dependency).as_posix()
            if "/" not in relative:
                relative = category(filename) + "/" + filename
            if (Path(filename).name != filename or dependency not in {p.name for p in root.iterdir() if p.is_dir()}
                    or source.is_symlink() or not source.resolve().is_relative_to(root)
                    or not source.is_file() or relative in members):
                raise ValueError(f"Invalid shared skill resource: {name}/{filename}")
            members[relative] = source
    return members
