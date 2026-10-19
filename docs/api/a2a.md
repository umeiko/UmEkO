# A2A API

Agent Card：`BASE_URL/.well-known/agent-card.json`；协议入口：`BASE_URL/a2a`。BASE_URL 必须是用户服务基址加 `/agent/{slug}`，并包含部署前缀。Card 可公开读取；协议请求带 `A2A-Version: 1.0`，需要凭据模式下另外带服务 Bearer。管理员开启免鉴权后无需 Bearer，Card 不再声明必需鉴权。免鉴权调用共用任务身份，详见[机器任务](machine-tasks.md)。

## 方法与输入

在“服务接入”下的“智能体管理”维护名称、介绍、版本、可选链接和提供方，勾选所需默认 Skill。Card 自动生成，私有工作指引和模型密钥不对外披露，详见[智能体管理 API](agents.md)。

`skills` 只包含该 Agent 选择且已启用、可解析的默认 Skill。每项 `id` 使用文件名，名称和介绍取自文档头部，不公开正文、脚本和附属资源。更新默认 Skill 会影响 Card 和新任务；已接收任务保留提交时的主文档副本。

协议接口、输入输出能力和鉴权声明由实际服务配置生成；无法通过提交 Card 修改这些字段。公开 Card 使用 `Cache-Control: no-cache`。Task 的 `metadata.agentId` 标记归属，幂等键与 Context 限定在同一 Agent、同一调用者范围内。

采用 A2A 1.0 JSON-RPC，支持 `SendMessage`、`SendStreamingMessage`、`GetTask`、`CancelTask`、`SubscribeToTask`；`ListTasks` 返回不支持操作。使用提交响应的本次 Task `id` 查询，不能用固定 `metadata.agentId` 代替。不是旧版 0.3 的 `message/send` 等方法名。

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

`raw` 在 JSON 中为 base64，SDK 对象中为 bytes。也可发送普通 `data` 对象，但不能用 text/data 包裹文件编码或附件 JSON。正文中的文件编码、长编码块和过量 Part 会在建任务前被拒绝，返回 `InvalidParams` 与 `retryable=false`，正确附件用法见错误 data；不要原样或拆段重试。规则见[输入门禁](machine-tasks.md#input-validation)。URL 文件仅接受本服务、同一账号有权读取的任务产物；其他文件用 raw 上传。模型由管理员配置，`metadata.umeko.model_id` 不再接受。

上述 URL 文件限制针对协议的 `url` Part；普通 HTTP/HTTPS 下载链接可以直接放进 `text` 需求正文，让 Agent 使用下载工具处理。下载或处理失败交给 Agent 判断，关键材料确实不可用时及时提交情况说明、请调用方提供工作台链接；平台不会因为一次工具失败强制结束任务。

主模型和默认视觉模型的配置方法见[智能体管理](agents.md)。文件序号列表和文件/文件夹下载可通过同一 Agent 的 [REST 接口](machine-tasks.md) 或 [MCP 工具](mcp.md) 完成，仍使用该 Task 的 `id`。

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

完整权限调用方收到的 Task 在 `metadata.workspaceUrl`、`metadata.workspaceHint` 中提供临时工作台地址与提示，`status.message` 同时给出可点击链接。
调用 Agent 应在提交成功后立即展示给用户，邀请其查看进度、文件和工具记录，任务结束后在网页中继续同一会话。流式初始 Task 与查询均携带此信息；非流式可设置 `returnImmediately=true` 立即取得链接。限制与有效期见
[临时工作台](machine-tasks.md#temporary-workspace)。
外部 Agent 也可通过临时会话 REST 接口继续原上下文，并实时同步到已打开的网页；这不会向原 A2A Task 追加消息。
具体调用步骤见[临时工作台与续聊](temporary-workspace.md)。

## 查询、列表、取消与流式

- `GetTask`：`id` 与可选 `historyLength`，0 不返回历史，负数无效。
- `ListTasks`：不提供任务列表，返回不支持操作；保存提交返回的 Task `id` 后使用 `GetTask`。
- `CancelTask`：`id`，仅活跃任务可取消；已结束返回 TaskNotCancelable。取消请求后通过查询判断最终状态。
- `SubscribeToTask`：`id`，订阅活跃任务；已结束任务用 GetTask 读取结果。

流式响应为 SSE 中的 JSON-RPC 结果。回复增量使用 `TaskArtifactUpdateEvent`，最终回复以 `append=false` 替换已累积的内容；最终状态使用 `TaskStatusUpdateEvent`。响应产物的第一个 Part 保留自然语言文本，后续 data Part 提供 Agent 的结果 JSON（text/files）；最终文件由 Agent 明确选择并经平台校验，文件项的 file_id 可交给同一 Agent 的 MCP download_file 或 REST 序号下载入口。产物 URL 指向受保护 REST 下载入口，需带有效服务凭据。

接口只支持 JSONRPC 1.0，未提供推送通知、扩展 Card、多轮输入或其他传输绑定。完整生命周期、额度、保留时间和授权见 [机器任务](machine-tasks.md)与[A2A 架构](../architecture/a2a.md)。A2A 与 MCP 由官方 SDK 路由提供，不包含在 FastAPI 的 OpenAPI 操作清单中。
