# MCP API

入口为用户服务基址加 `/mcp`，传输为 Streamable HTTP。需要凭据模式下，在管理端“服务接入”创建凭据，客户端发送 `Authorization: Bearer <token>`；管理员开启免鉴权后可省略此 Header。服务需要已配置并激活的 Provider / Model。免鉴权调用共用任务身份，详见[机器任务](machine-tasks.md)。

## 工具

| 工具 | 参数 | 结果 |
| --- | --- | --- |
| `list_models` | 无 | 默认模型 ID、可选模型 ID / 名称 / vision / Provider 名称 |
| `submit_task` | `prompt`，可选 `files`、`model_id`、`idempotency_key` | Task 与任务 ID，立即返回 |
| `get_task` | `task_id` | 状态、最终回复、错误、产物与到期时间 |
| `list_tasks` | 可选 `limit=50`、`offset=0` | `tasks` 与 `total`，最多 100 条 |
| `cancel_task` | `task_id` | 请求取消后的 Task |
| `read_artifact` | `task_id`、`artifact_id` | `name/media_type` 和 UTF-8 `text` 或二进制 `content_base64` |

`files` 为 `[{"name":"input.txt","content_base64":"..."}]`，不接受服务器路径。输入限制、权限与幂等规则见 [机器任务](machine-tasks.md)。`read_artifact` 与资源读取上限均为 256 KiB；大文件使用 GET Task 的 `download_url`，下载仍需授权。

资源模板：`umeko://tasks/{task_id}/artifacts/{artifact_id}`。模板读取返回二进制资源（blob）；需要文本内容可直接使用 `read_artifact`。

## 官方 Python 客户端示例

下面使用 `mcp` 2.x 和它所使用的 `httpx2`。调用方的 URL 与服务凭据由其安全配置提供。

```python
import asyncio
import os
import httpx2
from mcp.client import Client
from mcp.client.streamable_http import streamable_http_client

async def main():
    base = os.environ["UMEKO_SERVICE_URL"].rstrip("/")
    token = os.getenv("UMEKO_SERVICE_TOKEN")
    headers = {"Authorization": "Bearer " + token} if token else {}
    async with httpx2.AsyncClient(headers=headers) as http:
        async with Client(streamable_http_client(base + "/mcp", http_client=http), cache=None) as client:
            print([tool.name for tool in (await client.list_tools()).tools])
            result = await client.call_tool("submit_task", {"prompt": "说明你可以如何处理文件"})
            if result.is_error:
                raise RuntimeError(str(result.content))
            task = result.structured_content
            while task["status"] not in {"completed", "failed", "cancelled"}:
                await asyncio.sleep(1)
                result = await client.call_tool("get_task", {"task_id": task["id"]})
                if result.is_error:
                    raise RuntimeError(str(result.content))
                task = result.structured_content
            print(task)

asyncio.run(main())
```

业务错误通过 MCP 工具错误返回，客户端检查 `is_error`。身份无效为 HTTP 401。调用方断开后，已经提交的业务任务继续运行；需要停止时调用 `cancel_task`。

当前不提供 stdio 或 MCP 原生 Tasks 扩展。需要交互式 OAuth 的客户端不一定能直接使用本服务；先确认客户端支持自定义 Bearer Header 或 OAuth `client_credentials`。授权和生产代理配置见 [机器任务](machine-tasks.md)与[部署指南](../deployment.md)。
