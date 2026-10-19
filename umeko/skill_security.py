"""Read-only skill code and administrator-issued execution integrity records.

This enforces the application's trust boundary; it is not an OS sandbox.
Trust records live outside user sessions and never come from uploaded files.
"""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import tempfile

from .skill_layout import checked, slug

CODE_SUFFIXES = {".py", ".pyw", ".pyc", ".pyo", ".pyd", ".so", ".dll", ".pth"}


class SkillSecurityError(ValueError):
    pass


def protected_name(path: str | Path) -> bool:
    name = Path(str(path).replace("\\", "/")).name.rstrip(" .").split(":", 1)[0].casefold()
    return name == "config.json" or Path(name).suffix in CODE_SUFFIXES or name == "__pycache__"


def skill_scope(path: Path, roots=()) -> Path | None:
    path = path.absolute()
    for root in roots:
        root = Path(root).absolute()
        if path == root or path.is_relative_to(root):
            return root
    for parent in (path, *path.parents):
        if parent.name.casefold() == "skills" and parent.parent.name.casefold() == "client":
            return parent
    # Also protect the administrator's library from ordinary file tools in CLI use.
    from .skillpacks import skill_packs_dir
    root = skill_packs_dir().absolute()
    return root if path == root or path.is_relative_to(root) else None


def guard_skill_write(path: Path, *, source: Path | None = None, roots=()) -> None:
    """Preflight before creating, replacing, deleting or transferring an entry."""
    path = Path(path).absolute()
    scope = skill_scope(path, roots)
    if scope is None:
        return
    relative = path.relative_to(scope)
    if any(protected_name(part) for part in relative.parts):
        raise SkillSecurityError("技能 Python 文件和 config.json 为管理员下发的只读文件，拒绝修改、新建或删除")
    if any(":" in part or part.rstrip(" .") != part for part in relative.parts):
        raise SkillSecurityError("技能目录不接受别名、数据流或带尾随空格/点的路径")
    for entry in (path, *path.rglob("*")) if path.is_dir() else (path,):
        if protected_name(entry.name):
            raise SkillSecurityError("目录包含只读 Python 文件或 config.json，拒绝整体修改、移动或删除")
    if source is not None:
        source = Path(source)
        for entry in (source, *source.rglob("*")) if source.is_dir() else (source,):
            if protected_name(entry.name):
                raise SkillSecurityError("复制或移动会在技能目录产生 Python 文件或 config.json，已拒绝")


def _regular(path: Path) -> bytes:
    from .file_operations import is_link
    if not path.is_file() or is_link(path) or path.stat().st_nlink != 1:
        raise SkillSecurityError("脚本信任校验拒绝链接、缺失文件或非普通文件")
    return path.read_bytes()


def _digests(data: bytes) -> dict:
    # MD5 is retained for the requested compatibility check; SHA-256 prevents
    # treating an MD5 collision as administrator approval.
    return {"md5": hashlib.md5(data, usedforsecurity=False).hexdigest(),
            "sha256": hashlib.sha256(data).hexdigest()}


def _files(package: Path):
    from .file_operations import is_link
    if is_link(package):
        raise SkillSecurityError("技能目录不能是链接")
    for path in sorted(package.rglob("*")):
        if "__pycache__" in path.relative_to(package).parts:
            continue
        if is_link(path):
            raise SkillSecurityError("技能执行副本中不允许符号链接或目录联接")
        if path.is_file():
            yield path.relative_to(package).as_posix(), path


