# API 文档

以下介绍当前已实现的 HTTP API。另有 [MCP](mcp.md) 与 [A2A](a2a.md) 协议入口，共用[机器任务服务](machine-tasks.md)。

## 地址与认证

| 服务 | 默认地址 | 登录接口 | 登录 Cookie |
| --- | --- | --- | --- |
| 用户 API | `http://127.0.0.1:8000` | `POST /v1/auth/login` | `umeko_auth` |
| 管理 API | `http://127.0.0.1:9000` | `POST /admin/login` | `umeko_admin` |

网页 Session API 使用 Cookie 登录，用户 Cookie 与管理 Cookie 分开。机器 `/v1/tasks`、MCP、A2A 支持服务 Bearer 凭据与 OAuth `client_credentials`。管理接口只能向管理端口调用，并使用管理员 Cookie。

带路径前缀时，用户服务基址包含完整前缀，例如：

```text
BASE_URL=https://example.internal/doc-master/consistency/image-text
GET BASE_URL/v1/sessions
```

文档中的 `/v1/...` 是内部路由。管理面不自动继承用户面的 `UMEKO_BASE_PATH`；它有独立入口与 Cookie Path，代理部署需单独规划。

## 按能力阅读

| 能力 | 指南 |
| --- | --- |
| 用程序完成登录、提问和查询 | [调用入门](quickstart.md) |
| 账号、头像、模型选择 | [登录与模型](auth-models.md) |
| 会话、上下文、运行、取消 | [会话与运行](sessions-runs.md) |
| 工作区、附件、产物、会话技能 | [文件与技能](files-skills.md) |
| 一个请求上传文件并发起任务 | [一次性调用](proxy.md) |
| 无网页账号的有界任务与服务凭据 | [机器任务](machine-tasks.md) |
| 工具发现、提交、查询与产物资源 | [MCP](mcp.md) |
| Agent Card、发送、订阅与流式产物 | [A2A](a2a.md) |
| CPU、内存、磁盘、模型与任务队列 | [资源监控](monitoring.md) |
| Provider / Model、并发、用户、技能管理 | [管理 API](admin.md) |
| SSE 格式、事件、断线重连 | [流式事件](events.md) |
| 所有方法、参数、输入输出模型 | [用户完整参考](reference-user.md)、[管理完整参考](reference-admin.md)、[数据结构](schemas.md) |

## 机器可读定义

- [用户 OpenAPI JSON](openapi-user.json)
- [管理 OpenAPI JSON](openapi-admin.json)

用户服务同时提供运行时 `/openapi.json`、`/docs`、`/redoc`；管理服务关闭这些 HTTP 文档路由。本网站的管理定义从隔离的应用实例离线生成。静态定义额外补充认证、原始文件体、multipart 和 SSE 契约，不改变运行时服务。MCP 与 A2A JSON-RPC 由 SDK 路由提供，未计入 OpenAPI 操作数量。

## 通用约定与错误

JSON 请求使用 `Content-Type: application/json`。附件 / 文件接口使用原始字节体；只有一次性调用接口使用 multipart。成功删除或部分修改返回 `204`，没有 JSON 响应体。

| 状态码 | 常见含义 |
| --- | --- |
| `400` | 业务参数不合法、已有活跃 Run、空文件等 |
| `401` | 未登录、登录失效，或管理角色不符 |
| `403` | 文件路径超出允许范围等 |
| `404` | 资源不存在或不属于当前用户 |
| `409` | 操作与当前执行状态冲突，例如运行中清空上下文 |
| `413` | 头像或机器请求超过大小限制 |
| `422` | FastAPI / Pydantic 字段验证失败 |
| `429` | 机器任务等待数量或调用者额度已满 |

多数业务错误返回 `{"detail":"说明"}`；字段验证的 `detail` 是数组。并非每个端点都返回表中所有错误。完整参考列出的是 OpenAPI 声明响应，实际还包括鉴权中间件与业务逻辑产生的错误。

Session ID、Run ID、模型 ID 和文件 ID 都按不透明字符串使用，不自行拼造。列表当前没有统一分页。`/health` 不检查模型连通性。
