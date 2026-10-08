# 机器任务与服务凭据

程序或其他 Agent 无需创建网页用户名密码。管理员在“服务接入”选择接入方式：默认需要服务凭据，也可开启免鉴权。调用 UMEKO 的凭据与 Provider 模型 API Key 是两套配置；免鉴权不会向调用方提供模型密钥。

## 免鉴权接入

选择“免鉴权（无需凭据）”并保存后，MCP、A2A、REST `/v1/tasks` 及其事件、产物入口可不带 Authorization。只需配置服务地址；设置保存在数据库中，后续请求立即生效，重启后仍保留。网页登录和管理端登录不受此开关影响。

所有不带凭据的机器调用共用一个持久化身份，能查询、取消及下载同一 Agent 内该身份下的任务与文件，也共用每账号队列额度。不会为每个请求或 IP 创建服务账号，不按 IP 鉴权或隔离数据。共享幂等键须由调用方使用唯一业务标识。

带有效凭据的调用仍按对应服务账号隔离；传了无效或过期凭据会返回 401，不自动降级到免鉴权。切回“需要服务凭据”后，新的免凭据请求被拒绝，已接收任务继续执行。免鉴权任务可由管理员在资源监控中查看和停止。

后台任务列表及服务日志记录提交时的来源 IP，无法取得时显示未知。IP 仅作辅助记录，不出现在公开任务响应中。经过代理时以服务实际看到的地址为准，详见[部署指南](../deployment.md)。

## 地址和权限

下面所有路径相对具体 Agent 的完整基址，例如 `https://example.internal/doc-master/consistency/image-text/agent/image-qc`。每个 Agent 使用自己的工作指引、所选 Skill 和默认模型；调用者显式指定的 `model_id` 优先。配置方法见[智能体管理](agents.md)。

| scope | 用途 |
| --- | --- |
| `tasks:create` | 提交任务与 MCP 模型发现 |
| `tasks:read` | 查询、列出、订阅自己的任务 |
| `tasks:cancel` | 取消自己的任务 |
| `artifacts:read` | 读取自己的产物 |

A2A 的等待、查询和流式操作需要 `tasks:read`，发送还需要 `tasks:create`，取消同时需要 `tasks:cancel`。建议给完整任务流程授予上述四项；只读集成可只授予读取权限。

需要凭据模式下，REST `/v1/tasks` 接受服务 Bearer 或网页 Cookie；MCP / A2A 使用服务 Bearer。个人本地工作台的免登录模式不会自动放开 MCP / A2A，仍需显式开启服务接入的免鉴权模式。

仅有提交或取消权限时，相关响应只提供任务状态和标识，回复、错误正文及产物列表为空；幂等重试也不会绕过读取权限。

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
        # "model_id": "从模型列表获取的 ID",
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
| POST | `/v1/tasks` | `prompt`、可选 `files`、`model_id`；返回 202 与 Task |
| GET | `/v1/tasks?limit=50&offset=0` | 自己未到期的任务，limit 1–100 |
| GET | `/v1/tasks/{task_id}` | 持久化状态、结果、错误、到期时间、产物 |
| POST | `/v1/tasks/{task_id}/cancel` | 排队任务立即取消；运行任务协作式停止 |
| GET | `/v1/tasks/{task_id}/events` | SSE，支持 `after` 和 `Last-Event-ID` |
| GET | `/v1/tasks/{task_id}/artifacts/{artifact_id}/content` | 授权下载 |

状态为 `queued`、`running`、`cancelling`、`completed`、`failed`、`cancelled`。`expires_at` 在终态前为空；终态默认保留 24 小时。Task 中的 `artifacts` 含 `id`、`name`、`media_type`、`size`、`download_url`、`resource_uri`。

Task 的 `agent_id` 标记所属 Agent。查询、列表、事件、取消和产物均限制在当前 Agent 与账号内，换用另一个 Agent 路径会返回 404。新增 Agent 的排队任务保留提交时的工作指引和主 Skill 文本副本；快照及停用规则见[多智能体架构](../architecture/agents.md)。

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
