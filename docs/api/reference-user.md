# 用户接口完整参考

> 自动生成：请修改源码或生成器，不直接编辑本文件。

共 **60** 个 HTTP 操作。[下载 OpenAPI](openapi-user.json) · [数据结构](schemas.md)

路径为应用内部路由；带前缀部署时在公共 URL 前加 `UMEKO_BASE_PATH`。登录、原始字节体与 SSE 契约由生成器显式补充。

泛型 `object` / 任意 JSON 表示源码尚未声明完整字段模型，请结合各专题指南。表中响应码来自 OpenAPI，不包含中间件产生的全部错误。

## 接口索引

| 方法 | 路径 | 操作 |
| --- | --- | --- |
| GET | `/agent` | Agent Catalogue |
| GET | `/health` | Health |
| POST | `/v1/auth/register` | Register |
| POST | `/v1/auth/login` | Login |
| GET | `/v1/auth/me` | Me |
| GET | `/v1/auth/avatar` | Avatar |
| PUT | `/v1/auth/avatar` | Update Avatar |
| DELETE | `/v1/auth/avatar` | Delete Avatar |
| POST | `/v1/auth/logout` | Logout |
| GET | `/v1/models` | Available Models |
| PUT | `/v1/auth/model-prefs` | Set Model Prefs |
| PUT | `/v1/sessions/{session_id}/model` | Set Session Model |
| GET | `/v1/sessions/{session_id}/workspace/tree` | Workspace Tree |
| GET | `/v1/sessions/{session_id}/client/{kind}` | List Client Resources |
| POST | `/v1/sessions/{session_id}/client/{kind}` | Create Client Resource |
| GET | `/v1/sessions/{session_id}/client/{kind}/{name}` | Read Client Resource |
| PATCH | `/v1/sessions/{session_id}/client/{kind}/{name}` | Update Client Resource |
| DELETE | `/v1/sessions/{session_id}/client/{kind}/{name}` | Delete Client Resource |
| POST | `/v1/sessions/{session_id}/client/{kind}/generate` | Generate Client Resource |
| GET | `/v1/sessions/{session_id}/workspace/files/content` | Workspace File |
| GET | `/v1/sessions/{session_id}/workspace/files/raw/{file_path}` | Workspace File Raw |
| GET | `/v1/sessions/{session_id}/workspace/files/download` | Download Workspace File |
| POST | `/v1/sessions/{session_id}/workspace/entries` | Create Workspace Entry |
| DELETE | `/v1/sessions/{session_id}/workspace/entries` | Delete Workspace Entry |
| POST | `/v1/sessions/{session_id}/workspace/transfer` | Transfer Workspace Entry |
| POST | `/v1/sessions/{session_id}/workspace/extract` | Extract Workspace Archive |
| POST | `/v1/sessions/{session_id}/workspace/files` | Upload Workspace File |
| GET | `/v1/sessions` | List Sessions |
| POST | `/v1/sessions` | Create Session |
| PATCH | `/v1/sessions/{session_id}/title` | Rename Session |
| DELETE | `/v1/sessions/{session_id}` | Delete Session |
| GET | `/v1/sessions/{session_id}` | Read Session |
| GET | `/v1/sessions/{session_id}/messages` | Session Messages |
| GET | `/v1/sessions/{session_id}/tool-events` | Session Tool Events |
| GET | `/v1/sessions/{session_id}/context` | Session Context |
| POST | `/v1/sessions/{session_id}/context/compact` | Compact Session Context |
| POST | `/v1/sessions/{session_id}/context/clear` | Clear Session Context |
| POST | `/v1/sessions/{session_id}/chat/clear` | Clear Session Chat |
| POST | `/v1/sessions/{session_id}/clone` | Clone Session |
| POST | `/v1/sessions/{session_id}/runs` | Create Run |
| GET | `/v1/runs/{run_id}` | Read Run |
| GET | `/v1/sessions/{session_id}/active-run` | Active Run |
| POST | `/v1/runs/{run_id}/cancel` | Cancel Run |
| GET | `/v1/runs/{run_id}/events` | Stream Events |
| POST | `/v1/sessions/{session_id}/files` | Upload File |
| POST | `/v1/sessions/{session_id}/files/from-workspace` | Attach Workspace File |
| GET | `/v1/sessions/{session_id}/artifacts` | List Artifacts |
| GET | `/v1/sessions/{session_id}/artifacts/{artifact_id}/content` | Download Artifact |
| POST | `/v1/proxy/sessions` | Create Proxy Session |
| GET | `/v1/proxy/sessions/{session_id}` | Proxy Session Status |
| POST | `/agent/{agent_name}/v1/tasks` | Submit Task |
| GET | `/agent/{agent_name}/v1/tasks` | List Tasks |
| GET | `/agent/{agent_name}/v1/tasks/{task_id}` | Get Task |
| POST | `/agent/{agent_name}/v1/tasks/{task_id}/cancel` | Cancel Task |
| GET | `/agent/{agent_name}/v1/tasks/{task_id}/events` | Task Events |
| GET | `/agent/{agent_name}/v1/tasks/{task_id}/artifacts/{artifact_id}/content` | Download Artifact |
| GET | `/agent/{agent_name}/.well-known/oauth-protected-resource/mcp` | Oauth Resource |
| GET | `/agent/{agent_name}/.well-known/oauth-authorization-server` | Oauth Server |
| POST | `/agent/{agent_name}/oauth/token` | Oauth Token |
| GET | `/agent/{agent_name}/.well-known/agent-card.json` | Card |

