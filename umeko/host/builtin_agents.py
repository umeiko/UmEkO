"""Install default agents and recognized stock upgrades, preserving admin choices."""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
import tempfile

from ..skillpacks import parse_skill_pack_text

IMAGE_QC_SLUG = "image-qc"
IMAGE_QC_SKILL = "doc-image-qc.md"
INSTALL_KEY = "BUILTIN_IMAGE_QC_INSTALLED"
ASSETS = Path(__file__).resolve().parents[1] / "builtin_skills"
REPORT_SCRIPT = Path("doc-image-qc/render_report.py")
# SHA-256 of UTF-8 text with normalized newlines: bundled v1 and the earlier stock library script.
_STOCK_REPORT_DIGESTS = {
    "e3b61d1203ae91d4e3c7bbef9191f69cc844b0d48351744d3b25d1fb62e0ebfb",
    "19b4b417e2e74fd23787013e50a4a9c7aed39f47310540be13d95747799d3ef7",
    "9099203363b3e831dd7f0112cbfe280fb93b435f83ceb1def97bcd6150df1bc4",
}
_STOCK_SKILL_DIGESTS = {
    "381ba0c51c222a38318a7c4b078a03cff22fcd0e470685fe0748c6f38d9c9d1a",
    "2d08877be8ebaf950709cef13b6243903d144a590b48ff9e23fad299a263355e",
}
_STOCK_PROMPT_DIGESTS = {
    "6cb2e6ef66310b9b5df714642db4fb21a446711a0e084ed8cdc0f0848f3ab359",
}

IMAGE_QC_PROMPT = """你是图像质检智能体，帮助用户检查图片质量、图文一致性与可见问题，并交付可下载的检查报告。
收到图片质检任务时，先用 use_skill(name="doc-image-qc") 读取工作指引，再按需读取 checks.md。
支持单张图片、多张图片、Markdown 图文文档及包含文档和图片的压缩包。
只有图片时检查可见内容；没有配套正文、参考界面或产品资料时，明确标记无法核对的项目，不能编造依据。
使用已配置的视觉模型进行图像推理；无法使用视觉工具时说明需要管理员配置视觉模型，不把失败当作通过。
确认所需图片、文档或必要参照无法取得，且任务因此不能继续时，立即返回缺失项、已做的检查和补齐步骤，
通知外层 Agent 或用户进入本任务的临时工作台上传资料、补充说明或继续处理；不要空等、轮询文件或反复尝试同一失败操作。
要求外层 Agent 及时将任务响应中的 workspace_url（A2A 为 metadata.workspaceUrl）真实链接提供给用户，并附上待处理事项。
如果当前上下文已有服务返回的真实链接，直接附上；如果没有，明确指向上述响应字段，不编造地址、随机标识或本地环回链接。
未返回工作台链接时说明当前无法提供链接，请调用方使用有效的完整任务权限或已有工作台补齐资料，不声称已经通知对方。
仅缺可选正文或产品参照时，仍完成可执行的图片检查，将无法核对的项目记 NA，不能要求所有纯图片任务补文档。
检查结论记录证据、问题位置及修改建议，报告写入 generate/，不改动输入文件。
问候和能力咨询直接简洁回答；不相关的请求不加载质检正文、不反复提醒用户挂载技能。"""

FLOW_CHART_SLUG = "flow-chart-agent"
IMAGE_REASONING_SLUG = "image-resioning-agent"

BUILTIN_SERVICE_AGENTS = (
    {
        "slug": FLOW_CHART_SLUG,
        "name": "流程图生成Agent",
        "description": "根据需求文档或文字生成、修改简明可编辑的流程图和架构图，支持用户指定风格与图片导出，按需复检。",
        "skill_names": ["drawio-flowchart.md"],
        "system_prompt": """你是流程图生成智能体，帮助用户把需求转成简明、清晰、可编辑的流程图或架构图。
收到绘图或修改图表的任务时，先用 use_skill(name="drawio-flowchart") 读取工作指引，再按该 Skill 执行。
绘图规则、风格、委派、布局、导出和可选复检由 Skill 决定。
若所需 Skill 未下发，说明请管理员启用对应默认 Skill，不声称已经完成绘图。
交付实际生成的文件及其可下载链接。问候和能力咨询直接简洁回答。""",
    },
    {
        "slug": IMAGE_REASONING_SLUG,
        "name": "图像推理Agent",
        "description": "接受单图或最多 5 张图片及开放式提示词，进行图文问答、几何解题、因果推理与场景线索分析。",
        "skill_names": ["image-reasoning.md"],
        "system_prompt": """你是图像推理智能体，帮助用户结合图片与文字解答开放性问题。
收到图文分析或解题任务时，先用 use_skill(name="image-reasoning") 读取工作指引，再按该 Skill 执行。
每次任务支持 1 至 5 张图片，允许用户自由描述问题；沿用当前任务或会话中明确指向的图片进行追问。
若所需 Skill 未下发，说明请管理员启用对应默认 Skill。问候和能力咨询直接简洁回答。""",
    },
)


def agent_installation_key(slug: str) -> str:
    return "BUILTIN_AGENT_INSTALLED_" + slug


