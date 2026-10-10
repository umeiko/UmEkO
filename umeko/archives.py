"""Native 7-Zip backend shared by CLI, model tools, and the Web workspace."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import shutil
import subprocess
import tempfile
import time

from .cancellation import CancelCheck, raise_if_cancelled
from .file_operations import is_link, validate_tree

ARCHIVE_SUFFIXES = {".zip", ".7z", ".rar", ".tar", ".gz", ".bz2", ".xz", ".tgz", ".tbz2", ".txz", ".wim"}
MAX_ARCHIVE_ENTRIES = 5000
MAX_ARCHIVE_BYTES = 512 * 1024 * 1024
ARCHIVE_TIMEOUT = 300


@dataclass
class Member:
    name: str
    size: int | None
    directory: bool = False


def seven_zip_binary() -> str:
    configured = os.environ.get("SEVENZIP_PATH", "").strip()
    if configured:
        found = shutil.which(configured)
        if found:
            return found
        raise ValueError("SEVENZIP_PATH 未指向可执行的 7-Zip，请检查容器内路径和执行权限")
    for name in ("7zz", "7z", "7za"):
        found = shutil.which(name)
        if found:
            return found
    if os.name == "nt":
        for variable in ("ProgramFiles", "ProgramFiles(x86)"):
            candidate = Path(os.environ.get(variable, "C:/Program Files")) / "7-Zip" / "7z.exe"
            if candidate.is_file():
                return str(candidate)
    raise ValueError("压缩包操作需要 7-Zip。请在运行服务的系统/容器安装 7zz 或 7z，或用 SEVENZIP_PATH 指定可执行文件")


def _member_path(name: str) -> Path:
    normalized = name.replace("\\", "/")
    path = PurePosixPath(normalized)
    if (not name or any(char in name for char in "\x00\r\n\uf05c\uf03a\uf02f") or path.is_absolute()
            or PureWindowsPath(normalized).drive or ".." in path.parts
            or any(":" in part for part in path.parts)):
        raise ValueError("压缩包内含绝对路径、越界路径或不安全文件名")
    return Path(*path.parts)


def _check_members(members: list[Member]) -> list[Member]:
    if len(members) > MAX_ARCHIVE_ENTRIES or sum(member.size or 0 for member in members) > MAX_ARCHIVE_BYTES:
        raise ValueError("压缩包超过解压预算（5000 条目 / 512 MiB）")
    seen = {}
    checked = []
    for member in members:
        path = _member_path(member.name)
        if path == Path(".") and member.directory:
            continue
        if path == Path(".") or (member.size is not None and member.size < 0):
            raise ValueError("压缩包包含无效条目")
        key = path.as_posix().casefold()
        if key in seen or any(parent.as_posix().casefold() in seen and not seen[parent.as_posix().casefold()]
                              for parent in path.parents if parent != Path(".")):
            raise ValueError("压缩包条目重复或文件与目录冲突")
        seen[key] = member.directory
        checked.append(member)
    if any(any(seen.get(parent.as_posix().casefold()) is False for parent in _member_path(member.name).parents
               if parent != Path(".")) for member in checked):
        raise ValueError("压缩包文件与目录冲突")
    return checked


def _check_output_budget(target: Path) -> None:
    count, size = 0, 0
    for entry in target.rglob("*"):
        try:
            if is_link(entry):
                raise ValueError("解压内容中不允许链接")
            if entry.is_file():
                size += entry.stat().st_size
            elif not entry.is_dir():
                raise ValueError("解压内容中不允许特殊文件")
        except FileNotFoundError:
            continue
        count += 1
        if count > MAX_ARCHIVE_ENTRIES or size > MAX_ARCHIVE_BYTES:
            raise ValueError("解压内容超过条目或体积预算")


def _run_7zip(binary: str, arguments: list[str], should_cancel: CancelCheck,
              deadline: float, *, cwd: Path | None = None, output: Path | None = None) -> str:
    raise_if_cancelled(should_cancel)
    # Disk-backed logs avoid pipe deadlocks and large in-memory extraction output.
    with tempfile.TemporaryFile() as log:
        proc = subprocess.Popen(
            [binary, *arguments], stdin=subprocess.DEVNULL, stdout=log, stderr=log,
            cwd=cwd, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        try:
            while True:
                raise_if_cancelled(should_cancel)
                if time.monotonic() >= deadline:
                    raise ValueError("7-Zip 操作超时（5 分钟）")
                if output is not None:
                    _check_output_budget(output)
                if proc.poll() is not None:
                    break
                try:
                    proc.wait(timeout=.2)
                except subprocess.TimeoutExpired:
                    pass
            if proc.returncode:
                raise ValueError("7-Zip 处理失败，请检查压缩包是否损坏、加密或格式不受当前程序支持")
            log.seek(0)
            content = log.read(16 * 1024 * 1024 + 1)
            if len(content) > 16 * 1024 * 1024:
                raise ValueError("7-Zip 返回的条目元数据过大")
            return content.decode("utf-8", errors="strict")
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait()


def _native_members(archive: Path, binary: str, should_cancel: CancelCheck, deadline: float) -> list[Member]:
    listing = _run_7zip(binary, ["l", "-slt", "-ba", "-sccUTF-8", "-p", "--", str(archive)], should_cancel, deadline)
    members = []
    for block in listing.replace("\r\n", "\n").strip("\n").split("\n\n"):
        if not block:
            continue
        fields = {}
        for line in block.splitlines():
            key, separator, value = line.partition(" = ")
            if not separator or key in fields:
                raise ValueError("压缩包条目元数据含多行文件名或重复字段，无法安全解压")
            fields[key] = value
        # XZ/BZ2 streams have no stored filename; 7-Zip uses the archive stem.
        if "Path" not in fields and archive.suffix.lower() not in {".xz", ".bz2", ".txz", ".tbz2"}:
            raise ValueError("压缩包条目缺少路径，无法安全解压")
        mode = fields.get("Mode", "")
        attributes = fields.get("Attributes", "").split()
        unix_mode = next((part for part in attributes if len(part) == 10 and part[0] in "-dlbcps"), "")
        if fields.get("Symbolic Link") or fields.get("Hard Link") or (mode or unix_mode).startswith("l"):
            raise ValueError("压缩包中不允许符号链接或硬链接")
        if (mode or unix_mode) and (mode or unix_mode)[0] not in "-d":
            raise ValueError("压缩包中不允许特殊文件")
        if fields.get("Encrypted") == "+":
            raise ValueError("暂不支持加密压缩包，请先提供未加密版本")
        directory = fields.get("Folder") == "+" or "D" in fields.get("Attributes", "")
        try:
            size = int(fields["Size"]) if fields.get("Size") else None
        except ValueError as exc:
            raise ValueError("压缩包条目大小无效") from exc
        fallback_name = archive.stem + ".tar" if archive.suffix.lower() in {".txz", ".tbz2"} else archive.stem
        members.append(Member(fields.get("Path", fallback_name), size, directory))
    return _check_members(members)


def _extract_native(archive: Path, target: Path, members: list[Member], binary: str,
                    should_cancel: CancelCheck, deadline: float) -> None:
    # One process extracts the entire archive after ALL paths/types have been checked.
    _run_7zip(binary, ["x", "-y", "-p", "-sccUTF-8", "-bso0", "-bsp0", f"-o{target}", "--", str(archive)],
              should_cancel, deadline, output=target)
    validate_tree(target, should_cancel)
    expected = {_member_path(member.name).as_posix(): member for member in members}
    parents = {parent.as_posix() for member in members for parent in _member_path(member.name).parents}
    actual_files = set()
    for entry in target.rglob("*"):
        key = entry.relative_to(target).as_posix()
        member = expected.get(key)
        if member is None and not (entry.is_dir() and key in parents):
            raise ValueError("解压结果与预检条目不一致")
        if member is not None:
            if entry.is_dir() != member.directory or (entry.is_file() and member.size is not None and entry.stat().st_size != member.size):
                raise ValueError("解压条目类型或大小与预检不一致")
            if not member.directory:
                actual_files.add(key)
    if actual_files != {key for key, member in expected.items() if not member.directory}:
        raise ValueError("压缩包未完整解压")


@contextmanager
def _prepared_archive(archive: Path, should_cancel: CancelCheck):
    archive = archive.absolute()
    if archive.suffix.lower() not in ARCHIVE_SUFFIXES:
        raise ValueError("不支持的压缩包格式")
    binary = seven_zip_binary()
    deadline = time.monotonic() + ARCHIVE_TIMEOUT
    members = _native_members(archive, binary, should_cancel, deadline)
    if archive.name.lower().endswith((".tar.gz", ".tar.bz2", ".tar.xz", ".tgz", ".tbz2", ".txz")):
        # These have two native archive layers: compression stream, then TAR.
        if len(members) != 1 or members[0].directory:
            raise ValueError("压缩 TAR 外层结构无效")
        with tempfile.TemporaryDirectory(prefix=".umeko-archive-", dir=archive.parent) as temporary:
            staging = Path(temporary)
            _extract_native(archive, staging, members, binary, should_cancel, deadline)
            inner = staging / _member_path(members[0].name)
            inner_members = _native_members(inner, binary, should_cancel, deadline)
            yield inner, inner_members, binary, deadline
    else:
        yield archive, members, binary, deadline


def archive_members(archive: Path, should_cancel: CancelCheck = None) -> list[Member]:
    with _prepared_archive(archive, should_cancel) as (_, members, _, _):
        return members


def extract_archive(archive: Path, should_cancel: CancelCheck = None) -> Path:
    """Extract with native 7-Zip into a new sibling, cleaning failed output only."""
    with _prepared_archive(archive, should_cancel) as (prepared, members, binary, deadline):
        target = archive.absolute().parent / archive.stem
        counter = 1
        while target.exists() or target.is_symlink():
            target = archive.absolute().parent / f"{archive.stem}_{counter}"
            counter += 1
        target.mkdir()
        try:
            _extract_native(prepared, target, members, binary, should_cancel, deadline)
            raise_if_cancelled(should_cancel)
            top = list(target.iterdir())
            if len(top) == 1 and top[0].is_dir():
                wrapper = top[0]
                if not (wrapper / wrapper.name).exists():
                    for item in wrapper.iterdir():
                        item.rename(target / item.name)
                    wrapper.rmdir()
            return target
        except BaseException:
            shutil.rmtree(target)
            raise


def write_zip(source: Path, destination: Path, should_cancel: CancelCheck = None) -> Path:
    """Write a new ZIP; directory downloads also use this native backend."""
    source, destination = source.absolute(), destination.absolute()
    validate_tree(source, should_cancel)
    binary = seven_zip_binary()
    if source == destination or source in destination.parents:
        raise ValueError("不能把压缩包创建到源目录内部")
    if destination.exists() or destination.is_symlink():
        raise ValueError("压缩包目标已存在")
    try:
        _run_7zip(binary, ["a", "-tzip", "-mcu=on", "-sccUTF-8", "-bso0", "-bsp0", "-spd", "--", str(destination), f"./{source.name}"],
                  should_cancel, time.monotonic() + ARCHIVE_TIMEOUT, cwd=source.parent)
        return destination
    except BaseException:
        destination.unlink(missing_ok=True)
        raise


def create_zip(source: Path, output_dir: Path, should_cancel: CancelCheck = None) -> Path:
    source, output_dir = source.absolute(), output_dir.absolute()
    if source == output_dir or source in output_dir.parents:
        raise ValueError("不能把压缩包创建到源目录内部")
    output_dir.mkdir(parents=True, exist_ok=True)
    name = source.name if source.is_dir() else source.stem
    destination = output_dir / f"{name}.zip"
    counter = 1
    while destination.exists() or destination.is_symlink():
        destination = output_dir / f"{name}_{counter}.zip"
        counter += 1
    return write_zip(source, destination, should_cancel)
