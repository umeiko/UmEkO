"""统一运行事件协议（L1）。

引擎（UmekoAgent / FileSubAgent）只产生这里定义的事件；
CLI / Web / IDE 各交付端把同一份事件渲染成自己的形态（打印 / SSE / webview
消息），互不感知。这是前后端解耦的总开关。

轻量类型化约定：type 为字符串常量、data 为 dict —— 新增事件类型不破坏旧前端，
旧事件类型的 data 只增字段不改语义。
"""

from __future__ import annotations

from dataclasses import dataclass, field

# ---- 引擎事件（L1：UmekoAgent 产生，data 随类型而定） ----
ASSISTANT_DELTA = "assistant.delta"    # {text} 助手正文流式增量
REASONING_DELTA = "reasoning.delta"    # {text} 思考流增量（reasoning_content）
TOOL_TICK = "tool.tick"                # {text} 工具参数流式增量（token 估算用）
TOOL_STARTED = "tool.started"          # {name, arguments}
TOOL_COMPLETED = "tool.completed"      # {name, result}
PROGRESS_UPDATED = "progress.updated"  # {message}
SUBAGENT_PREFIX = "subagent."          # subagent.<started|update|finished|usage|tool.*>，data 透传

# ---- 宿主事件（L2：host/service 在引擎事件之上合成） ----
USAGE_DELTA = "usage.delta"            # {chars, kind: assistant|reasoning|tool|subagent}
WORKSPACE_CHANGED = "workspace.changed"  # {reason}
RESOURCE_ACTIVATED = "resource.activated"
REASONING_STATUS = "reasoning.status"  # {status: thinking}
RUN_QUEUED = "run.queued"
RUN_STARTED = "run.started"
RUN_CANCELLING = "run.cancelling"
RUN_COMPLETED = "run.completed"
RUN_FAILED = "run.failed"
RUN_CANCELLED = "run.cancelled"


@dataclass(frozen=True)
class RunEvent:
    """一次运行中的单个事件。type 取本模块常量；data 语义见各常量注释。"""

    type: str
    data: dict = field(default_factory=dict)
