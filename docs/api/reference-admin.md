# 管理接口完整参考

> 自动生成：请修改源码或生成器，不直接编辑本文件。

共 **49** 个 HTTP 操作。[下载 OpenAPI](openapi-admin.json) · [数据结构](schemas.md)

路径为应用内部路由；带前缀部署时在公共 URL 前加 `UMEKO_BASE_PATH`。登录、原始字节体与 SSE 契约由生成器显式补充。

泛型 `object` / 任意 JSON 表示源码尚未声明完整字段模型，请结合各专题指南。表中响应码来自 OpenAPI，不包含中间件产生的全部错误。

## 接口索引

| 方法 | 路径 | 操作 |
| --- | --- | --- |
| GET | `/health` | Health |
| POST | `/admin/login` | Login |
| POST | `/admin/logout` | Logout |
| GET | `/admin/v1/me` | Me |
| GET | `/admin/v1/resources` | Resources |
| GET | `/admin/v1/service-accounts` | Service Accounts |
| POST | `/admin/v1/service-accounts` | Create Service Account |
| GET | `/admin/v1/service-access` | Service Access |
| PUT | `/admin/v1/service-access` | Update Service Access |
| PATCH | `/admin/v1/service-accounts/{account_id}` | Update Service Account |
| GET | `/admin/v1/tasks` | Monitored Tasks |
| POST | `/admin/v1/tasks/{task_id}/cancel` | Stop Machine Task |
| GET | `/admin/v1/users` | Users |
| POST | `/admin/v1/users` | Create User |
| PUT | `/admin/v1/users/{user_id}/password` | Set Password |
| PUT | `/admin/v1/users/{user_id}/role` | Set Role |
| DELETE | `/admin/v1/users/{user_id}` | Delete User |
| GET | `/admin/v1/users/{user_id}/sessions` | User Sessions |
| DELETE | `/admin/v1/sessions/{session_id}` | Delete Session |
| POST | `/admin/v1/sessions/{session_id}/evict` | Evict Session |
| GET | `/admin/v1/providers` | List Providers |
| POST | `/admin/v1/providers` | Create Provider |
| PUT | `/admin/v1/providers/{provider_id}` | Update Provider |
| DELETE | `/admin/v1/providers/{provider_id}` | Delete Provider |
| POST | `/admin/v1/providers/{provider_id}/models` | Add Model |
| PUT | `/admin/v1/models/{model_id}` | Update Model |
| DELETE | `/admin/v1/models/{model_id}` | Delete Model |
| PUT | `/admin/v1/active-model` | Activate Model |
| POST | `/admin/v1/providers/import` | Import Providers |
| GET | `/admin/v1/default-skills` | List Default Skills |
| POST | `/admin/v1/default-skills/{name}/toggle` | Toggle Default Skill |
| POST | `/admin/v1/default-skills/import/{name}` | Import Default Skill |
| GET | `/admin/v1/default-skills/{name}` | Get Default Skill |
| PUT | `/admin/v1/default-skills/{name}` | Upload Default Skill |
| DELETE | `/admin/v1/default-skills/{name}` | Delete Default Skill |
| GET | `/admin/v1/skill-scripts/{pack}` | List Skill Scripts |
| GET | `/admin/v1/skill-scripts/{pack}/{script_name}` | Get Skill Script |
| PUT | `/admin/v1/skill-scripts/{pack}/{script_name}` | Put Skill Script |
| DELETE | `/admin/v1/skill-scripts/{pack}/{script_name}` | Delete Skill Script |
| PUT | `/admin/v1/skill-members/{pack}/{member_name}` | Put Skill Member |
| DELETE | `/admin/v1/skill-members/{pack}/{member_name}` | Delete Skill Member |
| GET | `/admin/v1/runtime-config` | Get Runtime Config |
| PUT | `/admin/v1/runtime-config` | Set Runtime Config |
| GET | `/admin/v1/skill-source/{name}` | Get Skill Source |
| PUT | `/admin/v1/skill-source/{name}` | Put Skill Source |
| DELETE | `/admin/v1/skill-source/{name}` | Delete Skill Source |
| GET | `/admin/v1/skill-library` | Skill Library Tree |
| GET | `/admin/v1/skill-scripts-template` | Skill Script Template |
| POST | `/admin/v1/skill-scripts/{pack}/{script_name}/test` | Test Skill Script |

