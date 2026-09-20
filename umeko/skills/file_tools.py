"""内置文件工具：文件读取/查找/写入/替换/搜索、读图/OCR、工作文档、Skill 挂载。

领域工具（如作图、领域状态查看）不进基座，由各领域项目以 extra_skills 注入。
"""

from __future__ import annotations

import difflib
import re
from functools import partial
from pathlib import Path
from typing import Callable, Iterable, Protocol

from ..cancellation import CancelCheck, raise_if_cancelled
from ..images import validate_image
from ..llm import LLMClient
from ..session import Session
from ..tree import build_tree, render_text
from .base import Skill
from .script_runner import run_skill_script

_MAX_DOC_BYTES = 200 * 1024
_MAX_FIND_RESULTS = 20
_MAX_GREP_RESULTS = 50
_MAX_LIST_ENTRIES = 200
_MAX_FIND_WALK = 5000  # 最多遍历的文件数，防止在大目录里卡死
_SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__"}
_DOC_WARN_BYTES = 20 * 1024  # 超过该大小的文件默认只返回开头预览，保护上下文
_HEAD_TOKENS = 100  # 截断预览的估算 token 数
_GREP_TRUNC_TOKENS = 2000  # grep 输出估算 token 超过此值视为超大，需截断


def _estimate_tokens(text: str) -> float:
    """与 main_agent 一致的粗略估算：CJK 计 1，其他计 0.25。"""
    return sum(1.0 if ord(char) >= 0x2E80 else 0.25 for char in text)


def _head_by_tokens(text: str, max_tokens: float = _HEAD_TOKENS) -> str:
    """截取开头约 max_tokens 个估算 token 的文本。"""
    budget = 0.0
    for index, char in enumerate(text):
        budget += 1.0 if ord(char) >= 0x2E80 else 0.25
        if budget >= max_tokens:
            return text[: index + 1]
    return text


def _format_file_size(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / (1024 * 1024):.1f} MB"


def _display_read_path(path: Path, root: Path | None) -> str:
    """Server 返回 Session 相对路径；本地 TUI 保留历史绝对路径表现。"""
    resolved = path.resolve()
    if root is not None:
        try:
            relative = resolved.relative_to(Path(root).resolve())
            return relative.as_posix() or "."
        except ValueError:
            # 正常情况下会先被 resolve_readable_path 拒绝；这里不回显意外绝对路径。
            return path.name
    return str(resolved)


def resolve_readable_path(
    path: str | Path,
    root: Path | None = None,
    readable_roots: Iterable[Path] | None = None,
    *,
    allow_root: bool = False,
) -> Path:
    """Resolve a read path and enforce an optional sandbox boundary.

    CLI callers keep the historical unrestricted behavior by omitting ``root``.
    Server callers pass the current Session root plus its user-visible subdirs.
    """
    raw = Path(path)
    if root is None:
        return raw.resolve()
    boundary = Path(root).resolve()
    candidate = (raw if raw.is_absolute() else boundary / raw).resolve()
    try:
        candidate.relative_to(boundary)
    except ValueError as exc:
        raise ValueError("只允许读取当前 Session 内的文件") from exc
    allowed = tuple(Path(item).resolve() for item in (readable_roots or (boundary,)))
    if candidate == boundary and allow_root:
        return candidate
    if not any(candidate == item or item in candidate.parents for item in allowed):
        raise ValueError("只允许读取当前 Session 的工作区、附件和产物目录")
    return candidate


def _search_roots(
    directory: str,
    root: Path | None,
    readable_roots: Iterable[Path] | None,
) -> list[Path]:
    search_root = resolve_readable_path(
        directory, root, readable_roots, allow_root=True
    )
    if root is not None and search_root == Path(root).resolve() and readable_roots:
        return [Path(item).resolve() for item in readable_roots if Path(item).is_dir()]
    return [search_root]


def _valid_file_glob(file_glob: str) -> bool:
    normalized = file_glob.replace("\\", "/")
    return (
        not Path(file_glob).is_absolute()
        and not normalized.startswith("/")
        and ".." not in normalized.split("/")
    )


