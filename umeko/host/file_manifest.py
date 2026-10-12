"""Bounded file metadata snapshots. No content reads and no agent rehydration."""
from __future__ import annotations

from datetime import datetime, timezone
import os
from pathlib import Path, PurePosixPath
import stat

ROOTS = ("workspace", "attachments", "generate")
MAX_ENTRIES = 4000
MAX_DEPTH = 24


def timestamp(value=None):
    try:
        return datetime.fromtimestamp(value, timezone.utc).isoformat() if value is not None else datetime.now(timezone.utc).isoformat()
    except (ValueError, OverflowError, OSError):
        return None


def _linked(info):
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & 0x400)


def session_root(data_root, user_id, session_id):
    # IDs must be single path components; reject reparse points in the session ancestry.
    if any(not value or any(char in value for char in '/\\:\x00') or value in {".", ".."}
           for value in (user_id, session_id)):
        return None
    base = Path(data_root).resolve()
    current = base
    for name in ("users", user_id, "sessions", session_id):
        current = current / name
        try:
            if _linked(current.lstat()) or not current.resolve().is_relative_to(base):
                return None
        except OSError:
            return None
    return current


def _totals(roots):
    files, directories, size = 0, 0, 0
    pending = list(roots)
    while pending:
        node = pending.pop()
        if node["type"] == "file":
            files += 1
            size += node.get("size") or 0
        elif node["type"] == "directory":
            directories += 1
            pending.extend(node.get("children", []))
    return {"file_count": files, "directory_count": directories, "total_size": size}


def capture(root, *, max_entries=MAX_ENTRIES, max_depth=MAX_DEPTH):
    root = Path(root)
    try:
        if _linked(root.lstat()) or not root.is_dir():
            return None
    except OSError:
        return None
    base = root.resolve()
    state = {"visited": 0, "complete": True}

    def walk(path, relative, depth):
        try:
            info = path.lstat()
            if _linked(info):
                return {"name": path.name, "path": relative, "type": "link", "size": None, "modified_at": timestamp(info.st_mtime)}
            if not path.resolve().is_relative_to(base):
                state["complete"] = False
                return None
            if stat.S_ISREG(info.st_mode):
                return {"name": path.name, "path": relative, "type": "file", "size": info.st_size, "modified_at": timestamp(info.st_mtime)}
            if not stat.S_ISDIR(info.st_mode):
                state["complete"] = False
                return None
            node = {"name": path.name, "path": relative, "type": "directory", "size": None,
                    "modified_at": timestamp(info.st_mtime), "children": []}
            if depth >= max_depth:
                state["complete"] = False
                node["truncated"] = True
                return node
            # Bound the directory iterator too; do not materialize a million-entry directory.
            entries = []
            with os.scandir(path) as iterator:
                for entry in iterator:
                    if state["visited"] >= max_entries:
                        state["complete"] = False
                        node["truncated"] = True
                        break
                    state["visited"] += 1
                    entries.append((entry.name, entry.is_dir(follow_symlinks=False)))
            for name, _ in sorted(entries, key=lambda item: (not item[1], item[0].casefold())):
                child = walk(path / name, relative + "/" + name, depth + 1)
                if child is not None:
                    node["children"].append(child)
            return node
        except OSError:
            state["complete"] = False
            return None

    roots = []
    for name in ROOTS:
        node = walk(root / name, name, 0)
        if node is not None:
            roots.append(node)
    return {"roots": roots, "captured_at": timestamp(), "complete": state["complete"], **_totals(roots)}


def recorded_files(payload, artifacts, captured_at):
    """A clearly partial legacy/submitted inventory, without inventing filesystem stats."""
    roots = [{"name": name, "path": name, "type": "directory", "size": None,
              "modified_at": None, "children": []} for name in ROOTS]
    by_path = {node["path"]: node for node in roots}
    count = 0
    for index, item in enumerate(payload.get("files", [])):
        name = item.get("name", "")
        if not name or any(char in name for char in '/\\:\x00') or name in {".", ".."}:
            continue
        by_path["attachments"]["children"].append({"id": f"input:{index}", "name": name,
            "path": "attachments/" + name, "type": "file", "size": item.get("size"), "modified_at": None})
        count += 1
    for item in artifacts:
        if count >= MAX_ENTRIES:
            break
        path = PurePosixPath(item["name"])
        if path.is_absolute() or ".." in path.parts or not 2 <= len(path.parts) <= MAX_DEPTH + 2 or path.parts[0] not in ROOTS or "\\" in item["name"]:
            continue
        for index in range(2, len(path.parts)):
            relative = "/".join(path.parts[:index])
            if relative not in by_path:
                node = {"name": path.parts[index - 1], "path": relative, "type": "directory",
                        "size": None, "modified_at": None, "children": []}
                by_path["/".join(path.parts[:index - 1])]["children"].append(node)
                by_path[relative] = node
                count += 1
                if count >= MAX_ENTRIES:
                    break
        if count >= MAX_ENTRIES:
            break
        by_path[str(path.parent)]["children"].append({"name": path.name, "path": path.as_posix(),
            "type": "file", "size": item["size"], "modified_at": None})
        count += 1
    return {"roots": roots, "captured_at": captured_at, "complete": False, **_totals(roots)}
