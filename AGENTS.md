# UmEkO 开发约定

## 路径前缀是所有服务入口的必需能力

项目必须同时支持域名根目录与多级路径前缀部署。新增或修改资源、API、协议入口与返回链接时，都要检查前缀；首页能打开不代表部署已验证。

- 用户工作台、REST、MCP、A2A 使用 `UMEKO_BASE_PATH`。
- 管理页面、登录和管理 API 使用独立的 `UMEKO_ADMIN_BASE_PATH`，默认空，不继承用户前缀。
- `UMEKO_PUBLIC_URL` 是用户/机器服务的外部完整地址，路径必须等于 `UMEKO_BASE_PATH`。管理前缀不能混入 Agent Card、MCP、A2A 或产物 URL。
- Provider 的 `base_url` 是上游模型地址，与网页部署前缀无关。
- 前缀在运行时配置，不能要求用户为不同部署路径重新构建前端，也不能从当前页面路径猜测前缀。

## 统一生成地址

前端使用 `frontend/src/shared/api.js` 中的 `appUrl()`，前缀来自服务端注入的 `umeko-base-path`。管理页调用 `frontend/src/admin/state.js` 的 `api()`；该函数负责拼接前缀，调用参数仍是 `/admin/...` 这样的内部路由。不要重复拼接，不要绕过公共入口直接 `fetch('/admin/...')`。

新增管理标签页和权限弹窗同样遵守此约定，包括 Tools 下发 `/admin/v1/tools` 与用户工具权限 `/admin/v1/users/{id}/tool-access`。它们只使用管理前缀，不读取 Provider 的 `base_url` 或用户服务的 `UMEKO_PUBLIC_URL`，也不为单个页面另建地址拼接方式。

资源、普通请求、SSE/EventSource、上传、头像、预览、下载及跳转都遵循这个约定。后端首页统一通过 `render_ui(entry, base_path)` 注入前缀与资源地址，构建产物中的相对模块地址保持不变。

机器协议通过 `umeko/server/task_api.py` 的 `public_base(settings, request)` 生成公开基址，通过 `task_view()` 生成产物下载 URL。它们同时考虑用户服务前缀与当前 `/agent/{slug}`，不要在各适配器内另写基址拼接逻辑。

对外机器入口始终是：

```text
<用户服务基址>/agent/<slug>/.well-known/agent-card.json
<用户服务基址>/agent/<slug>/a2a
<用户服务基址>/agent/<slug>/mcp
<用户服务基址>/agent/<slug>/v1/tasks
<用户服务基址>/agent/<slug>/oauth/token
```

SDK 内部的 `/a2a`、`/mcp` 等路由由 `AgentRoutingMiddleware` 包装；不要重新暴露顶级协议入口。OAuth issuer、token endpoint、resource、`WWW-Authenticate` 中的 metadata 地址、Agent Card 接口地址及产物链接都必须包含完整用户前缀与 Agent 路径。

## 代理、路由与登录保持一致

公共请求带完整前缀，代理转发前移除一次；标准服务入口分别设置两个端口的 Uvicorn `root_path`。自定义入口也要设置匹配的 `root_path`。避免多个代理重复去前缀，或前端重复加前缀。

鉴权中间件先按 ASGI `root_path` 还原内部路由，再判断权限。设置与删除 Cookie 必须使用相同的对应服务前缀 Path。前缀匹配要检查完整路径段边界，不能误把相似路径当作前缀。

NGINX/ALB 的规则必须转发前缀下全部子路径；SSE 和协议流要关闭缓冲。按部署说明处理可信代理的 Host、Authorization 与协议信息，不用未经验证的转发头自行猜测外部基址。

## 相关改动的验收

修改上述入口时，至少验证根路径和多级前缀。浏览器场景使用不同的用户与管理前缀；代理根路径应返回 404，防止漏前缀的请求误打误撞成功。