def _writable_path(path: str, root: Path, display_root: Path | None = None) -> Path:
    """写操作安全边界：只允许写产物目录内的文件；相对路径按产物目录解析。

    Server 模式下模型被引导使用 Session 相对路径（如 generate/a.md），
    此时首段与产物目录名重复，按 display_root（Session 根）解析，避免
    生成 generate/generate/a.md 的嵌套。
    """
    p = Path(path)
    if not p.is_absolute():
        if (
            display_root is not None
            and p.parts
            and p.parts[0] == root.name
        ):
            p = Path(display_root) / p
        else:
            p = root / p
    p = p.resolve()
    if p != root and root not in p.parents:
        raise ValueError(f"只允许写入产物目录（{root}）内的文件：{path}")
    return p


def write_file(
    path: str, content: str, root: Path, display_root: Path | None = None,
    should_cancel: CancelCheck = None,
) -> str:
    raise_if_cancelled(should_cancel)
    try:
        p = _writable_path(path, root, display_root)
    except ValueError as e:
        return f"错误：{e}"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return (
        f"文件已写入（{len(content)} 字符）："
        f"{_display_read_path(p, display_root)}"
    )


def replace_in_file(path: str, old_text: str, new_text: str, root: Path,
                    replace_all: bool = False,
                    display_root: Path | None = None,
                    should_cancel: CancelCheck = None) -> str:
    raise_if_cancelled(should_cancel)
    try:
        p = _writable_path(path, root, display_root)
    except ValueError as e:
        return f"错误：{e}"
    if not p.is_file():
        return f"错误：文件不存在：{path}"
    text = p.read_text(encoding="utf-8")
    count = text.count(old_text)
    if count == 0:
        return f"错误：在 {path} 中未找到要替换的文本（注意需与文件内容完全一致）"
    if count > 1 and not replace_all:
        return (
            f"错误：要替换的文本在 {path} 中出现 {count} 处，请提供更长的上下文"
            "保证唯一匹配，或确认要全部替换（replace_all=true）。"
        )
    text = text.replace(old_text, new_text) if replace_all \
        else text.replace(old_text, new_text, 1)
    p.write_text(text, encoding="utf-8")
    return (
        f"已在 {_display_read_path(p, display_root)} 中完成 "
        f"{count if replace_all else 1} 处替换。"
    )


def grep_files(
    pattern: str,
    directory: str = ".",
    file_glob: str = "",
    path: str = "",
    force_read: bool = False,
    root: Path | None = None,
    readable_roots: Iterable[Path] | None = None,
    should_cancel: CancelCheck = None,
    allow_force_read: bool = False,
) -> str:
    raise_if_cancelled(should_cancel)
    if force_read and not allow_force_read:
        return (
            "错误：force_read 仅限子 Agent 使用。"
            "请改用 delegate_task 派子 Agent 执行全文检索并总结要点。"
        )
    try:
        rx = re.compile(pattern)
    except re.error as e:
        return f"错误：正则表达式不合法：{e}"
    if file_glob and not _valid_file_glob(file_glob):
        return "错误：文件名过滤条件不能越出当前 Session"
    results: list[str] = []
    if path:
        # 只搜单个文件（模型想查某一个文件时直接给 path，无需 directory+file_glob）
        try:
            target = resolve_readable_path(path, root, readable_roots)
        except ValueError as e:
            return f"错误：{e}"
        if not target.is_file():
            return f"错误：文件不存在：{path}"
        try:
            lines = target.read_text(encoding="utf-8").splitlines()
        except (UnicodeDecodeError, OSError):
            return f"错误：不是 UTF-8 文本文件：{path}"
        size_label = _format_file_size(target.stat().st_size)
        for i, line in enumerate(lines, 1):
            raise_if_cancelled(should_cancel)
            if rx.search(line):
                results.append(
                    f"{_display_read_path(target, root)}:{i}: "
                    f"[{size_label}] {line.strip()[:150]}"
                )
                if len(results) >= _MAX_GREP_RESULTS:
                    break
        scope = _display_read_path(target, root)
    else:
        try:
            roots = _search_roots(directory, root, readable_roots)
        except ValueError as e:
            return f"错误：{e}"
        if not all(search_root.is_dir() for search_root in roots):
            return f"错误：目录不存在：{directory}"
        walked = 0
        for search_root in roots:
            for p in search_root.rglob(file_glob or "*"):
                raise_if_cancelled(should_cancel)
                relative_parts = p.relative_to(search_root).parts
                if any(part in _SKIP_DIRS or part.startswith(".") for part in relative_parts):
                    continue
                if not p.is_file():
                    continue
                walked += 1
                try:
                    lines = p.read_text(encoding="utf-8").splitlines()
                except (UnicodeDecodeError, OSError):
                    continue  # 跳过二进制/非 UTF-8 文件
                size_label = _format_file_size(p.stat().st_size)
                for i, line in enumerate(lines, 1):
                    raise_if_cancelled(should_cancel)
                    if rx.search(line):
                        results.append(
                            f"{_display_read_path(p, root)}:{i}: "
                            f"[{size_label}] {line.strip()[:150]}"
                        )
                        if len(results) >= _MAX_GREP_RESULTS:
                            break
                if len(results) >= _MAX_GREP_RESULTS or walked >= _MAX_FIND_WALK:
                    break
            if len(results) >= _MAX_GREP_RESULTS or walked >= _MAX_FIND_WALK:
                break
        scope = "、".join(_display_read_path(item, root) for item in roots)
    if not results:
        return f"没有匹配 {pattern!r} 的内容（搜索范围：{scope}）"
    suffix = f"（已达 {_MAX_GREP_RESULTS} 条上限）" if len(results) >= _MAX_GREP_RESULTS else ""
    output = f"找到 {len(results)} 处匹配{suffix}：\n" + "\n".join(results)
    if not force_read and _estimate_tokens(output) > _GREP_TRUNC_TOKENS:
        return (
            f"找到 {len(results)} 处匹配{suffix}，但结果过大，直接返回会严重占用上下文，"
            "仅给出开头预览：\n"
            f"{_head_by_tokens(output)}\n…\n"
            "提示：请收窄查询方式（更精确的正则，或用 path 只搜单个文件、"
            "限定 directory/file_glob），"
            "或用 delegate_task 派子 Agent 全文检索后总结要点"
            "（子 Agent 可用 force_read=true 获取完整结果）。"
        )
    return output


