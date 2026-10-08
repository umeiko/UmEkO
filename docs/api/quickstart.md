# API 调用入门

先启动服务并在管理面配置、激活模型。下面以 Python 为例；`BASE_URL` 不带末尾 `/`，公司部署时包含完整路径前缀。

## 登录与发起提问

```python
import time
import httpx

BASE_URL = "http://127.0.0.1:8000"

with httpx.Client(timeout=30, trust_env=False) as client:
    # 换成你已创建的用户账号；首次注册可调用 /v1/auth/register。
    response = client.post(BASE_URL + "/v1/auth/login",
                           json={"username": "your-user", "password": "your-password"})
    response.raise_for_status()
    # 同一个 Client 会保存登录 Cookie，后续请求复用它。

    response = client.post(BASE_URL + "/v1/sessions", json={})
    response.raise_for_status()
    session_id = response.json()["id"]

    response = client.post(BASE_URL + f"/v1/sessions/{session_id}/runs",
                           json={"input": "请介绍你的能力", "attachments": []})
    response.raise_for_status()  # 202 表示已接收，尚未完成。
    run_id = response.json()["id"]

    deadline = time.monotonic() + 300
    while True:
        response = client.get(BASE_URL + f"/v1/runs/{run_id}")
        response.raise_for_status()
        run = response.json()
        if run["status"] in {"completed", "failed", "cancelled"}:
            print(run["status"], run["reply"], run["error"])
            break
        if time.monotonic() >= deadline:
            # 示例选择超时后主动取消；只停止轮询不会取消服务器任务。
            client.post(BASE_URL + f"/v1/runs/{run_id}/cancel").raise_for_status()
            raise TimeoutError("已请求取消，请继续查询以确认最终状态")
        time.sleep(1)
```

如果服务重启，旧 Run 的内存状态会丢失，查询可能返回 `404`。当前 API 不承诺跨重启的工单查询。需要这种能力时采用[持久化任务设计](../architecture/api-service.md)。

## 附件

在创建 Run 前上传文件，然后把返回的文件 ID 放进 `attachments`：

```python
from pathlib import Path

response = client.post(
    BASE_URL + f"/v1/sessions/{session_id}/files",
    params={"filename": "sample.png"},
    content=Path("sample.png").read_bytes(),
    headers={"Content-Type": "application/octet-stream"},
)
response.raise_for_status()
file_id = response.json()["id"]

response = client.post(BASE_URL + f"/v1/sessions/{session_id}/runs",
                       json={"input": "查看附件内容", "attachments": [file_id]})
response.raise_for_status()
```

这个片段放在前一个示例的 `with httpx.Client(...)` 内，第一轮结束后执行。不要对原始附件接口使用 `files=` multipart 参数。

## 流式方式

创建 Run 后，可以代替轮询订阅 SSE。下面是最小读取示例；正式客户端还需重连和重复事件去重。

```python
import json

with client.stream("GET", BASE_URL + f"/v1/runs/{run_id}/events",
                   timeout=httpx.Timeout(30, read=300)) as response:
    response.raise_for_status()
    for line in response.iter_lines():
        if line.startswith("data: "):
            event = json.loads(line[6:])
            if event["type"] == "assistant.delta":
                print(event["data"]["text"], end="", flush=True)
            if event["type"] in {"run.completed", "run.failed", "run.cancelled"}:
                print("\n", event["type"], event["data"])
```

完整契约见[流式事件](events.md)。服务不使用 `[DONE]` 作为结束帧；查看 `run.*` 终态事件，并以 Run 查询为最终依据。

## 清理与网络

产物下载完毕后，如果不需要保留会话，可以 `DELETE /v1/sessions/{session_id}`。删除会清理该会话的数据和文件，应在 Run 到达终态后执行。

示例禁用系统代理，适用于可直达的本地 / 公司服务；需要代理时在客户端显式配置。公司 CA 应配置在调用端信任库中，不关闭 HTTPS 校验。这里是“调用程序到 UMEKO”的连接，与 UMEKO 的 `MODEL_CA_FILE` 控制的“UMEKO 到模型”的连接不同。