## GET /agent

Agent Catalogue

认证：无须登录。

| 响应码 | 内容 |
| --- | --- |
| 200 | application/json: object |

## GET /health

Health

认证：无须登录。

| 响应码 | 内容 |
| --- | --- |
| 200 | application/json: object |

## POST /v1/auth/register

Register

认证：无须登录。

请求体：必填。

`application/json` → `AuthInput`

| 响应码 | 内容 |
| --- | --- |
| 201 | application/json: UserView |
| 422 | application/json: HTTPValidationError |

## POST /v1/auth/login

Login

认证：无须登录。

请求体：必填。

`application/json` → `AuthInput`

| 响应码 | 内容 |
| --- | --- |
| 200 | application/json: UserView |
| 422 | application/json: HTTPValidationError |

## GET /v1/auth/me

Me

认证：`umeko_auth` Cookie。

| 响应码 | 内容 |
| --- | --- |
| 200 | application/json: UserView |

## GET /v1/auth/avatar

Avatar

认证：`umeko_auth` Cookie。

| 响应码 | 内容 |
| --- | --- |
| 200 | application/octet-stream: string |

## PUT /v1/auth/avatar

Update Avatar

认证：`umeko_auth` Cookie。

请求体：必填。

原始图片字节；支持 PNG/JPEG/WebP/GIF，最多 2 MiB。

`application/octet-stream` → `string`

```json
{
  "format": "binary",
  "type": "string"
}
```

| 响应码 | 内容 |
| --- | --- |
| 200 | application/json: UserView |

## DELETE /v1/auth/avatar

Delete Avatar

认证：`umeko_auth` Cookie。

| 响应码 | 内容 |
| --- | --- |
| 200 | application/json: UserView |

## POST /v1/auth/logout

Logout

认证：`umeko_auth` Cookie。

| 响应码 | 内容 |
| --- | --- |
| 204 | Successful Response |

## GET /v1/models

Available Models

认证：`umeko_auth` Cookie。

管理员配置的可用模型清单（不含凭据）+ 全局默认 + 我的偏好。

| 响应码 | 内容 |
| --- | --- |
| 200 | application/json: object |

## PUT /v1/auth/model-prefs

Set Model Prefs

认证：`umeko_auth` Cookie。

请求体：必填。

`application/json` → `ModelPrefsIn`

| 响应码 | 内容 |
| --- | --- |
| 200 | application/json: object |
| 422 | application/json: HTTPValidationError |

## PUT /v1/sessions/{session_id}/model

Set Session Model

认证：`umeko_auth` Cookie。

| 参数 | 位置 | 必填 | 类型与约束 |
| --- | --- | --- | --- |
| `session_id` | path | 是 | `{"title": "Session Id", "type": "string"}` |

请求体：必填。

`application/json` → `SessionModelIn`

| 响应码 | 内容 |
| --- | --- |
| 204 | Successful Response |
| 422 | application/json: HTTPValidationError |

## GET /v1/sessions/{session_id}/workspace/tree

Workspace Tree

认证：`umeko_auth` Cookie。

| 参数 | 位置 | 必填 | 类型与约束 |
| --- | --- | --- | --- |
| `session_id` | path | 是 | `{"title": "Session Id", "type": "string"}` |
| `filter` | query | 否 | `{"default": "", "title": "Filter", "type": "string"}` |

| 响应码 | 内容 |
| --- | --- |
| 200 | application/json: array<WorkspaceNode> |
| 422 | application/json: HTTPValidationError |

## GET /v1/sessions/{session_id}/client/{kind}

List Client Resources

认证：`umeko_auth` Cookie。

