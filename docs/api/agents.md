# 智能体管理

在管理端打开“服务接入”下的“智能体管理”，点击“新建智能体”，填写名称、访问路径和介绍，勾选需要的默认 Skill，然后保存。可选填内部工作指引、默认模型和默认视觉模型。弹窗会显示该 Agent 的完整调用地址与只读 Card 预览，配置立即生效并在重启后保留。URL 中的 `<name>` 对应这里填写的访问路径 `slug`，与用于展示的中文名称分开。

“配置与入口”弹窗分为“配置”“调用入口”“MCP 披露”和“Agent Card”。切换标签保留未保存的配置；公开卡片与披露详情展示已保存的服务定义。MCP 下可查看工具、资源、提示词及原始 JSON，工具详情包含说明、参数、必填项、默认值、`inputSchema`、`outputSchema` 和协议标注。停用 Agent 仍可在管理端查看定义，但实际外部调用返回 `404`。

## 自带的绘图与图像推理智能体

| 名称 | 访问路径 | 默认 Skill | 用途 |
| --- | --- | --- | --- |
| 流程图生成Agent | `flow-chart-agent` | `drawio-flowchart.md` | 从文档或文字生成、修改简明流程图和架构图，交付可编辑文件及图片 |
| 流程图修正 | `flowchart-correction` | `drawio-correction.md` | Mermaid 流程源码、单页 draw.io XML 或简短 Markdown 流程转换/整理风格，只交付 `.drawio` 或 XML |
| 图像推理Agent | `image-resioning-agent` | `image-reasoning.md` | 单图或最多 5 张图配合自由提示词，做图文问答、几何解题、因果推理和场景线索分析 |

首次安装这些智能体时启用其新安装的默认 Skill；如果技能已有管理员维护的启用/停用状态，则保留该状态，依赖被停用时新智能体也保持停用。已有同访问路径的配置不被覆盖；安装后编辑、停用或删除均不会在重启时被撤销。默认模型留空，沿用平台模型设置，管理员可给每个智能体选择专用模型。机器入口仍为 `<用户服务基址>/agent/<访问路径>/...`，管理前缀独立。

流程图智能体只负责加载绘图 Skill，绘图规范与实现都留在技能包中。该 Skill 使用 draw.io 原生 XML 和确定性布局，预装流程图、架构图风格；需求读取和 XML 编写交给平台现有文件子 Agent。默认不做图像复检，用户要求时做一到两轮。服务环境需安装 draw.io 桌面版，通过技能的 `config.json` 中 `drawio_path` 配置可执行文件，或设置 `UMEKO_DRAWIO_PATH`；未配置时仍可生成 `.drawio`。字体也需安装在服务环境中。可运行 `python scripts/package_drawio_skill.py` 构建独立 ZIP，解包到技能库后在后台导入，或分别上传主 MD 和同名目录的成员文件。

流程图修正用于已有流程的快速转换，不从图片或长文档设计流程。先运行技能门禁，接受 Mermaid `flowchart/graph`、单页单层 draw.io XML（含压缩 diagram）和编号/箭头表达的简短 Markdown 流程；其他输入简短说明原因后结束。门禁在第一次技能脚本调用执行，格式/规模检查不调用模型；内容是否确实是流程仍由智能体判断，并不是 HTTP 接收前的服务端硬拦截。有效任务只做一次转换及结构/语义保护校验，默认不导出图片或视觉复检，因此不依赖 draw.io 桌面程序。XML 上限 100,000 字符，Mermaid 8,000 字符/120 行，Markdown 2,000 字符/30 行，最多 60 节点/120 连线；更复杂的流程可拆分或交给流程图生成智能体。

