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

`raw` 在线上 JSON 中是 base64，在官方 SDK 中直接传 bytes。不要把整个附件 JSON 或 base64 放入 text/data。

## 用 URL 提供图片或文档

如果材料在一个可下载的网址上，可以直接把链接写进 `text`，也可以使用 `url` Part：

```json
[
  {"text": "请分析这两张图片"},
  {"url": "https://files.example.invalid/image-1.png"},
  {"url": "https://files.example.invalid/image-2.png"}
]
```

服务将输入中的链接按顺序附到 Agent 的需求正文末尾：`用户的请求还附带了这些url：<URL1>; <URL2>`。可以只提供 url Part；链接也占用需求的 200000 字符预算和消息的 64 个 Part 预算。文件字节或 data URL 仍请使用 raw。

协议接收层只转交链接，Agent 按需要尝试下载；链接不会自动成为工作区附件，也不会自动从旧任务复制产物。已在当前会话内的附件，可以在需求中直接说明文件名。下载仍遵循服务配置的网络与证书限制，失败时由 Agent 说明情况、提供可用临时工作台链接并提示补充材料。返回产物的 url 继续用于授权下载。

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
        terminal = {a2a.TaskState.TASK_STATE_COMPLETED, a2a.TaskState.TASK_STATE_FAILED,
                    a2a.TaskState.TASK_STATE_CANCELED}
        while task.status.state not in terminal:
            await asyncio.sleep(2)
            task = await client.get_task(a2a.GetTaskRequest(id=task.id, history_length=0))
        if task.status.state == a2a.TaskState.TASK_STATE_COMPLETED:
            for artifact in task.artifacts:
                for part in artifact.parts:
                    if part.WhichOneof("content") == "text":
                        print(part.text)
                    elif part.WhichOneof("content") == "url":
                        print(artifact.name, part.url)
        else:
            print(task.status)

asyncio.run(main())
```

上传文件时在 parts 中增加 `a2a.Part(raw=文件字节, filename="input.png", media_type="image/png")`。JSON 与 SDK 字段名不同，优先按客户端版本使用实际 schema，不混用旧版嵌套文件结构。

## 流式与返回

`SendStreamingMessage` 先给出初始 Task，再返回回复增量、最终产物和终态。Task 的 `metadata.workspaceUrl` / `workspaceHint` 保留可用工作台链接和接续提示；完成后的 `status.message` 直接返回正文，不再附加工作台链接。最终流式状态采用同样规则。

非流式长任务建议 `returnImmediately=true`，否则请求会等待执行结束，可能先遇到客户端或代理超时。`GetTask` 查询、`SubscribeToTask` 订阅活跃任务、`CancelTask` 请求取消。`ListTasks` 不支持；保存本次 Task ID。

`messageId` 非空且最多 150 字符，默认用于幂等。`contextId` 只对自己已有的任务分组，不继承模型记忆。不能向已有 Task 追加输入，也没有 INPUT_REQUIRED 工作流；多轮处理使用[临时工作台](workspace.md)。

## 如何直接取得结果

`GetTask` 返回 `TASK_STATE_COMPLETED` 后，调用 Agent 应把结果正文和交付文件直接呈现给用户，无需再调用别的接口、也不要求用户打开工作台。`artifacts` 中 `artifactId=response` 的文本 Part 是正文，data Part 含 `text/files`；其余文件产物中的 url 可下载文件。不要把整个 Task JSON 原样展示成答案。

`read_results` 是 MCP 的工具名，不是另一个 A2A 方法。需要获取临时工作台续聊后的最新结果时，由调用程序 GET `metadata.resultsUrl`，取得相同的 `{ready, text, files, ...}` JSON。`ready=true` 才有通过校验的结果；`ready=false` 应检查 status/error。不要让用户访问此 JSON 地址，也不要重复提交原任务。

Agent Card 的可选扩展 `urn:umeko:a2a:task-results:v1` 提供 GET 地址模板、`resultsUrl` 字段名和权限说明。地址包含完整部署前缀及当前 Agent 路径，不用手拼。需要 `tasks:read` 和同一调用身份；OAuth token 必须面向扩展中的 `oauthResource`（当前 Agent 的 `/v1/tasks`），仅针对 `/a2a` 的令牌不能跨用。免鉴权时无需 Bearer；下载文件另需 `artifacts:read`。

工作台仅在用户希望继续处理、查看执行细节或确需补资料时提供。已经成功拿到结果时，直接交付结果即可。