- Web/管理面：资源、登录、刷新后的登录状态、相关功能请求、退出与未登录 401。
- Tools/用户权限：实际点击读取和保存，刷新后确认设置保留；全局关闭的工具仍能单独授予用户。检查浏览器实际 GET/PUT 地址只含一次管理前缀，退出后读写均为 401。代理必须拒绝漏前缀、误用用户前缀及相似但不匹配的前缀。
- REST/机器协议：发现信息、任务提交/查询、相关流式输出和产物下载；需要凭据与免鉴权模式按改动范围验证。
- MCP/A2A：使用官方客户端，检查返回地址确实含前缀且可以访问。`umeko://` 是 MCP 逻辑资源 URI，不是 HTTP 下载 URL，不应添加网页前缀。

常用检查：

```sh
python -m pytest tests/test_deployment.py tests/test_configuration.py -q
python -m pytest tests/test_tool_access.py -q
python -m pytest tests/test_protocols.py tests/test_agent_card.py tests/test_agents.py tests/test_service_access.py -q
npm --prefix frontend run test:smoke
```

设置 `UMEKO_TEST_NGINX` 为本机 NGINX 可执行文件路径后，协议测试和前端浏览器测试会使用真实 NGINX 验证移除前缀后的访问。CI 已配置此项，不要移除。协议测试的代理仅用于有前缀的 HTTP 场景，未设置时仍测试直接访问。测试使用隔离数据和受控回复，不读取项目 `.env`，不调用实际模型服务。

验收报告区分原始端口直连、测试反向代理、CI 的真实 NGINX 与生产 ALB。没有读取生产代理规则并通过外部入口验收时，不能把本地通过表述为生产 ALB 已验证，也不能把可能的路径改写问题当作已确认的线上原因。

前端源码改动后运行格式检查和构建，并一起提交 `umeko/server/static/ui/`；不要直接编辑构建文件。部署说明见 [docs/deployment.md](docs/deployment.md)，前端说明见 [docs/frontend.md](docs/frontend.md)。

## 受控技能与升级兼容

技能安全机制见 [docs/architecture/skill-security.md](docs/architecture/skill-security.md)，运维步骤见 [docs/deployment.md](docs/deployment.md#skill-security-upgrade)。修改下发、执行器、内置技能安装或升级脚本时，同步检查以下约定：

- 管理员技能库是可信源；会话 `client/skills/` 是下发副本；`UMEKO_DATA_ROOT/skill_trust/<session_id>/<pack>.json` 是私有批准记录。不得从用户可改的副本生成批准记录，不得把记录移入用户可访问目录。
- 会话技能中的 `.py`、`config.json` 和导入相关受保护文件只读；文件写入、上传、复制、移动、改名、删除、下载落盘和解压均须走硬门禁，目录操作检查后代内容。网页只读不能代替后端检查。
- 执行前按固定位置、管理员白名单、MD5、SHA-256 检查整个包的受保护文件，含辅助模块与配置；执行校验后的私有副本。摘要按原始字节比较，不能在校验时忽略换行、BOM 或格式变化。
- 库升级不覆盖已有会话副本或重签已有记录。旧副本和旧记录匹配可继续运行旧版；首次启用门禁时，无记录的旧会话若与当前库不同会拒绝。清空聊天、重启及复制会话不等于获得新版本。
- 不得以删除 `skill_trust`、清空摘要、跳过不匹配文件或关闭校验作为升级/故障兜底。管理页文件“安全门禁”可由管理员从可信库重算并同步已有会话记录；默认仅同步字节一致的副本，显式重新下发时只写可信库字节。保持管理员身份校验、预览 SHA-256 乐观锁、会话装配/维护互斥、运行中跳过、原子发布与审计；不得接受客户端传入批准字节或从用户副本生成基准。操作只影响选定文件，其他门禁继续生效。
- 涉及此链路的变更至少验证新会话、原记录下的旧会话恢复、首次门禁升级的旧副本差异、辅助模块/config 篡改和 LF/CRLF 差异；使用隔离库及临时数据，不操作真实会话。执行通过不等于脚本已沙箱化。

## 数据与改动范围

保留无关的工作区改动。不要提交 `.env`、本地凭据、数据库或运行数据；测试不得操作真实 `server_data/`、`output/`、技能库或实际 Provider。

文档、代码注释、示例、测试用例和提交说明必须使用通用占位域名与合成数据，不得包含实际使用方名称、实际部署域名/IP、私有接口路径或下载令牌。排查问题时，不把用户提供的真实下载链接复制进源码或日志样例。
