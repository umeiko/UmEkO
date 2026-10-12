# 临时工作台与续聊

通过 MCP 或 A2A 提交任务后，可以把返回的临时工作台链接交给用户。用户打开链接，就能查看这次任务的对话、工具调用、附件和产物，并在同一个会话中继续处理。无需另外注册网页账号。

外部 Agent 也能通过这个链接继续原会话。已经打开的网页会自动显示新请求、流式回复和工具记录，无需刷新。

## 获取工作台链接

| 调用方式 | 工作台链接 | 提示与有效期 |
| --- | --- | --- |
| REST 机器任务 / MCP | `workspace_url` | `workspace_hint`、`workspace_expires_at`、`workspace_state` |
| A2A Task | `metadata.workspaceUrl` | `metadata.workspaceHint`、`metadata.workspaceExpiresAt`、`metadata.workspaceState` |

链接位于**用户服务基址**下。例如部署前缀为 `/doc-master/consistency/image-text`：

```text
机器入口：https://example.internal/doc-master/consistency/image-text/agent/image-qc/a2a
工作台：https://example.internal/doc-master/consistency/image-text/TMP/<随机标识>
```

工作台链接包含用户服务前缀，省略 `/agent/image-qc`，也不包含管理服务的前缀。直接使用服务返回的链接，不要自行从任务 ID 拼造。

只有具备 `tasks:create`、`tasks:read`、`tasks:cancel`、`artifacts:read` 四项权限的调用方才会收到可用链接；权限不足时为 `null`。免鉴权模式下同样会返回每条任务各自的临时链接。服务凭据与 Provider 的模型 Key 始终分开，返回链接不会披露模型 Key。

## 网页能做什么

临时工作台沿用完整工作台的聊天、工具详情、调用历史、上传、文件树、预览和下载界面。

| 功能 | 临时工作台行为 |
| --- | --- |
| 继续提问、上传文件、查看产物 | 可用，复用原会话上下文与文件 |
| 账号菜单、新建会话与会话管理 | 禁用 |
| 底部模型选择 | 禁用，使用 Agent 配置的模型 |
| 技能 | 仅展示任务提交时该 Agent 下发的技能，默认全部挂载，不能改选 |
| 原任务排队 | 显示准备页，准备完成后自动进入工作台 |
| 原任务或续聊仍在执行 | 显示执行过程，同一会话不能同时启动第二个 Run |
| 节点过期 | 显示“该节点已过期，请重新申请” |

这里有三个不同的标识：**Task** 是 MCP/A2A 提交的原始机器任务，**Session** 是承载上下文与文件的会话，**Run** 是会话里的一次提问。浏览器续聊或外部 Agent 续聊会创建新的 Run，继续使用同一个 Session。

后续对话不会改写原始 Task 的回复或状态；新增产物及文件元数据会更新，管理员仍可在原任务详情中查看这条会话的记录。

默认图像质检智能体发现必要图片或文档无法取得时，会及时结束本轮执行，说明缺少什么以及如何补齐。外层 Agent 应立即把响应中的真实工作台链接和待补事项交给用户，或通过临时会话接口继续处理，不应一直轮询原任务等待文件出现。此时任务状态 `completed` 表示本轮执行已结束，不代表图像检查已经完成或通过；原 Task 不进入 A2A 的 `input-required` 状态。仅缺可选参考资料时，继续可执行的检查，把无法核对项标为 NA。

## 外部 Agent 继续同一会话

先从原任务响应取得工作台链接，按以下步骤调用：

1. `GET <workspace_url>/v1/temporary`，取得 `session_id`。
2. 如果 `state` 为 `pending`，等待准备完成。`ready` 表示会话已经建立，不代表当前没有任务在运行。
3. 查询 `GET <workspace_url>/v1/sessions/<session_id>/active-run`。返回 `null` 后可提交续聊。
4. `POST <workspace_url>/v1/sessions/<session_id>/runs`，发送问题并取得 `run_id`。
5. 通过运行查询或 SSE 取得回复；已经打开的网页会同步显示这次输入及输出。

Python 示例使用 `httpx`。把服务返回的链接放入调用方的 `UMEKO_WORKSPACE_URL`，无需额外发送网页登录 Cookie 或模型 Key：

```python
import os
import httpx

workspace = os.environ["UMEKO_WORKSPACE_URL"].rstrip("/")
with httpx.Client(timeout=30) as client:
    response = client.get(workspace + "/v1/temporary")
    response.raise_for_status()
    info = response.json()
    if info["state"] != "ready":
        raise RuntimeError("工作台仍在准备，请稍后重试")

    session = workspace + "/v1/sessions/" + info["session_id"]
    response = client.get(session + "/active-run")
    response.raise_for_status()
    if response.json() is not None:
        raise RuntimeError("同一会话已有运行，请等它结束后继续")

    response = client.post(session + "/runs", json={
        "input": "请列出 attachments 中的文件，再回顾刚才的处理结果",
        "attachments": [],
    })
    response.raise_for_status()
    run = response.json()
    print("新运行：", run["id"])
    # 后续查询：workspace + "/v1/runs/" + run["id"]
    # 流式回复：workspace + "/v1/runs/" + run["id"] + "/events"
```