class ScriptTrust:
    def __init__(self, skill_root: Path, records: Path, *, revocation_check=None):
        self.skill_root = Path(skill_root).resolve()
        self.records = Path(records).resolve()
        if self.records.is_relative_to(self.skill_root):
            raise SkillSecurityError("执行白名单必须保存在用户技能目录之外")
        self.records.mkdir(parents=True, exist_ok=True)
        self.revocation_check = revocation_check

    def issue(self, pack: str, administrator_library: Path, *, approved_files: dict | None = None) -> None:
        """Issue an immutable manifest from administrator authority.

        Server callers must supply approved_files from the private library
        registry. None is reserved for direct, operator-owned CLI libraries.
        """
        pack = slug(pack)
        record = checked(self.records, pack + ".json")
        if record.exists():
            return  # Never bless an existing session's edited bytes on restore.
        source = checked(Path(administrator_library).resolve(), pack)
        files = {}
        if source.is_dir():
            for relative, path in _files(source):
                if protected_name(path):
                    if approved_files is None:
                        files[relative] = _digests(_regular(path))
                    elif relative in approved_files:
                        # Server dispatch never blesses changed library bytes.
                        files[relative] = dict(approved_files[relative])
        manifest = {"version": 1, "pack": pack, "files": files,
                    "scripts": [name for name in files if Path(name).suffix.casefold() == ".py"]}
        try:
            with record.open("x", encoding="utf-8") as stream:
                json.dump(manifest, stream, ensure_ascii=False, sort_keys=True)
        except FileExistsError:
            pass

    @contextmanager
    def execution(self, pack: str, script: str):
        pack = slug(pack)
        if not isinstance(script, str) or "\\" in script or ":" in script:
            raise SkillSecurityError("执行脚本必须使用包内 scripts/ 下的规范路径")
        parts = script.split("/")
        if any(part in {"", ".", ".."} for part in parts) or (len(parts) > 1 and parts[0] != "scripts"):
            raise SkillSecurityError("执行脚本路径越界或包含非法路径段")
        package = checked(self.skill_root, pack)
        relative = script if len(parts) > 1 else "scripts/" + script
        if not (package / relative).is_file() and len(parts) == 1:
            relative = script  # Read-only administrator-owned legacy libraries.
        target = checked(package, relative)
        record = checked(self.records, pack + ".json")
        if not record.is_file():
            raise SkillSecurityError("技能不在管理员下发的执行白名单中")
        manifest = json.loads(_regular(record))
        if manifest.get("version") != 1 or manifest.get("pack") != pack or relative not in manifest.get("scripts", []):
            raise SkillSecurityError("脚本不在管理员下发的执行白名单中")
        expected = manifest["files"]
        if self.revocation_check:
            self.revocation_check(pack, expected)
        verified, data_files = {}, {}
        total_bytes = 0
        for name, path in _files(package):
            if protected_name(path):
                if name not in expected:
                    raise SkillSecurityError("发现白名单外的技能代码或配置，拒绝执行：" + name)
                data = _regular(checked(package, name))
                actual = _digests(data)
                if actual["md5"] != expected[name]["md5"]:
                    raise SkillSecurityError("技能文件 MD5 校验失败，拒绝执行：" + name)
                if actual["sha256"] != expected[name]["sha256"]:
                    raise SkillSecurityError("技能文件 SHA-256 校验失败，拒绝执行：" + name)
                verified[name] = data
            else:
                data_files[name] = _regular(checked(package, name))
            total_bytes += len(verified.get(name, data_files.get(name, b"")))
            if len(verified) + len(data_files) > 5000 or total_bytes > 128 * 1024 * 1024:
                raise SkillSecurityError("技能执行副本超过文件或体积限制")
        if verified.keys() != expected.keys() or relative not in verified or not target.is_file():
            raise SkillSecurityError("白名单中的技能代码或配置缺失，拒绝执行")
        # Execute exactly the bytes just verified, never reopen editable session
        # files after validation. All sibling Python imports use this snapshot.
        with tempfile.TemporaryDirectory(prefix="execution-", dir=self.records) as temporary:
            base = Path(temporary)
            for name, data in {**data_files, **verified}.items():
                output = checked(base, pack + "/" + name)
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_bytes(data)
            if self.revocation_check:
                self.revocation_check(pack, expected)
            yield checked(base, pack + "/" + relative), base
