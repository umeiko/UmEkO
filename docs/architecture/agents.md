# 多智能体管理

一个 UMEKO 服务可以交付多个 Agent。管理员为每个 Agent 设置名字、介绍、工作指引、默认模型和技能选择；调用者通过不同路径使用它们。它们共享执行引擎、Provider 配置和模型并发队列。

例如，图文质检与文档整理可以分别使用 `/agent/image-qc` 和 `/agent/document-organizer`。二者的 Card、任务列表和技能选择独立，无需再部署两个进程。

## 配置如何进入执行链路

```mermaid
flowchart TB
    Admin[智能体管理表单] --> Registry[AgentRegistry · SQLite 配置]
    Defaults[默认 Skill 数据库副本] --> Registry
    Caller[调用者] --> Path[/agent/slug 路径解析]
    Registry --> Path
    Path --> Card[公开 Card · 介绍与所选技能的元数据]
    Path --> Protocols[MCP / A2A / REST]
    Protocols --> Tasks[共享 TaskService · Agent 与调用者归属]
    Tasks --> Snapshot[提交时保存工作指引与主 Skill 文本副本]
    Snapshot --> Engine[Session / Agent / 子 Agent]
    Engine --> Queue[共享每模型并发队列]
    Queue --> Models[共享 Provider / Model]
```

`AgentRegistry` 位于宿主层，不依赖 HTTP。接入层解析 URL，找到启用的配置，然后复用现有协议适配器和任务服务。没有为每个 Agent 启动一份 MCP 服务、Worker 池或模型队列。

| 内容 | 保存位置 / 行为 |
| --- | --- |
| 名称、介绍、版本、可选链接与提供方 | `agent_definitions`，用于生成公开 Card |
| 工作指引 | 同表；只供内部执行和管理员维护 |
| 默认模型 | 引用 Provider 管理中的模型 ID，不复制密钥 |
| 技能选择 | 引用“默认 Skill”的文件名；只下发所选且已启用、可解析的项 |
| Task 归属 | `service_tasks.agent_id`，每个新任务必须通过具体 Agent 的路径提交 |
| 执行快照 | Task 的私有 `input_json`，包含 Agent 配置和主 Skill 文本 |

## Skills 与 Card 使用同一份来源

管理员先在“默认 Skill”维护技能，再在“智能体管理”勾选该 Agent 使用的技能。Card 只披露这些技能的文件名、名称和介绍；新任务把对应主文档复制到自己的工作区。未选中的技能包不能通过 `use_skill` 的附属文件入口、`read_pack_file` 或 `run_skill_script` 访问。

这层选择控制的是技能包使用范围。文件处理、图像推理等基础工具仍由共享引擎提供。当前不提供每个 Agent 单独的基础工具白名单，也不对工作指引做强制业务流程编排。

## 配置修改与任务生命周期

提交时保存工作指引、技能选择和主 Skill 文本，明确设置的默认模型 ID 也在提交时写入任务。排队期间修改这些配置，不会改变该任务保存的内容。模型密钥继续从共享 Provider 配置读取；未指定 Agent 默认模型时沿用平台的默认选择机制。

快照覆盖主 Skill 文档，不复制整个技能目录。脚本及附属资源执行时仍读取技能库的当前文件；需要严格复现历史脚本时，应另做技能包版本管理。

停用 Agent 后，它的公开路径返回 404，已接收任务继续执行。资源监控可查看和停止这些任务；重新启用后，未到期结果可以继续通过原路径读取。有保留任务时禁止删除配置，需等任务到期清理后再删除。

## 隔离与共享的边界

Task 查询、列表、取消、事件、产物、幂等键和 A2A Context 都按“Agent + 调用者”检查归属。同一账号从另一个 Agent 路径访问 Task，得到 404。原始服务凭据仍是平台级的 scope 授权，当前没有按 Agent 分配凭据的管理功能。

免鉴权调用共用一个身份，因此同一个 Agent 内的免凭据调用仍能互相读取任务。来源 IP 只用于监控记录。任务容量、调用者额度和每模型并发限制继续全平台共享，不因增加 Agent 数量而扩大模型额度。

机器调用只通过 `/agent/{slug}/...` 提供。顶级 MCP、A2A、Card、Task 和 OAuth 入口均返回 404，全局 Card 配置与编辑接口已移除。网页聊天和 CLI 保持自己的入口与生命周期，Agent 路径仅提供机器服务。管理界面统一在“服务接入”下维护智能体和鉴权。

配置接口和实际地址见[智能体管理 API](../api/agents.md)。
