# REST API 调用

本页介绍机器任务 REST。浏览器用户的会话接口见本页末尾，它们使用不同的身份与生命周期。

## 最小完整调用

调用方配置 `UMEKO_SERVICE_URL` 为具体智能体基址。需要凭据时设置 `UMEKO_SERVICE_TOKEN`；免鉴权时不设置。示例不会要求或接收上游模型 Key。

```python
import os
import time
import uuid
import httpx

base = os.environ["UMEKO_SERVICE_URL"].rstrip("/")
token = os.getenv("UMEKO_SERVICE_TOKEN")
headers = {"Authorization": "Bearer " + token} if token else {}

with httpx.Client(headers=headers, timeout=30) as client:
    response = client.post(base + "/v1/tasks", json={
        "prompt": "说明你能处理哪些文件任务", "files": []
    }, headers={"Idempotency-Key": str(uuid.uuid4())})
    response.raise_for_status()
    task = response.json()
    if task.get("workspace_url"):
        print("可查看进度并接续：", task["workspace_url"])
    while task["status"] not in {"completed", "failed", "cancelled"}:
        time.sleep(2)
        response = client.get(base + "/v1/tasks/" + task["task_id"])
        response.raise_for_status()
        task = response.json()
    response = client.get(task["results_url"])
    response.raise_for_status()
    result = response.json()
    print(result["text"] if result["ready"] else result["error"])
    for file in result["files"]:
        print(file["name"], base + f"/v1/tasks/{task['task_id']}/files/{file['file_id']}/content")
```

需要上传文件时，`files` 采用以下格式，不包含 data URL 的头部：

```python
import base64
from pathlib import Path

files = [{"name": "input.png", "content_base64":
          base64.b64encode(Path("input.png").read_bytes()).decode("ascii")}]
```

## 常用操作

所有路径相对具体 Agent 基址。需要凭据的下载 GET 也要发送同一服务 Bearer。

| 方法与路径 | 用途 |
| --- | --- |
| `POST /v1/tasks` | 提交，成功为 202，立即返回任务和可用工作台链接 |
| `GET /v1/tasks/{id}` | 查询状态、回复、错误及产物元数据 |
| `GET /v1/tasks/{id}/results` | 获取最新通过校验的结果 text/files |
| `POST /v1/tasks/{id}/cancel` | 请求取消 |
| `GET /v1/tasks/{id}/events` | SSE 事件流 |
| `GET /v1/tasks/{id}/files` | 列目录，文件/目录使用稳定 file_id |
| `GET /v1/tasks/{id}/files/{file_id}/content` | 下载文件，目录返回 ZIP |

没有任务列表接口，保存提交时取得的本次 ID。幂等重试应复用同一键和同一输入；要创建新任务使用新键。旧节点到期后，同一幂等键不会恢复节点。

任务回执和查询提供 `results_url/results_hint`，由程序 GET 取得最新通过校验的结果。正文和文件应由调用方直接交付给用户，不要求用户访问 JSON 地址。结果接口需要 `tasks:read`；OAuth access token 的 resource 为当前 Agent 的 `/v1/tasks`，不能跨用仅面向 MCP/A2A 的令牌。

## 网页用户的 Session / Run API

普通网页会话使用网页登录 Cookie：`POST /v1/auth/login` 登录，`POST /v1/sessions` 创建会话，`POST /v1/sessions/{session_id}/runs` 以 `input` 和 `attachments` 发起一轮，`GET /v1/runs/{run_id}/events` 接收流式过程。这组路径相对**用户服务基址**，没有 `/agent/<slug>`。

普通会话、机器任务和临时工作台的权限不能混用；服务 Bearer 不等同于网页登录 Cookie。机器任务需要接续上下文时，优先使用返回的[临时工作台会话接口](workspace.md)。
