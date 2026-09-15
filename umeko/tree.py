"""共享目录树遍历核心：Agent 的 list_dir 与 WebUI 的 workspace_tree 共用。

兜底设计（两套消费端同一套护栏）：
- 每目录最多展示 max_per_dir 项，其余折叠进 omitted 计数；
- 整树访问条目上限 max_total，超限整树截断（防病态大目录拖死会话）；
- 目录深度上限 max_depth，更深的目录折叠不展开；
- 跳过 .git/node_modules 等垃圾目录与隐藏项；
- glob / 正则过滤：仅对文件名生效（目录始终保留，保证树可下钻），
  被滤掉的文件计入 omitted，用户能感知"有东西但被滤掉了"。
"""

from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass, field
from pathlib import Path

SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__"}

MAX_PER_DIR = 50    # 单目录最多展示的子项数
MAX_TOTAL = 4000    # 整树最多访问的条目数（含被跳过/过滤的）
MAX_DEPTH = 24      # 目录树最大深度


def compile_filter(pattern: str | None) -> re.Pattern | None:
    """把过滤串编译为对「文件名」匹配的正则。

    - ``glob:xxx`` 前缀 → glob 语义（如 glob:image-*）；
    - 含 ``*`` / ``?`` 的裸串 → 按 glob 处理（如 image-*）；
    - 其余 → 按正则处理（如 ^image-\\d+$），非法正则抛 ValueError；
    - 空串 / None → 不过滤。
    """
    if not pattern:
        return None
    text = pattern.strip()
    if not text:
        return None
    if text.startswith("glob:"):
        glob = text[5:].strip()
        return re.compile(fnmatch.translate(glob)) if glob else None
    if "*" in text or "?" in text:
        return re.compile(fnmatch.translate(text))
    try:
        return re.compile(text)
    except re.error as e:
        raise ValueError(
            f"过滤表达式不合法：{e}。可用 glob（如 image-*）或正则（如 ^image-\\d+$）。"
        ) from e


@dataclass
class TreeBudget:
    """跨目录共享的预算计数器。"""
    visited: int = 0
    truncated: bool = False
    max_total: int = MAX_TOTAL
    max_per_dir: int = MAX_PER_DIR
    max_depth: int = MAX_DEPTH


@dataclass
class TreeNode:
    """遍历产物：文本树渲染（list_dir）与 JSON 序列化（workspace_tree）共用。"""
    name: str
    path: str                      # 相对根的 posix 路径（根本身为 "."）
    is_dir: bool
    size: int | None = None
    children: list["TreeNode"] = field(default_factory=list)
    omitted: int = 0               # 该目录被折叠（超上限/被过滤）的子项数
    children_truncated: bool = False  # 因整树预算/深度上限被截断


def _list_level(
    directory: Path,
    budget: TreeBudget,
    rx: re.Pattern | None,
) -> tuple[list[TreeNode], int]:
    """列出单层目录的子项（目录优先、按名排序），返回 (入选, 折叠数)。"""
    try:
        entries = sorted(
            directory.iterdir(),
            key=lambda p: (not p.is_dir(), p.name.casefold()),
        )
    except OSError:
        return [], 0
    nodes: list[TreeNode] = []
    omitted = 0
    for index, entry in enumerate(entries):
        budget.visited += 1
        if budget.visited > budget.max_total:
            budget.truncated = True
            omitted += len(entries) - index
            break
        if entry.name.startswith(".") or entry.name in SKIP_DIRS:
            continue
        if entry.is_dir():
            nodes.append(TreeNode(name=entry.name, path="", is_dir=True))
        else:
            if rx is not None and not rx.search(entry.name):
                omitted += 1
                continue
            try:
                size = entry.stat().st_size
            except OSError:
                size = None
            nodes.append(TreeNode(name=entry.name, path="", is_dir=False, size=size))
        if len(nodes) >= budget.max_per_dir:
            omitted += len(entries) - index - 1
            break
    return nodes, omitted


def build_tree(
    root: Path,
    budget: TreeBudget | None = None,
    pattern: str | None = None,
    _depth: int = 0,
    _prefix: str = "",
) -> TreeNode:
    """递归构建 root 的树；返回根 TreeNode（root 自身不计预算）。

    节点 path 为相对 root 的 posix 路径；根节点 path 为 "."。
    """
    budget = budget or TreeBudget()
    label = root.name if _prefix == "" and _depth == 0 else _prefix.rstrip("/")
    node = TreeNode(name=root.name, path=label or ".", is_dir=True)
    if _depth >= budget.max_depth:
        node.children_truncated = True
        return node
    rx = compile_filter(pattern)
    children, omitted = _list_level(root, budget, rx)
    node.omitted = omitted
    child_prefix = f"{_prefix}{root.name}/" if _prefix else f"{root.name}/"
    # 根的显示名可能不同于真实目录名（如 workspace_tree 的可读根），
    # 但子项 path 一律从根名起算，保持与 WebUI 现有 path 语义一致。
    for child in children:
        if child.is_dir:
            node.children.append(
                build_tree(
                    root / child.name,
                    budget=budget,
                    pattern=pattern,
                    _depth=_depth + 1,
                    _prefix=child_prefix,
                )
            )
        else:
            child.path = f"{child_prefix}{child.name}"
            node.children.append(child)
    if budget.truncated:
        node.children_truncated = True
    return node


def format_size(size: int | None) -> str:
    if size is None:
        return "?"
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / (1024 * 1024):.1f} MB"


def render_text(
    node: TreeNode,
    max_level: int = 2,
    _prefix: str = "",
    _level: int = 0,
) -> str:
    """把 TreeNode 渲染成 Agent 可读的文本树（list_dir 的输出）。

    最多展开 max_level 层；更深的目录显示下钻提示。根节点自身不计层数。
    """
    lines: list[str] = []
    for index, child in enumerate(node.children):
        last = index == len(node.children) - 1
        branch = "└── " if last else "├── "
        connector = "    " if last else "│   "
        if child.is_dir:
            if _level < max_level - 1:
                lines.append(f"{_prefix}{branch}{child.name}/")
                body = render_text(child, max_level, _prefix + connector, _level + 1)
                if body:
                    lines.append(body)
            else:
                lines.append(
                    f"{_prefix}{branch}{child.name}/ "
                    f"（更深内容已折叠：list_dir 传该目录路径可下钻）"
                )
        else:
            size = f" ({format_size(child.size)})" if child.size is not None else ""
            lines.append(f"{_prefix}{branch}{child.name}{size}")
    if node.omitted:
        lines.append(
            f"{_prefix}…（其余 {node.omitted} 项被折叠："
            "指定该目录可查看，或用 filter 过滤）"
        )
    if node.children_truncated and not node.children:
        lines.append(f"{_prefix}…（目录过深或过大，已截断）")
    return "\n".join(lines)
