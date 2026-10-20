# 管理接口行为

本文件按任务说明调用方式。精确路径、全部请求模型、约束与响应码以管理服务的 `/admin/v1/openapi.json` 为准。默认管理端口 9000；带多级管理前缀时，基址包含前缀，下面的内部路由不重复加前缀。此处没有上游模型 Key 或默认登录密码。

## 登录与发现

`POST /admin/login`，JSON 为 `{username,password}`；保存返回的 `umeko_admin` Cookie。`GET /admin/v1/me` 验证管理员。`GET /admin/v1/openapi.json` 读取当前版本规范。最后 `POST /admin/logout` 撤销会话。

用户 Cookie、服务账号 Token、MCP/A2A OAuth Token 均不能用于管理。公开的 `/admin/automation` 与 `/admin/automation/skill/...` 仅提供 Skill 说明和调用脚本，不开放配置或用户数据。服务没有新增管理端口。

## 功能与入口

| 管理任务 | 主要入口 |
| --- | --- |
| Provider、模型与默认主模型 | `/admin/v1/providers`、`/models/{model_id}`、`/active-model`、`/providers/import` |
| 工具调用回合上限 | `/admin/v1/runtime-config` |
| 智能体配置、Card、MCP 披露 | `/admin/v1/agents`、`/agents/{agent_id}`、`/agents/{agent_id}/card`、`/agents/{agent_id}/mcp` |
| 机器接入与服务凭据 | `/admin/v1/service-access`、`/service-accounts`、`/service-accounts/{account_id}` |
| 用户、密码、角色 | `/admin/v1/users`、`/users/{user_id}/password`、`/users/{user_id}/role` |
| 用户模型和工具权限 | `/admin/v1/users/{user_id}/model-access`、`/users/{user_id}/tool-access` |
| 全局工具下发 | `/admin/v1/tools`、`/tools/{name}` |
| 用户会话与内容 | `/admin/v1/users/{user_id}/sessions`、`/sessions/{session_id}`、`/sessions/{session_id}/evict` |
| 资源、机器任务与文件树 | `/admin/v1/resources`、`/tasks`、`/tasks/{task_id}`、`/tasks/{task_id}/files`、`/tasks/{task_id}/cancel` |
| 技能库与下发 | `/admin/v1/skill-library`、`/skill-source/{name}`、`/default-skills` |
| 代码、成员文件与测试 | `/admin/v1/skill-scripts/{pack}`、`/skill-scripts/{pack}/{script_name}`、`/skill-members/{pack}/{member_name}` |
| 可信代码管理 | `/admin/v1/skill-security/catalog`、`/admin/v1/skill-security/selection`、`/admin/v1/skill-security/batch`、`/admin/v1/skill-security/{pack}/{member}` |

表中同一格省略前缀的路径均从 `/admin/v1` 开始。不要由此猜测 HTTP 方法或遗漏路径参数，执行前查 OpenAPI。

## 模型与供应商

先 GET providers，用 ID 定位供应商和具体模型。返回中含完整 `api_key`，调用助手脚本默认遮蔽它。PUT provider 只发需要改的字段；保留密钥可省略 `api_key` 或使用服务支持的掩码 `********`，不要提交自己的脱敏标记替换真实密钥。

每模型并发示例：`PUT /admin/v1/models/{id}`，`{"max_concurrent_requests":2}`；0 是不限制，不是关闭模型。相同模型 ID 的主/子/视觉调用共用额度。降低上限不终止已开始调用。

新增模型是 `POST /admin/v1/providers/{provider_id}/models`，字段为 name、vision、max_concurrent_requests、user_enabled。不要混淆模型注册表 ID 与上游 name。设置平台默认主模型用 `PUT /admin/v1/active-model`，`{"model_id":"<已读取的ID>"}`。

`PUT runtime-config` 的 `max_tool_iterations=0` 是无限；null 是清除覆盖。修改回合上限或激活平台默认模型会重载并驱逐在线会话缓存。监听地址、路径前缀、CA 等启动项不在此接口中。