def _upgrade_stock_file(library_dir: Path, relative: Path, digests: set[str]) -> bool:
    """Never recreate a deleted file or replace an unknown/customized version."""
    target = library_dir / relative
    if not target.is_file() or target.resolve() != library_dir.resolve() / relative:
        return False
    temporary = None
    try:
        current = target.read_text(encoding="utf-8")
        if hashlib.sha256(current.encode("utf-8")).hexdigest() not in digests:
            return False
        with tempfile.NamedTemporaryFile(dir=target.parent, prefix=".report-upgrade-", delete=False) as output:
            temporary = Path(output.name)
            output.write((ASSETS / relative).read_bytes())
        temporary.replace(target)
        return True
    except (OSError, UnicodeError):
        logging.getLogger(__name__).warning("Could not upgrade stock image QC asset %s", relative, exc_info=True)
        return False
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _upgrade_stock_report(library_dir: Path) -> bool:
    return _upgrade_stock_file(library_dir, REPORT_SCRIPT, _STOCK_REPORT_DIGESTS)


def _upgrade_builtin_assets(store, library_dir: Path) -> bool:
    report_updated = _upgrade_stock_report(library_dir)
    skill_updated = _upgrade_stock_file(library_dir, Path(IMAGE_QC_SKILL), _STOCK_SKILL_DIGESTS)
    # Library text and the dispatched DB copy are separate; synchronize only recognized defaults.
    source = library_dir / IMAGE_QC_SKILL
    if source.is_file() and source.resolve() == library_dir.resolve() / IMAGE_QC_SKILL:
        try:
            latest = (ASSETS / IMAGE_QC_SKILL).read_text(encoding="utf-8")
            current = store.default_skill(IMAGE_QC_SKILL)
            if (current is not None and source.read_text(encoding="utf-8") == latest
                    and hashlib.sha256(current.replace("\r\n", "\n").encode()).hexdigest() in _STOCK_SKILL_DIGESTS):
                store.upsert_default_skill(IMAGE_QC_SKILL, latest)  # Keeps the enabled/disabled state.
                skill_updated = True
        except (OSError, UnicodeError):
            logging.getLogger(__name__).warning("Could not synchronize the stock image QC skill", exc_info=True)
    return report_updated or skill_updated


def _upgrade_stock_prompt(registry) -> bool:
    """Upgrade an unchanged stock prompt without replacing other administrator choices."""
    with registry.store.connect() as db:
        row = db.execute("SELECT id,definition_json FROM agent_definitions WHERE slug=?", (IMAGE_QC_SLUG,)).fetchone()
        if row is None:
            return False
        definition = json.loads(row["definition_json"])
        current = definition.get("system_prompt", "").replace("\r\n", "\n")
        if hashlib.sha256(current.encode("utf-8")).hexdigest() not in _STOCK_PROMPT_DIGESTS:
            return False
        definition["system_prompt"] = IMAGE_QC_PROMPT
        # Compare the original JSON to preserve an edit made during startup.
        changed = db.execute("UPDATE agent_definitions SET definition_json=?,updated_at=? WHERE id=? AND definition_json=?",
                             (json.dumps(definition, ensure_ascii=False), datetime.now(timezone.utc).isoformat(),
                              row["id"], row["definition_json"])).rowcount
        return bool(changed)


def _install_image_qc_agent(registry, library_dir: Path) -> bool:
    store = registry.store
    if store.config().get(INSTALL_KEY) == "1":
        assets_updated = _upgrade_builtin_assets(store, library_dir)
        prompt_updated = _upgrade_stock_prompt(registry)
        return assets_updated or prompt_updated
    # Materialize editable library sources. An existing source or script wins.
    sources = [ASSETS / IMAGE_QC_SKILL, *sorted((ASSETS / Path(IMAGE_QC_SKILL).stem).rglob("*"))]
    for source in sources:
        if not source.is_file() or "__pycache__" in source.parts:
            continue
        target = library_dir / source.relative_to(ASSETS)
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            with target.open("xb") as output:
                output.write(source.read_bytes())
        except FileExistsError:
            pass
    _upgrade_builtin_assets(store, library_dir)
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
    _upgrade_stock_prompt(registry)
    store.set_config({INSTALL_KEY: "1"})
    return True


def install_builtin_agents(registry, library_dir: Path) -> bool:
    # Import locally: the generic skill installer shares the QC asset constants.
    from .builtin_skills import install_builtin_skills

    store = registry.store
    existing_skills = {item["name"] for item in store.default_skills()}
    changed = _install_image_qc_agent(registry, library_dir)
    changed = install_builtin_skills(store, library_dir) or changed
    for definition in BUILTIN_SERVICE_AGENTS:
        key = agent_installation_key(definition["slug"])
        if store.config().get(key) == "1":
            continue
        if not any(item["slug"] == definition["slug"] for item in registry.list()):
            skills = {item["name"]: item for item in store.default_skills()}
            if all(name in skills for name in definition["skill_names"]):
                # Enable only newly installed dependencies. Existing admin toggles win.
                for name in definition["skill_names"]:
                    if name not in existing_skills:
                        store.set_default_skill_enabled(name, True)
                        skills[name]["enabled"] = True
                registry.save({**definition, "disclosed_model_ids": [],
                               "enabled": all(skills[name]["enabled"] for name in definition["skill_names"])})
        # Keep subsequent edits, disabling and deletion, including removed dependencies.
        store.set_config({key: "1"})
        changed = True
    return changed
