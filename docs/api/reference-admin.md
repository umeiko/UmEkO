# 管理接口完整参考

> 自动生成：请修改源码或生成器，不直接编辑本文件。

共 **73** 个 HTTP 操作。[下载 OpenAPI](openapi-admin.json) · [数据结构](schemas.md)

路径为应用内部路由；带前缀部署时在公共 URL 前加 `UMEKO_ADMIN_BASE_PATH`。认证与操作行为来自运行时管理契约。

泛型 `object` / 任意 JSON 表示源码尚未声明完整字段模型，请结合各专题指南。表中响应码来自 OpenAPI，不包含中间件产生的全部错误。

## 接口索引

| 方法 | 路径 | 操作 |
| --- | --- | --- |
| GET | `/health` | 服务状态 |
| POST | `/admin/login` | 管理员登录 |
| POST | `/admin/logout` | 退出管理员登录 |
| GET | `/admin/v1/me` | 当前管理员 |
| GET | `/admin/v1/resources` | 资源监控 |
| GET | `/admin/v1/service-accounts` | 服务账号列表 |
| POST | `/admin/v1/service-accounts` | 创建服务账号 |
| GET | `/admin/v1/service-access` | 读取机器接入方式 |
| PUT | `/admin/v1/service-access` | 设置机器接入方式 |
| GET | `/admin/v1/agents` | 智能体目录与配置选项 |
| POST | `/admin/v1/agents` | 创建智能体 |
| PUT | `/admin/v1/agents/{agent_id}` | 更新智能体 |
| GET | `/admin/v1/agents/{agent_id}` | 读取智能体 |
| DELETE | `/admin/v1/agents/{agent_id}` | 删除智能体 |
| GET | `/admin/v1/agents/{agent_id}/card` | 预览 Agent Card |
| GET | `/admin/v1/agents/{agent_id}/mcp` | 查看 MCP 接口披露 |
| PATCH | `/admin/v1/service-accounts/{account_id}` | 更新或轮换服务凭据 |
| DELETE | `/admin/v1/service-accounts/{account_id}` | 删除服务账号及历史 |
| GET | `/admin/v1/tasks` | 机器任务列表 |
| POST | `/admin/v1/tasks/{task_id}/cancel` | 取消机器任务 |
| GET | `/admin/v1/tasks/{task_id}` | 机器任务详情 |
| GET | `/admin/v1/tasks/{task_id}/files` | 任务会话文件树 |
| GET | `/admin/v1/users` | 用户列表 |
| POST | `/admin/v1/users` | 创建用户 |
| PUT | `/admin/v1/users/{user_id}/password` | 重置用户密码 |
| GET | `/admin/v1/users/{user_id}/model-access` | 读取用户模型权限 |
| PUT | `/admin/v1/users/{user_id}/model-access` | 设置用户模型权限 |
| GET | `/admin/v1/tools` | 工具下发目录 |
| PUT | `/admin/v1/tools/{name}` | 设置工具全局下发 |
| GET | `/admin/v1/users/{user_id}/tool-access` | 读取用户工具权限 |
| PUT | `/admin/v1/users/{user_id}/tool-access` | 设置用户工具权限 |
| PUT | `/admin/v1/users/{user_id}/role` | 修改用户角色 |
| DELETE | `/admin/v1/users/{user_id}` | 删除用户与所属数据 |
| GET | `/admin/v1/users/{user_id}/sessions` | 用户会话列表 |
| GET | `/admin/v1/sessions/{session_id}` | 会话内容详情 |
| DELETE | `/admin/v1/sessions/{session_id}` | 删除会话与文件 |
| POST | `/admin/v1/sessions/{session_id}/evict` | 驱逐会话缓存 |
| GET | `/admin/v1/providers` | 供应商及模型目录 |
| POST | `/admin/v1/providers` | 创建模型供应商 |
| PUT | `/admin/v1/providers/{provider_id}` | 修改模型供应商 |
| DELETE | `/admin/v1/providers/{provider_id}` | 删除模型供应商 |
| POST | `/admin/v1/providers/{provider_id}/models` | 新增模型 |
| PUT | `/admin/v1/models/{model_id}` | 修改模型能力与并发 |
| DELETE | `/admin/v1/models/{model_id}` | 删除模型 |
| PUT | `/admin/v1/active-model` | 设置平台默认主模型 |
| POST | `/admin/v1/providers/import` | 批量导入供应商与模型 |
| GET | `/admin/v1/default-skills` | 技能下发列表 |
| POST | `/admin/v1/default-skills/{name}/toggle` | 切换技能下发开关 |
| POST | `/admin/v1/default-skills/import/{name}` | 从技能库导入下发入口 |
| GET | `/admin/v1/default-skills/{name}` | 读取已下发技能入口 |
| PUT | `/admin/v1/default-skills/{name}` | 保存技能下发入口 |
| DELETE | `/admin/v1/default-skills/{name}` | 删除技能下发入口 |
| GET | `/admin/v1/skill-scripts/{pack}` | 列出技能代码 |
| GET | `/admin/v1/skill-scripts/{pack}/{script_name}` | 读取技能脚本或成员文本 |
| PUT | `/admin/v1/skill-scripts/{pack}/{script_name}` | 保存技能代码 |
| DELETE | `/admin/v1/skill-scripts/{pack}/{script_name}` | 删除技能代码 |
| PUT | `/admin/v1/skill-members/{pack}/{member_name}` | 保存技能附属文本 |
| DELETE | `/admin/v1/skill-members/{pack}/{member_name}` | 删除技能附属文件 |
| GET | `/admin/v1/runtime-config` | 读取工具回合上限 |
| PUT | `/admin/v1/runtime-config` | 设置工具回合上限 |
| GET | `/admin/v1/skill-source/{name}` | 读取技能库主指引 |
| PUT | `/admin/v1/skill-source/{name}` | 保存技能库主指引 |
| DELETE | `/admin/v1/skill-source/{name}` | 删除技能库主指引 |
| GET | `/admin/v1/skill-library` | 管理员技能文件树 |
| GET | `/admin/v1/skill-scripts-template` | 读取脚本模板 |
| GET | `/admin/v1/skill-security/catalog` | 查询可信代码目录 |
| GET | `/admin/v1/skill-security/selection` | 取得跨页选择快照 |
| POST | `/admin/v1/skill-security/batch` | 批量批准或撤销可信版本 |
| GET | `/admin/v1/skill-security/{pack}/{member}` | 读取单文件安全门禁 |
| POST | `/admin/v1/skill-security/{pack}/{member}` | 批准当前文件版本 |
| DELETE | `/admin/v1/skill-security/{pack}/{member}` | 撤销文件可信版本 |
| POST | `/admin/v1/skill-scripts/{pack}/{script_name}/test` | 测试已批准的技能脚本 |
| GET | `/admin/v1/openapi.json` | 管理接口规范 |