| 参数 | 位置 | 必填 | 类型与约束 |
| --- | --- | --- | --- |
| `session_id` | path | 是 | `{"title": "Session Id", "type": "string"}` |
| `kind` | path | 是 | `{"title": "Kind", "type": "string"}` |

| 响应码 | 内容 |
| --- | --- |
| 200 | application/json: array<ClientResourceView> |
| 422 | application/json: HTTPValidationError |

## POST /v1/sessions/{session_id}/client/{kind}

Create Client Resource

认证：`umeko_auth` Cookie。

| 参数 | 位置 | 必填 | 类型与约束 |
| --- | --- | --- | --- |
| `session_id` | path | 是 | `{"title": "Session Id", "type": "string"}` |
| `kind` | path | 是 | `{"title": "Kind", "type": "string"}` |
| `filename` | query | 是 | `{"minLength": 1, "title": "Filename", "type": "string"}` |

请求体：必填。

UTF-8 技能文本；kind 只能为 skills。

`text/plain` → `string`

```json
{
  "format": "binary",
  "type": "string"
}
```

| 响应码 | 内容 |
| --- | --- |
| 201 | application/json: ClientResourceView |
| 422 | application/json: HTTPValidationError |

## GET /v1/sessions/{session_id}/client/{kind}/{name}

Read Client Resource

认证：`umeko_auth` Cookie。

| 参数 | 位置 | 必填 | 类型与约束 |
| --- | --- | --- | --- |
| `session_id` | path | 是 | `{"title": "Session Id", "type": "string"}` |
| `kind` | path | 是 | `{"title": "Kind", "type": "string"}` |
| `name` | path | 是 | `{"title": "Name", "type": "string"}` |

| 响应码 | 内容 |
| --- | --- |
| 200 | application/json: ClientResourceView |
| 422 | application/json: HTTPValidationError |

## PATCH /v1/sessions/{session_id}/client/{kind}/{name}

Update Client Resource

认证：`umeko_auth` Cookie。

| 参数 | 位置 | 必填 | 类型与约束 |
| --- | --- | --- | --- |
| `session_id` | path | 是 | `{"title": "Session Id", "type": "string"}` |
| `kind` | path | 是 | `{"title": "Kind", "type": "string"}` |
| `name` | path | 是 | `{"title": "Name", "type": "string"}` |

请求体：必填。

`application/json` → `ClientResourceUpdate`

| 响应码 | 内容 |
| --- | --- |
| 200 | application/json: ClientResourceView |
| 422 | application/json: HTTPValidationError |

## DELETE /v1/sessions/{session_id}/client/{kind}/{name}

Delete Client Resource

认证：`umeko_auth` Cookie。

| 参数 | 位置 | 必填 | 类型与约束 |
| --- | --- | --- | --- |
| `session_id` | path | 是 | `{"title": "Session Id", "type": "string"}` |
| `kind` | path | 是 | `{"title": "Kind", "type": "string"}` |
| `name` | path | 是 | `{"title": "Name", "type": "string"}` |

| 响应码 | 内容 |
| --- | --- |
| 204 | Successful Response |
| 422 | application/json: HTTPValidationError |

## POST /v1/sessions/{session_id}/client/{kind}/generate

Generate Client Resource

认证：`umeko_auth` Cookie。

| 参数 | 位置 | 必填 | 类型与约束 |
| --- | --- | --- | --- |
| `session_id` | path | 是 | `{"title": "Session Id", "type": "string"}` |
| `kind` | path | 是 | `{"title": "Kind", "type": "string"}` |

请求体：必填。

`application/json` → `ClientResourceGenerate`

| 响应码 | 内容 |
| --- | --- |
| 201 | application/json: ClientResourceView |
| 422 | application/json: HTTPValidationError |

## GET /v1/sessions/{session_id}/workspace/files/content

Workspace File

认证：`umeko_auth` Cookie。

| 参数 | 位置 | 必填 | 类型与约束 |
| --- | --- | --- | --- |
| `session_id` | path | 是 | `{"title": "Session Id", "type": "string"}` |
| `path` | query | 是 | `{"minLength": 1, "title": "Path", "type": "string"}` |

| 响应码 | 内容 |
| --- | --- |
| 200 | application/octet-stream: string |
| 422 | application/json: HTTPValidationError |

## GET /v1/sessions/{session_id}/workspace/files/raw/{file_path}

Workspace File Raw

认证：`umeko_auth` Cookie。

路径式文件访问：URL 自带位置信息，HTML 内的相对路径引用（图片/CSS）
可被浏览器正确解析。用于 HTML 报告等产物的整页渲染（新标签页打开）。

