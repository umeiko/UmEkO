"""Export current UmEkO skills to portable SkillHub packages, then build ZIPs."""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import stat
import zipfile


REPO = Path(__file__).resolve().parents[1]
TEMPLATES = REPO / "scripts" / "skillhub"
TEXT_TYPES = {".md", ".py", ".json", ".txt", ".yaml", ".yml", ".js", ".ts", ".sh"}
IGNORED = {"__pycache__", ".git", ".DS_Store", "Thumbs.db", "desktop.ini"}
TITLES = {"doc-image-qc": "图文文档图片质检", "drawio-flowchart": "draw.io 流程图与架构图",
          "image-reasoning": "图像推理"}
REQUIRED = {"name", "description", "slug", "displayName", "version"}
PREAMBLE = """## 独立 Skill 的调用方式

此包保留当前 UmEkO 技能的完整指引和附属资源，供支持 Agent Skills 的宿主加载。
执行下方正文前，先读取 [运行约定](references/host-compatibility.md)：正文中的工具名
映射为宿主的同等文件、视觉与委派能力，不能调用宿主未提供的工具。
`read_pack_file` 对应 `<技能目录>/<pack>/<member>`；
`run_skill_script` 对应本包 `scripts/run.py`（Python 3.10+，参数内容不变）。
没有子 Agent 时分段处理并说明无法隔离上下文；没有视觉能力时不猜测图片内容。
图像推理技能没有脚本依赖，可用模型原生视觉输入。

以下保留原始技能正文；其中 UmEkO 专属工具与会话目录名称按上述约定解释。

"""


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def is_link(path: Path) -> bool:
    if not path.exists() and not path.is_symlink():
        return False
    attributes = getattr(path.lstat(), "st_file_attributes", 0)
    return path.is_symlink() or bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))


def entry_parts(content: str) -> tuple[str, str, dict[str, str]]:
    match = re.match(r"\A---\r?\n(.*?)\r?\n---\r?\n(.*)\Z", content, re.S)
    if not match:
        raise ValueError("SKILL.md 缺少 YAML frontmatter 或正文")
    header, body = match.groups()
    fields = {}
    # The UmEkO library uses scalar identity fields. Preserve the complete header verbatim.
    for line in header.splitlines():
        field = re.fullmatch(r"([a-zA-Z][\w-]*):[ \t]*(.*)", line)
        if field:
            key, value = field.groups()
            if key in fields:
                raise ValueError(f"元数据字段重复：{key}")
            if value.startswith('"'):
                value = json.loads(value)
            elif value.startswith("'") and value.endswith("'"):
                value = value[1:-1].replace("''", "'")
            fields[key] = value
    return header, body, fields


def validate_entry(content: str) -> dict[str, str]:
    _, body, fields = entry_parts(content)
    if any(not fields.get(key) for key in REQUIRED) or not body.strip():
        raise ValueError("缺少 Agent Skills / SkillHub 必填字段或正文")
    name, slug = fields["name"], fields["slug"]
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name) or not 3 <= len(name) <= 64:
        raise ValueError("name 必须是 3–64 字符的 kebab-case")
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slug) or not 2 <= len(slug) <= 128:
        raise ValueError("slug 必须是 2–128 字符的 kebab-case")
    if not re.fullmatch(r"(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)", fields["version"]):
        raise ValueError("version 必须为 SemVer 主版本.次版本.修订号")
    if not 1 <= len(fields["description"]) <= 1024:
        raise ValueError("description 长度必须为 1–1024")
    return fields


def safe_files(root: Path) -> dict[str, bytes]:
    files = {}
    for source in sorted(root.rglob("*")):
        relative = source.relative_to(root)
        if any(part in IGNORED for part in relative.parts) or source.suffix in {".pyc", ".pyo"}:
            continue
        if is_link(source):
            raise ValueError(f"不打包符号链接或目录联接：{relative}")
        if not source.is_file():
            continue
        source.resolve().relative_to(root.resolve())
        if source.suffix.lower() not in TEXT_TYPES:
            raise ValueError(f"不支持的文件类型，需人工检查：{relative}")
        data = source.read_bytes()
        data.decode("utf-8")
        if len(data) > 1_000_000 or b"\0" in data:
            raise ValueError(f"文件非纯文本或超过 1 MB：{relative}")
        if source.suffix == ".py":
            ast.parse(data.decode("utf-8"), filename=str(relative))
        files[relative.as_posix()] = data
    if len(files) > 300:
        raise ValueError("单个 Skill 超过 300 个文件")
    return files


