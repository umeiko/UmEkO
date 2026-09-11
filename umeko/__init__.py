"""UMEKO — Unified Multi-agent Execution Kernel & Orchestrator.

统一多智能体执行内核与编排器：通用 Agent 基座。

- Unified：统一模型（OpenAI 兼容双模型）、工具（Skill 抽象）、状态（Session）与运行接口
- Multi-agent：主 Agent + 受限文件子 Agent（delegate_task），支持单/多 Agent 协作
- Execution Kernel：function-calling 循环、流式、取消、上下文压缩、判定解析
- Orchestrator：主/子 Agent 编排、任务交接与生命周期

从 Flowchart-cli 拆出的通用基座；流程图领域内容（mermaid/drawio/风格/作图循环）
不属于本包。
"""

try:
    from importlib.metadata import version as _pkg_version

    __version__ = _pkg_version("umeko")
except Exception:  # 未以包形式安装（直接源码运行）时的回退
    __version__ = "0.1.0"