## GET /health

Health

认证：无须登录。

| 响应码 | 内容 |
| --- | --- |
| 200 | application/json: object |

## POST /admin/login

Login

认证：无须登录。

请求体：必填。

`application/json` → `_Login`

| 响应码 | 内容 |
| --- | --- |
| 200 | application/json: object |
| 422 | application/json: HTTPValidationError |

## POST /admin/logout

Logout

认证：`umeko_admin` Cookie。

| 响应码 | 内容 |
| --- | --- |
| 204 | Successful Response |

## GET /admin/v1/me

Me

认证：`umeko_admin` Cookie。

| 响应码 | 内容 |
| --- | --- |
| 200 | application/json: object |

## GET /admin/v1/resources

Resources

认证：`umeko_admin` Cookie。

| 响应码 | 内容 |
| --- | --- |
| 200 | application/json: object |

## GET /admin/v1/service-accounts

Service Accounts

认证：`umeko_admin` Cookie。

| 响应码 | 内容 |
| --- | --- |
| 200 | application/json: object |

## POST /admin/v1/service-accounts

Create Service Account

认证：`umeko_admin` Cookie。

请求体：必填。

`application/json` → `_ServiceAccountIn`

| 响应码 | 内容 |
| --- | --- |
| 201 | application/json: object |
| 422 | application/json: HTTPValidationError |

## GET /admin/v1/service-access

Service Access

认证：`umeko_admin` Cookie。

| 响应码 | 内容 |
| --- | --- |
| 200 | application/json: object |

## PUT /admin/v1/service-access

Update Service Access

认证：`umeko_admin` Cookie。

请求体：必填。

`application/json` → `_ServiceAccessIn`

| 响应码 | 内容 |
| --- | --- |
| 200 | application/json: object |
| 422 | application/json: HTTPValidationError |

## PATCH /admin/v1/service-accounts/{account_id}

Update Service Account

认证：`umeko_admin` Cookie。

| 参数 | 位置 | 必填 | 类型与约束 |
| --- | --- | --- | --- |
| `account_id` | path | 是 | `{"title": "Account Id", "type": "string"}` |

请求体：必填。

`application/json` → `_ServiceAccountPatch`

| 响应码 | 内容 |
| --- | --- |
| 200 | application/json: object |
| 422 | application/json: HTTPValidationError |

## GET /admin/v1/tasks

Monitored Tasks

认证：`umeko_admin` Cookie。

| 响应码 | 内容 |
| --- | --- |
| 200 | application/json: array<object> |

## POST /admin/v1/tasks/{task_id}/cancel

Stop Machine Task

认证：`umeko_admin` Cookie。

| 参数 | 位置 | 必填 | 类型与约束 |
| --- | --- | --- | --- |
| `task_id` | path | 是 | `{"title": "Task Id", "type": "string"}` |

| 响应码 | 内容 |
| --- | --- |
| 200 | application/json: object |
| 422 | application/json: HTTPValidationError |

## GET /admin/v1/users

Users

认证：`umeko_admin` Cookie。

| 响应码 | 内容 |
| --- | --- |
| 200 | application/json: array<object> |

## POST /admin/v1/users

Create User

认证：`umeko_admin` Cookie。

请求体：必填。

`application/json` → `_UserCreate`

| 响应码 | 内容 |
| --- | --- |
| 201 | application/json: object |
| 422 | application/json: HTTPValidationError |

