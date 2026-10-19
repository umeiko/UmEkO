# MCP 调用

入口为具体 Agent 基址加 `/mcp`，采用 Streamable HTTP。当前提供业务 Task，不是 MCP 原生 Tasks 扩展，也不提供 stdio。

## 工具清单

| 工具 | 用途 |
| --- | --- |
| `get_agent_info` | 当前 Agent 的公开介绍与技能简介 |
| `submit_task` | 提交需求和可选附件，立即返回 task_id 与可用 workspace_url |
| `get_task` | 查询本次任务，不重复执行模型 |
| `read_results` | 取得最新已校验的 text 和 files |
| `list_file` | 列当前目录的直接子项，指定 directory_id 展开下一层 |
| `download_file` | 用 task_id/file_id 取得 HTTP 下载地址，目录为 ZIP |
| `cancel_task` | 请求取消 |

首次接入可读取 `prompts/get` 的 `task_lifecycle`，了解提交、轮询、下载与人工接续的约定。工具定义通过 `tools/list` 披露，不存在 `/mcp/tools/list` HTTP 地址。内部文件工具和技能脚本不会自动变成独立 MCP 工具。

## 官方 Python 客户端示例

以下使用 `mcp` 2.x 及其使用的 `httpx2`：

```python
import asyncio
import os
import uuid
import httpx2
from mcp.client import Client
from mcp.client.streamable_http import streamable_http_client

async def main():
    base = os.environ["UMEKO_SERVICE_URL"].rstrip("/")
    token = os.getenv("UMEKO_SERVICE_TOKEN")
    headers = {"Authorization": "Bearer " + token} if token else {}
    async with httpx2.AsyncClient(headers=headers) as http:
        async with Client(streamable_http_client(base + "/mcp", http_client=http), cache=None) as client:
            await client.call_tool("get_agent_info", {})
            receipt = await client.call_tool("submit_task", {
                "prompt": "说明你可以如何处理文件", "idempotency_key": str(uuid.uuid4())})
            if receipt.is_error:
                raise RuntimeError(str(receipt.content))
            task = receipt.structured_content
            if task.get("workspace_url"):
                print("请向用户展示工作台链接：", task["workspace_url"])
            while task["status"] not in {"completed", "failed", "cancelled"}:
                await asyncio.sleep(2)
                response = await client.call_tool("get_task", {"task_id": task["task_id"]})
                if response.is_error:
                    raise RuntimeError(str(response.content))
                task = response.structured_content
            response = await client.call_tool("read_results", {"task_id": task["task_id"]})
            if response.is_error:
                raise RuntimeError(str(response.content))
            result = response.structured_content
            print(result["text"] if result["ready"] else result["error"])
            for file in result["files"]:
                download = await client.call_tool("download_file", {
                    "task_id": task["task_id"], "file_id": file["file_id"]})
                if download.is_error:
                    raise RuntimeError(str(download.content))
                print(file["name"], download.structured_content["download_url"])

asyncio.run(main())
```

## 附件与长任务

`submit_task.files` 是 `[{"name":"input.png","content_base64":"<文件字节的base64>"}]`，普通 HTTP/HTTPS 下载链接可以放在 prompt 中。不要把 base64 塞进 prompt；结构错误时检查 `is_error`、`structured_content.error` 和正确上传提示。

图像推理可能很久，但提交请求很快返回，执行在服务端继续。调用方用 get_task 轮询，不需保持一条工具请求等待全部推理完成。断开 MCP 连接不会自动取消任务。MCP 不持续推送业务回复增量；要看实时对话可使用工作台，或选择 A2A/SSE。

当前调用方不能选择机器任务的模型，也没有模型列表或任务列表接口。不要用固定 agent_id 查询本次执行。
