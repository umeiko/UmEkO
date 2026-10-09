"""Install the packaged image QC agent once, without replacing administrator edits."""
from __future__ import annotations

from pathlib import Path

from ..skillpacks import parse_skill_pack_text

IMAGE_QC_SLUG = "image-qc"
IMAGE_QC_SKILL = "doc-image-qc.md"
INSTALL_KEY = "BUILTIN_IMAGE_QC_INSTALLED"
ASSETS = Path(__file__).resolve().parents[1] / "builtin_skills"

IMAGE_QC_PROMPT = """你是图像质检智能体，帮助用户检查图片质量、图文一致性与可见问题，并交付可下载的检查报告。
收到图片质检任务时，先用 use_skill(name="doc-image-qc") 读取工作指引，再按需读取 checks.md。
支持单张图片、多张图片、Markdown 图文文档及包含文档和图片的压缩包。
只有图片时检查可见内容；没有配套正文、参考界面或产品资料时，明确标记无法核对的项目，不能编造依据。
使用已配置的视觉模型进行图像推理；无法使用视觉工具时说明需要管理员配置视觉模型，不把失败当作通过。
检查结论记录证据、问题位置及修改建议，报告写入 generate/，不改动输入文件。
问候和能力咨询直接简洁回答；不相关的请求不加载质检正文、不反复提醒用户挂载技能。"""


def install_builtin_agents(registry, library_dir: Path) -> bool:
    store = registry.store
    if store.config().get(INSTALL_KEY) == "1":
        return False
    # Materialize editable library sources. An existing source or script wins.
    for source in sorted(ASSETS.rglob("*")):
        if not source.is_file() or "__pycache__" in source.parts:
            continue
        target = library_dir / source.relative_to(ASSETS)
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            with target.open("xb") as output:
                output.write(source.read_bytes())
        except FileExistsError:
            pass
    if store.default_skill(IMAGE_QC_SKILL) is None:
        content = (library_dir / IMAGE_QC_SKILL).read_text(encoding="utf-8")
        if parse_skill_pack_text(content) is None:
            raise ValueError("图像质检技能格式无效，请检查技能库中的 doc-image-qc.md")
        store.upsert_default_skill(IMAGE_QC_SKILL, content)
    if not any(item["slug"] == IMAGE_QC_SLUG for item in registry.list()):
        skill = next(item for item in store.default_skills() if item["name"] == IMAGE_QC_SKILL)
        registry.save({
            "slug": IMAGE_QC_SLUG,
            "name": "图像质检",
            "description": "检查单张图片或图文文档的图片质量、图文一致性及可见问题，生成检查清单与可下载的质检报告。",
            "system_prompt": IMAGE_QC_PROMPT,
            "skill_names": [IMAGE_QC_SKILL],
            "enabled": bool(skill["enabled"]),
        })
    # Later edits, disabling or deletion are deliberate choices, including deletion of skills.
    store.set_config({INSTALL_KEY: "1"})
    return True
