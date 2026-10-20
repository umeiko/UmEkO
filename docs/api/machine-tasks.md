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

## 输入门禁 {#input-validation}

REST、MCP、A2A 在创建业务任务、会话和暂存附件之前共用输入门禁。`prompt` / A2A 文本 Part 只放需求；文件通过 REST/MCP 的 `files[].content_base64`，或 A2A 1.0 的 `parts[].raw` 传输。A2A SDK 的 `raw` 使用 bytes，JSON 线上的值才是 base64；不要把整个附件对象序列化后塞进 `text` 或 `data`。

需求正文可包含普通 HTTP/HTTPS 文件链接，包括含较长签名参数的下载链接，不按文件编码拦截，也不在提交时探测是否能下载。A2A 也可使用 url Part，协议将多个链接按顺序汇总到需求正文末尾，不自动下载或登记为附件。Agent 可按需使用 `download_url`；下载和处理失败交由 Agent 根据必要程度、可行修正及已有材料判断。确认缺少关键材料而无法继续时，及时用 `submit_results` 说明原因、缺失项与补齐步骤并结束本轮，请外层 Agent 提供临时工作台链接。可选资料失败时可以继续其余工作；平台不因一次下载或处理错误强制终止任务。下载工具现有的访问范围和 TLS 安全约束继续适用。

以下输入会直接拒绝，不进入模型、队列或会话历史：

- 正文中的实际 base64 data URL、包含文件编码的附件 JSON、具有常见图片/压缩包/PDF 文件头的编码。
- 连续或只用空白、转义换行分隔的长编码块，累计达到 4096 字符；较短的 base64 讨论示例和普通代码、文本仍可使用。识别是确定性的格式规则，不代替文件内容审查，也不保证识别任意变形的编码。
- 需求文本超过 200000 字符；A2A 所有 text/data Part 与 url 汇总内容合计受同一上限限制，整条消息最多 64 个 Part。
- 文件名/编码不合法、附件超过 10 个或解码后总大小超过 20 MiB。整条 HTTP 请求另有 30 MiB 限制，超过时返回 413。

门禁错误含稳定的 `code`、`field`、`retryable=false`、`task_created=false`、`next_action` 和正确附件用法 `file_transport`，不回显输入文件字节。REST 返回 HTTP 400 的 `detail`，请求 Schema 校验错误保持 HTTP 422 并同样省略原始输入；MCP 返回 `isError=true`，`structuredContent.error` 与文本错误内容一致；A2A 返回 `InvalidParams`，在错误 data 的 `ErrorInfo.metadata` 中携带这些字段，官方 SDK 可通过异常的 `data` 读取。

例如 `FILE_CONTENT_IN_TEXT` 表示文件误放进正文，`PROMPT_TOO_LARGE` 表示文本过长。调用 Agent 应修正附件结构后再提交，不能原样重试、拆段重试或改塞进其他文本字段。无法上传时，及时告诉用户需要补充附件。拒绝发生在任务创建之前，因此没有 Task ID 或临时工作台链接；不要轮询不存在的任务。队列满的 429 属于另一类可稍后重试的错误。

## 临时工作台 {#temporary-workspace}

网页使用方式、外部 Agent 续聊示例与接口范围见[临时工作台与续聊](temporary-workspace.md)。

完整权限调用方的任务响应含 `workspace_url` 和 `workspace_hint`。地址为用户服务完整基址下的
`/TMP/<Temp_session_id>`，包含 `UMEKO_BASE_PATH`，不包含管理前缀或 `/agent/<slug>`。
REST 与 MCP 的提交、查询和取消响应直接返回这些字段；A2A 在 Task 的 `metadata.workspaceUrl`
和 `metadata.workspaceHint` 返回。链接在成功提交时即可取得，无需等待模型完成；MCP 提交回执的文字块和 A2A Task 的 `status.message` 也直接提供可点击链接及接续提示。

调用 Agent 应在提交成功后立即把链接交给用户，邀请其实时查看进度、工具记录和文件，任务结束后可在浏览器继续同一会话，无需另外注册或登录。排队时工作台显示准备页。若缺少必要图片、文档或需人工处理，说明待补事项并引导用户在该节点补齐，不要空等或重新创建任务。服务会返回明确引导，实际向用户展示仍取决于调用方 Agent。

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

REST/MCP 的任务回执与查询包含 `results_url/results_hint`，A2A 对应 Task `metadata.resultsUrl/resultsHint`。链接用于调用程序读取同一 Agent、同一调用方的结果 JSON，不是让用户自行跳转的网页；仍需 tasks:read 与正确的 OAuth resource。A2A 完成响应本身已含正文和产物，直接交付即可，不必额外 GET。详见 [A2A 结果读取](a2a.md#read-results)。

机器任务向主 Agent 注入内部 `submit_results(text, files)` 工具与提交提示词；工具校验通过后直接结束本轮，聊天正文无需是独立 JSON。参数或文件有误时先把错误返回模型修正，未调用工具时给予一次提交提醒。普通会话和文件子 Agent 不提供此工具，MCP 对外工具列表也不新增它。临时工作台续聊每轮重新提交，只有最新成功提交的结果才更新 `/results`，不会沿用上一轮的提交状态。

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