## GET /health

服务状态

认证：无须登录。

读取管理服务健康状态，不表示模型调用可用。

| 响应码 | 内容 |
| --- | --- |
| 200 | application/json: object |

## POST /admin/login

管理员登录

认证：无须登录。

验证管理员账号密码，设置 umeko_admin Cookie，有效期最长 7 天；登录响应不返回模型密钥。

请求体：必填。

`application/json` → `_Login`

| 响应码 | 内容 |
| --- | --- |
| 200 | application/json: object |
| 422 | application/json: HTTPValidationError |

## POST /admin/logout

退出管理员登录

认证：无须登录。

撤销当前 Cookie 对应的服务端登录令牌，并按相同管理前缀删除 Cookie。

| 响应码 | 内容 |
| --- | --- |
| 204 | Successful Response |

## GET /admin/v1/me

当前管理员

认证：`umeko_admin` Cookie。

读取当前登录管理员的身份。普通用户和未登录请求均返回 401。

| 响应码 | 内容 |
| --- | --- |
| 200 | application/json: object |
| 401 | 未登录、会话失效或不是管理员。 |

## GET /admin/v1/resources

资源监控

认证：`umeko_admin` Cookie。

读取主机、进程、任务队列、模型队列和历史采样；不发起模型调用。

| 响应码 | 内容 |
| --- | --- |
| 200 | application/json: object |
| 401 | 未登录、会话失效或不是管理员。 |

## GET /admin/v1/service-accounts

服务账号列表

认证：`umeko_admin` Cookie。

返回账号、权限选项与接入方式；不返回已有账号的原始凭据。

| 响应码 | 内容 |
| --- | --- |
| 200 | application/json: object |
| 401 | 未登录、会话失效或不是管理员。 |

## POST /admin/v1/service-accounts

创建服务账号

认证：`umeko_admin` Cookie。

原始 token 仅本次返回；请保存到调用者指定的受限位置。它是机器任务凭据，不能调用管理 API。

请求体：必填。

`application/json` → `_ServiceAccountIn`

| 响应码 | 内容 |
| --- | --- |
| 201 | application/json: object |
| 422 | application/json: HTTPValidationError |
| 401 | 未登录、会话失效或不是管理员。 |

## GET /admin/v1/service-access

读取机器接入方式

认证：`umeko_admin` Cookie。

读取凭据鉴权或共享匿名模式。此设置不改变管理员 API 鉴权。

| 响应码 | 内容 |
| --- | --- |
| 200 | application/json: object |
| 401 | 未登录、会话失效或不是管理员。 |

## PUT /admin/v1/service-access

设置机器接入方式

认证：`umeko_admin` Cookie。

required 为凭据鉴权，anonymous 为共享免鉴权；匿名调用不按 IP 隔离身份。管理 API 始终需要管理员。

请求体：必填。

`application/json` → `_ServiceAccessIn`

| 响应码 | 内容 |
| --- | --- |
| 200 | application/json: object |
| 422 | application/json: HTTPValidationError |
| 401 | 未登录、会话失效或不是管理员。 |

## GET /admin/v1/agents

智能体目录与配置选项

认证：`umeko_admin` Cookie。

返回智能体、可选模型和技能目录；endpoints 指向用户服务，不是管理服务。

| 响应码 | 内容 |
| --- | --- |
| 200 | application/json: object |
| 401 | 未登录、会话失效或不是管理员。 |

## POST /admin/v1/agents

创建智能体

认证：`umeko_admin` Cookie。

设置介绍、工作指引、默认主模型/视觉模型与技能范围；成功返回带 id 和 endpoints 的完整记录。

请求体：必填。

`application/json` → `_AgentIn`

| 响应码 | 内容 |
| --- | --- |
| 201 | application/json: object |
| 422 | application/json: HTTPValidationError |
| 401 | 未登录、会话失效或不是管理员。 |

## PUT /admin/v1/agents/{agent_id}

更新智能体

认证：`umeko_admin` Cookie。

按完整表单更新；先读取原记录，仅改目标字段再提交。访问路径 slug 不可改，修改对新任务生效。

| 参数 | 位置 | 必填 | 类型与约束 |
| --- | --- | --- | --- |
| `agent_id` | path | 是 | `{"title": "Agent Id", "type": "string"}` |

请求体：必填。

`application/json` → `_AgentIn`

| 响应码 | 内容 |
| --- | --- |
| 200 | application/json: object |
| 422 | application/json: HTTPValidationError |
| 401 | 未登录、会话失效或不是管理员。 |