| 参数 | 位置 | 必填 | 类型与约束 |
| --- | --- | --- | --- |
| `session_id` | path | 是 | `{"title": "Session Id", "type": "string"}` |
| `file_path` | path | 是 | `{"title": "File Path", "type": "string"}` |

| 响应码 | 内容 |
| --- | --- |
| 200 | application/octet-stream: string |
| 422 | application/json: HTTPValidationError |

## GET /v1/sessions/{session_id}/workspace/files/download

Download Workspace File

认证：`umeko_auth` Cookie。

| 参数 | 位置 | 必填 | 类型与约束 |
| --- | --- | --- | --- |
| `session_id` | path | 是 | `{"title": "Session Id", "type": "string"}` |
| `path` | query | 是 | `{"minLength": 1, "title": "Path", "type": "string"}` |

| 响应码 | 内容 |
| --- | --- |
| 200 | application/octet-stream: string |
| 422 | application/json: HTTPValidationError |

## POST /v1/sessions/{session_id}/workspace/entries

Create Workspace Entry

认证：`umeko_auth` Cookie。

| 参数 | 位置 | 必填 | 类型与约束 |
| --- | --- | --- | --- |
| `session_id` | path | 是 | `{"title": "Session Id", "type": "string"}` |

请求体：必填。

`application/json` → `WorkspaceEntryCreate`

| 响应码 | 内容 |
| --- | --- |
| 201 | application/json: WorkspaceFileView |
| 422 | application/json: HTTPValidationError |

## DELETE /v1/sessions/{session_id}/workspace/entries

Delete Workspace Entry

认证：`umeko_auth` Cookie。

| 参数 | 位置 | 必填 | 类型与约束 |
| --- | --- | --- | --- |
| `session_id` | path | 是 | `{"title": "Session Id", "type": "string"}` |
| `path` | query | 是 | `{"minLength": 1, "title": "Path", "type": "string"}` |

| 响应码 | 内容 |
| --- | --- |
| 204 | Successful Response |
| 422 | application/json: HTTPValidationError |

## POST /v1/sessions/{session_id}/workspace/transfer

Transfer Workspace Entry

认证：`umeko_auth` Cookie。

| 参数 | 位置 | 必填 | 类型与约束 |
| --- | --- | --- | --- |
| `session_id` | path | 是 | `{"title": "Session Id", "type": "string"}` |

请求体：必填。

`application/json` → `WorkspaceTransfer`

| 响应码 | 内容 |
| --- | --- |
| 200 | application/json: WorkspaceFileView |
| 422 | application/json: HTTPValidationError |

## POST /v1/sessions/{session_id}/workspace/extract

Extract Workspace Archive

认证：`umeko_auth` Cookie。

| 参数 | 位置 | 必填 | 类型与约束 |
| --- | --- | --- | --- |
| `session_id` | path | 是 | `{"title": "Session Id", "type": "string"}` |

请求体：必填。

`application/json` → `WorkspaceExtract`

| 响应码 | 内容 |
| --- | --- |
| 200 | application/json: WorkspaceFileView |
| 422 | application/json: HTTPValidationError |

## POST /v1/sessions/{session_id}/workspace/files

Upload Workspace File

认证：`umeko_auth` Cookie。

| 参数 | 位置 | 必填 | 类型与约束 |
| --- | --- | --- | --- |
| `session_id` | path | 是 | `{"title": "Session Id", "type": "string"}` |
| `filename` | query | 是 | `{"minLength": 1, "title": "Filename", "type": "string"}` |
| `path` | query | 否 | `{"default": "", "title": "Path", "type": "string"}` |

请求体：必填。

原始文件字节；filename 与可选 path 在查询参数中。

`application/octet-stream` → `string`

```json
{
  "format": "binary",
  "type": "string"
}
```

| 响应码 | 内容 |
| --- | --- |
| 201 | application/json: WorkspaceFileView |
| 422 | application/json: HTTPValidationError |

## GET /v1/sessions

List Sessions

认证：`umeko_auth` Cookie。

| 响应码 | 内容 |
| --- | --- |
| 200 | application/json: array<object> |

## POST /v1/sessions

Create Session

认证：`umeko_auth` Cookie。

请求体：必填。

`application/json` → `SessionCreate`

| 响应码 | 内容 |
| --- | --- |
| 201 | application/json: SessionView |
| 422 | application/json: HTTPValidationError |

## PATCH /v1/sessions/{session_id}/title

Rename Session

认证：`umeko_auth` Cookie。