def export_skills(source_root: Path, snapshot_dir: Path, version: str) -> list[Path]:
    entries = sorted(source_root.glob("*.md"))
    if not entries:
        raise ValueError("源技能目录没有 .md 主文件")
    exported = []
    for entry in entries:
        if is_link(entry):
            raise ValueError(f"不打包链接技能主文件：{entry.name}")
        original = entry.read_bytes()
        header, body, fields = entry_parts(original.decode("utf-8"))
        name = fields.get("name", "")
        if name != entry.stem:
            raise ValueError(f"技能名称必须与主文件名一致：{entry.name}")
        extra = {"slug": f"umeiko-{name}", "displayName": TITLES.get(name, name),
                 "version": version, "summary": fields.get("description", ""),
                 "homepage": "https://github.com/umeiko/UmEkO"}
        # Keep existing registry metadata if the administrator has supplied it.
        extra = {key: value for key, value in extra.items() if key not in fields}
        header += "\n" + "\n".join(f"{key}: {json.dumps(value, ensure_ascii=False)}" for key, value in extra.items())
        adapted = f"---\n{header}\n---\n\n{PREAMBLE}{body.lstrip()}"
        validate_entry(adapted)
        output = snapshot_dir / name
        if output.exists():
            raise ValueError(f"目标已经存在，请导出到新目录后比较更新：{output}")
        pack = source_root / name
        if is_link(pack):
            raise ValueError(f"不打包链接技能目录：{name}")
        members = safe_files(pack) if pack.is_dir() else {}
        files = {"SKILL.md": adapted.encode("utf-8"),
                 "references/host-compatibility.md": (TEMPLATES / "host-compatibility.md").read_bytes(),
                 **{f"{name}/{path}": data for path, data in members.items()}}
        sources = {entry.name: digest(original), **{f"{name}/{p}": digest(d) for p, d in members.items()}}
        changes = ["Added portable host instructions and SkillHub metadata to SKILL.md"]
        if name == "drawio-flowchart":
            config_name = f"{name}/config.json"
            config = json.loads(files[config_name])
            config["drawio_path"] = ""
            files[config_name] = (json.dumps(config, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
            changes.append("Cleared machine-specific drawio_path; preserved all other config fields")
        if any(script in members for script in ("prepare_drawio.py", "generate_drawio.py", "render_report.py")):
            files["scripts/run.py"] = (TEMPLATES / "run.py").read_bytes()
        manifest = {"name": name, "version": validate_entry(adapted)["version"],
                    "source_files_sha256": sources, "adaptations": changes,
                    "files_sha256": {p: digest(d) for p, d in sorted(files.items())}}
        files["package-manifest.json"] = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        for relative, data in files.items():
            target = output / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        exported.append(output)
    return exported


def package_skills(snapshot_dir: Path, output_dir: Path) -> list[Path]:
    packs = sorted(p.parent for p in snapshot_dir.glob("*/SKILL.md"))
    if not packs:
        raise ValueError("没有可打包的标准 Skill 目录")
    output_dir.mkdir(parents=True, exist_ok=True)
    outputs, records = [], []
    for pack in packs:
        fields = validate_entry((pack / "SKILL.md").read_text(encoding="utf-8"))
        files = safe_files(pack)
        manifest = json.loads(files["package-manifest.json"])
        actual = {p: digest(d) for p, d in files.items() if p != "package-manifest.json"}
        if actual != manifest["files_sha256"]:
            raise ValueError(f"快照清单不匹配：{pack.name}，请先审阅并更新清单")
        output = output_dir / f"{fields['name']}.zip"
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for relative, data in sorted(files.items()):
                path = PurePosixPath(relative)
                if path.is_absolute() or ".." in path.parts:
                    raise ValueError(f"不安全的包内路径：{relative}")
                info = zipfile.ZipInfo(relative, date_time=(2026, 10, 13, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o100644 << 16
                archive.writestr(info, data)
        with zipfile.ZipFile(output) as archive:
            if archive.testzip() is not None or "SKILL.md" not in archive.namelist():
                raise ValueError(f"ZIP 校验失败：{output.name}")
        if output.stat().st_size > 10_000_000:
            raise ValueError(f"ZIP 超过 10 MB：{output.name}")
        records.append({"name": fields["name"], "slug": fields["slug"], "version": fields["version"],
                        "zip": output.name, "size": output.stat().st_size, "files": len(files),
                        "sha256": digest(output.read_bytes())})
        outputs.append(output)
    (output_dir / "manifest.json").write_text(json.dumps({"skills": records}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output_dir / "SHA256SUMS.txt").write_text("".join(f"{r['sha256']}  {r['zip']}\n" for r in records), encoding="utf-8")
    return outputs


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="完整提取并打包 SkillHub ZIP（不读取数据库、不调用模型）")
    parser.add_argument("--source-root", type=Path, help="显式传入当前运行时技能目录以创建新快照")
    parser.add_argument("--snapshot-dir", type=Path, default=REPO / "skillhub")
    parser.add_argument("--output-dir", type=Path, default=REPO / "dist" / "skills" / "skillhub")
    parser.add_argument("--version", default="1.0.0")
    options = parser.parse_args()
    if options.source_root:
        export_skills(options.source_root, options.snapshot_dir, options.version)
    for output in package_skills(options.snapshot_dir, options.output_dir):
        print(output)
