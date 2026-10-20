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

内网使用手册位于 `service_docs/`，与 GitHub Pages 的 `docs/` 独立。手册内部页面与资源使用相对链接；工作台及管理页的文档入口统一读取服务端注入的 `umeko-guide-url`，优先指向 `UMEKO_PUBLIC_URL + /guide/`，未配置时使用当前服务前缀。临时工作台的能力路径不能混入手册链接。修改手册后运行 `python scripts/build_service_docs.py` 和 `--check`，一起提交 `umeko/server/static/guide/`；截图只使用隔离的合成数据。

## 受控技能与升级兼容

技能安全机制见 [docs/architecture/skill-security.md](docs/architecture/skill-security.md)，运维步骤见 [docs/deployment.md](docs/deployment.md#skill-security-upgrade)。修改下发、执行器、内置技能安装或升级脚本时，同步检查以下约定：

- 管理员技能库维护待下发文件；管理员通过“安全门禁”逐文件批准当前版本，持久化在数据库 `skill_file_approvals`。新会话 `client/skills/` 是下发副本；`UMEKO_DATA_ROOT/skill_trust/<session_id>/<pack>.json` 只从管理员批准的摘要生成。未批准、改动后的代码与配置不得自动获得信任；不得从用户可改的副本生成批准记录，不得把记录移入用户可访问目录。
- 会话技能中的 `.py`、`config.json` 和导入相关受保护文件只读；文件写入、上传、复制、移动、改名、删除、下载落盘和解压均须走硬门禁，目录操作检查后代内容。网页只读不能代替后端检查。
- 执行前按固定位置、管理员白名单、MD5、SHA-256 检查整个包的受保护文件，含辅助模块与配置；执行校验后的私有副本。摘要按原始字节比较，不能在校验时忽略换行、BOM 或格式变化。
- 库升级不覆盖已有会话副本或重签已有记录。旧副本和旧记录匹配可继续运行旧版；首次启用门禁时，无记录的旧会话若与当前库不同会拒绝。清空聊天、重启及复制会话不等于获得新版本。
- 不得以删除 `skill_trust`、清空摘要、跳过不匹配文件或关闭校验作为升级/故障兜底。管理页文件“安全门禁”仅显示、批准管理员库的当前版本，不扫描、同步或重新下发旧会话。保持管理员身份校验、预览 SHA-256 乐观锁、下发/源文件写入互斥、批准与审计同一事务；不得接受客户端传入批准字节或从用户副本生成基准。操作只影响选定文件，其他门禁继续生效。服务端脚本测试也必须使用显式批准记录；CLI 本机操作者的直接执行不使用服务器数据库。
- 涉及此链路的变更至少验证新会话、原记录下的旧会话恢复、首次门禁升级的旧副本差异、辅助模块/config 篡改和 LF/CRLF 差异；使用隔离库及临时数据，不操作真实会话。执行通过不等于脚本已沙箱化。
- 整库可信代码管理与单文件门禁共用 `SkillApprovals`，批量操作逐文件核对预览版本。移出可信区在数据库同一事务内删除批准、写撤销及审计；执行器检查撤销序号，拦截此前下发版本，重新批准不复活旧授权。保留未带序号旧记录的兼容性，直到显式撤销；不改写旧会话文件或中断已启动脚本。列表/搜索/分页/跨页全选与批量 API 同样只使用管理前缀。

## 管理 API 与外部管理 Skill

管理 GUI 的服务端功能应同时通过管理 API 提供。操作摘要、行为、认证约定集中在 `umeko/server/admin_contract.py`，新增管理路由需同步维护；在线 `/admin/v1/openapi.json`、开发文档和内网手册使用同一契约。运行 `python scripts/generate_api_docs.py` 和 `--check`，再按手册约定构建 `umeko/server/static/guide/`。

外部管理 Skill 位于 `umeko/server/admin_skill/`，通过 `/admin/automation` 清单和固定文件下载入口发布，不进入普通用户下发技能库，不在服务端执行。管理登录页及控制台的复制按钮只能使用当前浏览器 origin 和注入的管理前缀，不使用用户 `UMEKO_PUBLIC_URL`、Provider 地址或猜测路径。公开说明不得携带凭据；所有管理操作与在线规范继续要求管理员 Cookie。认证、接口字段或操作行为变化时同步维护 Skill 与客户端，并验证 `tests/test_admin_automation.py` 及浏览器 `UMEKO_UI_FOCUS=admin-automation` 的根路径/独立前缀、下载复制和退出 401。

“使用AI来配置”入口使用指导弹窗，完整下载为 `/admin/automation/skill.zip`。包内完整 API 参考与 schema 随生成器同步；修改 Skill 或其参考后用 `scripts/build_admin_skill.py` 和 `--check` 通过原生 7-Zip 构建与逐字节校验，提交 `umeko/server/admin_skill.zip`。下载只返回成品，不能在请求中打包或夹带运行配置；固定清单、ZIP 与 wheel/exe 数据项保持一致。

## 数据与改动范围

保留无关的工作区改动。不要提交 `.env`、本地凭据、数据库或运行数据；测试不得操作真实 `server_data/`、`output/`、技能库或实际 Provider。

文档、代码注释、示例、测试用例和提交说明必须使用通用占位域名与合成数据，不得包含实际使用方名称、实际部署域名/IP、私有接口路径或下载令牌。排查问题时，不把用户提供的真实下载链接复制进源码或日志样例。