| 参数 | 位置 | 必填 | 类型与约束 |
| --- | --- | --- | --- |
| `session_id` | path | 是 | `{"title": "Session Id", "type": "string"}` |

请求体：必填。

`application/json` → `SessionTitlePatch`

| 响应码 | 内容 |
| --- | --- |
| 204 | Successful Response |
| 422 | application/json: HTTPValidationError |

## DELETE /v1/sessions/{session_id}

Delete Session

认证：`umeko_auth` Cookie。

| 参数 | 位置 | 必填 | 类型与约束 |
| --- | --- | --- | --- |
| `session_id` | path | 是 | `{"title": "Session Id", "type": "string"}` |

| 响应码 | 内容 |
| --- | --- |
| 204 | Successful Response |
| 422 | application/json: HTTPValidationError |

## GET /v1/sessions/{session_id}

Read Session

认证：`umeko_auth` Cookie。

| 参数 | 位置 | 必填 | 类型与约束 |
| --- | --- | --- | --- |
| `session_id` | path | 是 | `{"title": "Session Id", "type": "string"}` |

| 响应码 | 内容 |
| --- | --- |
| 200 | application/json: SessionView |
| 422 | application/json: HTTPValidationError |

## GET /v1/sessions/{session_id}/messages

Session Messages

认证：`umeko_auth` Cookie。

| 参数 | 位置 | 必填 | 类型与约束 |
| --- | --- | --- | --- |
| `session_id` | path | 是 | `{"title": "Session Id", "type": "string"}` |

| 响应码 | 内容 |
| --- | --- |
| 200 | application/json: array<MessageView> |
| 422 | application/json: HTTPValidationError |

## GET /v1/sessions/{session_id}/tool-events

Session Tool Events

认证：`umeko_auth` Cookie。

| 参数 | 位置 | 必填 | 类型与约束 |
| --- | --- | --- | --- |
| `session_id` | path | 是 | `{"title": "Session Id", "type": "string"}` |

| 响应码 | 内容 |
| --- | --- |
| 200 | application/json: array<ToolEventView> |
| 422 | application/json: HTTPValidationError |

## GET /v1/sessions/{session_id}/context

Session Context

认证：`umeko_auth` Cookie。

| 参数 | 位置 | 必填 | 类型与约束 |
| --- | --- | --- | --- |
| `session_id` | path | 是 | `{"title": "Session Id", "type": "string"}` |

| 响应码 | 内容 |
| --- | --- |
| 200 | application/json: ContextView |
| 422 | application/json: HTTPValidationError |

## POST /v1/sessions/{session_id}/context/compact

Compact Session Context

认证：`umeko_auth` Cookie。

| 参数 | 位置 | 必填 | 类型与约束 |
| --- | --- | --- | --- |
| `session_id` | path | 是 | `{"title": "Session Id", "type": "string"}` |

| 响应码 | 内容 |
| --- | --- |
| 200 | application/json: ContextView |
| 422 | application/json: HTTPValidationError |

## POST /v1/sessions/{session_id}/context/clear

Clear Session Context

认证：`umeko_auth` Cookie。

| 参数 | 位置 | 必填 | 类型与约束 |
| --- | --- | --- | --- |
| `session_id` | path | 是 | `{"title": "Session Id", "type": "string"}` |

| 响应码 | 内容 |
| --- | --- |
| 200 | application/json: ContextView |
| 422 | application/json: HTTPValidationError |

## POST /v1/sessions/{session_id}/chat/clear

Clear Session Chat

认证：`umeko_auth` Cookie。

清空聊天记录与上下文（文件、Skill 挂载保留）。

| 参数 | 位置 | 必填 | 类型与约束 |
| --- | --- | --- | --- |
| `session_id` | path | 是 | `{"title": "Session Id", "type": "string"}` |

| 响应码 | 内容 |
| --- | --- |
| 200 | application/json: SessionView |
| 422 | application/json: HTTPValidationError |

## POST /v1/sessions/{session_id}/clone

Clone Session

认证：`umeko_auth` Cookie。

复制会话：文件目录、当前上下文、聊天记录与 Skill 挂载全部带走。

| 参数 | 位置 | 必填 | 类型与约束 |
| --- | --- | --- | --- |
| `session_id` | path | 是 | `{"title": "Session Id", "type": "string"}` |

| 响应码 | 内容 |
| --- | --- |
| 201 | application/json: SessionView |
| 422 | application/json: HTTPValidationError |

## POST /v1/sessions/{session_id}/runs

Create Run

认证：`umeko_auth` Cookie。

