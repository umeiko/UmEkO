# 一次性调用 API

**已实现：** `POST /v1/proxy/sessions` 把创建会话、上传文件、挂载技能和提交问题合并。这里的 proxy 是业务便捷接口，不是 NGINX 网络反向代理。

## 创建任务

需要先通过用户登录保存 `umeko_auth` Cookie。请求使用 `multipart/form-data`：

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `prompt` | 是 | 去掉首尾空白后不能为空 |
| `skill` | 否 | 技能包名称；从默认技能或服务器技能库查找 |
| `files` | 否 | 可重复的上传文件，保存到会话 workspace |

```python
from pathlib import Path
import httpx

base = "http://127.0.0.1:8000"
with httpx.Client(timeout=60, trust_env=False) as client:
    client.post(base + "/v1/auth/login", json={
        "username": "your-user", "password": "your-password"
    }).raise_for_status()
    with Path("input.zip").open("rb") as file:
        response = client.post(base + "/v1/proxy/sessions",
            data={"prompt": "检查上传文档与图片的一致性"},
            files=[("files", ("input.zip", file, "application/zip"))])
    response.raise_for_status()
    created = response.json()
    print(created["session_id"], created["run_id"])
```

成功返回 `201 ProxySessionView`：

```json
{"session_id":"session_example","run_id":"run_example","skill":null,"files":["workspace/input.zip"]}
```

不指定技能时使用普通 Agent 能力。指定技能前确保它已存在；不存在返回 `404`。文件路径说明会加入问题中，文件不是通过 Run 的 `attachments` 参数传入。

## 状态与交付物

`GET /v1/proxy/sessions/{session_id}` 返回 `ProxyStatusView`：

| 字段 | 说明 |
| --- | --- |
| `session_id`、`run_id` | 会话与可空 Run 标识 |
| `status` | 推断出的状态 |
| `reply` | 最后助手结论 |
| `progress` | 从工具历史推断的阶段描述 |
| `result` | 解析到的 `qc-report*.json` 内容，否则 `null` |
| `artifacts` | 筛选后的 `qc-report*.zip/html/json` 交付物 |

这个接口含文档质检领域的报告筛选逻辑。其他技能的普通产物请从 `/v1/sessions/{id}/artifacts` 查询。

状态查询先看活跃 Run，再看助手历史。Run 结束后内存 holder 被清空，失败且没有助手消息的情况可能显示 `unknown`，`run_id` 也可能为空。**保留创建时返回的 Run ID，用 `GET /v1/runs/{run_id}` 判断最终成功、失败或取消。** 该查询仅在原进程存活时有效。

## 生命周期限制

这个接口仍创建普通持久化 Session，没有自动到期、幂等键、服务凭据或持久化工单。它可能在后续技能校验失败前已创建会话；调用失败不代表完全没有创建数据。

结果下载完并确认 Run 已结束后，调用 `DELETE /v1/sessions/{session_id}` 清理。需要大规模服务调用时，按 [TaskService 设计](../architecture/api-service.md)增加有界队列与 TTL，不依靠无限创建会话。