class ImageQueue(Protocol):
    """read_image 写入、主 Agent 读取的图片队列（见 main_agent）。"""

    def add(self, path: str) -> str: ...


class CommandRunner(Protocol):
    """run_command 工具的执行后端（由界面层注入，见 chat_cli）。

    负责：红框展示命令、用户确认（或 yolo 直通）、执行并捕获输出、
    Ctrl+C 杀进程。返回给模型的文本（输出/错误/被拒说明）。
    """

    def run(self, command: str) -> str: ...


def read_document(
    path: str,
    force_read: bool = False,
    root: Path | None = None,
    readable_roots: Iterable[Path] | None = None,
    should_cancel: CancelCheck = None,
    allow_force_read: bool = False,
) -> str:
    raise_if_cancelled(should_cancel)
    if force_read and not allow_force_read:
        return (
            "错误：force_read 仅限子 Agent 使用。"
            "请改用 delegate_task 派子 Agent 读取该文件并提炼所需信息。"
        )
    try:
        p = resolve_readable_path(path, root, readable_roots)
    except ValueError as e:
        return f"错误：{e}"
    if not p.is_file():
        # 给出同目录下的相似文件名候选，让主 Agent 可以自行纠正路径重试
        hint = ""
        if p.parent.is_dir():
            names = [f.name for f in p.parent.iterdir() if f.is_file()]
            close = difflib.get_close_matches(p.name, names, n=3, cutoff=0.3)
            if close:
                hint = "。你是不是想找：" + "、".join(
                    _display_read_path(p.parent / c, root) for c in close
                )
        return f"错误：文件不存在：{path}{hint}"
    size = p.stat().st_size
    if size > _MAX_DOC_BYTES:
        return f"错误：文件超过 200KB，请精简后再试：{path}"
    try:
        text = p.read_text(encoding="utf-8")
        raise_if_cancelled(should_cancel)
    except UnicodeDecodeError:
        return f"错误：不是 UTF-8 文本文件：{path}"
    if not force_read and size > _DOC_WARN_BYTES:
        return (
            f"警告：文件 {_display_read_path(p, root)} 大小为 {_format_file_size(size)}，"
            "全文进入上下文会非常危险，仅返回开头预览：\n"
            f"{_head_by_tokens(text)}\n…\n"
            "提示：文件过大。请用 grep_files 查询你感兴趣的内容，"
            "或用 delegate_task 派子 Agent 提取你想要的信息"
            "（子 Agent 可用 force_read=true 强制全读，汇报后其上下文即销毁）。"
        )
    return text


