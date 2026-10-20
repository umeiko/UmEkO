# 智能体发布与冒烟测试

## 目录

1. 配置与发布
2. 不调用模型的发现检查
3. 最小真实任务
4. MCP 和 A2A 检查
5. 结果、排错与清理

管理基址、用户服务基址、具体 Agent 基址是三个不同对象。使用实际管理返回的 `endpoints`，不要把本地端口拼进对外入口。

## 1. 配置与发布

先 GET `/admin/v1/agents` 取得现有智能体、模型和技能选项。检查重名和已有 slug，按用户目标决定新增还是更新；不要每次都创建一个新智能体。

新增 POST `/admin/v1/agents` 的例子如下，执行时把模型 ID 和技能名替换为已读取的实际值。空 skill_names 适合不依赖技能的文本 Agent：

```json
{
  "slug": "document-assistant",
  "name": "文档助手",
  "description": "根据用户提供的材料回答问题并说明依据。",
  "system_prompt": "依据已取得的材料回答；缺少关键材料时说明缺少什么，并提供可用临时工作台链接。",
  "default_model_id": "已读取的主模型ID",
  "default_vision_model_id": "已读取的视觉模型ID",
  "skill_names": [],
  "enabled": true
}
```

没有视觉模型时省略 `default_vision_model_id`；需要技能时选已有合法下发入口，并确认所需脚本/配置已获明确审批。不要为了让测试通过而自动批准代码或移除业务门禁。

更新 PUT `/admin/v1/agents/{agent_id}` 是完整表单，先 GET 单个记录，保留非目标字段，只传当前 schema 允许的字段；不能把 id、endpoints、created_at 传回去。已有 slug 不可改；使用 enabled 控制是否发布。

保存后回读配置并记录以下返回值：

| endpoints 字段 | 发布接口 |
| --- | --- |
| agent_card | `<用户基址>/agent/<slug>/.well-known/agent-card.json` |
| mcp | `<用户基址>/agent/<slug>/mcp` |
| a2a | `<用户基址>/agent/<slug>/a2a` |
| tasks | `<用户基址>/agent/<slug>/v1/tasks` |

如果返回的是环回地址、错误协议或缺少用户前缀，先由部署者核对 `UMEKO_PUBLIC_URL` 和代理规则。不能在报告中把管理端口当作可访问的业务入口。

## 2. 不调用模型的发现检查

这组检查只读取配置和能力，不提交任务：

- 从外部调用方网络 GET endpoints.agent_card，确认名称、介绍、Skills 与选择一致，接口地址都含完整用户前缀和 Agent 路径。
- 管理 API GET `/admin/v1/agents/{id}/card` 和 `/mcp` 可检查服务端保存的 Card 与 MCP 披露，但它们通过不代表外部代理可用。
- 使用官方 MCP 客户端连接 endpoints.mcp，完成握手，调用 tools/list 和 get_agent_info；检查包含 submit_task、get_task、read_results、list_file、download_file、cancel_task。
- 不存在 `/mcp/tools/list` HTTP 路径；握手成功也不证明模型或技能已就绪。

需要机器鉴权时，为业务客户端使用已有的服务凭据。它不能来自 Provider Key 或管理员 Cookie。未带凭据的业务请求应被拒绝；不要为检查方便修改全局鉴权方式。

## 3. 最小真实任务

用户要求发布验收、冒烟测试或明确调用测试时，才执行实际业务；单纯查看配置不发模型请求。使用合成材料，不上传真实客户数据。测试输入应符合 Agent 的能力门禁：文本助手可用简短问候；图片质检必须附上一张合成测试图，不能用 hi 的拒答推断故障。

最小 REST 流程（业务客户端示例依赖 httpx；管理脚本本身仍无依赖）：

```python
import os
import time
import uuid
import httpx

base = os.environ["UMEKO_SERVICE_URL"].rstrip("/")  # 已含 /agent/<slug>
token = os.getenv("UMEKO_SERVICE_TOKEN")
headers = {"Authorization": "Bearer " + token} if token else {}
terminal = {"completed", "failed", "cancelled"}
deadline = time.monotonic() + 120
with httpx.Client(headers=headers, timeout=30, trust_env=False) as client:
    response = client.post(base + "/v1/tasks", json={
        "prompt": "请回复一句简短问候，不调用文件工具。", "files": []
    }, headers={"Idempotency-Key": str(uuid.uuid4())})
    response.raise_for_status()
    task = response.json()
    # workspace_url 是持有者可访问的临时链接，只交给预期用户。
    while task["status"] not in terminal and time.monotonic() < deadline:
        time.sleep(2)
        response = client.get(base + "/v1/tasks/" + task["task_id"])
        response.raise_for_status()
        task = response.json()
    if task["status"] not in terminal:
        print("测试尚未结束：", task["task_id"], task["status"])
    else:
        response = client.get(base + "/v1/tasks/" + task["task_id"] + "/results")
        response.raise_for_status()
        result = response.json()
        print(task["status"], result["text"] if result["ready"] else result["error"])
```

