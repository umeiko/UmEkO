# 管理 API

管理接口默认在 **9000** 端口。先 `POST /admin/login`，保存 `umeko_admin` Cookie。用户端口的登录不能代替管理端口登录。

资源监控、机器任务和服务凭据见[监控指南](monitoring.md)。创建服务账号使用 `POST /admin/v1/service-accounts`，JSON 为 `name`、可选 `scopes`（默认四项任务权限）、`expires_days`（默认 90，1–3650）。响应仅这一次包含 `token`；列表不返回已有凭据。

`PATCH /admin/v1/service-accounts/{id}` 可传 `enabled` 启用 / 停用，或 `rotate:true` 与可选 `expires_days` 更换凭据。更换和停用会撤销旧访问令牌；停用不取消已接收任务，需在资源监控中显式停止。

在“服务接入”的账号列表点击“删除”，确认后永久清理该服务账号、凭据、访问令牌，以及该账号的任务、事件、产物、会话和文件。删除接口为 `DELETE /admin/v1/service-accounts/{id}`，成功返回 `204`，不存在返回 `404`。仍有排队、执行或正在结束的任务时返回 `409`，请先在资源监控中停止并等待完成。删除只影响所选账号；免鉴权身份和其他账号的数据继续保留，名称可以重新用于创建新账号。

服务接入页面与智能体配置的说明集中在圆圈问号中，悬停、键盘聚焦或点击即可查看；按 Escape 或点击其他位置关闭。创建、保存和删除的操作反馈直接显示在页面中。

```json
{"username":"your-admin-name","password":"your-admin-password"}
```

示例使用占位符，调用时替换为已配置的管理员凭据。已有数据库以当前账号密码为准。登录成功返回 `{id, username}`，Cookie 的 Max-Age 为 7 天，服务同时校验数据库 Token。`GET /admin/v1/me` 查询管理员；`POST /admin/logout` 返回 `204`。

以下所有 `/admin/v1/...` 都要求管理员角色。完整输入模型与路由见[管理完整参考](reference-admin.md)。

## 会话查看

在用户列表点击“查看会话”，再点击会话标题或“查看内容”，可只读查看该用户的聊天消息、附件名称、工具调用参数与结果，以及保存的上下文摘要和技能挂载。“返回用户列表”回到用户管理；关闭详情则留在当前用户的会话列表。

`GET /admin/v1/sessions/{session_id}` 返回 `kind: "session"`、`record`（会话和用户名等信息）、`messages`、`tools` 与 `context`。消息的 `in_context` 标记区分当前上下文保留的消息和清空或压缩以前的历史。详情读取数据库，不唤醒已经卸载的会话。不存在返回 `404`，未登录或普通用户 Cookie 返回 `401`；用户端口不提供此接口。

任务和会话详情都使用管理前缀 `UMEKO_ADMIN_BASE_PATH`，与用户协议前缀独立。消息默认安全渲染 Markdown，可切换原文；工具参数与返回以保留换行的文本或格式化 JSON 显示。机器任务详情见[监控指南](monitoring.md)。

## Provider / Model 与并发

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| GET / POST | `/admin/v1/providers` | 列出 / 新增 Provider |
| PUT / DELETE | `/admin/v1/providers/{provider_id}` | 修改 / 删除 Provider |
| POST | `/admin/v1/providers/{provider_id}/models` | 新增模型 |
| PUT / DELETE | `/admin/v1/models/{model_id}` | 修改 / 删除模型 |
| PUT | `/admin/v1/active-model` | 激活主模型，重载并驱逐在线会话缓存 |
| POST | `/admin/v1/providers/import` | JSON 批量导入 |

Provider 创建参数：

```json
{"name":"Company","base_url":"https://models.example.com/v1","api_key":"YOUR_MODEL_KEY","proxy":null}
```

模型创建参数：

```json
{"name":"document-model","vision":false,"max_concurrent_requests":2,"user_enabled":true}
```

模型并发上限设置在**每个模型**上，默认 `0` 为无限制，正整数为同时请求数。`PUT /admin/v1/models/{model_id}` 可只传：

```json
{"max_concurrent_requests":2}
```

成功返回 `204`，当前进程内立即更新额度。等待请求按 FIFO 排队；流式请求直到流关闭才释放额度。降低额度不会中断已开始的请求，增大或改成 `0` 会放行等待请求。相同模型 ID 被主 / 子 / 视觉模型或不同用户使用时共享额度。