| 参数 | 位置 | 必填 | 类型与约束 |
| --- | --- | --- | --- |
| `session_id` | path | 是 | `{"title": "Session Id", "type": "string"}` |

请求体：必填。

`application/json` → `RunCreate`

| 响应码 | 内容 |
| --- | --- |
| 202 | application/json: RunView |
| 422 | application/json: HTTPValidationError |

## GET /v1/runs/{run_id}

Read Run

认证：`umeko_auth` Cookie。

| 参数 | 位置 | 必填 | 类型与约束 |
| --- | --- | --- | --- |
| `run_id` | path | 是 | `{"title": "Run Id", "type": "string"}` |

| 响应码 | 内容 |
| --- | --- |
| 200 | application/json: RunView |
| 422 | application/json: HTTPValidationError |

## GET /v1/sessions/{session_id}/active-run

Active Run

认证：`umeko_auth` Cookie。

| 参数 | 位置 | 必填 | 类型与约束 |
| --- | --- | --- | --- |
| `session_id` | path | 是 | `{"title": "Session Id", "type": "string"}` |

| 响应码 | 内容 |
| --- | --- |
| 200 | application/json: RunView / null |
| 422 | application/json: HTTPValidationError |

## POST /v1/runs/{run_id}/cancel

Cancel Run

认证：`umeko_auth` Cookie。

| 参数 | 位置 | 必填 | 类型与约束 |
| --- | --- | --- | --- |
| `run_id` | path | 是 | `{"title": "Run Id", "type": "string"}` |

| 响应码 | 内容 |
| --- | --- |
| 200 | application/json: RunView |
| 422 | application/json: HTTPValidationError |

## GET /v1/runs/{run_id}/events

Stream Events

认证：`umeko_auth` Cookie。

| 参数 | 位置 | 必填 | 类型与约束 |
| --- | --- | --- | --- |
| `run_id` | path | 是 | `{"title": "Run Id", "type": "string"}` |
| `after` | query | 否 | `{"default": 0, "minimum": 0, "title": "After", "type": "integer"}` |
| `Last-Event-ID` | header | 否 | `{"anyOf": [{"type": "integer"}, {"type": "null"}], "title": "Last-Event-Id"}` |

| 响应码 | 内容 |
| --- | --- |
| 200 | text/event-stream: string |
| 422 | application/json: HTTPValidationError |

## POST /v1/sessions/{session_id}/files

Upload File

认证：`umeko_auth` Cookie。

| 参数 | 位置 | 必填 | 类型与约束 |
| --- | --- | --- | --- |
| `session_id` | path | 是 | `{"title": "Session Id", "type": "string"}` |
| `filename` | query | 是 | `{"minLength": 1, "title": "Filename", "type": "string"}` |

请求体：必填。

原始附件字节；filename 在查询参数中。

`application/octet-stream` → `string`

```json
{
  "format": "binary",
  "type": "string"
}
```

| 响应码 | 内容 |
| --- | --- |
| 201 | application/json: FileView |
| 422 | application/json: HTTPValidationError |

## POST /v1/sessions/{session_id}/files/from-workspace

Attach Workspace File

认证：`umeko_auth` Cookie。

| 参数 | 位置 | 必填 | 类型与约束 |
| --- | --- | --- | --- |
| `session_id` | path | 是 | `{"title": "Session Id", "type": "string"}` |

请求体：必填。

`application/json` → `WorkspaceAttachmentCreate`

| 响应码 | 内容 |
| --- | --- |
| 201 | application/json: FileView |
| 422 | application/json: HTTPValidationError |

## GET /v1/sessions/{session_id}/artifacts

List Artifacts

认证：`umeko_auth` Cookie。

| 参数 | 位置 | 必填 | 类型与约束 |
| --- | --- | --- | --- |
| `session_id` | path | 是 | `{"title": "Session Id", "type": "string"}` |

| 响应码 | 内容 |
| --- | --- |
| 200 | application/json: array<ArtifactView> |
| 422 | application/json: HTTPValidationError |

## GET /v1/sessions/{session_id}/artifacts/{artifact_id}/content

Download Artifact

认证：`umeko_auth` Cookie。

| 参数 | 位置 | 必填 | 类型与约束 |
| --- | --- | --- | --- |
| `session_id` | path | 是 | `{"title": "Session Id", "type": "string"}` |
| `artifact_id` | path | 是 | `{"title": "Artifact Id", "type": "string"}` |

| 响应码 | 内容 |
| --- | --- |
| 200 | application/octet-stream: string |
| 422 | application/json: HTTPValidationError |

