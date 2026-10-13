import pytest

from umeko.config import ModelConfig, Settings
from umeko.host.builtin_agents import IMAGE_QC_PROMPT, install_builtin_agents
from umeko.server.app import create_app

LEGACY_IMAGE_QC_PROMPT = """你是图像质检智能体，帮助用户检查图片质量、图文一致性与可见问题，并交付可下载的检查报告。
收到图片质检任务时，先用 use_skill(name="doc-image-qc") 读取工作指引，再按需读取 checks.md。
支持单张图片、多张图片、Markdown 图文文档及包含文档和图片的压缩包。
只有图片时检查可见内容；没有配套正文、参考界面或产品资料时，明确标记无法核对的项目，不能编造依据。
使用已配置的视觉模型进行图像推理；无法使用视觉工具时说明需要管理员配置视觉模型，不把失败当作通过。
检查结论记录证据、问题位置及修改建议，报告写入 generate/，不改动输入文件。
问候和能力咨询直接简洁回答；不相关的请求不加载质检正文、不反复提醒用户挂载技能。"""


@pytest.mark.parametrize("customized", [False, True])
def test_prompt_upgrade_preserves_admin_choices_and_deleted_skill(tmp_path, customized):
    app = create_app(Settings(ModelConfig("fixture", "fixture-key", "https://unused.invalid")),
                     data_root=tmp_path / "data", workspace_root=tmp_path / "out")
    service, store = app.state.agent_service, app.state.store
    registry = service.agent_registry
    original = registry.by_slug("image-qc")
    provider = store.create_provider("fixture", "https://unused.invalid", "fixture-key")
    text = store.add_model(provider["id"], "chosen-text")
    vision = store.add_model(provider["id"], "chosen-vision", True)
    prompt = LEGACY_IMAGE_QC_PROMPT + ("\nAdministrator custom instructions" if customized else "")
    saved = registry.save({**original, "name": "Customized name", "description": "Custom description",
                           "enabled": False, "default_model_id": text["id"],
                           "default_vision_model_id": vision["id"], "system_prompt": prompt}, original["id"])
    # Prompt migration must work without revalidating or restoring a deliberately removed skill.
    store.delete_default_skill("doc-image-qc.md")
    library = service._skills_library_dir()
    (library / "doc-image-qc.md").unlink()
    assert install_builtin_agents(registry, library) is (not customized)
    upgraded = registry.get(original["id"])
    assert upgraded["system_prompt"] == (prompt if customized else IMAGE_QC_PROMPT)
    assert {k: v for k, v in upgraded.items() if k not in {"system_prompt", "updated_at"}} == {
        k: v for k, v in saved.items() if k not in {"system_prompt", "updated_at"}}
    assert store.default_skill("doc-image-qc.md") is None
    assert not (library / "doc-image-qc.md").exists()
    assert not install_builtin_agents(registry, library)
    registry.delete(original["id"])
    assert not install_builtin_agents(registry, library)
    assert "image-qc" not in {item["slug"] for item in registry.list()}