## GET /admin/v1/agents/{agent_id}

读取智能体

认证：`umeko_admin` Cookie。

读取配置、默认模型、技能与公开入口；工作指引属于管理员数据。

| 参数 | 位置 | 必填 | 类型与约束 |
| --- | --- | --- | --- |
| `agent_id` | path | 是 | `{"title": "Agent Id", "type": "string"}` |

| 响应码 | 内容 |
| --- | --- |
| 200 | application/json: object |
| 422 | application/json: HTTPValidationError |
| 401 | 未登录、会话失效或不是管理员。 |

## DELETE /admin/v1/agents/{agent_id}

删除智能体

认证：`umeko_admin` Cookie。

永久删除定义；有保留任务时可能返回 409，应先停用并等待生命周期清理。

| 参数 | 位置 | 必填 | 类型与约束 |
| --- | --- | --- | --- |
| `agent_id` | path | 是 | `{"title": "Agent Id", "type": "string"}` |

| 响应码 | 内容 |
| --- | --- |
| 204 | Successful Response |
| 422 | application/json: HTTPValidationError |
| 401 | 未登录、会话失效或不是管理员。 |

## GET /admin/v1/agents/{agent_id}/card

预览 Agent Card

认证：`umeko_admin` Cookie。

返回当前已保存配置生成的公开名片，私有工作指引不放入 Card。

| 参数 | 位置 | 必填 | 类型与约束 |
| --- | --- | --- | --- |
| `agent_id` | path | 是 | `{"title": "Agent Id", "type": "string"}` |

| 响应码 | 内容 |
| --- | --- |
| 200 | application/json: object |
| 422 | application/json: HTTPValidationError |
| 401 | 未登录、会话失效或不是管理员。 |

## GET /admin/v1/agents/{agent_id}/mcp

查看 MCP 接口披露

认证：`umeko_admin` Cookie。

读取 SDK 实际注册的工具、参数、资源和提示词，不执行工具。

| 参数 | 位置 | 必填 | 类型与约束 |
| --- | --- | --- | --- |
| `agent_id` | path | 是 | `{"title": "Agent Id", "type": "string"}` |

| 响应码 | 内容 |
| --- | --- |
| 200 | application/json: object |
| 422 | application/json: HTTPValidationError |
| 401 | 未登录、会话失效或不是管理员。 |

## PATCH /admin/v1/service-accounts/{account_id}

更新或轮换服务凭据

认证：`umeko_admin` Cookie。

enabled 控制启停；rotate=true 生成新凭据并撤销旧令牌。不要在超时后盲目重复轮换。停用不自动取消任务。

| 参数 | 位置 | 必填 | 类型与约束 |
| --- | --- | --- | --- |
| `account_id` | path | 是 | `{"title": "Account Id", "type": "string"}` |

请求体：必填。

`application/json` → `_ServiceAccountPatch`

| 响应码 | 内容 |
| --- | --- |
| 200 | application/json: object |
| 422 | application/json: HTTPValidationError |
| 401 | 未登录、会话失效或不是管理员。 |

## DELETE /admin/v1/service-accounts/{account_id}

删除服务账号及历史

认证：`umeko_admin` Cookie。

永久清理此账号的凭据、任务、事件、会话与文件；有活跃任务时返回 409。

| 参数 | 位置 | 必填 | 类型与约束 |
| --- | --- | --- | --- |
| `account_id` | path | 是 | `{"title": "Account Id", "type": "string"}` |

| 响应码 | 内容 |
| --- | --- |
| 204 | Successful Response |
| 422 | application/json: HTTPValidationError |
| 401 | 未登录、会话失效或不是管理员。 |

## GET /admin/v1/tasks

机器任务列表

认证：`umeko_admin` Cookie。

读取机器调用记录；结合任务详情排查输入、输出和工具过程。

| 响应码 | 内容 |
| --- | --- |
| 200 | application/json: array<object> |
| 401 | 未登录、会话失效或不是管理员。 |

## POST /admin/v1/tasks/{task_id}/cancel

取消机器任务

认证：`umeko_admin` Cookie。

协作式请求取消；调用后继续查询终态，不能把请求成功等同于子进程已退出。

| 参数 | 位置 | 必填 | 类型与约束 |
| --- | --- | --- | --- |
| `task_id` | path | 是 | `{"title": "Task Id", "type": "string"}` |

| 响应码 | 内容 |
| --- | --- |
| 200 | application/json: object |
| 422 | application/json: HTTPValidationError |
| 401 | 未登录、会话失效或不是管理员。 |

## GET /admin/v1/tasks/{task_id}

机器任务详情

认证：`umeko_admin` Cookie。

返回任务、消息、工具、上下文与事件；仅读取记录，不唤醒执行模型。

| 参数 | 位置 | 必填 | 类型与约束 |
| --- | --- | --- | --- |
| `task_id` | path | 是 | `{"title": "Task Id", "type": "string"}` |

| 响应码 | 内容 |
| --- | --- |
| 200 | application/json: object |
| 422 | application/json: HTTPValidationError |
| 401 | 未登录、会话失效或不是管理员。 |

## GET /admin/v1/tasks/{task_id}/files

任务会话文件树

认证：`umeko_admin` Cookie。

读取名称、目录、大小与时间等元数据；节点清理后可能返回快照，不提供文件内容备份。

| 参数 | 位置 | 必填 | 类型与约束 |
| --- | --- | --- | --- |
| `task_id` | path | 是 | `{"title": "Task Id", "type": "string"}` |

| 响应码 | 内容 |
| --- | --- |
| 200 | application/json: object |
| 422 | application/json: HTTPValidationError |
| 401 | 未登录、会话失效或不是管理员。 |