## POST /v1/proxy/sessions

Create Proxy Session

认证：`umeko_auth` Cookie。

一步创建会话并启动任务。

multipart/form-data 字段：
 - prompt: str（必填）发给 Agent 的指令
 - skill: str（可选）要挂载的技能包名（须在 default_skills 或服务器 skills/ 中）
 - files: list[UploadFile]（可选）随任务附带的文件（zip/png/md…），存入 workspace

请求体：必填。

`multipart/form-data` → `object`

```json
{
  "properties": {
    "files": {
      "items": {
        "format": "binary",
        "type": "string"
      },
      "type": "array"
    },
    "prompt": {
      "description": "去掉首尾空白后不能为空",
      "minLength": 1,
      "type": "string"
    },
    "skill": {
      "description": "可选的技能包名称",
      "type": "string"
    }
  },
  "required": [
    "prompt"
  ],
  "type": "object"
}
```

| 响应码 | 内容 |
| --- | --- |
| 201 | application/json: ProxySessionView |

## GET /v1/proxy/sessions/{session_id}

Proxy Session Status

认证：`umeko_auth` Cookie。

查询任务状态。

- running：progress 给出当前阶段（最近工具调用/推理中）
- completed：reply 为文字结论；result 内联 qc-report.json 的结构化结果；
  artifacts 只列交付物（qc-report-*.zip/html/json），中间产物不列。

| 参数 | 位置 | 必填 | 类型与约束 |
| --- | --- | --- | --- |
| `session_id` | path | 是 | `{"title": "Session Id", "type": "string"}` |

| 响应码 | 内容 |
| --- | --- |
| 200 | application/json: ProxyStatusView |
| 422 | application/json: HTTPValidationError |

## POST /agent/{agent_name}/v1/tasks

Submit Task

认证：服务 Bearer Token 或 `umeko_auth` Cookie；开启免鉴权后可省略凭据，共享匿名任务归属。

管理员开启免鉴权后可省略凭据；免鉴权调用共用任务身份。默认仍需要凭据。

| 参数 | 位置 | 必填 | 类型与约束 |
| --- | --- | --- | --- |
| `agent_name` | path | 是 | `{"pattern": "^[a-z0-9][a-z0-9-]{0,62}$", "type": "string"}` |

请求体：必填。

`application/json` → `TaskCreateInput`

| 响应码 | 内容 |
| --- | --- |
| 202 | application/json: object |
| 422 | application/json: HTTPValidationError |

## GET /agent/{agent_name}/v1/tasks

List Tasks

认证：服务 Bearer Token 或 `umeko_auth` Cookie；开启免鉴权后可省略凭据，共享匿名任务归属。

管理员开启免鉴权后可省略凭据；免鉴权调用共用任务身份。默认仍需要凭据。

| 参数 | 位置 | 必填 | 类型与约束 |
| --- | --- | --- | --- |
| `agent_name` | path | 是 | `{"pattern": "^[a-z0-9][a-z0-9-]{0,62}$", "type": "string"}` |
| `limit` | query | 否 | `{"default": 50, "maximum": 100, "minimum": 1, "title": "Limit", "type": "integer"}` |
| `offset` | query | 否 | `{"default": 0, "minimum": 0, "title": "Offset", "type": "integer"}` |

| 响应码 | 内容 |
| --- | --- |
| 200 | application/json: object |
| 422 | application/json: HTTPValidationError |

## GET /agent/{agent_name}/v1/tasks/{task_id}

Get Task

认证：服务 Bearer Token 或 `umeko_auth` Cookie；开启免鉴权后可省略凭据，共享匿名任务归属。

管理员开启免鉴权后可省略凭据；免鉴权调用共用任务身份。默认仍需要凭据。

| 参数 | 位置 | 必填 | 类型与约束 |
| --- | --- | --- | --- |
| `agent_name` | path | 是 | `{"pattern": "^[a-z0-9][a-z0-9-]{0,62}$", "type": "string"}` |
| `task_id` | path | 是 | `{"title": "Task Id", "type": "string"}` |

| 响应码 | 内容 |
| --- | --- |
| 200 | application/json: object |
| 422 | application/json: HTTPValidationError |

## POST /agent/{agent_name}/v1/tasks/{task_id}/cancel

Cancel Task

认证：服务 Bearer Token 或 `umeko_auth` Cookie；开启免鉴权后可省略凭据，共享匿名任务归属。

管理员开启免鉴权后可省略凭据；免鉴权调用共用任务身份。默认仍需要凭据。

