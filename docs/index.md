# UMEKO 文档

**Unified Multi-agent Execution Kernel & Orchestrator**：把模型调用、工具、文件、会话和用户管理组合成可部署的 Agent 服务。

这份文档先讲清楚当前系统如何工作，再给出 MCP、A2A 和机器调用的扩展方案。你可以从安装开始，也可以直接查接口。

<div class="grid cards" markdown>

- **开始使用**

    安装依赖，配置 Provider，打开工作台并完成第一次提问。

    [快速上手 →](quickstart.md)

- **架构设计**

    CLI、Web Server、API 的现状，以及 MCP / A2A 的接入规划。

    [阅读架构 →](architecture/index.md)

- **API 文档**

    Cookie 登录、Session / Run、文件上传、流式事件与管理接口。

    [调用入门 →](api/quickstart.md)

- **生产部署**

    NGINX / ALB 路径前缀、内网 HTTPS 证书、模型并发和数据保存。

    [部署指南 →](deployment.md)

</div>

## 能力状态

| 能力 | 当前状态 | 阅读入口 |
| --- | --- | --- |
| CLI 对话与共享 Provider 注册表 | 已实现 | [CLI](architecture/cli.md) |
| 用户工作台、独立管理端口 | 已实现 | [Web Server](architecture/webserver.md) |
| REST API、文件处理与 SSE | 已实现 | [API](api/index.md) |
| 每个模型独立的并发额度与调用排队 | 已实现，单进程内共享 | [模型配置](api/admin.md) |
| MCP 服务 | 架构设计，尚无协议端点 | [MCP](architecture/mcp.md) |
| A2A 服务 | 架构设计，尚无 Agent Card / 协议端点 | [A2A](architecture/a2a.md) |
| 机器身份、持久化任务队列、自动过期清理 | 架构设计 | [API 服务](architecture/api-service.md) |

!!! note "文档站与 Agent 服务"
    GitHub Pages 托管的是这份静态文档。Agent 服务仍需运行在你的电脑或服务器上，文档站不会替你运行模型、存储会话或接收业务 API 请求。

接口完整参考与 OpenAPI 文件由当前代码生成，手写指南补充登录、原始文件体和 SSE 等运行约定。后续代码改动会在发布时检查这些文件是否同步。