## GET /admin/v1/users

用户列表

认证：`umeko_admin` Cookie。

列出可管理的用户身份，不返回登录密码。

| 响应码 | 内容 |
| --- | --- |
| 200 | application/json: array<object> |
| 401 | 未登录、会话失效或不是管理员。 |

## POST /admin/v1/users

创建用户

认证：`umeko_admin` Cookie。

创建 user 或 admin 角色账号；用户名必须唯一。

请求体：必填。

`application/json` → `_UserCreate`

| 响应码 | 内容 |
| --- | --- |
| 201 | application/json: object |
| 422 | application/json: HTTPValidationError |
| 401 | 未登录、会话失效或不是管理员。 |

## PUT /admin/v1/users/{user_id}/password

重置用户密码

认证：`umeko_admin` Cookie。

为指定用户设置密码；不把密码放进聊天记录、命令参数或日志。

| 参数 | 位置 | 必填 | 类型与约束 |
| --- | --- | --- | --- |
| `user_id` | path | 是 | `{"title": "User Id", "type": "string"}` |

请求体：必填。

`application/json` → `_PasswordSet`

| 响应码 | 内容 |
| --- | --- |
| 204 | Successful Response |
| 422 | application/json: HTTPValidationError |
| 401 | 未登录、会话失效或不是管理员。 |

## GET /admin/v1/users/{user_id}/model-access

读取用户模型权限

认证：`umeko_admin` Cookie。

返回供应商范围、模型范围和不含 Provider 凭据的可选目录。

| 参数 | 位置 | 必填 | 类型与约束 |
| --- | --- | --- | --- |
| `user_id` | path | 是 | `{"title": "User Id", "type": "string"}` |

| 响应码 | 内容 |
| --- | --- |
| 200 | application/json: object |
| 422 | application/json: HTTPValidationError |
| 401 | 未登录、会话失效或不是管理员。 |

## PUT /admin/v1/users/{user_id}/model-access

设置用户模型权限

认证：`umeko_admin` Cookie。

两个字段均需提交。null 表示跟随全部/默认范围，[] 表示关闭；供应商与模型范围取交集。

| 参数 | 位置 | 必填 | 类型与约束 |
| --- | --- | --- | --- |
| `user_id` | path | 是 | `{"title": "User Id", "type": "string"}` |

请求体：必填。

`application/json` → `_UserModelAccessIn`

| 响应码 | 内容 |
| --- | --- |
| 200 | application/json: object |
| 422 | application/json: HTTPValidationError |
| 401 | 未登录、会话失效或不是管理员。 |

## GET /admin/v1/tools

工具下发目录

认证：`umeko_admin` Cookie。

列出工具、分类与全局开关；不执行工具。

| 响应码 | 内容 |
| --- | --- |
| 200 | application/json: object |
| 401 | 未登录、会话失效或不是管理员。 |

## PUT /admin/v1/tools/{name}

设置工具全局下发

认证：`umeko_admin` Cookie。

以 enabled 显式设置开关；个人授权可独立开放全局关闭的工具。submit_results 不在此开关范围。

| 参数 | 位置 | 必填 | 类型与约束 |
| --- | --- | --- | --- |
| `name` | path | 是 | `{"title": "Name", "type": "string"}` |

请求体：必填。

`application/json` → `_ToolDispatchIn`

| 响应码 | 内容 |
| --- | --- |
| 200 | application/json: object |
| 422 | application/json: HTTPValidationError |
| 401 | 未登录、会话失效或不是管理员。 |

## GET /admin/v1/users/{user_id}/tool-access

读取用户工具权限

认证：`umeko_admin` Cookie。

读取个人授权；null 跟随全局下发，[] 不开放可配置工具。

| 参数 | 位置 | 必填 | 类型与约束 |
| --- | --- | --- | --- |
| `user_id` | path | 是 | `{"title": "User Id", "type": "string"}` |

| 响应码 | 内容 |
| --- | --- |
| 200 | application/json: object |
| 422 | application/json: HTTPValidationError |
| 401 | 未登录、会话失效或不是管理员。 |

## PUT /admin/v1/users/{user_id}/tool-access

设置用户工具权限

认证：`umeko_admin` Cookie。

allowed_tool_names 是完整个人清单，null 跟随全局。保存后下一轮使用新权限。

| 参数 | 位置 | 必填 | 类型与约束 |
| --- | --- | --- | --- |
| `user_id` | path | 是 | `{"title": "User Id", "type": "string"}` |

请求体：必填。

`application/json` → `_UserToolAccessIn`

| 响应码 | 内容 |
| --- | --- |
| 200 | application/json: object |
| 422 | application/json: HTTPValidationError |
| 401 | 未登录、会话失效或不是管理员。 |

## PUT /admin/v1/users/{user_id}/role

修改用户角色

认证：`umeko_admin` Cookie。

设置 user/admin；服务保留至少一个管理员，失去管理员角色的登录会话不能继续管理。

| 参数 | 位置 | 必填 | 类型与约束 |
| --- | --- | --- | --- |
| `user_id` | path | 是 | `{"title": "User Id", "type": "string"}` |

请求体：必填。

`application/json` → `_RoleSet`

| 响应码 | 内容 |
| --- | --- |
| 204 | Successful Response |
| 422 | application/json: HTTPValidationError |
| 401 | 未登录、会话失效或不是管理员。 |

## DELETE /admin/v1/users/{user_id}

删除用户与所属数据

认证：`umeko_admin` Cookie。

永久删除该用户及相关会话数据；不能删除最后一个管理员。