## PUT /admin/v1/users/{user_id}/password

Set Password

认证：`umeko_admin` Cookie。

| 参数 | 位置 | 必填 | 类型与约束 |
| --- | --- | --- | --- |
| `user_id` | path | 是 | `{"title": "User Id", "type": "string"}` |

请求体：必填。

`application/json` → `_PasswordSet`

| 响应码 | 内容 |
| --- | --- |
| 204 | Successful Response |
| 422 | application/json: HTTPValidationError |

## PUT /admin/v1/users/{user_id}/role

Set Role

认证：`umeko_admin` Cookie。

| 参数 | 位置 | 必填 | 类型与约束 |
| --- | --- | --- | --- |
| `user_id` | path | 是 | `{"title": "User Id", "type": "string"}` |

请求体：必填。

`application/json` → `_RoleSet`

| 响应码 | 内容 |
| --- | --- |
| 204 | Successful Response |
| 422 | application/json: HTTPValidationError |

## DELETE /admin/v1/users/{user_id}

Delete User

认证：`umeko_admin` Cookie。

| 参数 | 位置 | 必填 | 类型与约束 |
| --- | --- | --- | --- |
| `user_id` | path | 是 | `{"title": "User Id", "type": "string"}` |

| 响应码 | 内容 |
| --- | --- |
| 204 | Successful Response |
| 422 | application/json: HTTPValidationError |

## GET /admin/v1/users/{user_id}/sessions

User Sessions

认证：`umeko_admin` Cookie。

| 参数 | 位置 | 必填 | 类型与约束 |
| --- | --- | --- | --- |
| `user_id` | path | 是 | `{"title": "User Id", "type": "string"}` |

| 响应码 | 内容 |
| --- | --- |
| 200 | application/json: array<object> |
| 422 | application/json: HTTPValidationError |

## DELETE /admin/v1/sessions/{session_id}

Delete Session

认证：`umeko_admin` Cookie。

| 参数 | 位置 | 必填 | 类型与约束 |
| --- | --- | --- | --- |
| `session_id` | path | 是 | `{"title": "Session Id", "type": "string"}` |

| 响应码 | 内容 |
| --- | --- |
| 204 | Successful Response |
| 422 | application/json: HTTPValidationError |

## POST /admin/v1/sessions/{session_id}/evict

Evict Session

认证：`umeko_admin` Cookie。

| 参数 | 位置 | 必填 | 类型与约束 |
| --- | --- | --- | --- |
| `session_id` | path | 是 | `{"title": "Session Id", "type": "string"}` |

| 响应码 | 内容 |
| --- | --- |
| 200 | application/json: object |
| 422 | application/json: HTTPValidationError |

## GET /admin/v1/providers

List Providers

认证：`umeko_admin` Cookie。

| 响应码 | 内容 |
| --- | --- |
| 200 | application/json: object |

## POST /admin/v1/providers

Create Provider

认证：`umeko_admin` Cookie。

请求体：必填。

`application/json` → `_ProviderIn`

| 响应码 | 内容 |
| --- | --- |
| 201 | application/json: object |
| 422 | application/json: HTTPValidationError |

## PUT /admin/v1/providers/{provider_id}

Update Provider

认证：`umeko_admin` Cookie。

| 参数 | 位置 | 必填 | 类型与约束 |
| --- | --- | --- | --- |
| `provider_id` | path | 是 | `{"title": "Provider Id", "type": "string"}` |

请求体：必填。

`application/json` → `_ProviderPatch`

| 响应码 | 内容 |
| --- | --- |
| 204 | Successful Response |
| 422 | application/json: HTTPValidationError |

## DELETE /admin/v1/providers/{provider_id}

Delete Provider

认证：`umeko_admin` Cookie。

| 参数 | 位置 | 必填 | 类型与约束 |
| --- | --- | --- | --- |
| `provider_id` | path | 是 | `{"title": "Provider Id", "type": "string"}` |

