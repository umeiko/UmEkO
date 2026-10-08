# 流式事件

**接口：`GET /v1/runs/{run_id}/events`，认证：`umeko_auth` Cookie。** 返回 `Content-Type: text/event-stream`，配有 `Cache-Control: no-cache` 和 `X-Accel-Buffering: no`。

## 帧与重连

```text
id: 3
event: assistant.delta
data: {"id":3,"run_id":"run_example","session_id":"session_example","type":"assistant.delta","timestamp":"2026-10-08T00:00:00+00:00","data":{"text":"你好"}}

```

每帧以空行结束。`data` 是完整事件对象，不是裸文本。事件 ID 在单个 Run 中从 1 递增；不同 Run 的 ID 不能互相比。

重连可使用 `Last-Event-ID: 3`，或查询 `?after=3`。两者都提供时 Header 优先。服务只返回 ID **大于**游标的事件。客户端按 `(run_id, id)` 去重，并忽略 `: keep-alive` 注释。

浏览器 `EventSource` 要监听具名事件，例如 `addEventListener("assistant.delta", ...)`；这里不是所有帧都送到 `onmessage`。同站 Cookie 会随请求发送，原生 EventSource 不支持随意添加 Bearer Header。

## 当前事件

| 类型 | `data` 常用字段 | 含义 |
| --- | --- | --- |
| `run.queued` | 空对象 | 等待执行 |
| `run.started` | 空对象 | 开始执行 |
| `run.cancelling` | 空对象 | 已收到取消请求 |
| `run.completed` | `reply` | 成功终态 |
| `run.failed` | `error` | 失败终态 |
| `run.cancelled` | `reply` | 取消终态 |
| `assistant.delta` | `text` | 助手正文增量 |
| `reasoning.status` | `status: thinking` | 推理状态 |
| `reasoning.delta` | `text` | 推理文字增量 |
| `tool.started` | `name`、`arguments` | 工具开始 |
| `tool.progress` | `name`、`output_delta` | 工具中间输出 |
| `tool.completed` | `name`、`result` | 工具结果 |
| `progress.updated` | `message` | 阶段说明 |
| `workspace.changed` | `reason` | 提醒客户端刷新文件树 |
| `resource.activated` | `kind`、`name` 等 | 本轮激活的资源 |
| `usage.delta` | `chars`、`kind` | 字符量统计，非供应商计费 token |
| `subagent.started` | `task` | 子 Agent 开始 |
| `subagent.delta` | `text` | 子 Agent 文字增量 |
| `subagent.reasoning.delta` | `text` | 子 Agent 推理增量 |
| `subagent.tool.started` / `.completed` | `name`、`arguments` / `result` | 子 Agent 工具 |
| `subagent.usage` | `chars` | 子 Agent 字符统计 |
| `subagent.completed` / `.failed` / `.cancelled` | `result` 或 `error` | 子 Agent 结束信息 |

增量事件是正文片段，需要按顺序追加；终态中的 `reply` 是最终答案，不能再次简单追加导致重复。工具参数和结果可包含字符串或结构化值，应按实际类型处理。未知事件类型可忽略，新增字段不应使客户端崩溃。

## 生命周期与故障判断

Run 到达终态且待发送事件已耗尽后，服务结束 SSE。客户端收到终态应关闭 EventSource，避免自动重连循环。网络断开不表示执行完成，查询 Run 判断状态。

事件缓冲只在当前进程中，不是持久化日志。断开连接不会取消 Run；重启后无法依靠 `Last-Event-ID` 恢复旧 Run。

如果页面能打开但回答迟迟不显示，依次检查：创建 Run 是否成功；事件 URL 是否包含正确前缀；SSE 是否 `200 text/event-stream`；是否收到 `run.failed`；是否被代理缓冲；模型 HTTPS 是否信任公司 CA。不要把所有无输出都归因于前端。

源码：[events.py](https://github.com/umeiko/UmEkO/blob/main/umeko/events.py)、[runner.py](https://github.com/umeiko/UmEkO/blob/main/umeko/runner.py)、[HTTP SSE](https://github.com/umeiko/UmEkO/blob/main/umeko/server/app.py)。
