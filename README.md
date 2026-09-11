# UMEKO — Unified Multi-agent Execution Kernel & Orchestrator

**统一多智能体执行内核与编排器**：通用 Agent 基座，从 Flowchart-cli 拆出的领域无关内核。

- **Unified**：统一模型（OpenAI 兼容，文本/视觉双模型）、工具（Skill 抽象，与 MCP inputSchema 同构）、状态（Session：产物边界 + 工作文档 + Skill 挂载）。
- **Multi-agent**：主 Agent 对话式调度 + 受限文件子 Agent（delegate_task，汇报后上下文销毁）。
- **Execution Kernel**：function-calling 主循环、流式收干、取消感知、上下文压缩/清空。
- **Orchestrator**：Skill 系统、任务交接、生命周期管理。

**基座不内置任何领域流程**：系统提示词、领域工具、意图路由全部由调用方注入。

## 结构

```
umeko/
├── agent.py       # 主 Agent：function-calling 主循环、上下文管理、delegate_task
├── sub_agent.py   # 文件子 Agent（受限工具、大文件 force_read、上下文即毁）
├── session.py     # Session：产物目录边界、工作文档、Skill 挂载
├── skills/        # Skill 抽象 + 内置文件/图像/命令工具（build_file_tools）
├── skillpacks.py  # 提示词型技能包（skills/*.md，frontmatter + 操作手册）
├── skill_agent.py # create_skill：Agent 自主沉淀可复用流程
├── llm/           # OpenAI 兼容客户端（流式收干、reasoning 回传、取消）
├── cancellation.py# 协作式取消（Esc/按钮 → OperationCancelled）
├── images.py      # 图像校验与 data URL
├── runtime.py     # 冻结/开发环境路径
└── prompts/       # OCR 提示词
```

## 作为平台使用

```python
from umeko import Session, Settings, UmekoAgent

settings = Settings.from_env()
session = Session(output_dir="./output")

agent = UmekoAgent(
    settings, session,
    system_prompt=MY_SYSTEM_PROMPT,      # 领域系统提示词
    extra_skills=[my_domain_skill],      # 领域工具（Skill 抽象，同构 MCP）
    on_token=print, on_tool=...,         # UI 回调
)
result = agent.chat("帮我汇总这几个文件", images=[...])
```

## 留在 Flowchart-cli 的领域内容（未迁入）

- `drawio/`、`mermaid/`、`styles/`：drawio/Mermaid 渲染、导出、主题样式；
- `agent.py` 的生成-渲染-验证循环与 XML/HTML 修复；
- `router.py`（领域意图路由）、`server/`、`chat_cli/`（界面层，按需按"适配器"移植）。

## 开发

```bash
cp .env.example .env   # 配置模型
python -m venv .venv && .venv/Scripts/pip install openai python-dotenv pytest
PYTHONPATH=$PWD .venv/Scripts/python -m pytest tests -q
PYTHONPATH=$PWD .venv/Scripts/python -m umeko.cli   # 最小 REPL 冒烟
```

> 注意：项目路径含中文时不要用 `pip install -e .`（生成的 .pth 会让 venv 按 GBK 解码崩溃），用 `PYTHONPATH` 方式运行。

领域项目以依赖或 fork 方式引入 Umeko，注入自己的 `system_prompt` 与 `extra_skills` 即可。