| 响应码 | 内容 |
| --- | --- |
| 204 | Successful Response |
| 422 | application/json: HTTPValidationError |

## POST /admin/v1/providers/{provider_id}/models

Add Model

认证：`umeko_admin` Cookie。

| 参数 | 位置 | 必填 | 类型与约束 |
| --- | --- | --- | --- |
| `provider_id` | path | 是 | `{"title": "Provider Id", "type": "string"}` |

请求体：必填。

`application/json` → `_ModelIn`

| 响应码 | 内容 |
| --- | --- |
| 201 | application/json: object |
| 422 | application/json: HTTPValidationError |

## PUT /admin/v1/models/{model_id}

Update Model

认证：`umeko_admin` Cookie。

| 参数 | 位置 | 必填 | 类型与约束 |
| --- | --- | --- | --- |
| `model_id` | path | 是 | `{"title": "Model Id", "type": "string"}` |

请求体：必填。

`application/json` → `_ModelPatch`

| 响应码 | 内容 |
| --- | --- |
| 204 | Successful Response |
| 422 | application/json: HTTPValidationError |

## DELETE /admin/v1/models/{model_id}

Delete Model

认证：`umeko_admin` Cookie。

| 参数 | 位置 | 必填 | 类型与约束 |
| --- | --- | --- | --- |
| `model_id` | path | 是 | `{"title": "Model Id", "type": "string"}` |

| 响应码 | 内容 |
| --- | --- |
| 204 | Successful Response |
| 422 | application/json: HTTPValidationError |

## PUT /admin/v1/active-model

Activate Model

认证：`umeko_admin` Cookie。

设为当前模型并全员生效（驱逐全部在线 Session）。

请求体：必填。

`application/json` → `_ActiveModelIn`

| 响应码 | 内容 |
| --- | --- |
| 200 | application/json: object |
| 422 | application/json: HTTPValidationError |

## POST /admin/v1/providers/import

Import Providers

认证：`umeko_admin` Cookie。

粘贴 JSON 批量导入；带 active 字段时一并激活并全员生效。

请求体：必填。

`application/json` → `_ImportIn`

| 响应码 | 内容 |
| --- | --- |
| 200 | application/json: object |
| 422 | application/json: HTTPValidationError |

## GET /admin/v1/default-skills

List Default Skills

认证：`umeko_admin` Cookie。

| 响应码 | 内容 |
| --- | --- |
| 200 | application/json: object |

## POST /admin/v1/default-skills/{name}/toggle

Toggle Default Skill

认证：`umeko_admin` Cookie。

停用/启用：停用后不再下发到新 Session（已播种的不撤回）。

| 参数 | 位置 | 必填 | 类型与约束 |
| --- | --- | --- | --- |
| `name` | path | 是 | `{"title": "Name", "type": "string"}` |

| 响应码 | 内容 |
| --- | --- |
| 200 | application/json: object |
| 422 | application/json: HTTPValidationError |

## POST /admin/v1/default-skills/import/{name}

Import Default Skill

认证：`umeko_admin` Cookie。

把服务器 skills/ 目录中的技能文件导入默认 Skill（导入后新 Session 生效）。

| 参数 | 位置 | 必填 | 类型与约束 |
| --- | --- | --- | --- |
| `name` | path | 是 | `{"title": "Name", "type": "string"}` |

| 响应码 | 内容 |
| --- | --- |
| 201 | application/json: object |
| 422 | application/json: HTTPValidationError |

## GET /admin/v1/default-skills/{name}

Get Default Skill

认证：`umeko_admin` Cookie。

| 参数 | 位置 | 必填 | 类型与约束 |
| --- | --- | --- | --- |
| `name` | path | 是 | `{"title": "Name", "type": "string"}` |

| 响应码 | 内容 |
| --- | --- |
| 200 | application/json: object |
| 422 | application/json: HTTPValidationError |