企业 HTTPS 使用本地 CA 配置，保持证书验证。图片/文件放 `files=[{"name":"test.png","content_base64":"文件字节base64"}]`；普通下载 URL 可在 prompt 中给出，不把 base64 放进 prompt。大任务可调整等待预算；到期后报告仍在执行及 task_id，不重复提交来试运气。

## 4. MCP 和 A2A 检查

每种协议最多先提交一个符合能力的合成任务，保留本次 ID 和同一幂等键；不要把重试变成很多重复任务。

### MCP

当前使用 MCP 2.x Streamable HTTP，官方客户端是 `mcp.client.Client` 与 `streamable_http_client`，其 HTTP 客户端为 httpx2：

```python
import httpx2
from mcp.client import Client
from mcp.client.streamable_http import streamable_http_client

# 放入 async 函数中；headers 使用机器 Bearer 或经配置的免鉴权方式。
async with httpx2.AsyncClient(headers=headers) as http:
    async with Client(streamable_http_client(base + "/mcp", http_client=http), cache=None) as client:
        tools = await client.list_tools()
        info = await client.call_tool("get_agent_info", {})
```

实际任务用 call_tool("submit_task", {"prompt":...,"files":[],"idempotency_key":...})。先检查 `is_error`，成功后读取 `structured_content.task_id` 和可用 `workspace_url`，及时将链接交给用户。使用 get_task 轮询、read_results 查业务结果，检查每次 is_error；使用与 REST 相同的终态及时间预算。submit_task 返回快速，不需要保持一条 MCP 工具调用等待整段图像推理。

### A2A

当前是 A2A **1.0** JSON-RPC，非旧版 message/send。发送到 endpoints.a2a，携带 `A2A-Version: 1.0` 与需要时的机器 Bearer，Content-Type 为 application/json：

```json
{
  "jsonrpc": "2.0",
  "id": "smoke-001",
  "method": "SendMessage",
  "params": {
    "message": {
      "messageId": "为本次测试生成唯一ID",
      "role": "ROLE_USER",
      "parts": [{"text": "请回复一句简短问候。"}]
    },
    "configuration": {"returnImmediately": true}
  }
}
```

成功后保留返回的本次 Task ID，读取 `metadata.workspaceUrl`，用 GetTask 轮询到终态；HTTP 200 仍需检查 JSON-RPC error。图片在 JSON 中是单独 Part：`{"raw":"文件字节base64","filename":"test.png","mediaType":"image/png"}`；SDK 的 raw 传 bytes，不把 JSON 的 base64 字符串当成 bytes 直接传。

官方 `a2a-sdk` 1.2.x 使用 `ClientFactory(ClientConfig(httpx_client=http, streaming=False)).create_from_url(base)`、`a2a.SendMessageRequest` 和 `a2a.GetTaskRequest`。官方类型的终态为 TASK_STATE_COMPLETED / FAILED / CANCELED。通过 Agent Card 发现端点；不要猜顶级 /a2a，也不要向已有 Task 强行追加输入。

## 5. 结果、排错与清理

报告至少包含：被改的配置、实际外部地址、通过的协议步骤、每次测试的 task_id、终态、业务输出或错误，以及尚未验证的项目。仅发现页通过不能写“模型调用正常”，任务 completed 也不能替代业务结果检查。缺少图片或文档时说明所缺材料，并把可用工作台链接交给用户，不重复提交同一无效输入。

长任务没有终态时停止无界轮询；按用户授权决定是否取消，取消后观察终态。用管理 API `/admin/v1/tasks/{id}` 和 `/files` 排查上下文、工具记录与文件元数据，不读取无关用户数据。401 核对机器身份，404 核对完整前缀与 slug，400/422 按字段错误修正，429 检查队列和并发，技能信任错误按明确摘要审批流程排查，不关闭校验。

只有用户授权清理时才删除本次临时测试创建的账号或定义；不要删除已有智能体、生产账号或所有任务。节点保留和到期清理由平台生命周期负责。报告中区分本机直连、测试代理和真实外部入口；没有通过实际 ALB 入口验收时不得声称生产 ALB 已通过。