def find_files(
    keyword: str,
    directory: str = ".",
    root: Path | None = None,
    readable_roots: Iterable[Path] | None = None,
    should_cancel: CancelCheck = None,
) -> str:
    raise_if_cancelled(should_cancel)
    try:
        roots = _search_roots(directory, root, readable_roots)
    except ValueError as e:
        return f"错误：{e}"
    if not all(search_root.is_dir() for search_root in roots):
        return f"错误：目录不存在：{directory}"
    matches: list[str] = []
    walked = 0
    for search_root in roots:
        for p in search_root.rglob("*"):
            raise_if_cancelled(should_cancel)
            relative_parts = p.relative_to(search_root).parts
            if any(part in _SKIP_DIRS or part.startswith(".") for part in relative_parts):
                continue
            if p.is_file():
                walked += 1
                if keyword.lower() in p.name.lower():
                    matches.append(
                        f"{_display_read_path(p, root)} | "
                        f"size={_format_file_size(p.stat().st_size)}"
                    )
                if len(matches) >= _MAX_FIND_RESULTS or walked >= _MAX_FIND_WALK:
                    break
        if len(matches) >= _MAX_FIND_RESULTS or walked >= _MAX_FIND_WALK:
            break
    if not matches:
        scope = "、".join(_display_read_path(item, root) for item in roots)
        return f"没有找到文件名包含 {keyword!r} 的文件（搜索范围：{scope}）"
    return "找到以下文件：\n" + "\n".join(matches)


def list_dir(
    directory: str = ".",
    filter: str = "",
    root: Path | None = None,
    readable_roots: Iterable[Path] | None = None,
    should_cancel: CancelCheck = None,
) -> str:
    """以 tree 形式列出目录结构；文件附带大小，不读取文件内容。

    兜底：单目录超 50 项折叠其余为计数提示；深层目录折叠可下钻。
    filter 支持 glob（image-*）或正则（^img-\\d+$），只过滤文件名。
    """
    raise_if_cancelled(should_cancel)
    try:
        roots = _search_roots(directory, root, readable_roots)
    except ValueError as e:
        return f"错误：{e}"
    if not roots or not all(search_root.is_dir() for search_root in roots):
        return f"错误：目录不存在：{directory}"
    boundary = Path(root).resolve() if root is not None else None

    def label(search_root: Path) -> str:
        if boundary is not None:
            try:
                relative = search_root.resolve().relative_to(boundary)
                return relative.as_posix() or "."
            except ValueError:
                pass
        supplied = Path(directory)
        return supplied.as_posix() if len(roots) == 1 else search_root.name

    lines: list[str] = []
    for search_root in roots:
        try:
            tree = build_tree(search_root, pattern=filter or None)
        except ValueError as e:
            return f"错误：{e}"
        header = label(search_root).rstrip("/")
        body = render_text(tree, max_level=2)
        lines.append(f"{header}/" + (f"\n{body}" if body else "（空目录）"))
    return "\n".join(lines)


def _make_read_image_handler(
    image_queue: ImageQueue,
    root: Path | None = None,
    readable_roots: Iterable[Path] | None = None,
):
    def read_image(path: str) -> str:
        try:
            safe_path = resolve_readable_path(path, root, readable_roots)
        except ValueError as e:
            return f"错误：{e}"
        result = image_queue.add(str(safe_path))
        if result.startswith("错误："):
            return result
        return (
            f"已读取图片 {_display_read_path(safe_path, root)}，"
            "内容将在下一步对你可见。"
        )

    return read_image


def _make_image_reasoning_handler(
    llm: LLMClient,
    root: Path | None,
    readable_roots: Iterable[Path],
    should_cancel: CancelCheck,
    on_progress: Callable[[str], None] | None = None,
    output_label: str = "视觉模型",
):
    """image_reasoning 工具的 handler：按任意 prompt 用视觉模型分析图片。

    流式返回：output 增量实时回调 on_progress（UI 可在工具卡片滚动展示）。
    """

    def image_reasoning(prompt: str, image_paths: list[str] | None = None) -> str:
        if not (prompt or "").strip():
            return "错误：image_reasoning 的 prompt 不能为空。"
        if not image_paths:
            return "错误：image_reasoning 至少需要一张图片。"
        images: list[Path] = []
        errors: list[str] = []
        for raw in image_paths or []:
            try:
                safe_path = resolve_readable_path(raw, root, readable_roots)
                images.append(validate_image(safe_path))
            except ValueError as exc:
                errors.append(f"{raw}：{exc}")
        if errors:
            return "错误：以下图片不可用：\n" + "\n".join(errors)
        output_chars = 0
        reasoning_chars = 0

        def output_delta(text: str) -> None:
            nonlocal output_chars
            output_chars += len(text)
            if on_progress is not None:
                on_progress(text)

        def reasoning_delta(text: str) -> None:
            nonlocal reasoning_chars
            reasoning_chars += len(text)

        return llm.chat_with_images_stream(
            [{"role": "user", "content": prompt.strip()}],
            images,
            on_delta=output_delta,
            on_reasoning=reasoning_delta,
            should_cancel=should_cancel,
        )

    return image_reasoning