## PUT /admin/v1/default-skills/{name}

Upload Default Skill

认证：`umeko_admin` Cookie。

上传/更新默认 Skill；对新 Session 生效（在线 Session 不回填）。

| 参数 | 位置 | 必填 | 类型与约束 |
| --- | --- | --- | --- |
| `name` | path | 是 | `{"title": "Name", "type": "string"}` |

请求体：必填。

`application/json` → `_DefaultSkillIn`

| 响应码 | 内容 |
| --- | --- |
| 201 | application/json: object |
| 422 | application/json: HTTPValidationError |

## DELETE /admin/v1/default-skills/{name}

Delete Default Skill

认证：`umeko_admin` Cookie。

| 参数 | 位置 | 必填 | 类型与约束 |
| --- | --- | --- | --- |
| `name` | path | 是 | `{"title": "Name", "type": "string"}` |

| 响应码 | 内容 |
| --- | --- |
| 204 | Successful Response |
| 422 | application/json: HTTPValidationError |

## GET /admin/v1/skill-scripts/{pack}

List Skill Scripts

认证：`umeko_admin` Cookie。

| 参数 | 位置 | 必填 | 类型与约束 |
| --- | --- | --- | --- |
| `pack` | path | 是 | `{"title": "Pack", "type": "string"}` |

| 响应码 | 内容 |
| --- | --- |
| 200 | application/json: object |
| 422 | application/json: HTTPValidationError |

## GET /admin/v1/skill-scripts/{pack}/{script_name}

Get Skill Script

认证：`umeko_admin` Cookie。

| 参数 | 位置 | 必填 | 类型与约束 |
| --- | --- | --- | --- |
| `pack` | path | 是 | `{"title": "Pack", "type": "string"}` |
| `script_name` | path | 是 | `{"title": "Script Name", "type": "string"}` |

| 响应码 | 内容 |
| --- | --- |
| 200 | application/json: object |
| 422 | application/json: HTTPValidationError |

## PUT /admin/v1/skill-scripts/{pack}/{script_name}

Put Skill Script

认证：`umeko_admin` Cookie。

新建/覆盖技能包脚本。内容须可编译（语法检查），防低级错误上线。

| 参数 | 位置 | 必填 | 类型与约束 |
| --- | --- | --- | --- |
| `pack` | path | 是 | `{"title": "Pack", "type": "string"}` |
| `script_name` | path | 是 | `{"title": "Script Name", "type": "string"}` |

请求体：必填。

`application/json` → `_DefaultSkillIn`

| 响应码 | 内容 |
| --- | --- |
| 201 | application/json: object |
| 422 | application/json: HTTPValidationError |

## DELETE /admin/v1/skill-scripts/{pack}/{script_name}

Delete Skill Script

认证：`umeko_admin` Cookie。

| 参数 | 位置 | 必填 | 类型与约束 |
| --- | --- | --- | --- |
| `pack` | path | 是 | `{"title": "Pack", "type": "string"}` |
| `script_name` | path | 是 | `{"title": "Script Name", "type": "string"}` |

| 响应码 | 内容 |
| --- | --- |
| 204 | Successful Response |
| 422 | application/json: HTTPValidationError |

## PUT /admin/v1/skill-members/{pack}/{member_name}

Put Skill Member

认证：`umeko_admin` Cookie。

新建/覆盖技能包成员文件（文本类；.py 脚本走 skill-scripts 端点）。

| 参数 | 位置 | 必填 | 类型与约束 |
| --- | --- | --- | --- |
| `pack` | path | 是 | `{"title": "Pack", "type": "string"}` |
| `member_name` | path | 是 | `{"title": "Member Name", "type": "string"}` |

请求体：必填。

`application/json` → `_DefaultSkillIn`

| 响应码 | 内容 |
| --- | --- |
| 201 | application/json: object |
| 422 | application/json: HTTPValidationError |