“模型与供应商”中每个模型的“下发给用户”勾选对应 `user_enabled`，控制默认向用户开放的模型。默认启用，旧数据库升级保留原有开放状态。取消后，跟随默认范围的用户不能发现或选择该模型；管理员仍可在某个用户的“用户设置”中单独授权，例如向 VIP 提供未全局下发的模型。下一轮运行会重新校验已有的主、子、视觉模型偏好及会话覆盖，不中断已经开始的运行。服务凭据和免鉴权机器身份调用的固定 Agent 按管理员为该 Agent 配置的模型执行；网页登录身份提交的请求遵守该用户的开放范围。

`PUT /admin/v1/models/{model_id}` 可单独传 `{"user_enabled":false}`；创建和 JSON 导入同样支持这个布尔字段。导入省略该字段时保留已有模型的下发状态。

这控制同时进行的上游请求，不控制每分钟请求数或 token 数；独立进程不共享额度。业务线程池的任务排队也不等于有界、持久化的业务队列。

导入 HTTP 请求必须有 **`document` 外层**：

```json
{
  "document": {
    "providers": [{
      "name":"Company","base_url":"https://models.example.com/v1","api_key":"YOUR_MODEL_KEY",
      "models":[{"name":"document-model","vision":false,"max_concurrent_requests":2}]
    }],
    "active":"Company/document-model"
  }
}
```

CLI 的导入文件只包含内层文档。导入按 Provider / 模型名称合并，省略已有模型的并发字段时保留原额度。带 `active` 时会激活并重载。

管理列表包含 `api_key` 完整值，不能按普通用户模型列表处理。Provider 修改时原样提交 `********` 表示保留旧 Key；其他可选字段的 `null` 会被忽略，需要按实际接口语义更新。

## 用户与会话

“Tools 管理”提供平台内置工具的逐项下发开关，包含文件、技能脚本、图像推理、委派及命令工具。
在用户列表点击“工具权限”，可让该用户跟随全局下发，或保存自己的工具清单；清单可包含
未全局下发的工具。权限作用于普通会话、主 Agent、子 Agent 和机器任务的临时工作台；
服务账号和免鉴权机器身份跟随全局下发。模型视觉能力、命令执行器配置及原有文件边界仍需满足。

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| GET | `/admin/v1/tools` | 工具目录、全局 `enabled`、`required`、下载上限 |
| PUT | `/admin/v1/tools/{name}` | `{"enabled":false}` 修改全局下发 |
| GET | `/admin/v1/users/{user_id}/tool-access` | 工具目录及该用户的 `allowed_tool_names` |
| PUT | `/admin/v1/users/{user_id}/tool-access` | `{"allowed_tool_names":null}` 跟随全局；`[]` 关闭可配置工具；名称数组单独授权 |

已移除工作文档专用工具。读取权限时，`allowed_tool_names` 只含当前有效工具，`retired_tool_names` 列出旧记录中待清理的专用工具授权；旧授权不自动转换成范围更大的文件权限。保存有效工具选择后清理旧名；提交已移除的工具名会被拒绝。历史调用记录和笔记文件继续保留。

工具管理页按文件操作、图像理解、技能与脚本、任务编排和协议能力分类，默认收起，可逐组或全部展开。搜索支持中英文名称、工具标识和分类，自动展开匹配结果；清除筛选后恢复之前的展开状态。分类标题显示工具数量和当前已下发数量。

保存后下一轮重新装配工具列表，已有会话与恢复会话也适用；执行前再次检查权限，撤销后不能凭
旧工具名调用，也不能通过委派绕过。权限保存于服务数据库，不修改源码。
`submit_results` 是机器任务协议必需工具，不提供停用开关，不接受用户自选授权；它只在机器任务
和对应临时工作台中注入，普通会话和子 Agent 均不暴露。