def build_file_tools(
    session: Session,
    image_queue: ImageQueue,
    vision_llm: LLMClient | None = None,
    command_runner: CommandRunner | None = None,
    readable_root: Path | None = None,
    readable_roots: Iterable[Path] | None = None,
    should_cancel: CancelCheck = None,
    allow_force_read: bool = False,
    on_tool_progress: Callable[[str, str], None] | None = None,
) -> list[Skill]:
    """构建主 Agent 的工具表。ocr_llm 不为 None 时注册 ocr_image
    （主模型无视觉能力时，用多模态验证模型做图片文字提取）；
    command_runner 不为 None 时注册 run_command（界面层提供确认与进程管理）；
    allow_force_read 为 True 时（子 Agent）允许 read_document/grep_files
    使用 force_read=true 强制返回完整内容。"""
    writable_root = session.output_dir  # write_file/replace_in_file 的写入边界
    session_path_hint = (
        "服务端仅允许当前 Session，路径必须使用 workspace/、attachments/、generate/"
        "开头的 Session 相对路径；返回结果也只显示相对路径。"
        if readable_root is not None else ""
    )
    force_read_hint = (
        "需要完整内容时可用 force_read=true 强制全读，读完后只提炼要点返回。"
        if allow_force_read
        else "force_read=true 仅子 Agent 可用（主 Agent 调用会被拒绝）；"
        "需要大文件全文时请 delegate_task 派子 Agent 提炼。"
    )
    skills = [
        Skill(
            name="read_document",
            description=(
                "读取本地文本文件（.txt/.md 等 UTF-8 文本文件）。"
                "超过 20KB 的大文件默认只返回开头约 100 token 的预览和警告，"
                "以保护上下文；需要其中具体内容时优先 grep_files 定位。"
                + force_read_hint + session_path_hint
            ),
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "文档文件路径"},
                    "force_read": {
                        "type": "boolean",
                        "description": "强制返回完整内容（仅限子 Agent），默认 false",
                        "default": False,
                    },
                },
                "required": ["path"],
            },
            handler=partial(
                read_document, root=readable_root, readable_roots=readable_roots,
                should_cancel=should_cancel, allow_force_read=allow_force_read,
            ),
        ),
        Skill(
            name="list_dir",
            description=(
                "以 tree 形式列出目录的两级结构，目录优先、文件附带大小；"
                "不读取文件内容，适合在查找、批量处理或委派前了解目录组织方式。"
                "超大目录有兜底：单目录超过 50 项时其余折叠为计数提示，"
                "深层目录折叠为下钻提示（传入该目录路径可继续展开）。"
                "filter 可按文件名过滤，支持 glob（如 image-*）或正则"
                "（如 ^img-\\d+$），只作用于文件，目录始终保留。"
                + session_path_hint
            ),
            parameters={
                "type": "object",
                "properties": {
                    "directory": {
                        "type": "string",
                        "description": "当前可读范围内要查看的目录，默认列出可读根目录",
                        "default": ".",
                    },
                    "filter": {
                        "type": "string",
                        "description": (
                            "文件名过滤：glob（image-*、*.png）或正则（^img-\\d+$）；"
                            "默认不过滤"
                        ),
                        "default": "",
                    },
                },
            },
            handler=partial(
                list_dir,
                root=readable_root,
                readable_roots=readable_roots,
                should_cancel=should_cancel,
            ),
        ),
        Skill(
            name="find_files",
            description=(
                "按文件名关键词在目录中模糊查找文件，用于用户给出的路径有误时"
                "自行猜测正确文件。返回匹配的文件路径与文件大小。" + session_path_hint
            ),
            parameters={
                "type": "object",
                "properties": {
                    "keyword": {"type": "string", "description": "文件名关键词，如 1.txt 或 登录"},
                    "directory": {
                        "type": "string",
                        "description": "搜索的起始目录，默认当前目录",
                        "default": ".",
                    },
                },
                "required": ["keyword"],
            },
            handler=partial(
                find_files, root=readable_root, readable_roots=readable_roots,
                should_cancel=should_cancel,
            ),
        ),
        Skill(
            name="write_file",
            description=(
                "新建或整体覆盖一个文本文件（自动创建父目录）。"
                "用于生成中间文档、或按用户要求输出其它格式的文件"
                "（markdown、csv、纯文本等）。仅限产物目录内，相对路径按产物目录解析。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "目标文件路径"},
                    "content": {"type": "string", "description": "完整文件内容"},
                },
                "required": ["path", "content"],
            },
            handler=partial(
                write_file, root=writable_root, display_root=readable_root,
                should_cancel=should_cancel,
            ),
        ),
        Skill(
            name="replace_in_file",
            description=(
                "在文本文件中做精确字符串替换（先 read_document 拿到原文再改）。"
                "old_text 必须与文件内容完全一致；多处匹配时需提供更长上下文或 "
                "replace_all=true。仅限产物目录内。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "目标文件路径"},
                    "old_text": {"type": "string", "description": "要被替换的原文（精确匹配）"},
                    "new_text": {"type": "string", "description": "替换后的新文本"},
                    "replace_all": {
                        "type": "boolean",
                        "description": "是否替换全部匹配处，默认 false（仅一处，多处则报错）",
                        "default": False,
                    },
                },
                "required": ["path", "old_text", "new_text"],
            },
            handler=partial(
                replace_in_file, root=writable_root, display_root=readable_root,
                should_cancel=should_cancel,
            ),
        ),
        Skill(
            name="grep_files",
            description=(
                "按正则表达式搜索文件内容，返回 文件:行号: 匹配行。"
                "每条结果包含文件大小，用于在中间文档/代码中定位内容"
                "（配合 replace_in_file 修改）。只搜某一个文件时直接传 path，"
                "不要用 directory+file_glob 凑。结果过大时会被截断为约 100 token"
                " 的预览并提示，此时请收窄 pattern，或用 path 限定单个文件。"
                + force_read_hint + session_path_hint
            ),
            parameters={
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "正则表达式，如 保存设置"},
                    "path": {
                        "type": "string",
                        "description": "只搜索这一个文件（优先于 directory/file_glob），如 workspace/notes.md",
                        "default": "",
                    },
                    "directory": {
                        "type": "string",
                        "description": "搜索的起始目录，默认当前目录",
                        "default": ".",
                    },
                    "file_glob": {
                        "type": "string",
                        "description": "文件名过滤，如 *.md；默认所有文件",
                        "default": "",
                    },
                    "force_read": {
                        "type": "boolean",
                        "description": "结果超大时仍返回完整内容（仅限子 Agent），默认 false",
                        "default": False,
                    },
                },
                "required": ["pattern"],
            },
            handler=partial(
                grep_files, root=readable_root, readable_roots=readable_roots,
                should_cancel=should_cancel, allow_force_read=allow_force_read,
            ),
        ),
        Skill(
            name="read_image",
            description=(
                "查看一张本地图片。调用后图片内容将对你可见。"
                "仅在主模型具备多模态能力时有效。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "图片文件路径"},
                },
                "required": ["path"],
            },
            handler=_make_read_image_handler(
                image_queue, readable_root, readable_roots
            ),
        ),
        Skill(
            name="create_skill",
            description=(
                "根据用户描述生成提示词型 Skill，校验通过后写入当前会话的 skills 目录。"
                "用户要求沉淀新的领域流程、操作规范或 Agent 指引时调用。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "英文小写 Skill 标识"},
                    "description": {"type": "string", "description": "完整需求、触发条件和期望行为"},
                },
                "required": ["name", "description"],
            },
            handler=session.create_skill,
        ),
        Skill(
            name="list_skill_packs",
            description=(
                "列出 skills/ 目录下所有可用的技能包（名称与适用场景）。"
                "遇到自己不熟悉领域的任务（如特定导出格式、行业规范、"
                "第三方工具对接）时，先调用本工具看看有没有现成指引。"
            ),
            parameters={"type": "object", "properties": {}},
            handler=session.list_skill_packs,
        ),
        Skill(
            name="use_skill",
            description=(
                "读取指定技能包的完整操作指引并遵照执行。"
                "技能包名须来自 list_skill_packs。"
                "也支持 包名/附属文件.md 形式读取包内附属文档"
                "（如检查项清单等数据文件，清单见 list_skill_packs 输出）。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "技能包名"},
                },
                "required": ["name"],
            },
            handler=session.use_skill,
        ),
        Skill(
            name="read_working_doc",
            description=(
                "读取工作文档：多任务/多信息源场景下整合关键信息的中间产物"
                "（markdown）。继续之前的复杂任务前先读它，避免遗漏上下文。"
            ),
            parameters={"type": "object", "properties": {}},
            handler=session.read_working_doc,
        ),
        Skill(
            name="write_working_doc",
            description=(
                "写入或修改工作文档（整体覆盖，先 read_working_doc 再改即可局部修订）。"
                "用于把关键信息与中间结论整合成一份 markdown，"
                "而不是全部堆在自己的对话上下文里。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "content": {
                        "type": "string",
                        "description": "工作文档的完整 markdown 内容",
                    },
                },
                "required": ["content"],
            },
            handler=session.write_working_doc,
        ),
    ]
    if command_runner is not None:
        skills.append(
            Skill(
                name="run_command",
                description=(
                    "运行一条单行 shell 命令并返回输出（执行前会向用户请求确认，"
                    "用户可能拒绝）。用于用户明确要求的系统操作、格式转换、"
                    "批量文件处理等；命令尽量只读，破坏性命令务必先向用户说明风险。"
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "command": {
                            "type": "string",
                            "description": "要执行的单行 shell 命令",
                        },
                    },
                    "required": ["command"],
                },
                handler=command_runner.run,
            )
        )
    if vision_llm is not None:
        skills.append(
            Skill(
                name="image_reasoning",
                description=(
                    "使用视觉模型分析一张或多张图片（不限文字：可提取文字/描述内容/"
                    "按指令检查图片）。prompt 里写清楚要做什么（如“提取图中全部文字”"
                    "即为 OCR）。流式返回，执行中即可在工具卡片看到实时输出。"
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "prompt": {
                            "type": "string",
                            "description": (
                                "发给视觉模型的完整指令，如“提取图中全部文字，按原样输出”"
                                "或“描述图片内容”"
                            ),
                        },
                        "image_paths": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "要分析的一张或多张图片路径",
                        },
                    },
                    "required": ["prompt", "image_paths"],
                },
                handler=_make_image_reasoning_handler(
                    vision_llm, readable_root, readable_roots, should_cancel,
                    on_progress=(
                        (lambda text: on_tool_progress("image_reasoning", text))
                        if on_tool_progress is not None else None
                    ),
                ),
            )
        )
    # 技能包脚本执行器（框架机制，无领域知识）：skills/<pack>/<script>.py
    skills.append(
        Skill(
            name="run_skill_script",
            description=(
                "执行技能包自带的确定性 Python 脚本（不消耗推理，样式与行为由脚本"
                "保证一致）。只能执行技能库中同名包目录下的 .py。脚本通过 stdin 收 "
                "JSON 参数、stdout 一行 JSON 返回结果；执行中的进度会实时显示。"
                "适合：报告渲染、格式转换、批量校验等确定性工作。"
                "先 list_skill_packs 确认包名，脚本名由技能包文档给出。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "pack": {
                        "type": "string",
                        "description": "技能包名（如 doc-image-qc，须与其 .md 同名）",
                    },
                    "script": {
                        "type": "string",
                        "description": "包内脚本文件名（如 render_report.py）",
                    },
                    "args": {
                        "type": "string",
                        "description": "传给脚本的 JSON 参数字符串，如 {\"data_path\": \"generate/qc-report.json\"}",
                        "default": "{}",
                    },
                },
                "required": ["pack", "script"],
            },
            handler=lambda pack, script, args="": run_skill_script(
                pack=pack, script=script, args=args,
                workdir=writable_root,
                session_root=readable_root,
                should_cancel=should_cancel,
                on_progress=(
                    (lambda text: on_tool_progress("run_skill_script", text))
                    if on_tool_progress is not None else None
                ),
            ),
        )
    )
    return skills
