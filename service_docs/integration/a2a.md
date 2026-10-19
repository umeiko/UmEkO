# A2A 调用

使用 A2A 1.0 JSON-RPC：先从具体 Agent 基址获取 `/.well-known/agent-card.json`，协议请求发送到 `/a2a`，携带 `A2A-Version: 1.0`。这不是旧版 0.3 的 `message/send` 方法名。

## Agent Card 和 Skills

Agent Card 是智能体的公开名片，包含介绍、服务地址、协议能力和鉴权声明。Skills 来自管理员给这个 Agent 选择的技能简介，可有多个；完整指引、脚本和模型密钥不在 Card 中公开。

## 最小请求

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
        {"text": "检查附件并说明结论"},
        {"raw": "ZXhhbXBsZQ==", "filename": "input.txt", "mediaType": "text/plain"}
      ]
    },
    "configuration": {"returnImmediately": true}
  }
}
```

`raw` 在线上 JSON 中是 base64，在官方 SDK 中直接传 bytes。不要把整个附件 JSON 或 base64 放入 text/data。协议 `url` Part 只接受同一服务有权读取的任务产物；普通下载链接放进 `text`，由 Agent 按需使用下载工具处理。

## 官方 Python 客户端

```python
import asyncio
import os
import uuid
import httpx
from a2a import types as a2a
from a2a.client import ClientConfig, ClientFactory

async def main():
    base = os.environ["UMEKO_SERVICE_URL"].rstrip("/")
    token = os.getenv("UMEKO_SERVICE_TOKEN")
    headers = {"A2A-Version": "1.0"}
    if token:
        headers["Authorization"] = "Bearer " + token
    async with httpx.AsyncClient(headers=headers, timeout=30) as http:
        client = await ClientFactory(ClientConfig(httpx_client=http, streaming=False)).create_from_url(base)
        request = a2a.SendMessageRequest(
            message=a2a.Message(message_id=str(uuid.uuid4()), role=a2a.Role.ROLE_USER,
                parts=[a2a.Part(text="说明你支持的任务")]),
            configuration=a2a.SendMessageConfiguration(return_immediately=True))
        events = [event async for event in client.send_message(request)]
        task = next(event.task for event in events if event.HasField("task"))
        print("请向用户展示工作台链接：", task.metadata["workspaceUrl"])
        terminal = {a2a.TaskState.TASK_STATE_COMPLETED, a2a.TaskState.TASK_STATE_FAILED,
                    a2a.TaskState.TASK_STATE_CANCELED}
        while task.status.state not in terminal:
            await asyncio.sleep(2)
            task = await client.get_task(a2a.GetTaskRequest(id=task.id, history_length=0))
        print(task.status, task.artifacts)

asyncio.run(main())
```

上传文件时在 parts 中增加 `a2a.Part(raw=文件字节, filename="input.png", media_type="image/png")`。JSON 与 SDK 字段名不同，优先按客户端版本使用实际 schema，不混用旧版嵌套文件结构。

## 流式与返回

`SendStreamingMessage` 先给出初始 Task，再返回回复增量、最终产物和终态。Task 的 `metadata.workspaceUrl` / `workspaceHint` 与 `status.message` 中提供可用工作台链接和接续提示。

非流式长任务建议 `returnImmediately=true`，否则请求会等待执行结束，可能先遇到客户端或代理超时。`GetTask` 查询、`SubscribeToTask` 订阅活跃任务、`CancelTask` 请求取消。`ListTasks` 不支持；保存本次 Task ID。

`messageId` 非空且最多 150 字符，默认用于幂等。`contextId` 只对自己已有的任务分组，不继承模型记忆。不能向已有 Task 追加输入，也没有 INPUT_REQUIRED 工作流；多轮处理使用[临时工作台](workspace.md)。