| 参数 | 位置 | 必填 | 类型与约束 |
| --- | --- | --- | --- |
| `user_id` | path | 是 | `{"title": "User Id", "type": "string"}` |

| 响应码 | 内容 |
| --- | --- |
| 204 | Successful Response |
| 422 | application/json: HTTPValidationError |
| 401 | 未登录、会话失效或不是管理员。 |

## GET /admin/v1/users/{user_id}/sessions

用户会话列表

认证：`umeko_admin` Cookie。

读取持久化会话及当前内存状态。

| 参数 | 位置 | 必填 | 类型与约束 |
| --- | --- | --- | --- |
| `user_id` | path | 是 | `{"title": "User Id", "type": "string"}` |

| 响应码 | 内容 |
| --- | --- |
| 200 | application/json: array<object> |
| 422 | application/json: HTTPValidationError |
| 401 | 未登录、会话失效或不是管理员。 |

## GET /admin/v1/sessions/{session_id}

会话内容详情

认证：`umeko_admin` Cookie。

只读返回消息、工具、上下文摘要及挂载信息，不触发模型调用。

| 参数 | 位置 | 必填 | 类型与约束 |
| --- | --- | --- | --- |
| `session_id` | path | 是 | `{"title": "Session Id", "type": "string"}` |

| 响应码 | 内容 |
| --- | --- |
| 200 | application/json: object |
| 422 | application/json: HTTPValidationError |
| 401 | 未登录、会话失效或不是管理员。 |

## DELETE /admin/v1/sessions/{session_id}

删除会话与文件

认证：`umeko_admin` Cookie。

永久删除历史与会话目录；与仅驱逐缓存不同。

| 参数 | 位置 | 必填 | 类型与约束 |
| --- | --- | --- | --- |
| `session_id` | path | 是 | `{"title": "Session Id", "type": "string"}` |

| 响应码 | 内容 |
| --- | --- |
| 204 | Successful Response |
| 422 | application/json: HTTPValidationError |
| 401 | 未登录、会话失效或不是管理员。 |

## POST /admin/v1/sessions/{session_id}/evict

驱逐会话缓存

认证：`umeko_admin` Cookie。

卸载内存态，保留历史；可能影响当前运行，调用前核对目标与活跃状态。

| 参数 | 位置 | 必填 | 类型与约束 |
| --- | --- | --- | --- |
| `session_id` | path | 是 | `{"title": "Session Id", "type": "string"}` |

| 响应码 | 内容 |
| --- | --- |
| 200 | application/json: object |
| 422 | application/json: HTTPValidationError |
| 401 | 未登录、会话失效或不是管理员。 |

## GET /admin/v1/providers

供应商及模型目录

认证：`umeko_admin` Cookie。

管理员可读取完整 Provider api_key，结果须按敏感数据处理，不直接贴入 AI 对话。

| 响应码 | 内容 |
| --- | --- |
| 200 | application/json: object |
| 401 | 未登录、会话失效或不是管理员。 |

## POST /admin/v1/providers

创建模型供应商

认证：`umeko_admin` Cookie。

配置上游地址、密钥和可选代理；base_url 是上游模型地址，与网页前缀无关。

请求体：必填。

`application/json` → `_ProviderIn`

| 响应码 | 内容 |
| --- | --- |
| 201 | application/json: object |
| 422 | application/json: HTTPValidationError |
| 401 | 未登录、会话失效或不是管理员。 |

## PUT /admin/v1/providers/{provider_id}

修改模型供应商

认证：`umeko_admin` Cookie。

只提交变更字段；api_key='********' 表示保留现有密钥。null 字段不更新。

| 参数 | 位置 | 必填 | 类型与约束 |
| --- | --- | --- | --- |
| `provider_id` | path | 是 | `{"title": "Provider Id", "type": "string"}` |

请求体：必填。

`application/json` → `_ProviderPatch`

| 响应码 | 内容 |
| --- | --- |
| 204 | Successful Response |
| 422 | application/json: HTTPValidationError |
| 401 | 未登录、会话失效或不是管理员。 |

## DELETE /admin/v1/providers/{provider_id}

删除模型供应商

认证：`umeko_admin` Cookie。

删除供应商及其模型，先核对当前默认模型和依赖它的智能体。

| 参数 | 位置 | 必填 | 类型与约束 |
| --- | --- | --- | --- |
| `provider_id` | path | 是 | `{"title": "Provider Id", "type": "string"}` |

| 响应码 | 内容 |
| --- | --- |
| 204 | Successful Response |
| 422 | application/json: HTTPValidationError |
| 401 | 未登录、会话失效或不是管理员。 |

## POST /admin/v1/providers/{provider_id}/models

新增模型

认证：`umeko_admin` Cookie。

设置上游模型名称、视觉标记、用户下发及每模型并发；0 表示无限制。

| 参数 | 位置 | 必填 | 类型与约束 |
| --- | --- | --- | --- |
| `provider_id` | path | 是 | `{"title": "Provider Id", "type": "string"}` |

请求体：必填。

`application/json` → `_ModelIn`

| 响应码 | 内容 |
| --- | --- |
| 201 | application/json: object |
| 422 | application/json: HTTPValidationError |
| 401 | 未登录、会话失效或不是管理员。 |

## PUT /admin/v1/models/{model_id}

修改模型能力与并发

认证：`umeko_admin` Cookie。

只提交变更字段。并发按模型 ID 共享，降低上限不打断已开始的调用；user_enabled 控制全局用户下发。

| 参数 | 位置 | 必填 | 类型与约束 |
| --- | --- | --- | --- |
| `model_id` | path | 是 | `{"title": "Model Id", "type": "string"}` |

请求体：必填。

`application/json` → `_ModelPatch`

