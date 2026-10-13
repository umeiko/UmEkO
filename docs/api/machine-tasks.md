# 机器任务与服务凭据

程序或其他 Agent 无需创建网页用户名密码。管理员在“服务接入”选择接入方式：默认需要服务凭据，也可开启免鉴权。调用 UMEKO 的凭据与 Provider 模型 API Key 是两套配置；免鉴权不会向调用方提供模型密钥。

## 免鉴权接入

选择“免鉴权（无需凭据）”并保存后，MCP、A2A、REST `/v1/tasks` 及其事件、产物入口可不带 Authorization。只需配置服务地址；设置保存在数据库中，后续请求立即生效，重启后仍保留。网页登录和管理端登录不受此开关影响。

所有不带凭据的机器调用共用一个持久化身份，能查询、取消及下载同一 Agent 内该身份下的任务与文件，也共用每账号队列额度。不会为每个请求或 IP 创建服务账号，不按 IP 鉴权或隔离数据。共享幂等键须由调用方使用唯一业务标识。

带有效凭据的调用仍按对应服务账号隔离；传了无效或过期凭据会返回 401，不自动降级到免鉴权。切回“需要服务凭据”后，新的免凭据请求被拒绝，已接收任务继续执行。免鉴权任务可由管理员在资源监控中查看和停止。

后台任务列表及服务日志记录提交时的来源 IP，无法取得时显示未知。IP 仅作辅助记录，不出现在公开任务响应中。经过代理时以服务实际看到的地址为准，详见[部署指南](../deployment.md)。

## 地址和权限

下面所有路径相对具体 Agent 的完整基址，例如 `https://example.internal/doc-master/consistency/image-text/agent/image-qc`。每个 Agent 使用自己的工作指引、所选 Skill 和管理员配置的默认模型。配置方法见[智能体管理](agents.md)。

对外 REST、MCP、A2A 均不接受调用方选择 `model_id`，不提供模型列表或任务列表。提交返回本次执行的 `id/task_id`，以及标记服务归属的固定 `agent_id`；之后用本次 `task_id` 查询状态和取文件，不能查询其他 Agent 或调用方所属任务。

| scope | 用途 |
| --- | --- |
| `tasks:create` | 提交任务与 MCP 模型发现 |
| `tasks:read` | 查询、列出、订阅自己的任务 |
| `tasks:cancel` | 取消自己的任务 |
| `artifacts:read` | 读取自己的产物 |

A2A 的等待、查询和流式操作需要 `tasks:read`，发送还需要 `tasks:create`，取消同时需要 `tasks:cancel`。建议给完整任务流程授予上述四项；只读集成可只授予读取权限。

需要凭据模式下，REST `/v1/tasks` 接受服务 Bearer 或网页 Cookie；MCP / A2A 使用服务 Bearer。个人本地工作台的免登录模式不会自动放开 MCP / A2A，仍需显式开启服务接入的免鉴权模式。

仅有提交或取消权限时，相关响应只提供任务状态和标识，回复、错误正文及产物列表为空；幂等重试也不会绕过读取权限。

## 临时工作台 {#temporary-workspace}

网页使用方式、外部 Agent 续聊示例与接口范围见[临时工作台与续聊](temporary-workspace.md)。

完整权限调用方的任务响应含 `workspace_url` 和 `workspace_hint`。地址为用户服务完整基址下的
`/TMP/<Temp_session_id>`，包含 `UMEKO_BASE_PATH`，不包含管理前缀或 `/agent/<slug>`。
MCP 的 `submit_task`、`get_task` 和任务列表直接返回这些字段；A2A 在 Task 的 `metadata.workspaceUrl`
和 `metadata.workspaceHint` 返回。可以把链接交给用户，在浏览器继续同一会话，无需另外注册或登录。

临时工作台复用聊天、工具记录、上传、文件树、预览、下载与 SSE。账号、新建会话、会话管理和模型选择不可操作；
技能仅展示任务提交时该 Agent 下发的选定技能，全部勾选且只读。任务排队时显示准备页，准备好后自动打开；
原任务未结束前不能启动第二次对话。浏览器后续对话保留原上下文、工作指引及 Agent 的模型设置，
不改写原始机器任务的回复。后续产物和文件元数据会更新，管理员仍可在原任务下排查。

