# 启动与生产部署指南

本指南适用于当前源码和由当前源码构建的 exe。旧版发布包需确认是否已经包含 Provider 配置迁移、运行时前缀和模型 CA 支持。

## 首次启动

### 源码运行（Windows / WSL / Linux）

在项目根目录安装服务端依赖：

```sh
uv sync --extra server
```

没有 `uv` 时，用 `python -m pip install -e ".[server]"`，之后直接使用 `python -m ...` 启动。
普通 `uv sync` 只安装基础模型客户端依赖，Web 服务还需要 `server` 中的 FastAPI、Uvicorn、文件上传、MCP、A2A SDK 与资源监控依赖。

首次部署从 [.env.example](https://github.com/umeiko/UmEkO/blob/main/.env.example) 复制 `.env`；已经有 `.env` 时保留现有文件。
Windows PowerShell 可以使用：

```powershell
if (-not (Test-Path -LiteralPath .env)) { Copy-Item -LiteralPath .env.example -Destination .env }
```

本地开发保持 `UMEKO_BASE_PATH` 和 `MODEL_CA_FILE` 为空。如果模型使用公司私有 CA，填入实际 CA 路径。
首次生产启动前设置自己的 `UMEKO_ADMIN_USERNAME` 和 `UMEKO_ADMIN_PASSWORD`。

启动带登录和管理面的服务：

```sh
uv run python -m umeko.server --env .env --host 127.0.0.1 --port 8000
```

启动后按顺序操作：

1. 打开管理面 `http://127.0.0.1:9000/`，使用已配置的管理员凭据登录。
2. 在 Provider / Model 中添加模型 API 地址、密钥和模型名，设置视觉能力并激活主模型；也可用下文的 CLI 导入。
3. 打开用户工作台 `http://127.0.0.1:8000/`，登录或注册账号，创建会话并发起一次提问。

引导配置只在没有管理员的数据库中创建账号；重启不会自动改动已有账号的密码。
已有账号需要在管理面重置密码，单独修改 `.env` 不会重置数据库中的账号。

配置了公共前缀时，第 3 步应访问 NGINX / ALB 的公共地址，参见“带前缀部署”。
服务可以在未配置模型时启动，但 `/health` 成功并不表示模型已配置或能够回答。

### 启动方式与监听地址

| 入口 | 默认地址 | 适用场景 |
| --- | --- | --- |
| `python -m umeko.server` | 用户面 `127.0.0.1:8000`，管理面 `127.0.0.1:9000` | 带登录的共享服务、生产部署 |
| `python -m umeko.local` | `127.0.0.1:8765`，无管理端口 | 个人本机工作台，免登录且允许本地命令执行 |
| `python -m umeko.cli` | 无监听端口 | 终端对话，先配置并激活 Provider 模型 |

使用 `uv` 安装时，在上述命令前加 `uv run`。本地免登录模式只用于个人环境，生产共享服务使用 `umeko.server`。
`--no-admin` 可以关闭管理端口；首次安装使用它之前，先通过 CLI 导入并激活模型。
已有管理员账号时，修改 `.env` 的引导密码不会重置账号，应在管理面修改。
当前首次创建管理员的启动日志会打印账号和密码，这段日志按私有配置保管。

NGINX 和应用在同一台机器时，应用监听 `127.0.0.1` 即可。
NGINX 在另一个容器或机器时，应用需监听可被代理访问的接口，例如容器内使用：

```sh
uv run python -m umeko.server --env .env --host 0.0.0.0 --port 8000
```

`0.0.0.0` 表示监听所有网卡，不是浏览器访问地址。对外提供 NGINX / ALB 入口，后端 8000 端口只允许代理访问；
管理面默认仍监听回环地址，远程管理使用受控内网入口或隧道，不把 9000 当作公共用户入口。
用户面的 `--host` 不会改变管理面的地址，管理面有独立的 `--admin-host` / `--admin-port` 参数。

这些命令在终端前台运行，按 `Ctrl+C` 停止。生产环境由公司的服务管理或容器平台负责常驻和自动重启；
采用单个应用进程，不添加多 worker 或自动重载参数；若平台预设 `WEB_CONCURRENCY`，将其设为 `1`。

### Windows exe

把 `umeko-server.exe` 放在固定目录，首次启动前在旁边准备 `.env`。PowerShell 启动示例：

```powershell
.\umeko-server.exe --env .env --host 127.0.0.1 --port 8000
```

exe 读取同样的部署配置和 Provider 数据库，用户面 / 管理面端口及配置顺序与源码启动一致。
不要把升级后的 exe 放到另一个空目录就当作原安装继续运行；应保留数据目录或显式指定原目录。

## 配置放在哪里

模型配置统一保存在 `UMEKO_DATA_ROOT/umeko.db` 的 Provider / Model 注册表中。
网页管理面、CLI、本地工作台使用同一解析逻辑，不再以 `.env` 的 API 地址和密钥作为回退配置。
核心代码仍可直接构造 `Settings(ModelConfig(...))`，用于嵌入和隔离测试。

| 配置 | 位置 | 生效方式 |
| --- | --- | --- |
| 模型 API 地址、密钥、代理、模型名、视觉能力 | 管理面 Provider / Model，或 CLI 导入 | 网页下一轮提问生效；管理面修改仍执行原有重载；运行中的 CLI 用 `/reload` |
| 用户主/子/视觉模型选择，会话模型覆盖 | 网页用户设置及会话设置 | 下一轮提问 |
| 服务前缀、模型 CA、数据目录 | `.env` 或进程/容器环境变量 | 重启 |
| 首次管理员账号 | `.env` 的 `UMEKO_ADMIN_USERNAME/PASSWORD` | 仅无管理员账号时用于引导 |

`.env` 默认位于启动目录；exe 优先读取 exe 旁边的文件，也可通过 `--env` 指定。
进程环境变量优先于 `.env`。`UMEKO_DATA_ROOT`、`MODEL_CA_FILE` 的相对路径以所选 `.env` 所在目录为准；
启动参数 `--data-root` 优先于环境变量，其相对路径以启动目录为准。
已有本地工作台数据在 `local_data` 时，继续用 `--data-root local_data`；需要和云端共用 Provider 时指定同一目录。
容器部署需持久化数据目录，CA 文件需挂载到容器可读的位置。
如果使用 `--workspace-root`，该路径相对于进程启动目录，生产环境建议明确指定固定位置。

### CLI 与网页对齐

首次安装可先从管理面创建并激活模型，也可复制 `providers.example.json` 为 `providers.local`，填写后导入：

```sh
python -m umeko.cli providers import providers.local
python -m umeko.cli providers list
python -m umeko.cli providers use mdl_这里替换为list显示的ID
python -m umeko.cli
```

导入 JSON 的格式与管理面相同，`active` 是 `Provider名称/模型名称`。
`list` 不显示密钥。Web、CLI、本地工作台默认共用 `server_data/umeko.db`；
不同目录代表不同安装，不会自动同步。CLI 的 `/reload` 读取最新选择并开始新对话。
`providers.local` 和数据库都包含凭据，已经被 Git 忽略，不要放入源码提交。

### 旧配置迁移

首次升级会一次性导入旧 `.env` / 环境变量以及旧数据库覆盖项中的模型配置；
已存在的 Provider 凭据和激活选择不会被覆盖。迁移完成后，运行时模型只从注册表读取。
保留的旧 `.env` 项之后修改也不会更改模型。

确认数据目录后，使用下列命令核对迁移并移除旧 `.env` 的模型项：

```sh
python -m umeko.cli --env .env --data-root server_data providers migrate-env --remove
```

迁移先在一个数据库事务里完成，成功后才删除文件中的旧模型项；重复执行不会新增相同配置。
不完整配置会报错并保留旧项。管理员账号和部署配置保留。

## 带前缀部署

假设浏览器地址为 `https://公司域名/doc-master/consistency/image-text/`，应用监听服务器 8000 端口：

```ini
UMEKO_DATA_ROOT=server_data
UMEKO_BASE_PATH=/doc-master/consistency/image-text
UMEKO_PUBLIC_URL=https://example.internal/doc-master/consistency/image-text
MODEL_CA_FILE=/etc/umeko/certs/company-model-ca.pem
```

`UMEKO_BASE_PATH` 只填域名后面的公共路径，不填域名、端口或 `/v1` API 路由。
允许 URL 安全的英文、数字及 `- _ . ~` 路径段，末尾斜杠会自动移除。
本地根路径访问时留空。它在返回 HTML 时注入，因此不需要重新构建前端。
CSS/JS、普通 API、头像、预览、下载与事件连接都会带此前缀，Cookie 也限定在此前缀内。

`UMEKO_PUBLIC_URL` 为机器协议提供完整的外部基址，路径必须与 `UMEKO_BASE_PATH` 一致，不带末尾斜杠、查询参数或用户凭据。Agent Card、OAuth metadata、resource 校验与产物链接都使用它；MCP Host 校验也接受这个域名。本地可留空从请求推导，生产请显式配置，避免代理内部主机名进入下载链接。

代理和应用要约定：**浏览器使用完整前缀，转到应用前移除一次前缀。**

```text
浏览器 GET /doc-master/consistency/image-text/v1/runs/xxx/events
  → ALB / 外层代理按前缀路由
  → 内层 NGINX 移除前缀
  → 应用收到 GET /v1/runs/xxx/events
```

单层 NGINX 示例（放入对应的 `server` 块；HTTPS 证书由公司入口配置）：

```nginx
location = /doc-master/consistency/image-text {
    return 308 /doc-master/consistency/image-text/;
}
location /doc-master/consistency/image-text/ {
    # 示例允许 64 MB 上传，按实际文档/压缩包大小调整。
    client_max_body_size 64m;
    # 这里的末尾 / 将匹配的 location 前缀替换为 /。
    proxy_pass http://127.0.0.1:8000/;
    proxy_http_version 1.1;
    proxy_set_header Connection "";
    proxy_set_header Host $http_host;
    proxy_set_header Authorization $http_authorization;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_buffering off;
    proxy_cache off;
    proxy_read_timeout 600s;
}
```

如果 ALB 已经移除前缀，NGINX 应直接转发收到的内部路径，不再移除第二次。
上面的 `$scheme` 适用于 NGINX 自己接收入口 HTTPS。TLS 终止在 ALB 时，内层 NGINX 应保留可信 ALB 提供的
`X-Forwarded-Proto`，不要用内部 HTTP 的 `$scheme` 覆盖外部 HTTPS；这条链路只接受可信代理的连接。
容器分开部署时，`127.0.0.1` 只代表当前容器，应把上游改为应用服务名及其端口。
每层代理都应允许长连接并关闭流式缓冲；云 ALB 的空闲超时也需核对。
上传大小限制在每层入口都需要核对，示例的 `64m` 不是应用承诺的固定上限。
普通入口使用 `python -m umeko.server` 会自动设置 ASGI `root_path`。
自定义 Uvicorn 启动方式时，`--root-path` 需与 `UMEKO_BASE_PATH` 一致。
原始端口主要用于代理转发和健康检查；配置前缀后直接打开原始端口并不能代表公共入口验证。
当前 Run 状态保存在应用进程内，部署使用单个应用进程；多实例或多 worker 的任务调度需另行支持共享状态。
重启不能恢复正在执行的 Run；计划升级时先等任务结束或停止任务。

代理 HTTPS 的协议信息由 `X-Forwarded-Proto` 传递。NGINX 同机时默认信任回环来源；
容器或远端代理可通过 Uvicorn 支持的 `FORWARDED_ALLOW_IPS` 环境变量显式信任相应代理地址。
管理面仍在独立端口，`UMEKO_BASE_PATH` 只影响用户工作台。

### MCP、A2A 与自动发现

机器入口统一为用户服务基址加 `/agent/{slug}`，其下提供 `/mcp`、`/a2a`、`/v1/tasks`、`/oauth/token` 和 `/.well-known/...`。顶级协议入口已移除。代理应转发 Authorization，不能把协议请求改成网页登录页；A2A SSE 与 REST 任务流都要关闭缓冲。机器请求体最多 30 MiB，OAuth 表单最多 16 KiB，网关可设置更严格的限制。

使用客户端配置的完整 MCP URL、Agent Card URL 或 ClientFactory 基址时，始终包含前缀。MCP 未授权响应提供 `WWW-Authenticate` 的 `resource_metadata` 地址，可据此访问本服务的 metadata。

带路径的 OAuth issuer 自动发现可能按 RFC 8414 在域名根下寻找 `/.well-known/oauth-authorization-server/<服务前缀>`；受保护资源也可能寻找 `/.well-known/oauth-protected-resource/<服务前缀>/mcp`。本应用的 metadata 位于公共前缀加 `/agent/{slug}` 下；自动发现需包含完整 Agent 路径。需要自动发现的网关应为这些域名根路径配置到对应 metadata 的路由，或让调用方显式配置 metadata 地址。不要把其他服务的整个 `/.well-known/` 目录都转发到 UMEKO。当前只实现客户端凭据流程，没有交互式 OAuth / PKCE。

## 机器任务容量与资源监控

在管理端“服务接入”创建调用凭据，“资源监控”查看资源、模型队列和机器任务，并可停止活跃任务。具体指标见[资源监控](api/monitoring.md)。这些管理入口不在用户端口暴露。

需要同事直接调用时，可在“服务接入”选择免鉴权并保存；MCP、A2A 和机器任务入口无需 Key。此开关保存在数据库中，默认需要凭据，修改后即时生效。免鉴权调用共享任务和文件访问权限以及每账号队列额度；带凭据仍按服务账号隔离。网页登录与管理登录保持独立。

后台任务列表记录来源 IP，无法取得时为空；IP 不参与鉴权。应用只读取 ASGI 服务器提供的客户端地址，不自行信任请求中的 `X-Forwarded-For`。经过 NGINX / ALB 时可能记录代理地址；需要真实客户端 IP 时，按上文配置已知代理的 `FORWARDED_ALLOW_IPS`，不要信任任意来源。参见 [Uvicorn 代理配置](https://www.uvicorn.org/deployment/)。

`.env` 可配置以下参数，修改后重启：

```ini
UMEKO_TASK_WORKERS=4
UMEKO_TASK_QUEUE_LIMIT=100
UMEKO_TASK_CALLER_LIMIT=20
UMEKO_TASK_RETENTION_SECONDS=86400
UMEKO_TASK_TIMEOUT_SECONDS=3600
```

`WORKERS` 限制机器调度同时占用的执行槽，`QUEUE_LIMIT` 限制全局等待数量，`CALLER_LIMIT` 限制每账号未结束任务。当前 Run 执行池也有容量限制；增加任务槽并不直接增加模型吞吐。每模型额度仍在 Provider 页面设置。

终态结果和工作区默认保留 24 小时，清理约每分钟一次；运行中的任务不会因结果保留期限被删除。超时发起协作式取消，外部工具停止可能需要时间。新机器任务记录落盘，排队任务在重启后继续调度，执行中任务标记中断失败；普通网页 Run 仍不能跨重启恢复。

备份应包含整个 `UMEKO_DATA_ROOT`，其中数据库含服务凭据摘要和 Provider 配置，任务产物在用户工作区。不要只备份 SQLite 而漏掉待执行输入与产物。部署仍要求单个应用进程；多进程共享数据库不等于支持多 Worker 调度。

## 模型并发与调用排队

在管理面 **Provider / Model** 的模型列表填写「并发上限」并保存。每个模型独立设置，
`0`（默认）表示不限制；例如设为 `2`，同一时刻最多允许两次该模型的请求，其余调用按先后顺序等待。
主 Agent、子 Agent、视觉分析、上下文压缩和 Skill 生成调用同一个注册表模型时共用额度，
不同模型各自排队。上限保存在数据库，不放在 `.env`；旧数据库升级后模型默认保持无限制。
JSON 导入也支持模型字段 `max_concurrent_requests`，省略时不会覆盖已有模型的上限。

保存上限后，已加载会话也会生效，不需要重新「设为当前」或重启。降低上限时不强行中断
已有请求，等待正在执行的请求自然结束后再按新额度放行；改回 `0` 会放行等待调用。
流式请求直到收流、关闭连接后才释放额度；失败或取消同样释放。等待中的调用可以通过
现有停止按钮取消，不会再发往模型服务。应用日志会记录模型排队等待。

这是**单进程的模型调用队列**，不是可跨重启恢复的任务队列，也不限制每分钟请求数 / token 数。
生产仍使用单个应用进程；多实例部署需要共享限流器和任务状态。额度只统计本进程的调用，
同一公司模型被其他应用共用时，仍可能收到 LiteLLM 的限流错误，应按平台给本应用的额度设置。
独立 CLI 进程的调用不计入 Web 服务的额度；通过独立 CLI 导入修改上限后，重启正在运行的 Web 服务以应用更新。
队列本身不创建新会话；已有的任务接收、历史保留和 Session 清理策略仍需按部署需求另行设置。

## 模型 HTTPS 证书

网站入口和模型服务可以使用不同的 CA。需要让调用模型的 Python 服务信任**模型 CA**，
不是把两处 HTTPS 证书改成相同的文件。

从运维获得签发模型服务证书的 CA 文件（PEM，可包含根/中间 CA 链），设置 `MODEL_CA_FILE` 后重启。
主模型、视觉模型、子模型以及 Provider 切换都会继承此信任配置。
客户端保留默认/公共 CA，追加公司 CA，仍验证证书和域名。
文件不存在或格式错误会在启动时明确报错；域名不匹配、证书过期仍需运维修复。

## 验证

部署完成后，从真实浏览器入口验证，而不只检查后端端口：

1. `https://公司域名/项目前缀/health` 返回 `{"status":"ok"}`；这是服务存活检查。
2. 页面样式正常；浏览器开发者工具的 Network 中，5 个 CSS/JS 请求都位于同一前缀下并返回 200。
3. 登录、创建会话、上传文件、预览和下载均正常，刷新后登录态保留。
4. 提问后检查 `POST 前缀/v1/sessions/{session_id}/runs`：202 只表示任务已收到。
5. 同时检查 `GET 前缀/v1/runs/{run_id}/events`：正常响应类型为 `text/event-stream`，回答应分批显示并结束。

有进程重启、模型选择变化或部署配置变化时，重新验证第 4、5 步。
路径修复后仍没有回答，要看 `run.failed` 中的实际错误；可能是模型 CA、网络、密钥或模型接口配置。

实际红帽 UBI 容器实验命令和入口见 [代理实验](https://github.com/umeiko/UmEkO/blob/main/scripts/proxy_lab/README.md)。
实验覆盖根路径和此前缀、真实 UmEkO 前端及 Agent、独立的网站/模型 CA、文件预览下载和流式输出。
故意让事件接口返回 404 时，前端会查询任务最终结果；任务状态也不可用时，显示失败提示并恢复输入。
假模型只验证调用链路，不替代公司真实模型和真实 ALB 的现场验证。
`scripts/proxy_lab` 的镜像和编排是隔离验证环境，使用假模型、测试 CA 和测试账号，不作为正式生产部署配置。

## 升级、持久化与备份

部署目录应固定，尤其要固定 `UMEKO_DATA_ROOT`：里面保存 Provider 密钥、用户、历史和会话文件。
默认会话文件在 `UMEKO_DATA_ROOT/users/` 下，完整备份数据目录，不要只复制 `umeko.db`。
管理面技能库在应用目录的 `skills/` 中（源码运行是项目根目录，exe 是 exe 所在目录），也应保留；
使用的外部产物目录、自定义 `--workspace-root`、部署 `.env` 和 CA 文件一并纳入备份。
数据库和模型导入文件包含凭据，按私有配置管理，不提交到 Git。

推荐的升级顺序：

1. 等待或停止进行中的任务，停止应用进程，在停写状态下备份数据、技能库和配置。
2. 更新源码或替换 exe；源码安装按新版本重新安装服务端依赖。
3. 使用同一个 `.env` 和数据目录启动。需要整理旧模型配置时，按“旧配置迁移”步骤操作。
4. 验证页面、登录、文件和一次模型流式回答，再恢复正常使用。

把容器数据写在临时容器层、改变启动目录后使用默认相对路径，都会让新进程看起来像“全新安装”。
容器中的数据目录和技能库使用持久化存储，证书与 `.env` 放在应用能读取的固定位置。

## 多 Agent 路径部署

先在管理端“服务接入”下新建并启用 Agent，再把调用方 URL 更新为它的完整地址。没有自动创建的默认 Agent。旧全局 Card 编辑接口与顶级机器入口已删除。

“智能体管理”配置保存在原 `umeko.db`，无需增加 `.env` 项，也无需为每个 Agent 新开一个端口或应用进程。升级启动时自动添加 Agent 配置表与任务归属字段，旧机器任务可在管理员资源监控中查看，但旧顶级协议地址不再可用；升级前按上节备份数据目录。

如果公共部署前缀为 `/doc-master/consistency/image-text`，独立 MCP 地址为 `/doc-master/consistency/image-text/agent/image-qc/mcp`。代理按前述配置只剥离部署前缀，转给应用的路径必须保留 `/agent/image-qc/mcp`。不要再剥离 `/agent/image-qc`，否则请求会落到已移除的顶级入口，返回 404。

`UMEKO_PUBLIC_URL` 填用户服务的完整公共基址，含部署前缀，不含某个 Agent 路径。应用自动追加 `/agent/{slug}`，生成 Card、协议、OAuth 与产物地址。流式和超时配置仍沿用 MCP / A2A 的代理规则。

保存新配置立即影响后续请求。停用会让该 Agent 的公开入口返回 404，已接收任务继续执行；管理员可从资源监控取消。需要继续供调用者读取结果时，等任务处理完且结果不再需要后再停用。仍有保留任务的 Agent 不允许删除。

管理方法见[智能体管理](api/agents.md)，模型并发与任务容量继续由平台统一控制。

## 常见问题定位

| 现象 | 优先检查 |
| --- | --- |
| 启动提示缺少 `fastapi` / `uvicorn` | 安装 `server` 依赖，确认使用同一个 Python 环境 |
| 页面打开但没有样式，或 `/static/...` 返回 404 | `UMEKO_BASE_PATH` 与公共入口一致，代理只移除一次前缀，修改后重启并刷新页面 |
| 提问请求 202，但一直没有回答 | 分开检查事件接口 `/v1/runs/{id}/events` 和模型调用结果，不能把 202 当作回答成功 |
| 回答全部结束后才一次出现 | 每层 NGINX 关闭 `proxy_buffering`，核对外层代理的缓冲和超时设置 |
| 上传文件返回 413 | 核对 NGINX 的 `client_max_body_size` 及其他入口限制；头像接口另有 2 MB 应用限制 |
| `CERTIFICATE_VERIFY_FAILED` | 加载模型服务对应的 CA，核对文件可读、模型域名、证书有效期和证书链 |
| 浏览器提示网站证书不可信 | 检查网站入口的 HTTPS 证书及浏览器的公司 CA 信任；`MODEL_CA_FILE` 只影响 Python 调用模型 |
| 新进程里 Provider / 用户 / 历史消失 | `.env` 选择、实际数据目录和容器持久化挂载是否仍与原安装一致 |
| 页面可以用，但管理面 9000 连不上 | 是否启用 `--no-admin`，以及管理面是否仍监听 `127.0.0.1`；它与用户面地址独立 |
| Run 接口间歇性 404，或重启后任务找不到 | 是否启用了多 worker / 多实例，或进程重启；当前 Run 状态在单进程内 |

参考：[NGINX proxy_pass](https://nginx.org/en/docs/http/ngx_http_proxy_module.html#proxy_pass)、
[FastAPI 代理与 root_path](https://fastapi.tiangolo.com/advanced/behind-a-proxy/)、
[Uvicorn 设置](https://uvicorn.dev/settings/)。
