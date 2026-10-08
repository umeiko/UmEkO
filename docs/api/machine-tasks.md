# 机器任务与服务凭据

程序或其他 Agent 无需创建网页用户名密码。管理员在管理端“服务接入”创建服务账号，保存只显示一次的凭据。调用 UMEKO 的凭据与 Provider 模型 API Key 是两套配置。

## 地址和权限

下面所有路径相对用户服务的完整基址，例如 `https://example.internal/doc-master/consistency/image-text`。这些入口不在管理端口上。

| scope | 用途 |
| --- | --- |
| `tasks:create` | 提交任务与 MCP 模型发现 |
| `tasks:read` | 查询、列出、订阅自己的任务 |
| `tasks:cancel` | 取消自己的任务 |
| `artifacts:read` | 读取自己的产物 |

A2A 的等待、查询和流式操作需要 `tasks:read`，发送还需要 `tasks:create`，取消同时需要 `tasks:cancel`。建议给完整任务流程授予上述四项；只读集成可只授予读取权限。

REST `/v1/tasks` 同时接受服务 Bearer 和网页 Cookie；MCP / A2A 必须使用服务 Bearer，个人本地工作台的免登录模式也不会自动放开协议入口。

仅有提交或取消权限时，相关响应只提供任务状态和标识，回复、错误正文及产物列表为空；幂等重试也不会绕过读取权限。

## 最小调用

在调用方环境配置 `UMEKO_SERVICE_URL` 和 `UMEKO_SERVICE_TOKEN`，后者不要放入仓库。下面的 Python 示例使用 `httpx`，带前缀时无需改其他路径。

```python
import base64
import os
import time
from pathlib import Path
import httpx

base = os.environ["UMEKO_SERVICE_URL"].rstrip("/")
token = os.environ["UMEKO_SERVICE_TOKEN"]
with httpx.Client(headers={"Authorization": f"Bearer {token}"}, timeout=30) as client:
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

同一账号的幂等键和输入相同返回原 Task；输入不同返回 `409`。结果到期后该键可以重新使用。输入最多 200000 字符、10 个文件、文件原始字节合计 20 MiB；JSON / A2A / MCP 请求体上限 30 MiB，含 base64 和其他字段。文件名不能包含路径。

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