`attachments` 接受附件接口返回的文件 ID，不是服务器文件路径；续聊的文件接口也必须使用工作台链接作为基址。已有会话文件和历史会继续保留。附件上传与运行事件格式分别见[文件与技能](files-skills.md)、[流式事件](events.md)。

查询活跃运行和提交之间可能有其他调用进入。服务端仍会检查并发；同会话已有运行时提交返回 `400`，调用方应等待它结束。

!!! note "MCP/A2A 原任务与会话续聊"
    已完成的 A2A Task 当前不接受追加消息，`contextId` 只用于分组，不继承另一个任务的模型记忆。
    MCP 再次调用 `submit_task` 或 A2A 使用新消息 ID 提交，会创建新任务和新工作台；同一幂等键重试则返回原任务。
    想沿用这次处理的上下文与文件，应使用上述临时会话 REST 接口，或直接在临时网页中继续提问。

## 实时同步与接口范围

网页通过工作台作用域内的 `/v1/temporary/events` 监听会话变化。发现外部调用启动的新 Run 后，自动接上该 Run 的 SSE，显示文字增量、工具调用及最终结果。很快就完成的运行从保存的消息和工具记录补齐。同步保留输入草稿、待发送附件和当前文件预览。

下面的路径全部相对 `workspace_url`，不能改用普通用户基址或管理端口：

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| GET | `/v1/temporary` | 工作台状态、原任务 ID、会话 ID、到期时间 |
| POST | `/v1/temporary/activity` | 报告实际用户操作并续期 |
| GET | `/v1/temporary/events` | 会话变化 SSE，不续期 |
| GET | `/v1/sessions/<session_id>/active-run` | 当前活跃 Run 或 `null` |
| POST | `/v1/sessions/<session_id>/runs` | 同会话续聊，返回 `202 RunView` |
| GET | `/v1/runs/<run_id>` | 查询本会话运行 |
| GET | `/v1/runs/<run_id>/events` | 运行事件 SSE |
| POST | `/v1/runs/<run_id>/cancel` | 请求停止本会话运行 |

会话变化 SSE 使用 `session.changed`，数据含 `message_count`、`message_id` 和 `run_id`；闲置时发送保活注释。过期时发送 `session.expired` 并结束连接。该通知用于发现会话变化，回复正文和工具过程来自运行 SSE。

临时入口由服务中间件限制在一条会话内，无法访问其他会话、账号设置、模型配置或管理 API。访问不允许的操作返回 `403`；工作台过期或无效返回 `410`，错误代码为 `temporary_workspace_expired`。这些临时入口不在 FastAPI 自动生成的 OpenAPI 操作清单中。

生产代理必须转发前缀下所有子路径，并关闭 SSE 缓冲；外部完整地址由 `UMEKO_PUBLIC_URL` 配置。部署步骤见[部署指南](../deployment.md)。

## 过期、续期与清理

| 配置 | 默认值 | 作用 |
| --- | --- | --- |
| `UMEKO_MACHINE_IDLE_SECONDS` | 900 秒（15 分钟） | 尚未打开网页的纯机器节点，任务结束后闲置回收 |
| `UMEKO_TMP_IDLE_SECONDS` | 3600 秒（1 小时） | 首次打开工作台后，按网页闲置时间回收 |
| `UMEKO_TASK_RETENTION_SECONDS` | 86400 秒（24 小时） | 调用记录的保留期限，与节点及文件期限分开 |

网页顶部显示到期时间。实际点击、键盘输入、滚动、提交请求会续期；被动打开页面、心跳、会话变化监听和任务查询不会持续续期。运行中的原任务或续聊会受保护，结束后重新开始闲置计时。

首次读取 `/v1/temporary` 会把节点切换到工作台闲置期限，外部 Agent 按上面的示例初始化工作台时也会发生这一切换；后续重复查询不会续期。

到期访问立即失效，后台约每分钟回收一次节点、内存缓存与会话文件。数据库中的消息、工具记录和文件树快照保留到调用记录期限，供管理员排查；文件树快照不保留文件正文。已有页面与新打开的过期链接都会显示过期提示。

要重新申请，请提交新机器任务并使用新的幂等键或 A2A 消息 ID。继续使用旧幂等键不会复活已过期的节点。

!!! note "链接就是本会话的访问凭据"
    拥有有效工作台链接即可读写这一条会话。仅交给预期使用者，避免把真实链接写进公开文档或日志。
    停用、删除或到期的服务账号会使已有链接失效；普通用户 Cookie 不会扩大临时链接的权限。
