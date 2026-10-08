# 智能体管理

在管理端打开“服务接入”下的“智能体管理”，点击“新建智能体”，填写名称、访问路径和介绍，勾选需要的默认 Skill，然后保存。可选填内部工作指引和默认模型。弹窗会显示该 Agent 的完整调用地址与只读 Card 预览，配置立即生效并在重启后保留。URL 中的 `<name>` 对应这里填写的访问路径 `slug`，与用于展示的中文名称分开。

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
  "skill_names": ["doc-image-qc.md"],
  "enabled": true
}
```

`doc-image-qc.md` 仅作示例，实际文件名从 `GET /admin/v1/agents` 的 `skills[].filename` 获取。

| 字段 | 规则 |
| --- | --- |
| `slug` | 必填，1–63 位小写字母、数字或连字符；首位为字母或数字；创建后不可修改，全平台唯一 |
| `name` / `description` | 必填且非空，最多 200 / 10000 字符；公开 |
| `version` | 非空，省略时使用当前 UMEKO 版本；公开 |
| `system_prompt` | 可选，最多 100000 字符；私有工作指引 |
| `default_model_id` | 可选现有模型 ID；为空时跟随平台默认；调用者的显式 `model_id` 优先 |
| `skill_names` | 默认 `[]`；默认 Skill 文件名数组；不存在或无法解析的项拒绝保存 |
| `enabled` | 默认 `true`，停用会关闭该 Agent 的公开入口 |
| `documentationUrl` / `iconUrl` | 可选，完整 HTTP / HTTPS 地址 |
| `provider` | 可选 `{"organization":"提供方名称","url":"https://example.internal"}`，两项同时填写 |

公开 Card 的 Skills 只包含选择列表中同时已启用的默认 Skill。全局停用某项后，它仍保留在 Agent 的选择中，但不披露、不向新任务下发；重新启用后恢复。清空选择允许普通任务，Card 的 `skills` 为空数组。

路径冲突、未知模型 / Skill、无效网址或试图修改 slug 返回 400；不存在的配置返回 404；配置仍有保留任务时删除返回 409。工作指引、技能正文、脚本与模型密钥不会写入公开 Card 或目录。

## 任务归属与兼容

REST Task 返回 `agent_id`；A2A Task 在 `metadata.agentId` 中返回相同 ID。查询、取消、事件、产物和 Context 都限定在原 Agent 与调用者内，不能换一个 Agent 路径读取。幂等键也在此范围内唯一。

同一服务凭据可按既有 scope 使用多个 Agent；当前没有按 Agent 单独分配权限的开关。免鉴权调用在同一个 Agent 内共用任务身份，不能将不同 IP 当作数据隔离边界。

更新配置影响新提交的任务；已接收任务保留其提交时的工作指引与主 Skill 文本。停用不自动取消已接收任务。保留任务未清理时不能删除 Agent，管理员可在“资源监控”查看归属和停止任务。

顶级 `/mcp`、`/a2a`、`/.well-known/agent-card.json`、`/v1/tasks` 和 OAuth 入口已移除，统一使用 `/agent/{slug}/...`。原全局 Card 编辑接口也已删除。升级后在“服务接入”的智能体管理中创建 Agent，并更新调用方地址。网页登录、聊天和 CLI 入口继续独立使用。执行快照、共享并发和技能资源版本的边界见[架构设计](../architecture/agents.md)。
