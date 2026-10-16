"""Read a member from the current session package, or the CLI's skill library."""

from __future__ import annotations

from pathlib import Path

from ..skillpacks import skill_packs_dir
from ..skill_layout import member_path


def _resolve_member(pack: str, member: str, override_dir: Path | None = None) -> Path:
    """校验并解析 skills/<pack>/<member>，防路径穿越。"""
    if not pack or "/" in pack or "\\" in pack or ".." in pack:
        raise ValueError(f"非法技能包名：{pack}")
    base = (override_dir or skill_packs_dir()).resolve()
    target = member_path(base, pack, member)
    try:
        target.relative_to(base)
    except ValueError as e:
        raise ValueError("路径越界") from e
    if not target.is_file():
        raise ValueError(f"文件不存在：{pack}/{member}")
    return target


def read_pack_file(pack: str, member: str, directory: Path | None = None) -> str:
    """工具 handler：读取服务器技能库中包内附属文件内容。"""
    try:
        target = _resolve_member(pack, member, directory)
    except ValueError as e:
        return f"错误：{e}"
    try:
        content = target.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        return f"错误：无法读取：{e}"
    return (
        f"技能包 {pack} 的文件 {member}：\n\n{content}"
    )