## DELETE /admin/v1/skill-members/{pack}/{member_name}

Delete Skill Member

认证：`umeko_admin` Cookie。

| 参数 | 位置 | 必填 | 类型与约束 |
| --- | --- | --- | --- |
| `pack` | path | 是 | `{"title": "Pack", "type": "string"}` |
| `member_name` | path | 是 | `{"title": "Member Name", "type": "string"}` |

| 响应码 | 内容 |
| --- | --- |
| 204 | Successful Response |
| 422 | application/json: HTTPValidationError |

## GET /admin/v1/runtime-config

Get Runtime Config

认证：`umeko_admin` Cookie。

| 响应码 | 内容 |
| --- | --- |
| 200 | application/json: object |

## PUT /admin/v1/runtime-config

Set Runtime Config

认证：`umeko_admin` Cookie。

设置运行参数后立即驱逐全部在线 Session 生效。max_tool_iterations=0 表示无限。

请求体：必填。

`application/json` → `_RuntimeConfigIn`

| 响应码 | 内容 |
| --- | --- |
| 200 | application/json: object |
| 422 | application/json: HTTPValidationError |

## GET /admin/v1/skill-source/{name}

Get Skill Source

认证：`umeko_admin` Cookie。

| 参数 | 位置 | 必填 | 类型与约束 |
| --- | --- | --- | --- |
| `name` | path | 是 | `{"title": "Name", "type": "string"}` |

| 响应码 | 内容 |
| --- | --- |
| 200 | application/json: object |
| 422 | application/json: HTTPValidationError |

## PUT /admin/v1/skill-source/{name}

Put Skill Source

认证：`umeko_admin` Cookie。

新建/覆盖技能库源文件（.md，须带合法 front matter）。

| 参数 | 位置 | 必填 | 类型与约束 |
| --- | --- | --- | --- |
| `name` | path | 是 | `{"title": "Name", "type": "string"}` |

请求体：必填。

`application/json` → `_DefaultSkillIn`

| 响应码 | 内容 |
| --- | --- |
| 201 | application/json: object |
| 422 | application/json: HTTPValidationError |

## DELETE /admin/v1/skill-source/{name}

Delete Skill Source

认证：`umeko_admin` Cookie。

| 参数 | 位置 | 必填 | 类型与约束 |
| --- | --- | --- | --- |
| `name` | path | 是 | `{"title": "Name", "type": "string"}` |

| 响应码 | 内容 |
| --- | --- |
| 204 | Successful Response |
| 422 | application/json: HTTPValidationError |

## GET /admin/v1/skill-library

Skill Library Tree

认证：`umeko_admin` Cookie。

技能库树：包（.md + 同名目录脚本/成员文件）。一个 Skill = 文件夹 + 同名 .md。

成员文件（checks.md 等）是 read_pack_file 的运行时输入，与脚本一同列出并带修改时间。

| 响应码 | 内容 |
| --- | --- |
| 200 | application/json: object |

## GET /admin/v1/skill-scripts-template

Skill Script Template

认证：`umeko_admin` Cookie。

统一契约的脚本模板（面板可下载/新建时预填）。

| 响应码 | 内容 |
| --- | --- |
| 200 | application/json: object |

## POST /admin/v1/skill-scripts/{pack}/{script_name}/test

Test Skill Script

认证：`umeko_admin` Cookie。

在隔离环境测试脚本：临时 workdir，超时强杀，返回结果与进度。

| 参数 | 位置 | 必填 | 类型与约束 |
| --- | --- | --- | --- |
| `pack` | path | 是 | `{"title": "Pack", "type": "string"}` |
| `script_name` | path | 是 | `{"title": "Script Name", "type": "string"}` |

请求体：必填。

`application/json` → `_ScriptTestIn`

| 响应码 | 内容 |
| --- | --- |
| 200 | application/json: object |
| 422 | application/json: HTTPValidationError |
