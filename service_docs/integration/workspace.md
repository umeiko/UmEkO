# 临时工作台与接续

机器提交成功时即可取得临时工作台链接，排队阶段也能打开准备页。权限足够时，接入 Agent 应立即把真实链接交给用户，让其查看对话、工具记录和文件；执行结束后还可以继续同一会话。

| 协议 | 链接字段 |
| --- | --- |
| REST / MCP | `workspace_url` 和 `workspace_hint` |
| A2A | Task `metadata.workspaceUrl`、`metadata.workspaceHint`，以及 `status.message` |

工作台形如 `https://agents.example.internal/workbench/TMP/<随机标识>`。它使用用户服务前缀，没有 `/agent/<slug>`，也没有管理前缀。不要自行拼接或把内部环回地址替换进真实链接。

## 临时工作台的限制

账号、新建会话、会话切换和模型选择不可操作；只能处理当前任务的原 Session。技能仅披露该 Agent 下发的选定技能，默认勾选且不能改选。原任务仍在执行时不能同时再启动一轮。

链接等同于这个会话的访问凭据，拥有链接的人可以读写当前会话，只应交给预期使用者。它不会授予管理权限或其他会话访问权。只有具备四项完整任务 scope 的调用方才收到可用链接；账号停用、删除或到期也会影响访问。

## 缺资料时如何接续

1. 执行 Agent 说明缺少什么、下载或处理为什么失败、已经完成哪些部分。
2. 外层 Agent 将真实工作台链接和待补事项交给用户，避免继续轮询原 Task 等文件自动出现。
3. 用户在工作台上传材料并发送新的要求；这会创建同一 Session 的新 Run。
4. 外层 Agent 可以对原 task_id 再调用 read_results 或 REST results，取得最近一次通过校验的结果。

原 Task 的执行状态和原始回复不会被续聊改写；最新结果清单、消息与文件元数据会继续记录。任务完成后续聊仍是临时节点，不转为永久用户会话。

## 程序也能继续同一会话

下面的 URL 以收到的 workspace_url 为基准，不能改成普通用户或管理入口：

```python
import os
import httpx

workspace = os.environ["UMEKO_WORKSPACE_URL"].rstrip("/")
with httpx.Client(timeout=30) as client:
    response = client.get(workspace + "/v1/temporary")
    response.raise_for_status()
    info = response.json()
    if info["state"] != "ready":
        raise RuntimeError("工作台尚未就绪或已过期")
    session = workspace + "/v1/sessions/" + info["session_id"]
    active = client.get(session + "/active-run")
    active.raise_for_status()
    if active.json() is not None:
        raise RuntimeError("上一轮仍在执行，请稍后再提交")
    response = client.post(session + "/runs", json={
        "input": "请根据刚补充的说明继续处理", "attachments": []})
    response.raise_for_status()
    print(response.json()["id"])
```

已打开的网页会同步输入、流式回复和工具记录。这是同一会话的 REST 续聊，不是向原 A2A Task 追加消息。上传附件使用该临时 Session 的文件接口，仍遵循文件大小与路径约束。
