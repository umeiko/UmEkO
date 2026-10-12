# MCP API

入口为用户服务基址加 `/agent/{slug}/mcp`，传输为 Streamable HTTP。需要凭据模式下，在管理端“服务接入”创建凭据，客户端发送 `Authorization: Bearer <token>`；管理员开启免鉴权后可省略此 Header。服务需要已配置并激活的 Provider / Model。免鉴权调用共用任务身份，详见[机器任务](machine-tasks.md)。

## 工具

客户端的 `UMEKO_SERVICE_URL` 必须设为 `/agent/{slug}` 对应的完整地址，以使用指定 Agent 的模型和技能配置。MCP 初始化仍使用平台名 UMEKO，具体 Agent 通过 `get_agent_info` 识别。任务查询、资源读取和取消限定在当前 Agent 的调用者归属内。

| 工具 | 参数 | 结果 |
| --- | --- | --- |
| `get_agent_info` | 无 | 当前路径对应的公开 Agent Card，含介绍和实际披露的技能 |
| `list_models` | 无 | 当前 Agent 允许披露的主模型 ID / 名称 / vision / Provider 名称，含默认主模型；默认视觉模型 ID 按披露范围返回 |
| `submit_task` | `prompt`，可选 `files`、`model_id`、`idempotency_key` | Task 与任务 ID，立即返回 |
| `get_task` | `task_id` | 状态、最终回复、错误、产物与到期时间 |
| `list_tasks` | 可选 `limit=50`、`offset=0` | `tasks` 与 `total`，最多 100 条 |
| `cancel_task` | `task_id` | 请求取消后的 Task |
| `read_artifact` | `task_id`、`artifact_id` | `name/media_type` 和 UTF-8 `text` 或二进制 `content_base64` |

`files` 为 `[{"name":"input.txt","content_base64":"..."}]`，不接受服务器路径。输入限制、权限与幂等规则见 [机器任务](machine-tasks.md)。`read_artifact` 与资源读取上限均为 256 KiB；大文件使用 GET Task 的 `download_url`，下载仍需授权。

`list_models` 受智能体配置中的“主模型披露”约束，默认主模型始终可用。`submit_task.model_id` 必须是已披露模型；REST 和 A2A 使用相同限制。`default_vision_model_id` 仅在显式配置且该模型也已披露时返回，`null` 表示自动选择或未公开此 ID；不改变内部视觉模型配置。视觉模型在智能体管理中配置，`submit_task.model_id` 只覆盖主模型。选择规则见[智能体管理](agents.md)。

资源模板：`umeko://tasks/{task_id}/artifacts/{artifact_id}`。模板读取返回二进制资源（blob）；需要文本内容可直接使用 `read_artifact`。

管理端“服务接入 → 智能体管理 → 配置与入口 → MCP 披露”可查看这些接口的实际定义，包括输入、返回 JSON Schema、只读等标注、资源模板和原始 JSON。该视图与对外 MCP 服务复用同一套 SDK 注册，读取定义不产生任务，不要求从管理服务器连回公网，也不需要额外提供调用凭据。管理 API 为 `GET /admin/v1/agents/{agent_id}/mcp`，响应含 `endpoint`、`auth_mode`、`enabled`、`server`、`transport`、`tools`、`resources`、`resourceTemplates`、`prompts`；仅接受管理员 Cookie。

`tools/list` 是 JSON-RPC 方法，向 `/agent/{slug}/mcp` 发送 POST；不存在 `/mcp/tools/list` HTTP 路由。不同 Agent 共用这些服务接口，执行任务时才应用各自的配置。Agent 内部文件、图像工具和所选 Skill 不自动成为独立 MCP 工具；具体能力由 `get_agent_info` 返回的 Agent Card 披露。当前返回 Schema 采用通用对象结构，完整字段约定仍见各专题文档，不把未声明的字段当成 SDK 校验保证。

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

完整权限任务的响应还含 `workspace_url`、`workspace_hint`，调用 Agent 可把链接交给用户打开临时工作台继续处理。
链接包含用户服务前缀，且只能访问该任务的原会话；权限、有效期与限制见[临时工作台](machine-tasks.md#temporary-workspace)。
外部 Agent 可通过临时会话 REST 接口继续原上下文，已经打开的网页会自动同步输入、流式回复和工具记录。
再次 `submit_task` 使用新幂等键会建立新会话；沿用原会话的示例见[临时工作台与续聊](temporary-workspace.md)。

当前不提供 stdio 或 MCP 原生 Tasks 扩展。需要交互式 OAuth 的客户端不一定能直接使用本服务；先确认客户端支持自定义 Bearer Header 或 OAuth `client_credentials`。授权和生产代理配置见 [机器任务](machine-tasks.md)与[部署指南](../deployment.md)。
