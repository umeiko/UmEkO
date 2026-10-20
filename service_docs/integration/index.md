# 选择接入方式

三种机器入口共用同一套任务、会话、额度和文件生命周期。先取得管理员公布的**具体智能体基址**，例如：

```text
https://agents.example.internal/workbench/agent/reviewer
```

| 方式 | 适用对象 | 提交后怎么取结果 |
| --- | --- | --- |
| [REST](rest.md) | 业务程序、脚本、已有 HTTP 集成 | 取得 Task ID，查询状态和 results，按 file_id 下载 |
| [MCP](mcp.md) | 支持 MCP 的外部 Agent | submit_task → get_task → read_results → download_file |
| [A2A](a2a.md) | 需要 Agent Card 发现与协议协作的 Agent | GetTask 完成后直接交付 artifacts 正文与文件 |

## 接入前确认

1. 使用的是用户服务地址和具体 Agent 路径，不是管理端或上游模型地址。
2. 确认当前服务采用凭据还是免鉴权。需要凭据时传服务 Bearer，不传 Provider 的模型 Key。
3. 了解技能输入要求及返回格式。MCP 使用 `get_agent_info`；A2A 获取 Agent Card。
4. 保存本次提交返回的 Task ID 和工作台链接，不用固定的 agent_id 代替任务 ID。
5. 正常完成时直接交付正文和文件；工作台链接先保存，仅在用户想查看进度、接续或确需补材料时提供。

## 输入与文件

需求文字可以包含普通 HTTP/HTTPS 文件链接。文件字节通过协议的附件字段传输，不把 base64 或 data URL 粘贴进聊天正文。最多 10 个附件、解码后合计 20 MiB，完整 HTTP 请求还受 30 MiB 限制；文本最多 200000 字符。A2A 一条消息最多 64 个 Part。

普通下载链接不在提交阶段预先下载；下载或处理是否构成阻塞由执行 Agent 判断。错误附件结构则在建立任务前拒绝，不占用模型调用。详见[注意事项](troubleshooting.md)。

## 权限

完整流程一般需要 `tasks:create`、`tasks:read`、`tasks:cancel`、`artifacts:read`。只有具备全部四项的调用方才收到可用临时工作台链接；否则链接字段为空。查询、取消与下载还检查当前 Agent 和调用者归属。

免鉴权适合明确接受共享身份的协作环境；它不按 IP 隔离用户。带凭据时仍按服务账号检查权限，无效凭据不会降级成免鉴权。
