"""Bounded, platform-independent file entry operations shared by tools and hosts."""

from __future__ import annotations

import os
from itertools import chain
from pathlib import Path, PureWindowsPath
import shutil
from typing import Iterable

from .cancellation import CancelCheck, raise_if_cancelled


def is_link(path: Path) -> bool:
    """Include Windows junctions and other reparse points, not only symlinks."""
    return path.is_symlink() or bool(getattr(path.lstat(), "st_file_attributes", 0) & 0x400)


def bounded_path(root: Path, path: str | Path, allowed_roots: Iterable[Path] | None = None,
                 *, allow_root: bool = False) -> Path:
    boundary = root.resolve()
    text = str(path)
    if not text.strip() or "\x00" in text:
        raise ValueError("文件路径不能为空")
    if os.name != "nt" and PureWindowsPath(text).drive:
        raise ValueError("文件路径超出安全目录")
    raw = Path(text.replace("\\", "/"))
    candidate = raw if raw.is_absolute() else boundary / raw
    try:
        # Check lexical containment first; do not resolve links before inspecting them.
        relative = candidate.relative_to(boundary)
        current = boundary
        for part in relative.parts:
            current /= part
            if current.exists() or current.is_symlink():
                if is_link(current):
                    raise ValueError("不允许操作符号链接或目录联接")
        candidate = candidate.resolve()
        candidate.relative_to(boundary)
    except ValueError as exc:
        raise ValueError("文件路径超出安全目录或包含链接") from exc
    roots = tuple(Path(item).resolve() for item in (allowed_roots or (boundary,)))
    if not all(item == boundary or boundary in item.parents for item in roots):
        raise ValueError("无有效的安全目录")
    if not any(candidate == item or item in candidate.parents for item in roots):
        raise ValueError("只允许操作当前会话的工作区、附件和产物目录")
    if not allow_root and (candidate == boundary or candidate in roots):
        raise ValueError("不能修改安全目录的顶层节点")
    return candidate


def validate_tree(path: Path, should_cancel: CancelCheck = None) -> None:
    """Reject linked/special entries before a recursive mutation starts."""
    for entry in chain((path,), path.rglob("*") if path.is_dir() else ()):
        raise_if_cancelled(should_cancel)
        if is_link(entry) or not (entry.is_file() or entry.is_dir()):
            raise ValueError("目录中包含链接或非普通文件，已拒绝操作")


def operate_files(operation: str, path: str | Path, target: str | Path = "", *,
                  root: Path, allowed_roots: Iterable[Path] | None = None,
                  recursive: bool = False, overwrite: bool = False,
                  should_cancel: CancelCheck = None) -> Path:
    """Targets are exact paths; existing directories are never merged or replaced."""
    raise_if_cancelled(should_cancel)
    if operation not in {"cp", "mv", "rm", "mkdir"}:
        raise ValueError("operation 只支持 cp、mv、rm、mkdir")
    if not isinstance(recursive, bool) or not isinstance(overwrite, bool):
        raise ValueError("recursive 和 overwrite 必须为布尔值")
    source = bounded_path(root, path, allowed_roots)
    if operation == "mkdir":
        if target or overwrite:
            raise ValueError("mkdir 不接受 target 或 overwrite")
        source.mkdir(parents=recursive)
        return source
    if not source.exists():
        raise FileNotFoundError(str(path))
    validate_tree(source, should_cancel)
    if operation == "rm":
        if target or overwrite:
            raise ValueError("rm 不接受 target 或 overwrite")
        if source.is_dir():
            shutil.rmtree(source) if recursive else source.rmdir()
        else:
            source.unlink()
        return source
    destination = bounded_path(root, target, allowed_roots)
    if source == destination or source in destination.parents:
        raise ValueError("不能复制或移动到自身或自身内部")
    if not destination.parent.is_dir():
        raise ValueError("目标父目录不存在，请先 mkdir")
    if destination.exists() and (not overwrite or source.is_dir() or destination.is_dir()):
        raise ValueError("目标已存在；仅文件支持显式 overwrite=true")
    if operation == "cp":
        if source.is_dir():
            if not recursive:
                raise ValueError("复制目录需要 recursive=true")
            def copy_file(src, dst):
                raise_if_cancelled(should_cancel)
                return shutil.copy2(src, dst)
            try:
                shutil.copytree(source, destination, copy_function=copy_file)
            except BaseException:
                # This is a new, prevalidated destination; never clean an existing target.
                if destination.exists():
                    shutil.rmtree(destination)
                raise
        else:
            shutil.copy2(source, destination)
    else:
        # All nodes are on one session filesystem; rename avoids implicit directory merging.
        source.replace(destination) if overwrite else source.rename(destination)
    return destination