| 响应码 | 内容 |
| --- | --- |
| 204 | Successful Response |
| 422 | application/json: HTTPValidationError |
| 401 | 未登录、会话失效或不是管理员。 |

## DELETE /admin/v1/models/{model_id}

删除模型

认证：`umeko_admin` Cookie。

删除模型配置；使用此默认模型的智能体需要重新配置。

| 参数 | 位置 | 必填 | 类型与约束 |
| --- | --- | --- | --- |
| `model_id` | path | 是 | `{"title": "Model Id", "type": "string"}` |

| 响应码 | 内容 |
| --- | --- |
| 204 | Successful Response |
| 422 | application/json: HTTPValidationError |
| 401 | 未登录、会话失效或不是管理员。 |

## PUT /admin/v1/active-model

设置平台默认主模型

认证：`umeko_admin` Cookie。

设置后重载配置并驱逐在线会话缓存，可能影响活跃任务。

请求体：必填。

`application/json` → `_ActiveModelIn`

| 响应码 | 内容 |
| --- | --- |
| 200 | application/json: object |
| 422 | application/json: HTTPValidationError |
| 401 | 未登录、会话失效或不是管理员。 |

## POST /admin/v1/providers/import

批量导入供应商与模型

认证：`umeko_admin` Cookie。

document 包装导入内容；指定 active 时激活并重载。不是简单追加，不应盲目重试。

请求体：必填。

`application/json` → `_ImportIn`

| 响应码 | 内容 |
| --- | --- |
| 200 | application/json: object |
| 422 | application/json: HTTPValidationError |
| 401 | 未登录、会话失效或不是管理员。 |

## GET /admin/v1/default-skills

技能下发列表

认证：`umeko_admin` Cookie。

读取数据库下发状态与管理员库的 imported/enabled/stale 信息。

| 响应码 | 内容 |
| --- | --- |
| 200 | application/json: object |
| 401 | 未登录、会话失效或不是管理员。 |

## POST /admin/v1/default-skills/{name}/toggle

切换技能下发开关

认证：`umeko_admin` Cookie。

每次调用都会反转状态，不是幂等设置。先 GET 当前状态，仅在目标不同的时候调用一次，再回读。

| 参数 | 位置 | 必填 | 类型与约束 |
| --- | --- | --- | --- |
| `name` | path | 是 | `{"title": "Name", "type": "string"}` |

| 响应码 | 内容 |
| --- | --- |
| 200 | application/json: object |
| 422 | application/json: HTTPValidationError |
| 401 | 未登录、会话失效或不是管理员。 |

## POST /admin/v1/default-skills/import/{name}

从技能库导入下发入口

认证：`umeko_admin` Cookie。

name 为包名.md，读取管理员库 SKILL.md 并写入默认下发配置，新会话生效。

| 参数 | 位置 | 必填 | 类型与约束 |
| --- | --- | --- | --- |
| `name` | path | 是 | `{"title": "Name", "type": "string"}` |

| 响应码 | 内容 |
| --- | --- |
| 201 | application/json: object |
| 422 | application/json: HTTPValidationError |
| 401 | 未登录、会话失效或不是管理员。 |

## GET /admin/v1/default-skills/{name}

读取已下发技能入口

认证：`umeko_admin` Cookie。

读取数据库中的技能主指引，可能与管理员库源文件不同。

| 参数 | 位置 | 必填 | 类型与约束 |
| --- | --- | --- | --- |
| `name` | path | 是 | `{"title": "Name", "type": "string"}` |

| 响应码 | 内容 |
| --- | --- |
| 200 | application/json: object |
| 422 | application/json: HTTPValidationError |
| 401 | 未登录、会话失效或不是管理员。 |

## PUT /admin/v1/default-skills/{name}

保存技能下发入口

认证：`umeko_admin` Cookie。

以 content 保存合法 SKILL.md 文本；不自动审批脚本或改写旧会话副本。

| 参数 | 位置 | 必填 | 类型与约束 |
| --- | --- | --- | --- |
| `name` | path | 是 | `{"title": "Name", "type": "string"}` |

请求体：必填。

`application/json` → `_DefaultSkillIn`

| 响应码 | 内容 |
| --- | --- |
| 201 | application/json: object |
| 422 | application/json: HTTPValidationError |
| 401 | 未登录、会话失效或不是管理员。 |

## DELETE /admin/v1/default-skills/{name}

删除技能下发入口

认证：`umeko_admin` Cookie。

移除默认下发记录，不自动删除管理员库源文件和旧会话副本。

| 参数 | 位置 | 必填 | 类型与约束 |
| --- | --- | --- | --- |
| `name` | path | 是 | `{"title": "Name", "type": "string"}` |

| 响应码 | 内容 |
| --- | --- |
| 204 | Successful Response |
| 422 | application/json: HTTPValidationError |
| 401 | 未登录、会话失效或不是管理员。 |

## GET /admin/v1/skill-scripts/{pack}

列出技能代码

认证：`umeko_admin` Cookie。

列出包内 Python 文件和大小；辅助模块不一定是可执行入口。

| 参数 | 位置 | 必填 | 类型与约束 |
| --- | --- | --- | --- |
| `pack` | path | 是 | `{"title": "Pack", "type": "string"}` |

| 响应码 | 内容 |
| --- | --- |
| 200 | application/json: object |
| 422 | application/json: HTTPValidationError |
| 401 | 未登录、会话失效或不是管理员。 |

## GET /admin/v1/skill-scripts/{pack}/{script_name}

读取技能脚本或成员文本

认证：`umeko_admin` Cookie。

读取管理员库中的脚本或附属文本，包括 references 与 config.json；不是读取普通用户会话副本。