`download_url` 从网址下载文件到当前工作区，最大 20 MB，使用方式见[文件与技能](files-skills.md#url-download)。

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| GET / POST | `/admin/v1/users` | 用户列表 / 创建 `{username,password,role}` |
| PUT | `/admin/v1/users/{user_id}/password` | `{password}` 重置密码 |
| PUT | `/admin/v1/users/{user_id}/role` | `{role}` 修改角色 |
| GET / PUT | `/admin/v1/users/{user_id}/model-access` | 查看 / 设置用户的供应商与模型开放范围 |
| DELETE | `/admin/v1/users/{user_id}` | 删除用户和所属数据 |
| GET | `/admin/v1/users/{user_id}/sessions` | 用户会话列表 |
| DELETE | `/admin/v1/sessions/{session_id}` | 删除会话和文件 |
| POST | `/admin/v1/sessions/{session_id}/evict` | 驱逐内存缓存，不是删除历史 |

角色为 `user` / `admin`；服务保留至少一个管理员。驱逐和配置重载可能取消该缓存中的活跃任务，调用前需理解对在线用户的影响。

用户列表的“用户设置”按供应商和模型勾选开放范围。GET 返回 `allowed_provider_ids`、`allowed_model_ids` 和不含供应商凭据的模型目录。PUT 需提交两个字段：

```json
{"allowed_provider_ids":["provider_example"],"allowed_model_ids":["model_example"]}
```

`allowed_provider_ids=null` 表示开放全部供应商（含以后新增）；指定数组只开放这些供应商，空数组关闭全部。`allowed_model_ids=null` 表示跟随全局下发模型（含以后新增并下发的模型）；指定数组是管理员为该用户明确授权的完整模型清单，可包含 `user_enabled=false` 的模型；空数组关闭全部模型。**个人模型授权始终与该用户的供应商范围取交集**，单独授权不会更改模型的全局下发开关，也不向其他用户开放该模型。已有用户默认两个字段均为 `null`。在后台勾选一个未全局下发模型时，会保留当前默认下发模型，并添加这项个人授权；取消“全部下发模型”勾选或普通模型选择不会自动授予其他未下发模型。

新设置下一轮运行生效；已失去权限的选择回退到范围内的默认模型或第一个可用模型，无模型时拒绝新调用，仍可浏览已有会话。用户偏好和会话覆盖接口拒绝未开放的模型 ID（`403`）。管理员身份在用户工作台使用模型时也遵守自己的开放范围。

## 默认技能与服务器技能库

| 路径（均在 `/admin/v1` 下） | 方法与行为 |
| --- | --- |
| `/default-skills` | GET 列出数据库默认技能与库文件信息 |
| `/default-skills/{name}` | GET 内容；PUT `{content}`；DELETE |
| `/default-skills/{name}/toggle` | POST 切换默认启用 |
| `/default-skills/import/{name}` | POST 从服务器技能库导入 |
| `/skill-library` | GET 列出服务器技能包 |
| `/skill-source/{name}` | GET / PUT `{content}` / DELETE 提示词源文件 |
| `/skill-scripts/{pack}` | GET 脚本列表 |
| `/skill-scripts/{pack}/{script_name}` | GET / PUT `{content}` / DELETE Python 脚本 |
| `/skill-members/{pack}/{member_name}` | PUT `{content}` / DELETE 包内非脚本资源 |
| `/skill-scripts-template` | GET 脚本模板 |
| `/skill-scripts/{pack}/{script_name}/test` | POST 测试脚本 |
| `/skill-security/{pack}/{member}` | GET 查看可信源摘要、分页会话门禁状态及最近管理员操作；POST 重算并同步白名单 |

默认技能启停主要影响新会话，不自动撤销已经分发到现有会话的副本。服务器技能库写入应用目录的 `skills/`，备份时需单独包含。

技能内容 PUT 的 JSON 为 `{"content":"..."}`，创建 / 更新通常返回 `201`，删除为 `204`；完整模型以参考为准。Python 脚本保存检查语法。测试请求为 `{"args":"{}","timeout":10}`，`args` 是 JSON **字符串**；超时限制在 1–30 秒，使用临时工作目录并返回 `{output: ...}`。这是受信任脚本的执行测试，不是容器级隔离。

安全门禁仅支持包内 `scripts/` 下的 `.py` 与 `config.json`，使用独立管理前缀。GET 支持 `offset` 和 `limit`（默认 30，最多 100），返回 `current` 双摘要、`sessions` 文件状态、全量 `counts`、`total` 及最近 `events`。POST JSON 为 `{"sha256":"GET 返回的 current.sha256","redispatch":false}`；摘要必须是 64 位十六进制，源文件变化返回 `409`，额外字段或非布尔 `redispatch` 返回 `422`。不接受客户端传入文件内容、批准摘要或操作人。

默认只同步与可信源一致的旧副本；`redispatch: true` 用管理员源文件替换此文件后更新批准记录。范围是已有该包批准记录的全部会话，运行/排队会话跳过，坏记录及链接不自动修复。返回 `updated`、`unchanged`、`skipped_mismatch`、`skipped_busy`、`skipped_invalid`、`failed` 和审计 `event_id`，可再次 GET 核对。操作不执行脚本，也不放宽其他文件校验。维护流程见[重算与重新下发](../deployment.md#skill-admin-reapproval)。

## 工具回合上限

`GET /admin/v1/runtime-config` / `PUT /admin/v1/runtime-config` 管理主 Agent 工具回合数：

```json
{"max_tool_iterations":0}
```

`0` 为无限，`null` 清空覆盖回到默认，正整数为上限。这与模型并发字段不同；修改会重载并驱逐在线会话缓存。