链接使用不可猜测的随机标识，只能访问一条任务对应的会话；拥有此链接即可读写该会话，
请仅交给预期使用者。它不会授予账号管理、其他会话、模型配置或其他协议入口的权限。
仅当调用凭据同时有四项任务权限时才返回链接；只读或仅提交权限返回 `null`，不会通过链接提升权限。
停用、删除或到期的服务账号会使已有链接失效；免鉴权的任务也各有独立的临时链接。

纯机器节点在任务结束后默认 15 分钟回收，由 `UMEKO_MACHINE_IDLE_SECONDS` 配置；
首次打开临时工作台后，改为网页闲置默认 1 小时，由 `UMEKO_TMP_IDLE_SECONDS` 配置。
顶部展示到期时间。实际点击、键盘输入、滚动、提交任务会续期，心跳和被动轮询不会续期。
运行中的原任务及后续对话不会被回收，结束后重新开始闲置计时。过期、删除会话或任务被回收后，
新打开和已经打开的页面都显示“该节点已过期，请重新申请”。内存缓存释放不等同于删除节点，
有效期内可从持久化历史恢复。节点回收释放 Agent、Run 缓冲和会话文件；调用记录、消息、工具记录和文件树快照
按 `UMEKO_TASK_RETENTION_SECONDS` 默认继续保留 24 小时供管理员排查，到记录期限后一起删除。
浏览器续聊仍使用原 REST/SSE 会话能力，MCP/A2A 的原任务标识与结果保持不变。

外部 Agent 也可用 `workspace_url + /v1/temporary` 获取 `session_id`，再向
`workspace_url + /v1/sessions/<session_id>/runs` 提交 `{"input": "继续处理", "attachments": []}`。
已打开的临时工作台自动显示这次输入、流式回复和工具记录，无需刷新；仍限制一条会话同时只能有一个运行。
这属于同一会话的 REST 续聊，不能向已完成的 A2A Task 追加消息；重新提交 MCP/A2A 任务会建立新的任务与临时工作台。

重新申请时提交新任务，并使用新的幂等键或 A2A 消息 ID。同一幂等键在调用记录保留期内仍返回原任务，不恢复过期节点。

## 最小调用

在调用方环境配置 `UMEKO_SERVICE_URL`；需要凭据时另外配置 `UMEKO_SERVICE_TOKEN`，后者不要放入仓库。免鉴权时不设置 Token。下面的 Python 示例使用 `httpx`，带前缀时无需改其他路径。

```python
import base64
import os
import time
from pathlib import Path
import httpx

base = os.environ["UMEKO_SERVICE_URL"].rstrip("/")
token = os.getenv("UMEKO_SERVICE_TOKEN")
headers = {"Authorization": f"Bearer {token}"} if token else {}
with httpx.Client(headers=headers, timeout=30) as client:
    response = client.post(base + "/v1/tasks", headers={"Idempotency-Key": "document-001"}, json={
        "prompt": "检查附件并生成报告",
        "files": [{"name": "input.txt", "content_base64": base64.b64encode(Path("input.txt").read_bytes()).decode()}],
    })
    response.raise_for_status()
    task = response.json()
    while task["status"] not in {"completed", "failed", "cancelled"}:
        time.sleep(1)
        response = client.get(base + "/v1/tasks/" + task["id"])
        response.raise_for_status()
        task = response.json()
    print(task["status"], task["reply"], task["error"])
    for artifact in task["artifacts"]:
        response = client.get(artifact["download_url"])
        response.raise_for_status()
        Path(Path(artifact["name"]).name).write_bytes(response.content)
```

同一 Agent、同一账号的幂等键和输入相同返回原 Task；输入不同返回 `409`。结果到期清理后该键可以重新使用。输入最多 200000 字符、10 个文件、文件原始字节合计 20 MiB；JSON / A2A / MCP 请求体上限 30 MiB，含 base64 和其他字段。文件名不能包含路径。

## REST 操作

