# 管理 API

管理接口默认在 **9000** 端口。先 `POST /admin/login`，保存 `umeko_admin` Cookie。用户端口的登录不能代替管理端口登录。

```json
{"username":"your-admin-name","password":"your-admin-password"}
```

示例使用占位符，调用时替换为已配置的管理员凭据。已有数据库以当前账号密码为准。登录成功返回 `{id, username}`，Cookie 的 Max-Age 为 7 天，服务同时校验数据库 Token。`GET /admin/v1/me` 查询管理员；`POST /admin/logout` 返回 `204`。

以下所有 `/admin/v1/...` 都要求管理员角色。完整输入模型与路由见[管理完整参考](reference-admin.md)。

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
{"name":"document-model","vision":false,"max_concurrent_requests":2}
```

模型并发上限设置在**每个模型**上，默认 `0` 为无限制，正整数为同时请求数。`PUT /admin/v1/models/{model_id}` 可只传：

```json
{"max_concurrent_requests":2}
```

成功返回 `204`，当前进程内立即更新额度。等待请求按 FIFO 排队；流式请求直到流关闭才释放额度。降低额度不会中断已开始的请求，增大或改成 `0` 会放行等待请求。相同模型 ID 被主 / 子 / 视觉模型或不同用户使用时共享额度。

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

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| GET / POST | `/admin/v1/users` | 用户列表 / 创建 `{username,password,role}` |
| PUT | `/admin/v1/users/{user_id}/password` | `{password}` 重置密码 |
| PUT | `/admin/v1/users/{user_id}/role` | `{role}` 修改角色 |
| DELETE | `/admin/v1/users/{user_id}` | 删除用户和所属数据 |
| GET | `/admin/v1/users/{user_id}/sessions` | 用户会话列表 |
| DELETE | `/admin/v1/sessions/{session_id}` | 删除会话和文件 |
| POST | `/admin/v1/sessions/{session_id}/evict` | 驱逐内存缓存，不是删除历史 |

角色为 `user` / `admin`；服务保留至少一个管理员。驱逐和配置重载可能取消该缓存中的活跃任务，调用前需理解对在线用户的影响。

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

默认技能启停主要影响新会话，不自动撤销已经分发到现有会话的副本。服务器技能库写入应用目录的 `skills/`，备份时需单独包含。

技能内容 PUT 的 JSON 为 `{"content":"..."}`，创建 / 更新通常返回 `201`，删除为 `204`；完整模型以参考为准。Python 脚本保存检查语法。测试请求为 `{"args":"{}","timeout":10}`，`args` 是 JSON **字符串**；超时限制在 1–30 秒，使用临时工作目录并返回 `{output: ...}`。这是受信任脚本的执行测试，不是容器级隔离。

## 工具回合上限

`GET /admin/v1/runtime-config` / `PUT /admin/v1/runtime-config` 管理主 Agent 工具回合数：

```json
{"max_tool_iterations":0}
```

`0` 为无限，`null` 清空覆盖回到默认，正整数为上限。这与模型并发字段不同；修改会重载并驱逐在线会话缓存。