| 参数 | 位置 | 必填 | 类型与约束 |
| --- | --- | --- | --- |
| `agent_name` | path | 是 | `{"pattern": "^[a-z0-9][a-z0-9-]{0,62}$", "type": "string"}` |
| `task_id` | path | 是 | `{"title": "Task Id", "type": "string"}` |

| 响应码 | 内容 |
| --- | --- |
| 200 | application/json: object |
| 422 | application/json: HTTPValidationError |

## GET /agent/{agent_name}/v1/tasks/{task_id}/events

Task Events

认证：服务 Bearer Token 或 `umeko_auth` Cookie；开启免鉴权后可省略凭据，共享匿名任务归属。

管理员开启免鉴权后可省略凭据；免鉴权调用共用任务身份。默认仍需要凭据。

| 参数 | 位置 | 必填 | 类型与约束 |
| --- | --- | --- | --- |
| `agent_name` | path | 是 | `{"pattern": "^[a-z0-9][a-z0-9-]{0,62}$", "type": "string"}` |
| `task_id` | path | 是 | `{"title": "Task Id", "type": "string"}` |
| `after` | query | 否 | `{"default": 0, "minimum": 0, "title": "After", "type": "integer"}` |

| 响应码 | 内容 |
| --- | --- |
| 200 | text/event-stream: string |
| 422 | application/json: HTTPValidationError |

## GET /agent/{agent_name}/v1/tasks/{task_id}/artifacts/{artifact_id}/content

Download Artifact

认证：服务 Bearer Token 或 `umeko_auth` Cookie；开启免鉴权后可省略凭据，共享匿名任务归属。

管理员开启免鉴权后可省略凭据；免鉴权调用共用任务身份。默认仍需要凭据。

| 参数 | 位置 | 必填 | 类型与约束 |
| --- | --- | --- | --- |
| `agent_name` | path | 是 | `{"pattern": "^[a-z0-9][a-z0-9-]{0,62}$", "type": "string"}` |
| `task_id` | path | 是 | `{"title": "Task Id", "type": "string"}` |
| `artifact_id` | path | 是 | `{"title": "Artifact Id", "type": "string"}` |

| 响应码 | 内容 |
| --- | --- |
| 200 | application/octet-stream: string |
| 422 | application/json: HTTPValidationError |

## GET /agent/{agent_name}/.well-known/oauth-protected-resource/mcp

Oauth Resource

认证：无须登录。

| 参数 | 位置 | 必填 | 类型与约束 |
| --- | --- | --- | --- |
| `agent_name` | path | 是 | `{"pattern": "^[a-z0-9][a-z0-9-]{0,62}$", "type": "string"}` |

| 响应码 | 内容 |
| --- | --- |
| 200 | application/json: object |

## GET /agent/{agent_name}/.well-known/oauth-authorization-server

Oauth Server

认证：无须登录。

| 参数 | 位置 | 必填 | 类型与约束 |
| --- | --- | --- | --- |
| `agent_name` | path | 是 | `{"pattern": "^[a-z0-9][a-z0-9-]{0,62}$", "type": "string"}` |

| 响应码 | 内容 |
| --- | --- |
| 200 | application/json: object |

## POST /agent/{agent_name}/oauth/token

Oauth Token

认证：服务账号凭据（表单或 HTTP Basic）。

| 参数 | 位置 | 必填 | 类型与约束 |
| --- | --- | --- | --- |
| `agent_name` | path | 是 | `{"pattern": "^[a-z0-9][a-z0-9-]{0,62}$", "type": "string"}` |

请求体：必填。

client_credentials；也可用 HTTP Basic 传 client_id/client_secret。

`application/x-www-form-urlencoded` → `object`

```json
{
  "properties": {
    "client_id": {
      "type": "string"
    },
    "client_secret": {
      "type": "string",
      "writeOnly": true
    },
    "grant_type": {
      "enum": [
        "client_credentials"
      ],
      "type": "string"
    },
    "resource": {
      "type": "string"
    },
    "scope": {
      "type": "string"
    }
  },
  "required": [
    "grant_type"
  ],
  "type": "object"
}
```

| 响应码 | 内容 |
| --- | --- |
| 200 | application/json: 任意 JSON |

## GET /agent/{agent_name}/.well-known/agent-card.json

Card

认证：无须登录。

| 参数 | 位置 | 必填 | 类型与约束 |
| --- | --- | --- | --- |
| `agent_name` | path | 是 | `{"pattern": "^[a-z0-9][a-z0-9-]{0,62}$", "type": "string"}` |

| 响应码 | 内容 |
| --- | --- |
| 200 | application/json: 任意 JSON |