未指定风格时，两种绘图技能复用同源的内置 `style.md`、流程布局与 XML 辅助脚本；安装后各包的资源可独立维护，改动一个包不会自动修改另一个包。指定风格时将 `style.md` 上传到同一任务附件并在请求中指明。默认返回 `.drawio` 文件，明确要求源码才返回 XML；已有 XML 的节点 ID、文字、层次、连线端点及标签被改变时拒绝交付。机器入口沿用统一路由：`<用户服务基址>/agent/flowchart-correction/mcp`、`.../a2a`、`.../v1/tasks`，用户服务基址包含 `UMEKO_BASE_PATH`。

图像推理智能体复用平台现有视觉工具，可选原生视觉输入或配置的视觉模型。问题与图片一起交给模型，多图保留顺序并注明证据来自哪张图；提示词保持开放，不使用固定质检清单。超过 5 张时按 Skill 指引请用户选择，不擅自截取或分析全部图片。答案区分可见事实、明确条件和推测；几何题不把示意图外观当成已知条件，因果和线索分析保留替代解释与不确定性。普通文本追问也可直接回答。

图片按文件内容识别，支持无后缀、错误后缀的真实 PNG/JPEG/WebP/GIF/BMP/TIFF。发送模型前自动等比缩放至最长边 2560、总计不超过 400 万像素，并控制编码后单图体积；原始附件保留。动画/多页文件只分析第 1 帧/页，缩放及页帧范围会告知模型。损坏或超过安全解码限额的文件会明确报错；详见[图片预处理策略](../architecture/index.md#image-input)。

管理员编辑 Skill 并保存后，更新运行库与后续下发的主文档。每个新会话取得完整的独立目录副本，已有会话保留自己的文档、脚本和修改；不会再从共享库执行最新版脚本。`umeko/builtin_skills/<技能名>/SKILL.md` 是安装模板，启动只升级识别出的原版，保留管理员修改和删除。目录迁移与模型修改副本的边界见[技能与脚本工具](../architecture/skills.md)。

<a id="builtin-image-qc"></a>

## 自带的图像质检智能体

首次启动或首次升级到含内置智能体的版本时，自动添加“图像质检”，访问路径为 `image-qc`，选择 `doc-image-qc.md` 技能。支持单张 / 多张图片、Markdown 图文文档及文档压缩包；配套 `checks.md` 和 `render_report.py` 生成 HTML、JSON 与含图片的 ZIP 报告，产物保存在 `generate/`。没有正文或真实产品参照时，相应项目标记为未检查，不凭空判定一致性。

在 Provider / Model 中配置并激活主模型，标记视觉模型并设置平台默认视觉模型后即可使用；也可在这个智能体的“配置与入口”中指定专用主模型和视觉模型。初始模型选择留空，沿用平台选择，不内置模型地址或密钥。技能正文仍按需加载，问候或不相关任务不执行质检流程。

智能体与技能均可由管理员维护。初始化只补缺失项；已有 `image-qc` 配置、自定义技能正文和脚本保持原样。已有同名技能被停用时，新添加的智能体也保持停用。初始化成功后，修改、停用或删除默认项都不会在重启时被撤销。升级时只更新内容完全匹配已知原版的智能体提示词、质检指引和报告脚本，并同步仍为原版的默认 Skill 正文；不覆盖自定义内容，不恢复已删除的文件，保留名称、模型、技能选择及启用/停用状态。

默认工作指引要求：确认缺少必要图片、文档或其他关键资料，导致任务无法继续时，及时返回缺失项、已做的检查与补齐步骤，邀请外层 Agent 或用户进入该任务的临时工作台处理，不在后台空等或反复重试。调用方应把 `workspace_url`（A2A 为 `metadata.workspaceUrl`）中的真实链接及时交给用户；模型未取得链接时会指向响应字段，不编造网址。仅缺可选正文或产品参照时仍继续可执行检查，并将无法核对项记为 NA。接口与续聊示例见[临时工作台](temporary-workspace.md)。

HTML 报告的矩阵表头展示“编号 + 检查项名称”，下方“检查项说明”列出本报告涉及的检查范围，下载离线查看也能读到。说明来自当前技能包的 `checks.md`；管理员修改清单后，新生成的报告采用新的说明。C 为通用检查（C1 图文一致性、C2 图片质量、C3 敏感信息），S 为原理图，N 为组网图，U 为界面截图。U1 核对截图与描述，U2 对照真实产品界面；缺少对应正文或产品参照时记 NA。NA 表示未检查，矩阵中的“—”表示本图未列入该项检查，两者均不表示通过。已有报告需要重新运行 `render_report.py` 才会补上说明，不需要重新调用模型检查图片。

报告可混合引用文档配图和粘贴附件：`images/example.png` 按 `doc_dir` 解析，`attachments/example.png`、`workspace/...`、`generate/...` 按当前 Session 根目录解析；当前 Session 安全目录内的绝对路径也会转换。打包后的 HTML 与 JSON 统一使用 Session 相对路径，ZIP 保留对应目录，避免不同目录中的同名图片冲突。未引用的附件不会自动加入报告。文件缺失或路径越界时，工具返回值和 HTML 中会明确列出未打包图片，不能作为完整交付。

## 每个 Agent 的对外地址

假设用户服务完整基址为 `https://example.internal/doc-master/consistency/image-text`，访问路径填 `image-qc`：

```text
Agent 基址  https://example.internal/doc-master/consistency/image-text/agent/image-qc
Agent Card  <Agent 基址>/.well-known/agent-card.json
A2A         <Agent 基址>/a2a
MCP         <Agent 基址>/mcp
REST Task   <Agent 基址>/v1/tasks
```

把 [MCP](mcp.md)、[A2A](a2a.md) 或 [REST 任务](machine-tasks.md)示例中的 `UMEKO_SERVICE_URL` 改为 Agent 基址即可。凭据和免鉴权方式仍在“服务接入”统一配置。MCP 的 `get_agent_info` 返回当前路径对应的公开 Card。

用户服务的 `GET /agent` 是公开目录，只列出启用 Agent 的名字、介绍、slug 与 Card 地址。`GET /agent/{slug}/` 返回该 Agent 的名字、介绍和协议地址；它不显示网页工作台。未知或停用的 Agent 路径返回 404。

## 管理接口

以下接口在管理端口，使用管理员 Cookie `umeko_admin`：

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| GET | `/admin/v1/agents` | 全部配置，以及可选择的模型、默认 Skill 和默认版本 |
| POST | `/admin/v1/agents` | 创建；返回 201 与保存的配置 |
| GET | `/admin/v1/agents/{agent_id}` | 读取配置 |
| PUT | `/admin/v1/agents/{agent_id}` | 完整替换配置；未提交的可选字段恢复默认值 |
| DELETE | `/admin/v1/agents/{agent_id}` | 无保留任务时删除，成功为 204 |
| GET | `/admin/v1/agents/{agent_id}/card` | 管理员预览 Card；停用时也可预览 |
| GET | `/admin/v1/agents/{agent_id}/mcp` | 查看同一 SDK 注册产生的工具、资源模板与提示词定义，不执行工具或调用模型 |

保存响应包含 `id`、`created_at`、`updated_at` 和 `endpoints`。这些只读字段不要放入创建 / 更新请求，未知字段返回 422。

```json
{
  "slug": "image-qc",
  "name": "图文质检 Agent",
  "description": "检查文档图片与文字的一致性并生成报告",
  "version": "1.0.0",
  "system_prompt": "检查完成后给出问题位置、证据和修正建议。",
  "default_model_id": null,
  "default_vision_model_id": null,
  "skill_names": ["doc-image-qc.md"],
  "enabled": true
}
```

`doc-image-qc.md` 是自带的图像质检技能；其他技能文件名从 `GET /admin/v1/agents` 的 `skills[].filename` 获取。

| 字段 | 规则 |
| --- | --- |
| `slug` | 必填，1–63 位小写字母、数字或连字符；首位为字母或数字；创建后不可修改，全平台唯一 |
| `name` / `description` | 必填且非空，最多 200 / 10000 字符；公开 |
| `version` | 非空，省略时使用当前 UMEKO 版本；公开 |
| `system_prompt` | 可选，最多 100000 字符；私有工作指引 |
| `default_model_id` | 可选现有模型 ID；为空时跟随平台默认；对外调用方不能覆盖 |
| `default_vision_model_id` | 可选现有视觉模型 ID；用于主 Agent 与子 Agent 的图像推理工具；为空时自动选择；非视觉模型拒绝保存 |
| `disclosed_model_ids` | 兼容保留的管理字段，拒绝未知或重复模型 ID；当前对外不提供模型列表或选择模型的能力 |
| `skill_names` | 默认 `[]`；默认 Skill 文件名数组；不存在或无法解析的项拒绝保存 |
| `enabled` | 默认 `true`，停用会关闭该 Agent 的公开入口 |
| `documentationUrl` / `iconUrl` | 可选，完整 HTTP / HTTPS 地址 |
| `provider` | 可选 `{"organization":"提供方名称","url":"https://example.internal"}`，两项同时填写 |

公开 Card 的 Skills 只包含选择列表中同时已启用的默认 Skill。全局停用某项后，它仍保留在 Agent 的选择中，但不披露、不向新任务下发；重新启用后恢复。清空选择允许普通任务，Card 的 `skills` 为空数组。

对外 MCP 不再提供 `list_models`，REST、MCP、A2A 的任务提交均不接受调用方的 `model_id`。管理员通过默认主模型和默认视觉模型决定执行选择；主模型留空时跟随平台默认。原“主模型披露”配置保留以兼容已有管理数据，当前不开放外部模型发现或切换。普通注册用户工作台的模型选择保持独立，临时工作台不能改选模型。

修改默认模型影响新提交的任务，已接收或排队任务保留提交时的模型选择。

默认视觉模型的下拉框只显示 Provider / Model 中已标记视觉能力的模型。显式选择后，`image_reasoning` 与使用视觉模型的文字提取优先使用该模型，即使主模型本身也支持看图。留空则沿用自动规则：用户视觉偏好优先，否则由支持视觉的主模型处理，或选择注册表中的视觉模型（优先同 Provider）。`read_image` 直接把图片交给主模型或子模型，仍取决于它们自身的视觉能力。视觉配置引用共享 Provider 的密钥、代理与每模型并发队列，保存在数据库，不需要新增 `.env` 项。

路径冲突、未知模型 / Skill、无效网址或试图修改 slug 返回 400；不存在的配置返回 404；配置仍有保留任务时删除返回 409。工作指引、技能正文、脚本与模型密钥不会写入公开 Card 或目录。

## 任务归属与兼容

REST Task 返回 `agent_id`；A2A Task 在 `metadata.agentId` 中返回相同 ID。查询、取消、事件、产物和 Context 都限定在原 Agent 与调用者内，不能换一个 Agent 路径读取。幂等键也在此范围内唯一。

同一服务凭据可按既有 scope 使用多个 Agent；当前没有按 Agent 单独分配权限的开关。免鉴权调用在同一个 Agent 内共用任务身份，不能将不同 IP 当作数据隔离边界。

更新配置影响新提交的任务；已接收任务保留其提交时的工作指引、主 Skill 文本和显式选择的默认模型 / 默认视觉模型 ID。排队期间改选视觉模型不影响已提交任务；删除原视觉模型或取消其视觉标记会使该任务失败，管理员可从服务日志查看配置原因。停用不自动取消已接收任务。保留任务未清理时不能删除 Agent，管理员可在“资源监控”查看归属和停止任务。

顶级 `/mcp`、`/a2a`、`/.well-known/agent-card.json`、`/v1/tasks` 和 OAuth 入口已移除，统一使用 `/agent/{slug}/...`。原全局 Card 编辑接口也已删除。升级后在“服务接入”的智能体管理中创建 Agent，并更新调用方地址。网页登录、聊天和 CLI 入口继续独立使用。执行快照、共享并发和技能资源版本的边界见[架构设计](../architecture/agents.md)。
