"""Visual capability prompts and real tool loops with controlled model replies."""
from copy import deepcopy
import base64
import json
import shutil

import pytest
from openai.types.chat import ChatCompletionMessage

from umeko.agent import UmekoAgent
from umeko.config import ModelConfig, Settings
from umeko.host.builtin_agents import ASSETS, IMAGE_QC_PROMPT
from umeko.llm import LLMClient
from umeko.prompts.system import DEFAULT_SYSTEM
from umeko.session import Session


PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/lXcAAAAASUVORK5CYII=")


def reply(content="done", *, tool=None, arguments=None, call_id="call"):
    return ChatCompletionMessage(role="assistant", content=content, tool_calls=[{
        "id": call_id, "type": "function", "function": {
            "name": tool, "arguments": json.dumps(arguments, ensure_ascii=False),
        },
    }] if tool else None)


@pytest.fixture
def agent_factory(tmp_path):
    agents = []

    def make(*, main_vision=False, separate_vision=False, sub_vision=False, qc=False):
        root = tmp_path / str(len(agents))
        roots = tuple(root / name for name in ("workspace", "attachments", "generate"))
        for directory in roots:
            directory.mkdir(parents=True)
        library = root / "client/skills"
        library.mkdir(parents=True)
        if qc:
            shutil.copy2(ASSETS / "doc-image-qc.md", library)
            shutil.copytree(ASSETS / "doc-image-qc", library / "doc-image-qc")
        model = lambda name: ModelConfig(name, "fixture-key", "http://unused.invalid")
        settings = Settings(model("main"), text_model_vision=main_vision,
                            vision_model=model("visual") if separate_vision else None,
                            sub_model=model("sub"), sub_model_vision=sub_vision)
        session = Session(settings, roots[2], skill_dir=library)
        events = []
        agent = UmekoAgent(settings, session, DEFAULT_SYSTEM + (IMAGE_QC_PROMPT if qc else ""),
                           readable_root=root, readable_roots=roots,
                           on_event=lambda name, data: events.append((name, data)))
        agents.append(agent)
        image = roots[1] / "sample.png"
        image.write_bytes(PNG)
        return agent, image, events

    yield make
    for agent in agents:
        agent.close()


@pytest.mark.parametrize("main_vision", [False, True])
@pytest.mark.parametrize("separate_vision", [False, True])
@pytest.mark.parametrize("sub_vision", [False, True])
def test_prompt_reports_actual_visual_capabilities(agent_factory, main_vision, separate_vision, sub_vision):
    agent, _, _ = agent_factory(main_vision=main_vision, separate_vision=separate_vision, sub_vision=sub_vision)
    system = agent._messages[0]["content"]
    assert "ocr_image" not in system
    assert ("read_image" in agent._skills) == main_vision
    assert ("image_reasoning" in agent._skills) == (main_vision or separate_vision)
    assert ("image_reasoning" in agent._subagent._skills) == (sub_vision or separate_vision)
    if "image_reasoning" in agent._skills:
        assert "当前工具列表已提供 image_reasoning" in system
        assert "不要仅因当前模型不能直接看图就拒答" in system
        assert "当前会话没有可用的视觉分析能力" not in system
        assert "普通看图问题也可以调用" in agent._skills["image_reasoning"].description
    elif sub_vision:
        assert "文件子 Agent 已提供 image_reasoning" in system
        assert "需要看图时用 delegate_task" in system
    else:
        assert "当前会话没有可用的视觉分析能力" in system
    if "image_reasoning" in agent._skills and "image_reasoning" in agent._subagent._skills:
        assert agent._skills["image_reasoning"].description == agent._subagent._skills["image_reasoning"].description


def test_text_main_can_answer_non_ocr_image_question_with_visual_tool(agent_factory, monkeypatch):
    agent, image, events = agent_factory(separate_vision=True)
    requests, visual_calls = [], []
    question = "这张图里的两个区域分别表示什么？"
    visual_prompt = question + "请按画面区域解释布局，不要猜测无法确认的内容。"

    def text_chat(llm, messages, tools, **kwargs):
        requests.append(deepcopy(messages))
        if len(requests) == 1:
            assert isinstance(messages[-1]["content"], str)
            assert question in messages[-1]["content"] and str(image) in messages[-1]["content"]
            return reply(tool="image_reasoning", arguments={"prompt": visual_prompt, "image_paths": ["attachments/sample.png"]})
        assert messages[-1]["role"] == "tool" and "布局分析结果" in messages[-1]["content"]
        return reply("根据图片分析结果回答。")

    def visual_chat(llm, messages, image_paths, **kwargs):
        assert llm._model.name == "visual"
        visual_calls.append((messages, image_paths))
        kwargs["on_delta"]("布局分析结果")
        return "布局分析结果"

    monkeypatch.setattr(LLMClient, "chat_with_tools_stream", text_chat)
    monkeypatch.setattr(LLMClient, "chat_with_images_stream", visual_chat)
    assert agent.chat(question, images=[image]) == "根据图片分析结果回答。"
    assert visual_calls == [([{"role": "user", "content": visual_prompt}], [image])]
    assert any(name == "tool.progress" and data["output_delta"] == "布局分析结果" for name, data in events)
    assert not agent._skill_results  # Ordinary visual questions need no skill package.


