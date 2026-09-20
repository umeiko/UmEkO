"""read_pack_file：按需读取技能包附属文件（渐进式播种，不落盘会话）。

会话只播种主 md（提示词）；包内附属文档（数据清单等）通过本工具
从服务器技能库按需读取，内容直接注入当前对话上下文（不拷贝到会话目录）。
好处：会话磁盘占用最小；附属文件永远读到服务器最新版。
"""

from __future__ import annotations

from pathlib import Path

from ..skillpacks import skill_packs_dir


def _resolve_member(pack: str, member: str, override_dir: Path | None = None) -> Path:
    """校验并解析 skills/<pack>/<member>，防路径穿越。"""
    if not pack or "/" in pack or "\\" in pack or ".." in pack:
        raise ValueError(f"非法技能包名：{pack}")
    name = Path(member).name
    if name != member or not name:
        raise ValueError(f"非法文件名（不带路径）：{member}")
    base = (override_dir or skill_packs_dir()).resolve()
    target = (base / pack / name).resolve()
    try:
        target.relative_to(base)
    except ValueError as e:
        raise ValueError("路径越界") from e
    if not target.is_file():
        raise ValueError(f"文件不存在：{pack}/{name}")
    return target


def read_pack_file(pack: str, member: str) -> str:
    """工具 handler：读取服务器技能库中包内附属文件内容。"""
    try:
        target = _resolve_member(pack, member)
    except ValueError as e:
        return f"错误：{e}"
    try:
        content = target.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        return f"错误：无法读取：{e}"
    return (
        f"技能包 {pack} 的附属文件 {member}（服务器最新版）：\n\n{content}"
    )
