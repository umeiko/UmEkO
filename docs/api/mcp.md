# MCP API

入口为用户服务基址加 `/agent/{slug}/mcp`，传输为 Streamable HTTP。需要凭据模式下，在管理端“服务接入”创建凭据，客户端发送 `Authorization: Bearer <token>`；管理员开启免鉴权后可省略此 Header。服务需要已配置并激活的 Provider / Model。免鉴权调用共用任务身份，详见[机器任务](machine-tasks.md)。

## 工具

客户端的 `UMEKO_SERVICE_URL` 必须设为 `/agent/{slug}` 对应的完整地址，以使用指定 Agent 的模型和技能配置。MCP 初始化仍使用平台名 UMEKO，具体 Agent 通过 `get_agent_info` 识别。任务查询、资源读取和取消限定在当前 Agent 的调用者归属内。

| 工具 | 参数 | 结果 |
| --- | --- | --- |
| `get_agent_info` | 无 | 当前路径对应的公开 Agent Card，含介绍和实际披露的技能 |
| `submit_task` | `prompt`，可选 `files`、`idempotency_key` | 立即返回本次执行的 `id/task_id`、`agent_id`、临时工作台链接与用户接续提示 |
| `get_task` | `task_id` | 状态、最终回复、错误、产物与到期时间 |
| `list_file` | `task_id`，可选 `directory_id` | 当前目录的直接子项，包含文件名、类型、大小和稳定序号 `file_id` |
| `download_file` | `task_id`、`file_id` | 受保护的 HTTP 下载链接；文件夹自动打包 ZIP |
| `cancel_task` | `task_id` | 请求取消后的 Task |
| `read_results` | `task_id` | `ready`、自然语言 `text`、最终文件 `files`、结果更新时间及执行/节点状态 |

提交的 `files` 为 `[{"name":"input.txt","content_base64":"..."}]`，不接受服务器路径。输入限制、权限与幂等规则见 [机器任务](machine-tasks.md)。`read_results` 读取持久化的结果 JSON，不再次调用模型、不读取文件字节；文件统一使用 `download_file` 下载。

