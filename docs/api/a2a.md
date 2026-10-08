# A2A API

Agent Card：`BASE_URL/.well-known/agent-card.json`；协议入口：`BASE_URL/a2a`。BASE_URL 必须包含部署前缀。Card 可公开读取；协议请求带 `A2A-Version: 1.0`，需要凭据模式下另外带服务 Bearer。管理员开启免鉴权后无需 Bearer，Card 不再声明必需鉴权。免鉴权调用共用任务身份，详见[机器任务](machine-tasks.md)。

## 方法与输入

采用 A2A 1.0 JSON-RPC，方法名为 `SendMessage`、`SendStreamingMessage`、`GetTask`、`ListTasks`、`CancelTask`、`SubscribeToTask`。不是旧版 0.3 的 `message/send` 等方法名。

```json
{
  "jsonrpc": "2.0",
  "id": "request-001",
  "method": "SendMessage",
  "params": {
    "message": {
      "messageId": "document-001",
      "role": "ROLE_USER",
      "parts": [
        {"text": "检查附件并生成报告"},
        {"raw": "5paH5pys", "filename": "input.txt", "mediaType": "text/plain"}
      ]
    },
    "configuration": {"returnImmediately": true},
    "metadata": {"umeko": {"idempotency_key": "document-001"}}
  }
}
```

`raw` 在 JSON 中为 base64，SDK 对象中为 bytes。也可发送 `data` 对象。URL 文件仅接受本服务、同一账号有权读取的任务产物；其他文件用 raw 上传。支持 `metadata.umeko.model_id` 选择模型，未设置时使用默认模型。

`messageId` 必须非空且不超过 150 字符，默认用于幂等。自定义幂等键使用 `metadata.umeko.idempotency_key`。已有任务暂不接受补充输入；`contextId` 只分组自己已有的任务，不继承模型记忆。

## 官方客户端

```python
import asyncio
import os
import httpx
from a2a import types as a2a
from a2a.client import ClientConfig, ClientFactory

async def main():
    base = os.environ["UMEKO_SERVICE_URL"].rstrip("/")
    token = os.getenv("UMEKO_SERVICE_TOKEN")
    headers = {"A2A-Version": "1.0"}
    if token:
        headers["Authorization"] = "Bearer " + token
    async with httpx.AsyncClient(headers=headers, timeout=120) as http:
        client = await ClientFactory(ClientConfig(httpx_client=http, streaming=True)).create_from_url(base)
        request = a2a.SendMessageRequest(message=a2a.Message(
            message_id="document-001", role=a2a.Role.ROLE_USER,
            parts=[a2a.Part(text="检查附件"), a2a.Part(raw=b"example", filename="input.txt", media_type="text/plain")],
        ))
        task_id = None
        async for event in client.send_message(request):
            if event.HasField("task"):
                task_id = event.task.id
            if event.HasField("artifact_update"):
                print(event.artifact_update)
        task = await client.get_task(a2a.GetTaskRequest(id=task_id, history_length=0))
        print(task.status, task.artifacts)

asyncio.run(main())
```

SDK `streaming=False` 使用非流式发送。任务很长时可用 `return_immediately`，拿到 ID 后轮询或订阅，避免代理请求超时。

## 查询、列表、取消与流式

- `GetTask`：`id` 与可选 `historyLength`，0 不返回历史，负数无效。
- `ListTasks`：`pageSize` 最多 100、`pageToken`、`contextId`、`status`、`statusTimestampAfter`、`historyLength`、`includeArtifacts`。返回任务、总数及下一页 token。
- `CancelTask`：`id`，仅活跃任务可取消；已结束返回 TaskNotCancelable。取消请求后通过查询判断最终状态。
- `SubscribeToTask`：`id`，订阅活跃任务；已结束任务用 GetTask 读取结果。

流式响应为 SSE 中的 JSON-RPC 结果。回复增量使用 `TaskArtifactUpdateEvent`，最终回复以 `append=false` 替换已累积的内容；最终状态使用 `TaskStatusUpdateEvent`。产物 URL 指向受保护 REST 下载入口，需带有效服务凭据。

接口只支持 JSONRPC 1.0，未提供推送通知、扩展 Card、多轮输入或其他传输绑定。完整生命周期、额度、保留时间和授权见 [机器任务](machine-tasks.md)与[A2A 架构](../architecture/a2a.md)。A2A 与 MCP 由官方 SDK 路由提供，不包含在 FastAPI 的 OpenAPI 操作清单中。