| 参数 | 位置 | 必填 | 类型与约束 |
| --- | --- | --- | --- |
| `pack` | path | 是 | `{"title": "Pack", "type": "string"}` |
| `script_name` | path | 是 | `{"title": "Script Name", "type": "string"}` |

| 响应码 | 内容 |
| --- | --- |
| 200 | application/json: object |
| 422 | application/json: HTTPValidationError |
| 401 | 未登录、会话失效或不是管理员。 |

## PUT /admin/v1/skill-scripts/{pack}/{script_name}

保存技能代码

认证：`umeko_admin` Cookie。

content 必须为合法 Python；写入管理员库，仅保存不会赋予信任。目录路径相对当前包。

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
| 401 | 未登录、会话失效或不是管理员。 |

## DELETE /admin/v1/skill-scripts/{pack}/{script_name}

删除技能代码

认证：`umeko_admin` Cookie。

删除选定管理员库文件，不隐式删除信任审计和旧会话副本。

| 参数 | 位置 | 必填 | 类型与约束 |
| --- | --- | --- | --- |
| `pack` | path | 是 | `{"title": "Pack", "type": "string"}` |
| `script_name` | path | 是 | `{"title": "Script Name", "type": "string"}` |

| 响应码 | 内容 |
| --- | --- |
| 204 | Successful Response |
| 422 | application/json: HTTPValidationError |
| 401 | 未登录、会话失效或不是管理员。 |

## PUT /admin/v1/skill-members/{pack}/{member_name}

保存技能附属文本

认证：`umeko_admin` Cookie。

保存 Markdown、JSON、YAML、TXT、CSV 等成员；Python 使用 skill-scripts。config.json 修改后需要审核新摘要。

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
| 401 | 未登录、会话失效或不是管理员。 |

## DELETE /admin/v1/skill-members/{pack}/{member_name}

删除技能附属文件

认证：`umeko_admin` Cookie。

删除指定包内成员；Python 文件需用 skill-scripts 入口。

| 参数 | 位置 | 必填 | 类型与约束 |
| --- | --- | --- | --- |
| `pack` | path | 是 | `{"title": "Pack", "type": "string"}` |
| `member_name` | path | 是 | `{"title": "Member Name", "type": "string"}` |

| 响应码 | 内容 |
| --- | --- |
| 204 | Successful Response |
| 422 | application/json: HTTPValidationError |
| 401 | 未登录、会话失效或不是管理员。 |

## GET /admin/v1/runtime-config

读取工具回合上限

认证：`umeko_admin` Cookie。

返回持久化覆盖值；max_tool_iterations=null 表示没有覆盖。

| 响应码 | 内容 |
| --- | --- |
| 200 | application/json: object |
| 401 | 未登录、会话失效或不是管理员。 |

## PUT /admin/v1/runtime-config

设置工具回合上限

认证：`umeko_admin` Cookie。

0 为无限，null 清除覆盖，正整数为上限；修改会重载配置并驱逐在线会话缓存。

请求体：必填。

`application/json` → `_RuntimeConfigIn`

| 响应码 | 内容 |
| --- | --- |
| 200 | application/json: object |
| 422 | application/json: HTTPValidationError |
| 401 | 未登录、会话失效或不是管理员。 |

## GET /admin/v1/skill-source/{name}

读取技能库主指引

认证：`umeko_admin` Cookie。

name 为包名.md，映射到管理员库包目录的 SKILL.md。

| 参数 | 位置 | 必填 | 类型与约束 |
| --- | --- | --- | --- |
| `name` | path | 是 | `{"title": "Name", "type": "string"}` |

| 响应码 | 内容 |
| --- | --- |
| 200 | application/json: object |
| 422 | application/json: HTTPValidationError |
| 401 | 未登录、会话失效或不是管理员。 |

## PUT /admin/v1/skill-source/{name}

保存技能库主指引

认证：`umeko_admin` Cookie。

content 需包含合法技能 frontmatter；保存管理员库入口，与 default-skills 下发记录分开。

| 参数 | 位置 | 必填 | 类型与约束 |
| --- | --- | --- | --- |
| `name` | path | 是 | `{"title": "Name", "type": "string"}` |

请求体：必填。

`application/json` → `_DefaultSkillIn`

| 响应码 | 内容 |
| --- | --- |
| 201 | application/json: object |
| 422 | application/json: HTTPValidationError |
| 401 | 未登录、会话失效或不是管理员。 |

## DELETE /admin/v1/skill-source/{name}

删除技能库主指引

认证：`umeko_admin` Cookie。

只删除主入口；配套成员和下发记录需要按用户要求分别处理。

| 参数 | 位置 | 必填 | 类型与约束 |
| --- | --- | --- | --- |
| `name` | path | 是 | `{"title": "Name", "type": "string"}` |

| 响应码 | 内容 |
| --- | --- |
| 204 | Successful Response |
| 422 | application/json: HTTPValidationError |
| 401 | 未登录、会话失效或不是管理员。 |

## GET /admin/v1/skill-library

管理员技能文件树

认证：`umeko_admin` Cookie。

列出包、脚本、成员及下发状态；包含孤立成员目录，字段中的名称不是服务器任意绝对路径。

| 响应码 | 内容 |
| --- | --- |
| 200 | application/json: object |
| 401 | 未登录、会话失效或不是管理员。 |

## GET /admin/v1/skill-scripts-template

读取脚本模板

认证：`umeko_admin` Cookie。

返回当前确定性脚本的输入输出契约模板，不创建或执行脚本。

| 响应码 | 内容 |
| --- | --- |
| 200 | application/json: object |
| 401 | 未登录、会话失效或不是管理员。 |

## GET /admin/v1/skill-security/catalog