`tools/list` 会在 `submit_task.files` 的 JSON Schema 中明确披露 `name`、`content_base64` 和限制。文件编码不能放进 `prompt`，也不能粘贴 data URL；这类输入会在建任务前直接拒绝。检查 `is_error` 和 `structured_content["error"]`，按 `file_transport` 修正，`retryable=false` 时不要原样重试。完整规则见[输入门禁](machine-tasks.md#input-validation)。

普通 HTTP/HTTPS 下载链接可以写进 `prompt`，由 Agent 按需尝试下载。下载和处理失败不触发新的强制门禁：Agent 自行判断是否缺少关键材料，无法继续时提交原因和补齐方式，并请调用方提供工作台链接；可选资料失败时仍可继续其余工作。

## 最终结果

机器任务运行时向主 Agent 注入专用的 `submit_results` 工具和提交指引。Agent 调用 `submit_results(text="自然语言结果", files=[{"path":"generate/final.drawio", "description":"可编辑图表"}])` 提交答案，普通聊天回复无需写成独立 JSON。工具即时校验参数、真实文件和会话边界；失败时把原因返回模型修正，成功后直接完成本轮，不再依赖下一次模型回复。平台持久化明确选择的文件并分配稳定的 `file_id`。没有文件时使用空数组；不会扫描目录补齐清单，也不把草稿自动认作最终产物。

`submit_results` 是被调用 Agent 的内部工具，不属于对外 MCP 工具列表，也不暴露给普通工作台会话或文件子 Agent。机器临时工作台续聊会保留这个工具，每轮独立提交；若模型先用普通文字收尾，平台给予一次提交提醒，仍未成功调用时才报告未提交答案。既有结果继续由 `read_results` 读取，调用方不用改为解析模型正文。

`read_results` 返回如下结构，`files[].file_id` 可直接交给 `download_file`，无需先列目录寻找文件：

```json
{"task_id":"task_...","status":"completed","ready":true,"text":"已完成分析。","files":[{"file_id":1,"name":"final.drawio","path":"generate/final.drawio","type":"file","size":1234,"description":"可编辑图表"}],"updated_at":"...","error":null,"workspace_state":"available"}
```

结果读取需要 `tasks:read`，实际文件下载仍需要 `artifacts:read`。任务未完成时 `ready=false`；历史任务没有结果 JSON 时会说明缺失，不从旧产物列表推测最终文件。临时工作台续聊后，同一 `task_id` 返回最近一次通过校验的结果，原任务执行回复和状态仍保留。节点过期后可以读取保留的结果文字与文件元数据，下载则返回不存在。

主模型与视觉模型在智能体管理中配置，调用方不能选择模型；`list_models` 和 `list_tasks` 不再提供。查询、取消与文件访问使用提交返回的本次 `task_id`，仍限定当前 Agent 和调用方归属。固定的 `agent_id` 标记服务归属，不能代替执行 ID。

`list_file(task_id)` 仅列出 `workspace`、`attachments`、`generate` 三个顶层目录；指定其中的文件夹 `file_id` 为 `directory_id` 时，只展开该文件夹的直接子项，不递归展开。序号按任务持久保存，不因排序或新增文件重新分配；不同任务的序号不可混用。`download_file` 返回的 URL 含完整用户部署前缀和 `/agent/{slug}`；需要凭据模式下，下载 GET 携带服务凭据。文件夹 ZIP 保留内部层次与空目录，临时归档在响应完成后清理。会话私有配置、链接和外部路径不提供下载，节点过期后文件访问返回不存在。

## 使用契约提示词

`prompts/list` 披露 `task_lifecycle`，无参数；首次接入可用 `prompts/get` 读取。它说明提交和状态的区别、保存本次 `task_id`、完成后用 `read_results` 读取最终清单并按序号下载、避免重复提交、取消、缺资料时交付真实工作台链接，以及节点过期后的处理。

```python
guide = await client.get_prompt("task_lifecycle")
```

原 `read_artifact` 工具与二进制产物资源模板已移除，MCP 不再内联传输文件内容。

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
            if task["workspace_url"]:
                print("可在临时工作台查看进度并继续处理：", task["workspace_url"])
            while task["status"] not in {"completed", "failed", "cancelled"}:
                await asyncio.sleep(1)
                result = await client.call_tool("get_task", {"task_id": task["id"]})
                if result.is_error:
                    raise RuntimeError(str(result.content))
                task = result.structured_content
            result = await client.call_tool("read_results", {"task_id": task["task_id"]})
            if result.is_error:
                raise RuntimeError(str(result.content))
            print(result.structured_content["text"])
            for file in result.structured_content["files"]:
                download = await client.call_tool("download_file", {"task_id": task["task_id"], "file_id": file["file_id"]})
                print(file["name"], download.structured_content["download_url"])

asyncio.run(main())
```

业务错误通过 MCP 工具错误返回，客户端检查 `is_error`。身份无效为 HTTP 401。调用方断开后，已经提交的业务任务继续运行；需要停止时调用 `cancel_task`。

完整权限任务的响应还含 `workspace_url`、`workspace_hint`。提交成功的文字回执另附可点击链接；调用 Agent 应立即展示给用户，邀请其查看进度、文件和工具记录，任务结束后可继续同一会话。
链接包含用户服务前缀，且只能访问该任务的原会话；权限、有效期与限制见[临时工作台](machine-tasks.md#temporary-workspace)。
外部 Agent 可通过临时会话 REST 接口继续原上下文，已经打开的网页会自动同步输入、流式回复和工具记录。
再次 `submit_task` 使用新幂等键会建立新会话；沿用原会话的示例见[临时工作台与续聊](temporary-workspace.md)。

当前不提供 stdio 或 MCP 原生 Tasks 扩展。需要交互式 OAuth 的客户端不一定能直接使用本服务；先确认客户端支持自定义 Bearer Header 或 OAuth `client_credentials`。授权和生产代理配置见 [机器任务](machine-tasks.md)与[部署指南](../deployment.md)。