| 操作 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/v1/tasks` | `prompt`、可选 `files`；返回 202 与 Task，含本次 `id/task_id` 和服务 `agent_id` |
| GET | `/v1/tasks/{task_id}` | 持久化状态、结果、错误、到期时间、产物 |
| GET | `/v1/tasks/{task_id}/results` | Agent 提交并由平台校验的结果 JSON，含自然语言 `text` 与最终文件清单 `files` |
| POST | `/v1/tasks/{task_id}/cancel` | 排队任务立即取消；运行任务协作式停止 |
| GET | `/v1/tasks/{task_id}/events` | SSE，支持 `after` 和 `Last-Event-ID` |
| GET | `/v1/tasks/{task_id}/artifacts/{artifact_id}/content` | 授权下载 |
| GET | `/v1/tasks/{task_id}/files` | 顶层目录及 `file_id`；可传 `directory_id`，只列对应文件夹的直接子项 |
| GET | `/v1/tasks/{task_id}/files/{file_id}/content` | 按序号授权下载文件；文件夹自动打包 ZIP |

状态为 `queued`、`running`、`cancelling`、`completed`、`failed`、`cancelled`。`expires_at` 在终态前为空；终态默认保留 24 小时。Task 中兼容保留的 `artifacts` 只登记 Agent 明确选择的最终文件，含 `id`、`name`、`media_type`、`size`、`download_url`。完整最终清单从 `/results` 读取，包含文件和目录的 `file_id`，可通过 `/files/{file_id}/content` 下载；不从目录扫描推测最终交付件。

`workspace_expires_at` 是节点和产物文件的回收期限，`workspace_state` 为 `available` 或 `expired`；
此期限与调用记录的 `expires_at` 分开。节点过期后仍可查询原 Task 的回复与产物元数据，但文件下载与资源读取返回不存在。
A2A 对应 `metadata.workspaceExpiresAt`、`metadata.workspaceState`。节点物理清理约每分钟执行一次；到期访问立即被拒绝。

Task 的 `agent_id` 标记所属 Agent。查询、文件列表、事件、取消和产物均限制在当前 Agent 与账号内，换用另一个 Agent 路径会返回 404。文件序号按任务持久保存，新增文件不会改变已列出条目的序号；可用目录序号逐层展开，默认不递归。文件访问需要 `artifacts:read`，且仅包含本次任务的 `workspace`、`attachments`、`generate`。新增 Agent 的排队任务保留提交时的工作指引和主 Skill 文本副本；快照及停用规则见[多智能体架构](../architecture/agents.md)。

SSE 每帧含 `id`、`event`、`data`，data 是 `id/type/data/created_at` 事件对象。只保留最近 500 条，不作为完整审计日志；重连缺失历史时以 GET Task 的最终结果为准。原生浏览器 EventSource 不能设置 Bearer Header，可用支持 Header 的 SSE 客户端。

| 错误 | 含义 |
| --- | --- |
| 401 | 凭据失效、停用、到期或令牌的 resource 不匹配 |
| 403 | 缺少 scope |
| 404 | 任务 / 产物不存在、到期或属于别人 |
| 409 | 同一幂等键使用了不同输入 |
| 413 | 请求体过大 |
| 429 | 任务队列或调用者额度已满；按 `Retry-After` 重试 |

## OAuth 客户端凭据

服务账号 ID 为 `client_id`，服务凭据为 `client_secret`。支持表单或 HTTP Basic，不提供交互式 OAuth 登录。

```python
response = httpx.post(base + "/oauth/token", data={
    "grant_type": "client_credentials",
    "client_id": os.environ["UMEKO_SERVICE_CLIENT_ID"],
    "client_secret": token,
    "resource": base + "/mcp",
    "scope": "tasks:create tasks:read tasks:cancel artifacts:read",
})
response.raise_for_status()
access_token = response.json()["access_token"]
```

访问令牌有效期最多 1 小时，且服务账号凭据必须仍有效。scope 不能超出账号权限；resource 可为 `base + /mcp`、`/a2a` 或 `/v1/tasks`，默认 `/mcp`，令牌不能跨 resource 使用。用 MCP / A2A resource 的短期令牌下载 REST 产物时，需换取 `/v1/tasks` resource 的令牌或使用原服务凭据。

发现地址为 `/.well-known/oauth-protected-resource/mcp` 和 `/.well-known/oauth-authorization-server`。路径前缀部署的自动发现注意事项见 [部署指南](../deployment.md)。

## 资源与生命周期

任务排队和模型排队分开限制。管理员在 Provider 页面控制每模型并发，在 `.env` 控制机器任务容量与保留时间。管理员停用凭据会阻止后续请求，已经接收的任务继续执行；需要停止时在“资源监控”中取消。

服务重启会恢复排队任务，执行中任务标记中断失败。业务连接断开不会取消已接收任务。查询结果不加载 Agent，终态内存会释放，到期工作区与记录自动回收。详见 [API 服务架构](../architecture/api-service.md)。