查询可信代码目录

认证：`umeko_admin` Cookie。

搜索、筛选、分页查看当前版本和信任状态；不扫描或重新下发旧会话。

| 参数 | 位置 | 必填 | 类型与约束 |
| --- | --- | --- | --- |
| `q` | query | 否 | `{"default": "", "maxLength": 200, "title": "Q", "type": "string"}` |
| `pack` | query | 否 | `{"default": "", "maxLength": 120, "title": "Pack", "type": "string"}` |
| `status` | query | 否 | `{"default": "", "enum": ["", "trusted", "unlisted", "changed", "revoked", "missing", "invalid"], "title": "Status", "type": "string"}` |
| `kind` | query | 否 | `{"default": "", "enum": ["", "python", "config"], "title": "Kind", "type": "string"}` |
| `offset` | query | 否 | `{"default": 0, "minimum": 0, "title": "Offset", "type": "integer"}` |
| `limit` | query | 否 | `{"default": 50, "maximum": 200, "minimum": 1, "title": "Limit", "type": "integer"}` |

| 响应码 | 内容 |
| --- | --- |
| 200 | application/json: object |
| 422 | application/json: HTTPValidationError |
| 401 | 未登录、会话失效或不是管理员。 |

## GET /admin/v1/skill-security/selection

取得跨页选择快照

认证：`umeko_admin` Cookie。

返回所有筛选结果的明确文件版本，仅用于构建后续逐文件操作清单，不自动批准。

| 参数 | 位置 | 必填 | 类型与约束 |
| --- | --- | --- | --- |
| `q` | query | 否 | `{"default": "", "maxLength": 200, "title": "Q", "type": "string"}` |
| `pack` | query | 否 | `{"default": "", "maxLength": 120, "title": "Pack", "type": "string"}` |
| `status` | query | 否 | `{"default": "", "enum": ["", "trusted", "unlisted", "changed", "revoked", "missing", "invalid"], "title": "Status", "type": "string"}` |
| `kind` | query | 否 | `{"default": "", "enum": ["", "python", "config"], "title": "Kind", "type": "string"}` |

| 响应码 | 内容 |
| --- | --- |
| 200 | application/json: object |
| 422 | application/json: HTTPValidationError |
| 401 | 未登录、会话失效或不是管理员。 |

## POST /admin/v1/skill-security/batch

批量批准或撤销可信版本

认证：`umeko_admin` Cookie。

每批 1–200 项，各项核对 SHA-256；部分失败不回滚其他成功项，必须逐项检查 results。

请求体：必填。

`application/json` → `_SkillTrustBatchIn`

| 响应码 | 内容 |
| --- | --- |
| 200 | application/json: object |
| 422 | application/json: HTTPValidationError |
| 401 | 未登录、会话失效或不是管理员。 |

## GET /admin/v1/skill-security/{pack}/{member}

读取单文件安全门禁

认证：`umeko_admin` Cookie。

查看当前双摘要、批准与撤销记录；批准 current.sha256，撤销 approved.sha256。

| 参数 | 位置 | 必填 | 类型与约束 |
| --- | --- | --- | --- |
| `pack` | path | 是 | `{"title": "Pack", "type": "string"}` |
| `member` | path | 是 | `{"title": "Member", "type": "string"}` |

| 响应码 | 内容 |
| --- | --- |
| 200 | application/json: object |
| 422 | application/json: HTTPValidationError |
| 401 | 未登录、会话失效或不是管理员。 |

## POST /admin/v1/skill-security/{pack}/{member}

批准当前文件版本

认证：`umeko_admin` Cookie。

提交预览 current.sha256；源字节已变返回 409。仅批准选定管理员库文件，不执行、不重签旧会话。

| 参数 | 位置 | 必填 | 类型与约束 |
| --- | --- | --- | --- |
| `pack` | path | 是 | `{"title": "Pack", "type": "string"}` |
| `member` | path | 是 | `{"title": "Member", "type": "string"}` |

请求体：必填。

`application/json` → `_SkillApprovalIn`

| 响应码 | 内容 |
| --- | --- |
| 200 | application/json: object |
| 422 | application/json: HTTPValidationError |
| 401 | 未登录、会话失效或不是管理员。 |

## DELETE /admin/v1/skill-security/{pack}/{member}

撤销文件可信版本

认证：`umeko_admin` Cookie。

提交 approved.sha256，事务内撤销并审计；拦截旧授权后续执行，不中断已启动脚本。

| 参数 | 位置 | 必填 | 类型与约束 |
| --- | --- | --- | --- |
| `pack` | path | 是 | `{"title": "Pack", "type": "string"}` |
| `member` | path | 是 | `{"title": "Member", "type": "string"}` |

请求体：必填。

`application/json` → `_SkillApprovalIn`

| 响应码 | 内容 |
| --- | --- |
| 200 | application/json: object |
| 422 | application/json: HTTPValidationError |
| 401 | 未登录、会话失效或不是管理员。 |

## POST /admin/v1/skill-scripts/{pack}/{script_name}/test

测试已批准的技能脚本

认证：`umeko_admin` Cookie。

args 为 JSON 对象字符串，timeout 限制在 1–30 秒；整包受保护代码/配置必须获准。临时工作目录不是安全沙箱。

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
| 401 | 未登录、会话失效或不是管理员。 |

## GET /admin/v1/openapi.json

管理接口规范

认证：`umeko_admin` Cookie。

读取当前运行版本的完整 OpenAPI，包括参数、请求模型、认证与操作影响；需要管理员登录。

| 响应码 | 内容 |
| --- | --- |
| 200 | application/json: object |
| 401 | 未登录、会话失效或不是管理员。 |
