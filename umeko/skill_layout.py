"""Standard skill directories with conservative, idempotent legacy migration."""
from __future__ import annotations

from pathlib import Path
import re
import shutil


def slug(value: str) -> str:
    value = value[:-3] if value.endswith(".md") else value
    if not re.fullmatch(r"[a-zA-Z0-9_-]+", value):
        raise ValueError("非法技能包名")
    return value


def checked(root: Path, relative: str) -> Path:
    root = root.resolve()
    parts = relative.split("/")
    if any(part in {"", ".", ".."} or ":" in part or "\\" in part for part in parts):
        raise ValueError("非法技能文件路径")
    path = root.joinpath(*parts)
    if path.resolve() != path or not path.resolve().is_relative_to(root):
        raise ValueError("技能路径越界或包含链接")
    return path


def entry_path(root: Path, name: str, *, create=False) -> Path:
    name = slug(name)
    standard = checked(root, name + "/SKILL.md")
    legacy = checked(root, name + ".md")
    return standard if create or standard.is_file() or not legacy.is_file() else legacy


def entries(root: Path) -> dict[str, Path]:
    if not root.is_dir():
        return {}
    names = {path.stem for path in root.glob("*.md")} | {path.parent.name for path in root.glob("*/SKILL.md")}
    result = {}
    for name in sorted(names):
        try:
            path = entry_path(root, name)
            if path.is_file():
                result[name] = path
        except ValueError:
            continue
    return result


def category(name: str) -> str:
    suffix = Path(name).suffix.lower()
    return "scripts" if suffix in {".py", ".sh", ".js", ".ts"} else "references" if suffix in {".md", ".markdown"} else "assets"


def member_path(root: Path, pack: str, member: str, *, create=False) -> Path:
    pack = slug(pack)
    if member == "SKILL.md":
        return entry_path(root, pack, create=create)
    if "/" in member:
        if member.split("/", 1)[0] not in {"scripts", "references", "assets"}:
            raise ValueError("成员路径须位于 scripts/references/assets")
        return checked(root, pack + "/" + member)
    legacy = checked(root, pack + "/" + member)
    standard = checked(root, pack + "/" + category(member) + "/" + member)
    if standard.is_file() or create:
        return standard
    return legacy


def migrate_library(root: Path) -> None:
    """Move only unambiguous legacy files, never overwrite customized/new files."""
    if not root.is_dir():
        return
    for name, entry in entries(root).items():
        target = entry_path(root, name, create=True)
        target.parent.mkdir(parents=True, exist_ok=True)
        if entry != target and not target.exists():
            entry.replace(target)
    for package in root.iterdir():
        if not package.is_dir() or package.is_symlink() or not (package / "SKILL.md").is_file():
            continue
        for source in list(package.iterdir()):
            if not source.is_file() or source.name == "SKILL.md" or source.is_symlink():
                continue
            target = member_path(root, package.name, source.name, create=True)
            if not target.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                source.replace(target)


def copy_package(source: Path, target: Path, name: str, content: str, *, refresh=False) -> Path:
    """Dispatch an independent package. Restoring a session preserves its edits."""
    name = slug(name)
    destination = entry_path(target, name, create=True)
    marker = checked(target, "." + name + ".dispatched")
    if destination.exists() and marker.exists() and not refresh:
        return destination
    package = source / name
    if package.is_dir() and not package.is_symlink():
        for path in package.rglob("*"):
            if not path.is_file() or path.is_symlink() or "__pycache__" in path.parts or path.suffix in {".pyc", ".pyo"}:
                continue
            relative = path.relative_to(package).as_posix()
            if relative == "SKILL.md":
                continue
            output = member_path(target, name, relative if "/" in relative else category(relative) + "/" + relative, create=True)
            output.parent.mkdir(parents=True, exist_ok=True)
            if refresh or not output.exists():
                shutil.copyfile(path, output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if refresh or not destination.exists():
        destination.write_text(content, encoding="utf-8")
    marker.write_text("1", encoding="ascii")
    return destination


def file_metadata(root: Path, name: str) -> list[dict]:
    package = checked(root, slug(name))
    result = []
    if package.is_dir():
        for path in sorted(package.rglob("*")):
            if not path.is_file() or "__pycache__" in path.parts or path.suffix in {".pyc", ".pyo"}:
                continue
            relative = path.relative_to(package).as_posix()
            try:
                checked(package, relative)
            except ValueError:
                continue
            stat = path.stat()
            result.append({"name": relative, "path": relative, "size": stat.st_size, "mtime": int(stat.st_mtime)})
    return result
