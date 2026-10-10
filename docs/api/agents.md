# 智能体管理

在管理端打开“服务接入”下的“智能体管理”，点击“新建智能体”，填写名称、访问路径和介绍，勾选需要的默认 Skill，然后保存。可选填内部工作指引、默认模型和默认视觉模型。弹窗会显示该 Agent 的完整调用地址与只读 Card 预览，配置立即生效并在重启后保留。URL 中的 `<name>` 对应这里填写的访问路径 `slug`，与用于展示的中文名称分开。

<a id="builtin-image-qc"></a>

## 自带的图像质检智能体

首次启动或首次升级到含内置智能体的版本时，自动添加“图像质检”，访问路径为 `image-qc`，选择 `doc-image-qc.md` 技能。支持单张 / 多张图片、Markdown 图文文档及文档压缩包；配套 `checks.md` 和 `render_report.py` 生成 HTML、JSON 与含图片的 ZIP 报告，产物保存在 `generate/`。没有正文或真实产品参照时，相应项目标记为未检查，不凭空判定一致性。

在 Provider / Model 中配置并激活主模型，标记视觉模型并设置平台默认视觉模型后即可使用；也可在这个智能体的“配置与入口”中指定专用主模型和视觉模型。初始模型选择留空，沿用平台选择，不内置模型地址或密钥。技能正文仍按需加载，问候或不相关任务不执行质检流程。

智能体与技能均可由管理员维护。初始化只补缺失项；已有 `image-qc` 配置、自定义技能正文和脚本保持原样。已有同名技能被停用时，新添加的智能体也保持停用。初始化成功后，修改、停用或删除默认项都不会在重启时被撤销。升级时只更新内容完全匹配已知原版的质检指引和报告脚本，并同步仍为原版的默认 Skill 正文；不覆盖自定义内容，不恢复已删除的文件，保留启用/停用状态。

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
| `default_model_id` | 可选现有模型 ID；为空时跟随平台默认；调用者的显式 `model_id` 优先 |
| `default_vision_model_id` | 可选现有视觉模型 ID；用于主 Agent 与子 Agent 的图像推理工具；为空时自动选择；非视觉模型拒绝保存 |
| `skill_names` | 默认 `[]`；默认 Skill 文件名数组；不存在或无法解析的项拒绝保存 |
| `enabled` | 默认 `true`，停用会关闭该 Agent 的公开入口 |
| `documentationUrl` / `iconUrl` | 可选，完整 HTTP / HTTPS 地址 |
| `provider` | 可选 `{"organization":"提供方名称","url":"https://example.internal"}`，两项同时填写 |

公开 Card 的 Skills 只包含选择列表中同时已启用的默认 Skill。全局停用某项后，它仍保留在 Agent 的选择中，但不披露、不向新任务下发；重新启用后恢复。清空选择允许普通任务，Card 的 `skills` 为空数组。

默认视觉模型的下拉框只显示 Provider / Model 中已标记视觉能力的模型。显式选择后，`image_reasoning` 与使用视觉模型的文字提取优先使用该模型，即使主模型本身也支持看图；调用者的 `model_id` 只覆盖主模型。留空则沿用自动规则：用户视觉偏好优先，否则由支持视觉的主模型处理，或选择注册表中的视觉模型（优先同 Provider）。`read_image` 直接把图片交给主模型或子模型，仍取决于它们自身的视觉能力。视觉配置引用共享 Provider 的密钥、代理与每模型并发队列，保存在数据库，不需要新增 `.env` 项。

路径冲突、未知模型 / Skill、无效网址或试图修改 slug 返回 400；不存在的配置返回 404；配置仍有保留任务时删除返回 409。工作指引、技能正文、脚本与模型密钥不会写入公开 Card 或目录。

## 任务归属与兼容

REST Task 返回 `agent_id`；A2A Task 在 `metadata.agentId` 中返回相同 ID。查询、取消、事件、产物和 Context 都限定在原 Agent 与调用者内，不能换一个 Agent 路径读取。幂等键也在此范围内唯一。

同一服务凭据可按既有 scope 使用多个 Agent；当前没有按 Agent 单独分配权限的开关。免鉴权调用在同一个 Agent 内共用任务身份，不能将不同 IP 当作数据隔离边界。

更新配置影响新提交的任务；已接收任务保留其提交时的工作指引、主 Skill 文本和显式选择的默认模型 / 默认视觉模型 ID。排队期间改选视觉模型不影响已提交任务；删除原视觉模型或取消其视觉标记会使该任务失败，管理员可从服务日志查看配置原因。停用不自动取消已接收任务。保留任务未清理时不能删除 Agent，管理员可在“资源监控”查看归属和停止任务。

顶级 `/mcp`、`/a2a`、`/.well-known/agent-card.json`、`/v1/tasks` 和 OAuth 入口已移除，统一使用 `/agent/{slug}/...`。原全局 Card 编辑接口也已删除。升级后在“服务接入”的智能体管理中创建 Agent，并更新调用方地址。网页登录、聊天和 CLI 入口继续独立使用。执行快照、共享并发和技能资源版本的边界见[架构设计](../architecture/agents.md)。