def test_subagent_accepts_general_visual_task_without_skill_and_respects_tool_filter(agent_factory, monkeypatch):
    agent, image, _ = agent_factory(sub_vision=True)
    requests, visual_calls = [], []

    def text_chat(llm, messages, tools, **kwargs):
        requests.append(deepcopy(messages))
        if len(requests) == 1:
            assert "普通图像理解按主 Agent 转交的用户要求执行，不以 Skill 为前提" in messages[0]["content"]
            return reply(tool="image_reasoning", arguments={"prompt": "解释图片布局", "image_paths": ["attachments/sample.png"]})
        return reply("布局已说明")

    def visual_chat(llm, messages, image_paths, **kwargs):
        assert llm._model.name == "sub" and image_paths == [image]
        visual_calls.append(messages[0]["content"])
        return "布局已说明"

    monkeypatch.setattr(LLMClient, "chat_with_tools_stream", text_chat)
    monkeypatch.setattr(LLMClient, "chat_with_images_stream", visual_chat)
    assert agent._subagent.run("解释 attachments/sample.png 的布局") == "布局已说明"
    assert visual_calls == ["解释图片布局"]
    assert agent._subagent.run("只列目录", allowed_tools={"list_dir"}) == "布局已说明"
    assert "当前会话没有可用的视觉分析能力" in requests[-1][0]["content"]
    assert "当前工具列表已提供 image_reasoning" not in requests[-1][0]["content"]


def test_qc_keeps_skill_workflow_and_passes_checks_to_delegated_visual_tool(agent_factory, monkeypatch):
    agent, image, _ = agent_factory(separate_vision=True, qc=True)
    checks = (ASSETS / "doc-image-qc/checks.md").read_text(encoding="utf-8").strip()
    visual_prompt = "按以下技能检查标准质检此图片，逐项给出结论与证据；缺少参照记 NA：\n" + checks
    task = "质检 attachments/sample.png。使用 image_reasoning，完整检查标准与要求：\n" + visual_prompt
    main_requests, sub_requests, visual_calls = [], [], []

    def text_chat(llm, messages, tools, **kwargs):
        if llm._model.name == "main":
            main_requests.append(deepcopy(messages))
            if len(main_requests) == 1:
                return reply(tool="use_skill", arguments={"name": "doc-image-qc"}, call_id="skill")
            if len(main_requests) == 2:
                assert "只当调度器" in messages[-1]["content"]
                assert "阶段 2：逐图质检" in messages[-1]["content"]
                return reply(tool="delegate_task", arguments={"task": task}, call_id="delegate")
            return reply("图片已检查，按质检技能继续处理报告。")
        sub_requests.append(deepcopy(messages))
        if len(sub_requests) == 1:
            assert "C1" in messages[-1]["content"] and checks in messages[-1]["content"]
            return reply(tool="image_reasoning", arguments={"prompt": visual_prompt, "image_paths": ["attachments/sample.png"]})
        return reply("sample.png | WARN | 缺少正文参照，相关项目为 NA")

    def visual_chat(llm, messages, image_paths, **kwargs):
        visual_calls.append((llm._model.name, messages[0]["content"], image_paths))
        return "图像已检查，缺少正文参照的项目为 NA。"

    monkeypatch.setattr(LLMClient, "chat_with_tools_stream", text_chat)
    monkeypatch.setattr(LLMClient, "chat_with_images_stream", visual_chat)
    assert "按质检技能" in agent.chat("按图像质检技能检查这张图片", images=[image])
    assert visual_calls == [("visual", visual_prompt, [image])]
    assert not any(call.get("function", {}).get("name") == "image_reasoning"
                   for message in agent._messages for call in message.get("tool_calls", []))
    assert "必须遵守，不用通用看图流程替代它" in agent._messages[0]["content"]
    assert "专业质检的检查标准与执行流程必须来自主 Agent 交给你的 Skill" in sub_requests[0][0]["content"]