## 智能体与服务账号

GET agents 会返回模型/技能选项与完整智能体列表。智能体 PUT 是完整表单：先 GET 单个记录，保留介绍、工作指引、版本、默认主/视觉模型和技能列表，仅改目标字段；请求只包含 schema 允许的字段，不回传 id、endpoints、时间等只读字段。已有 slug 不能改名。模型披露是遗留兼容字段，对外任务不支持调用方切换模型。

服务凭据只用于机器任务。创建或轮换时的 token 只返回一次；用受限本地文件保留，之后列表无法取回。PATCH `rotate:true` 不是幂等操作。停用不取消已接受的任务；删除会永久清理该账号及历史，有活跃任务时 409。匿名机器接入共享身份与额度，不按 IP 隔离；管理接口仍需要管理员。

## 权限与删除

模型权限 PUT 必须同时包含 `allowed_provider_ids`、`allowed_model_ids`。供应商 null 为全部，模型 null 为跟随默认下发；任一空数组关闭相应范围。明确的模型清单可以包含未全局下发的模型，但始终与供应商范围取交集。

工具权限的 `allowed_tool_names=null` 跟随全局，[] 关闭可配置工具，数组为完整个人授权。可单独授权全局未下发工具。`submit_results` 是机器协议必需能力，不在开关中。

用户角色只有 user/admin，不能移除最后一个管理员。删除用户、会话、服务账号是数据清理；驱逐 session 缓存保留历史，取消任务是协作式停止。操作前核对用户明确授权的目标、依赖与范围，执行后回读状态。

## 技能文件、下发与门禁

逻辑入口名为 `pack-name.md`，实际位于管理员库 `pack-name/SKILL.md`：

1. PUT `/admin/v1/skill-source/pack-name.md`，`{"content":"<合法SKILL.md全文>"}`，保存管理员库。
2. 需要下发时，PUT `/admin/v1/default-skills/pack-name.md` 同步正文，或 POST `/admin/v1/default-skills/import/pack-name.md` 从库导入。先 GET default-skills 核对 imported、enabled、stale。
3. `/default-skills/{name}/toggle` 每次调用反转开关。先比较当前与目标状态，不需要变化就不调用；断连后先 GET 再决定是否补做。
4. Python 用 `/skill-scripts/{pack}/{script_name}` 保存，其他文本成员用 `/skill-members/{pack}/{member_name}` 保存，JSON 都是 `{content}`。成员路径相对当前包，例如 `scripts/run.py`、`references/checks.md`、`assets/config.json`，不传服务器绝对路径。
5. 代码/config 保存、下发、信任批准是独立动作。不要假定保存或启用已自动授权执行，也不要仅因当前任务想运行脚本就跳过审核。

单文件门禁 GET 返回 current、approved、trusted、status。审核当前文件后，POST `{sha256:current.sha256}` 批准；DELETE `{sha256:approved.sha256}` 撤销。批量 POST `/skill-security/batch` 为 `{action:"approve或revoke",items:[{pack,member,sha256}]}`，1–200 项，逐项检查结果。跨页全选先通过 selection 固定明确文件与摘要，不能在执行时自动换用新版本。

409 表示版本变化，必须重新读取并核对变更。不能删除 `skill_trust`、清空摘要、重签用户副本或关闭校验。旧会话不自动更新；撤销后再批准也不复活旧授权。Python 测试接口的请求为 `{"args":"{}","timeout":10}`，args 是 JSON 字符串，测试需整包受保护文件获准，且不构成沙箱。

## 回读与错误

204 无响应体，客户端应当作成功；HTTP 200 也可能包含批量逐项失败或脚本业务错误。任务 completed 不代表业务检查通过，必须读结果和限制。

401 重新检查管理员登录；400/422 按具体字段修正；404 检查基址、前缀、ID 与是否已删除；409 先读取冲突状态。所有变更都不自动网络重试：请求超时后先回读，尤其避免重复创建、开关反转、凭据轮换、导入或执行脚本。
