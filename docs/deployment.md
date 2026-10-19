# 启动与生产部署指南

本指南适用于当前源码和由当前源码构建的 exe。旧版发布包需确认是否已经包含 Provider 配置迁移、运行时前缀和模型 CA 支持。

## 首次启动

### 跨平台压缩包支持 {#archive-support}

网页“解压”、目录打包下载和 Agent 的 `archive_tool` 使用同一个原生 7-Zip 后端。ZIP、TAR、TAR.GZ/TGZ、TAR.BZ2/TBZ2、TAR.XZ/TXZ、单文件 GZ/BZ2/XZ、7z、RAR、WIM 等均调用 7-Zip，不使用 Python 解压或压缩实现。原生程序按整包批量处理，避免逐个文件启动进程。

所有格式都需要运行环境中的 7-Zip。未设置 `SEVENZIP_PATH` 时依次搜索 `PATH` 中的 `7zz`、`7z`、`7za`，Windows 还会检查常见安装目录。指定该变量时严格使用指定程序，无效路径或缺少执行权限会报错。

Ubuntu/Debian 可安装发行版提供的 `7zip`；RAR 解码器可能是单独的 `7zip-rar` 包，具体取决于软件源和构建。官方 [7-Zip 下载页](https://www.7-zip.org/download.html)提供 Linux x86-64 与 ARM64 命令行版本，可用于 Red Hat/UBI 等没有合适软件包的镜像。根据架构下载，在构建镜像时把 `7zz` 或 `7zzs` 放到可执行目录，或挂载已准备的程序，然后设置：

```ini
# 示例：路径必须在容器内部存在，并且服务用户有执行权限。
SEVENZIP_PATH=/usr/local/bin/7zz
```

不要把 Windows 的 `C:/Program Files/7-Zip/7z.exe` 配置带到 Linux。安装在宿主机并不代表容器内可用；可在容器内运行 `7zz i` 确认格式支持。缺少程序时，网页解压 API 返回 `400`，模型工具返回明确的安装/配置提示。加密压缩包暂不支持；解压条目限制、路径校验与清理行为见[文件与技能](api/files-skills.md)。

文件整理使用模型工具 `file_operate`，不需要在生产环境开放通用命令执行。Web/机器任务仅可操作当前 Session 的 `workspace/`、`attachments/`、`generate/`，CLI 的新文件整理工具仅可操作当前产物目录。文本写入仍保留原来的产物目录限制。

### 源码运行（Windows / WSL / Linux）

在项目根目录安装服务端依赖：

```sh
uv sync --extra server
```

没有 `uv` 时，用 `python -m pip install -e ".[server]"`，之后直接使用 `python -m ...` 启动。
普通 `uv sync` 只安装基础模型客户端依赖，Web 服务还需要 `server` 中的 FastAPI、Uvicorn、文件上传、MCP、A2A SDK 与资源监控依赖。

仓库已包含构建后的 Vue 前端，直接启动 Python 服务即可，生产环境不需要 Node 或 Vite 服务。修改 `frontend/` 源码后，在打包或部署前执行 `cd frontend`、`npm ci`、`npm run build`；将更新后的 `umeko/server/static/ui/` 与后端一起发布，勿只拷贝首页。开发与验证步骤见[前端开发](frontend.md)。

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

启动后，“服务接入 → 智能体管理”自带 `image-qc` 图像质检智能体；配置主模型和视觉模型后可直接接入。首次初始化会将配套检查清单和报告脚本补入技能库，已有自定义文件不覆盖。后续启动只更新内容完全匹配已知原版的质检指引和报告脚本，保留自定义版本、检查清单及启用状态，不恢复已删除的文件。技能库默认是启动目录的 `skills/`（exe 则在其旁边），可用 `UMEKO_SKILL_DIR` 指向固定的可写、持久化目录；管理面与执行工具共用此路径。详见[图像质检智能体](api/agents.md#builtin-image-qc)。

首次上线及后续更新，还需完成[受控技能的部署与升级验收](#skill-security-upgrade)：网页和模型能用，不等于会话脚本已通过白名单与摘要检查。

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

### draw.io 导出与原始字体 {#drawio-font}

绘图 Skill 默认使用 **方正兰亭黑简体**，实际 family 为 `方正兰亭黑简体` / `FZLanTingHeiS-R-GB`，
样式为 Regular。项目维护方已确认公司取得商业授权，原始字体文件单独提供在
[assets Release](https://github.com/umeiko/UmEkO/releases/tag/assets)：

- [下载 FZLanTingHeiS-R-GB.ttf](https://github.com/umeiko/UmEkO/releases/download/assets/FZLanTingHeiS-R-GB.ttf)
- [下载 SHA256SUMS.txt](https://github.com/umeiko/UmEkO/releases/download/assets/SHA256SUMS.txt)

字体文件为 2,400,742 字节，SHA-256：
`5301bdfe967da491eec7edf29c6ba50cf44f27ad30a0d70a7f74247f3656199b`。
字体授权独立于项目代码许可，使用范围以相应字体授权为准。

**Windows**：下载字体，右键选择“为所有用户安装”，再重启实际运行绘图的服务。
只在管理员个人账户安装，并不代表其他服务账户也能读取该字体。

**Linux（fontconfig）**：运行以下命令下载、校验并安装：

```sh
curl --fail --location --retry 3 \
  https://github.com/umeiko/UmEkO/releases/download/assets/FZLanTingHeiS-R-GB.ttf \
  --output /tmp/FZLanTingHeiS-R-GB.ttf
printf '%s  %s\n' \
  '5301bdfe967da491eec7edf29c6ba50cf44f27ad30a0d70a7f74247f3656199b' \
  '/tmp/FZLanTingHeiS-R-GB.ttf' | sha256sum --check -
sudo install -d -m 0755 /usr/local/share/fonts/umeko
sudo install -m 0644 /tmp/FZLanTingHeiS-R-GB.ttf /usr/local/share/fonts/umeko/
sudo fc-cache -f
fc-match -f '%{family}\n' '方正兰亭黑简体'
```

最后一条应包含 `方正兰亭黑简体` 或 `FZLanTingHeiS-R-GB`，不要把命令成功但返回替代字体当作安装完成。
在绘图 Skill 的 `config.json` 中保留 `"font_family": "方正兰亭黑简体"`、`"font_size": "10.5"`。

**Docker**：字体必须在容器内可用；可将宿主已安装的字体目录只读挂载：

```sh
--mount type=bind,src=/usr/local/share/fonts/umeko,dst=/usr/local/share/fonts/umeko,readonly
```

字体目录权限需允许容器服务账户读取；容器启动后执行 `fc-match` 核对实际 family。
方正字体作为独立 Release 资产下载，Skill ZIP 不包含字体二进制。
Linux 版 draw.io、Xvfb、`drawio_path`、完整 Docker 命令和无模型验收见
[绘图 Skill 的 Linux 部署说明](https://github.com/umeiko/UmEkO/blob/main/umeko/builtin_skills/drawio-flowchart/references/linux-deployment.md)。

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
进程环境变量优先于 `.env`。`UMEKO_DATA_ROOT`、`MODEL_CA_FILE`、`UMEKO_DOWNLOAD_CA_FILE` 的相对路径以所选 `.env` 所在目录为准；
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
管理面仍在独立端口，`UMEKO_BASE_PATH` 只影响用户工作台；管理前缀使用下面的独立配置。

### 管理页面的路径前缀 { #admin-prefix }

例如用户页是 `https://example.internal/doc-master/consistency/image-text/`，管理页是
`https://example.internal/doc-master/consistency/image-text-admin/`：

```ini
UMEKO_BASE_PATH=/doc-master/consistency/image-text
UMEKO_ADMIN_BASE_PATH=/doc-master/consistency/image-text-admin
UMEKO_PUBLIC_URL=https://example.internal/doc-master/consistency/image-text
```

`UMEKO_ADMIN_BASE_PATH` 填管理页在浏览器里的完整路径前缀，不填域名或端口。
它不继承用户页前缀；留空时仍从管理端口根路径访问。两项都在运行时生效，修改 `.env` 后重启服务，无须重新构建前端。
管理页的 JS/CSS、登录、退出和全部管理 API 使用此管理前缀，管理员 Cookie 也限定在此路径。
`UMEKO_PUBLIC_URL` 始终是用户/机器服务地址，管理页展示的 Agent Card、A2A、MCP 链接仍指向用户服务。
Provider 中的 `base_url` 是上游模型地址，与这些网页部署前缀无关。

在对应的内网 NGINX `server` 块增加独立规则：

```nginx
location = /doc-master/consistency/image-text-admin {
    return 308 /doc-master/consistency/image-text-admin/;
}
location /doc-master/consistency/image-text-admin/ {
    client_max_body_size 64m;
    proxy_pass http://127.0.0.1:9000/;
    proxy_http_version 1.1;
    proxy_set_header Connection "";
    proxy_set_header Host $http_host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_read_timeout 600s;
}
```

此规则移除管理前缀后转到 9000；用户规则转到 8000。若 ALB 已移除前缀，内层不要重复移除。
使用 `python -m umeko.server` 时两个端口的 ASGI `root_path` 都会自动配置；自定义管理端 Uvicorn 入口的
`--root-path` 须与 `UMEKO_ADMIN_BASE_PATH` 一致。管理端代理应放在公司受控的内网入口。

部署后通过**外部管理地址**验证：

1. 页面资源均在管理前缀下，例如 `…/image-text-admin/static/ui/assets/…`，返回 200。
2. 登录请求发往 `…/image-text-admin/admin/login`；登录后 `…/image-text-admin/admin/v1/me` 返回 200。
3. 切换用户、模型、Tools 管理、会话、技能、资源监控和服务接入各页，确认请求都在管理前缀下。
4. 退出后 `…/image-text-admin/admin/v1/me` 返回 401；未登录时管理 API 也应返回 401。

旧版本只支持用户页前缀，管理页仍从域名根路径请求。部署本修复时需一起更新 Python 代码和随包的
`umeko/server/static/ui`，重启并刷新页面；只修改 `.env` 或只替换 HTML 不足以修复旧管理脚本。

### Tools 下发与用户工具权限的 ALB 验收

Tools 使用同一个管理端请求入口，不需要单独配置 `base_url`。以上述配置为例，浏览器的请求地址为：

| 操作 | 请求路径 |
| --- | --- |
| 读取工具下发状态 | `GET /doc-master/consistency/image-text-admin/admin/v1/tools` |
| 保存某个工具的下发状态 | `PUT /doc-master/consistency/image-text-admin/admin/v1/tools/{name}` |
| 读取、保存用户工具权限 | `GET/PUT /doc-master/consistency/image-text-admin/admin/v1/users/{id}/tool-access` |

这些请求只加一次 `UMEKO_ADMIN_BASE_PATH`。Provider 的 `base_url` 仅用于访问上游模型；
`UMEKO_PUBLIC_URL` 用于用户/机器服务公开地址，均不用于管理端请求。ALB 规则应覆盖整个管理前缀下的子路径，
不能只转发管理首页或静态文件；每层转发中的方法、请求正文及 Cookie 都要保留。

在测试账号上通过外部管理地址完成以下操作，避免修改生产用户的实际权限：

1. 登录后在浏览器网络面板核对上述 GET/PUT 请求，确认没有漏前缀、重复前缀或误用用户前缀。
2. 在 Tools 管理关闭一个工具，刷新页面确认仍关闭；在用户管理中为测试用户单独勾选该工具，保存并重新打开确认授权保留。
3. 退出登录，核对管理员 Cookie 已删除，以上读取和保存接口均返回 401。
4. 在仅开放这两个前缀的代理入口，确认无前缀 `/admin/v1/tools`、误用用户前缀的管理路径及相似的错误前缀均返回 404。
   如果域名还承载其他系统，对应路径也必须避免被错误转入 UmEkO 管理端。

自动回归覆盖根路径、用户与管理各自独立配置前缀，以及不同的多级前缀。浏览器测试经过移除一次前缀的 HTTP 代理；
设置 `UMEKO_TEST_NGINX` 时使用真实 NGINX，CI 保持此配置。首页 200 或原始端口直连成功不足以证明 ALB 部署通过，
生产仍需按实际 ALB/NGINX 转发规则从外部入口完成上述验收。

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
UMEKO_TMP_IDLE_SECONDS=3600
UMEKO_MACHINE_IDLE_SECONDS=900
UMEKO_TASK_TIMEOUT_SECONDS=3600
```

`WORKERS` 限制机器调度同时占用的执行槽，`QUEUE_LIMIT` 限制全局等待数量，`CALLER_LIMIT` 限制每账号未结束任务。当前 Run 执行池也有容量限制；增加任务槽并不直接增加模型吞吐。每模型额度仍在 Provider 页面设置。

调用记录默认保留 24 小时；纯机器节点及文件在任务结束后默认 15 分钟回收。打开临时工作台后改为网页无实际操作 1 小时回收，心跳不续期；运行中的任务会等执行结束后再计时。清理约每分钟执行一次，释放节点、文件及内存，数据库中的消息、工具记录、文件树快照保留到调用记录期限。超时发起协作式取消，外部工具停止可能需要时间。新机器任务记录落盘，排队任务在重启后继续调度，执行中任务标记中断失败；普通网页 Run 仍不能跨重启恢复。

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

## 内网模型的工具调用兼容

如果 LiteLLM 返回 `400`，错误包含 `"auto" tool choice requires --enable-auto-tool-choice and --tool-call-parser`，
说明下游推理服务尚未开启原生自动工具调用。主 Agent 和子 Agent 的请求带 `tools`；未显式设置
`tool_choice` 时，上游仍可能默认使用 `auto`。`image_reasoning` 内部的视觉请求只发送图片与问题，
不带工具列表，因此视觉分析能成功不代表该模型的原生工具协议也可用。

网页聊天与 MCP/A2A 共用模型客户端，但模型选择可能不同：网页有用户模型偏好和会话覆盖，
机器任务使用 Agent 默认模型或调用方指定的 `model_id`，视觉模型另行选择。检查管理端中智能体的
主模型、视觉模型设置，以及日志中的 `model`、工具数、图片数和 `tool_choice`，确认失败的是哪一级请求。

UMEKO **每次先尝试原生工具请求**。仅收到明确表示不支持工具协议的 `400`（包括上面的错误）时，
对本次请求回退为文本 JSON 工具协议：去掉 HTTP 请求里的 `tools` 和 `tool_choice`，把已披露工具与
参数定义写入系统指引，并转换历史工具消息。模型输出经过结构和工具名检查后，仍由原有工具执行器运行；
文件范围、技能范围和权限约束保持生效。不会因为其他 `400`、认证失败或限流而触发这个回退。

回退不会修改 Provider 配置或缓存为模型的默认模式；下一次请求继续先尝试原生调用，因此上游修复后
立即使用原生能力。正常支持工具的模型保留原来的请求与流式行为。回退模式收齐并校验 JSON 后再展示正文，
避免把内部协议内容显示成聊天回答；工具事件与可用的推理进度仍通过 SSE 返回。JSON 格式错误最多纠正一次，
仍失败时明确报错；回退请求同样遵循模型并发额度和取消操作。

从根本上修复时，请运维按实际模型和 vLLM 版本开启 `--enable-auto-tool-choice`，并设置该模型匹配的
`--tool-call-parser`，不能仅在客户端删掉 `tool_choice`，也不能用 `tool_choice="none"` 替代工具执行。
模型还需能遵循文本 JSON 指引，客户端回退无法保证任何模型都有可靠的工具能力。
服务端配置详见 [vLLM 官方工具调用说明](https://docs.vllm.ai/en/latest/features/tool_calling/#automatic-function-calling)。

## 模型 HTTPS 证书

网站入口和模型服务可以使用不同的 CA。需要让调用模型的 Python 服务信任**模型 CA**，
不是把两处 HTTPS 证书改成相同的文件。

从运维获得签发模型服务证书的 CA 文件（PEM，可包含根/中间 CA 链），设置 `MODEL_CA_FILE` 后重启。
主模型、视觉模型、子模型以及 Provider 切换都会继承此信任配置。
客户端保留默认/公共 CA，追加公司 CA，仍验证证书和域名。
文件不存在或格式错误会在启动时明确报错；域名不匹配、证书过期仍需运维修复。

## 内网文件下载与 HTTPS 证书 { #download-network }

文件下载与模型调用是独立链路。`MODEL_CA_FILE` 只用于模型；下载工具的企业 CA 用
`UMEKO_DOWNLOAD_CA_FILE` 配置。两项可以指向同一份公司 CA 文件，下载仍保留默认公共 CA 并检查域名和有效期。

从运维获取公司 CA 的 PEM 文件，配置服务使用的 `.env` 后重启：

```ini
UMEKO_DOWNLOAD_CA_FILE=/etc/umeko/certs/company-files-ca.pem
UMEKO_DOWNLOAD_INTERNAL_HOSTS=files.example.internal
```

Windows 可填 `C:/certs/company-files-ca.pem`；相对路径以 `.env` 所在目录为准。
Docker 要把 CA 文件只读挂载进容器，配置值填写容器中的路径，不是宿主机路径。
证书文件不存在或格式错误会在启动时明确报错。服务器仍需能解析并连接文件主机。

如果暂时拿不到 CA，需要允许指定文件站的自签名证书，可由管理员显式配置：

```ini
UMEKO_DOWNLOAD_INTERNAL_HOSTS=files.example.internal
UMEKO_DOWNLOAD_TLS_INSECURE_HOSTS=files.example.internal
```

修改后重启，重新发起下载即可。此方式对列出的主机关闭证书和域名校验，无法验证文件来源；
仅在明确接受这一点时使用，取得 CA 后可清空免校验列表并改用 CA 配置。
没有全局关闭校验的开关，Agent 也不能通过工具参数选择关闭校验。成功结果会附带本次免校验主机的提示。

两个主机列表相互独立：`INTERNAL_HOSTS` 开放网络访问，`TLS_INSECURE_HOSTS` 只控制证书校验。
填写精确域名或 IP，多个用**英文逗号**分隔，不带协议、端口或路径，不支持 `*`、子域名通配符或网段。

多个内网文件主机可以这样配置：

```ini
UMEKO_DOWNLOAD_INTERNAL_HOSTS=files.example.internal,reports.example.internal
UMEKO_DOWNLOAD_TLS_INSECURE_HOSTS=files.example.internal
```

这里允许访问两个内网主机，仅对 `files.example.internal` 跳过证书校验；
`reports.example.internal` 仍需通过默认证书信任库或已配置的企业 CA 验证。
以上域名均为占位示例，部署时替换成实际文件主机名，修改后重启服务。
文件链接若重定向到其他内网主机，也要单独将目标主机加入内网列表，并按其证书情况配置 TLS 信任。

如果多个站点共用同一公司 CA，只需配置一次 `UMEKO_DOWNLOAD_CA_FILE`，
清空 `UMEKO_DOWNLOAD_TLS_INSECURE_HOSTS`，即可保留各站点的证书校验；
`UMEKO_DOWNLOAD_INTERNAL_HOSTS` 仍须列出需要开放的全部内网文件主机。

内网开放限于这些主机解析到的 RFC1918 IPv4 / IPv6 ULA 地址；本机回环、链路本地、保留和云元数据地址仍禁止。
公网文件主机不需要加入 `INTERNAL_HOSTS`。每一次重定向都会重新匹配目标主机的网络与 TLS 策略，
不会把一个主机的授权传给其他主机。20 MiB 大小限制、工作区边界和失败清理保持生效。

遇到 `TLS_CERTIFICATE_VERIFY_FAILED` 时，Agent 和工具详情会收到文件主机、校验原因和上述配置名；
不会自动以不校验方式重试。`TLS_ERROR` 表示其他 TLS 握手错误，`DNS_ERROR` 表示解析失败，
`DOWNLOAD_TIMEOUT` 表示连接或读取超时。错误详情不会包含下载网址中的查询令牌。

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
`UMEKO_DATA_ROOT/skill_trust/` 保存与会话代码配套的批准记录，须与数据库、会话文件在同一次停写备份中保存和恢复。
管理面技能库在应用目录的 `skills/` 中（源码运行是项目根目录，exe 是 exe 所在目录），也应保留；
使用的外部产物目录、自定义 `--workspace-root`、部署 `.env` 和 CA 文件一并纳入备份。
数据库和模型导入文件包含凭据，按私有配置管理，不提交到 Git。

推荐的升级顺序：

1. 等待或停止进行中的任务，停止应用进程，在停写状态下备份数据、技能库和配置。
2. 更新源码或替换 exe；源码安装按新版本重新安装服务端依赖。
3. 使用同一个 `.env` 和数据目录启动。需要整理旧模型配置时，按“旧配置迁移”步骤操作。
4. 按下节验证技能库、新会话和保留的旧会话，不覆盖旧副本或重签记录。
5. 验证页面、登录、文件、一次模型流式回答和实际技能执行，再恢复正常使用。

把容器数据写在临时容器层、改变启动目录后使用默认相对路径，都会让新进程看起来像“全新安装”。
容器中的数据目录和技能库使用持久化存储，证书与 `.env` 放在应用能读取的固定位置。

### 受控技能的部署与升级验收 {#skill-security-upgrade}

管理员库提供源文件；数据库白名单保存管理员确认的具体版本；每个会话有独立副本，其私有记录采用已批准的路径与 MD5 / SHA-256。完整机制见[受控技能与执行信任](architecture/skill-security.md)。这不是操作系统文件“只读属性”，也不是 Python 沙箱。

#### 首次部署

1. 固定数据与技能库位置。容器示例配置如下，均指**容器内**的绝对路径；分别挂载持久化存储。不要把 `UMEKO_SKILL_DIR` 指向某个用户的会话副本，也不要只保留数据目录中的数据库。

    ```ini
    UMEKO_DATA_ROOT=/srv/umeko/data
    UMEKO_SKILL_DIR=/srv/umeko/skills
    ```

2. 以实际服务账号检查这两个目录可读写；私有记录留在数据根的 `skill_trust/`，不作为静态目录发布。固定启动目录，核对容器环境和 `.env` 的最终取值。
3. 在管理面的技能库确认 `SKILL.md`、`scripts/` 下的入口及辅助模块、`assets/config.json` 完整，并配置下发范围和 Agent 技能披露。二进制位置等配置由管理员在库中维护，先适配当前系统，再对每个 Python 文件与 `config.json` 打开“安全门禁 → 加入可信白名单”，之后创建使用它的会话。
4. 真正新建一个用户会话，或提交一个新的 MCP/A2A 任务，用合成输入执行一次所需技能。查看工具结果中的脚本路径和实际产物，确认没有 `SCRIPT_TRUST_REJECTED`。
5. 如需机器服务，从实际带前缀的外部入口重复验证，并查看任务对应的 `session_id`。管理页面的脚本“测试”运行管理员库，只能辅助检查程序和依赖，**不能证明某个旧会话的副本与摘要匹配**；健康检查、普通聊天和 `list_skill_script` 成功也不能替代执行验收。

#### 升级前后必须保留什么

停止新任务并等待或停止正在执行的任务，停应用后成套备份：数据库、`users/` 下的会话文件、`skill_trust/`、管理员技能库、私有配置及 CA。记录应用版本、实际目录/容器卷、计划更改的技能文件；不把这些私有备份提交 Git。

更新源码、镜像或 exe 后，先核对持久化卷是否挂到了原位置。空目录挂载会遮住镜像内文件；数据库已有安装标记时，删除技能库并重启也不保证重新安装所有资源。启动会保留管理员自定义与删除，仅按内置资源的已知原版策略更新，不能把“拉了最新代码”视为所有运行库文件都已更新。

需要更改 `.py`、辅助模块或 `config.json` 时，在**管理员库**审查并维护完整版本，暂停创建新会话直到修改完成。不要让发布脚本递归覆盖 `users/*/sessions/*/client/skills/`，也不要在下发后格式化、改换行或重新编码会话代码。共享模块需与对应入口成套验证；信任校验会检查整个包的受保护文件。

升级启动后至少检查两种会话：

- **新会话**：先在管理页逐文件批准当前库的代码、辅助模块与 `config.json`，再创建新会话验证；未批准或改动后未确认的文件会拒绝执行，配置和依赖也要可用。
- **保留的旧会话**：已有的旧副本和原摘要匹配时应能继续执行旧版。它不会自动变成新版；清空聊天、重启、复制会话都不是刷新技能版本的方法。若旧版存在安全问题，应停止相关任务并处理受影响的旧会话，不能仅更新技能库。

首次启用“库文件版本白名单”时，库内 `.py` 和 `config.json` 需要管理员显式确认；不会因为文件位于库中、版本升级或历史维护事件而自动获准。批准状态保存在数据库 `skill_file_approvals`，后续相同字节升级可沿用，变化后的文件需重新确认。旧会话已有的记录保留；无记录时只采用当前显式批准摘要，不覆盖旧副本，也不自动修复差异。确认可信库后新建会话，不要期待重启给旧文件重新批准。MCP/A2A 新任务创建服务会话，临时工作台续聊沿用原会话；复用幂等键可能返回旧任务，核对真实任务与会话 ID。

迁移 Windows / Linux 或更换构建方式时，按原始字节传输已有会话与批准记录。LF/CRLF、BOM、JSON 缩进变化均会改变摘要。可以在**发布前**统一可信库的编码和换行，再为新会话下发；不能在校验时忽略差异，也不能事后统一旧会话文件的换行来“修复”。回滚时同样成套恢复备份，核对旧应用能否识别该版本的数据格式。

#### MD5 失败如何定位 {#skill-md5-troubleshooting}

`技能文件 MD5 校验失败，拒绝执行：<包内相对路径>` 表示此文件与该会话的批准摘要不同，脚本尚未启动。它本身不能证明被恶意篡改，也不能单凭这一行判定是模型、代理或操作系统的问题。一个辅助模块或 `config.json` 不匹配，就会让同包的所有脚本被拒绝。

先在资源监控或会话的工具详情记录任务/会话 ID、包名、报错的相对路径、应用版本，并区分：

| 观察结果 | 下一步 |
| --- | --- |
| 只有升级前旧会话失败，新建会话成功 | 对比旧副本、该会话摘要与当前库；重点核对首次启用门禁、旧配置修改、跨平台换行和备份版本 |
| 新建会话也失败 | 核对是否真的得到新 `session_id`、实际进程/容器卷和可信库路径；检查下发期间是否仍有写入。若库与新副本按同一版本生成仍失败，保留证据排查下发/校验实现，不要跳过检查 |
| 当前入口没变，但报辅助模块或配置不匹配 | 对比报错文件，而不是只比较入口 `.py`；核对整包升级和配置修改 |
| 所有包同时失败 | 优先查批量覆盖/格式转换、混用备份、首次门禁升级和目录/卷切换；这些是排查方向，不是已确认原因 |
| 报“白名单外”“缺失”或“链接” | 检查完整包、披露/下发范围、包内路径及文件类型；这些与 MD5 不匹配是不同的拒绝原因 |

下面是**只读核对示例**：替换占位路径与标识，使用部署环境的 Python 运行；它不加载项目、不调用模型、不执行技能、不改文件、不生成批准记录，也不输出配置内容。

```python
import hashlib
import json
from pathlib import Path

data = Path("/srv/umeko/data")
library = Path("/srv/umeko/skills")
user_id, session_id, pack = "usr_example", "sess_example", "sample-skill"
record = data / "skill_trust" / session_id / (pack + ".json")
session = data / "users" / user_id / "sessions" / session_id / "client/skills" / pack

def inspect(path):
    if not path.is_file():
        return {"exists": False}
    raw = path.read_bytes()
    return {"exists": True, "bytes": len(raw),
            "md5": hashlib.md5(raw, usedforsecurity=False).hexdigest(),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "crlf": raw.count(b"\r\n"), "utf8_bom": raw.startswith(b"\xef\xbb\xbf")}

approved = json.loads(record.read_text(encoding="utf-8"))["files"] if record.is_file() else {}
print("approval_exists:", record.is_file())
for relative in sorted(set(approved) | {"scripts/run.py", "assets/config.json"}):
    # The two sample paths can be replaced with the path reported by the tool.
    parts = relative.split("/")
    if any(p in {"", ".", ".."} or ":" in p or "\\" in p for p in parts):
        raise ValueError("Invalid relative path in approval record")
    print(json.dumps({"file": relative, "approved": approved.get(relative),
                      "session": inspect(session.joinpath(*parts)),
                      "library_now": inspect(library.joinpath(pack, *parts))}, ensure_ascii=False))
```

解释结果：会话摘要匹配批准记录即可保持原信任，当前库可以是更新版本；“库与会话不同”本身不一定故障。若记录匹配当前库、却不匹配旧会话，可能是旧会话首次建立记录后遇到版本差异；需结合升级时间和备份确认。若记录匹配原备份，却不匹配当前会话，则进一步检查会话是否被覆盖或转换格式。字节数不同表明文件不同，字节数相同也不代表摘要相同；不能仅凭打开文件后“内容看起来一样”判断安全。

#### 安全恢复

优先审查并确认管理员库版本，**新建会话**验证，再迁移需要继续处理的用户输入与普通工作文件。不要复制失败会话的 `client/skills/` 或批准记录到新会话；复制整个旧会话同样会保留旧问题。

管理员安全门禁只管理当前库版本，不处理旧会话。若必须延续原会话，可停止服务并保留故障现场，从可信、同一时间点的备份恢复与原批准记录匹配的会话文件及必要数据，再离线核对摘要并验收。不能确定可信版本时保留拒绝，转到经过验证的新会话。

不要删除 `skill_trust/`、手改 JSON 中的 MD5/SHA-256、从当前用户副本重新计算白名单、跳过辅助模块，或关闭校验。删除记录不会刷新旧文件，反而可能在恢复时用另一版本的库建立摘要；直接认可当前字节也会把未知改动变成可信代码。

#### 管理页当前版本信任管理 {#skill-admin-reapproval}

1. 在独立管理入口打开“技能库”，确认当前管理员库中的入口、辅助模块和配置是要交付的版本。选择 `.py` 或 `config.json`，先保存，再点“安全门禁”。不要把未核实的会话文件上传覆盖可信源。
2. 查看当前版本状态与 MD5 / SHA-256：“当前版本未加入白名单”表示尚未批准；“文件已变化，需重新确认”表示当前字节与最近批准版本不同；“当前版本已信任”表示双摘要匹配。
3. 审查无误后点“加入可信白名单”。服务重新读取已保存的库文件，批准该版本并记录确认人和时间。状态应变为已信任；若文件在查看后变化而返回 `409`，先刷新、核对后再操作。
4. 对包内入口、辅助 `.py` 模块与 `config.json` 逐文件确认。批准只影响所选文件；其他受保护文件未批准或变化时，整包仍拒绝执行。管理端脚本测试也遵循这个门禁。
5. 新建会话或提交新的 MCP/A2A 任务验证真实入口。按钮不扫描、修改或重新下发旧会话。批准与审计保存在数据库 `skill_file_approvals` 和 `skill_file_approval_events`，随数据库备份；重启无需重复确认相同版本，后续文件字节变化才需再次批准。

需要集中维护时，使用“技能库 → 可信代码管理”，按技能、状态、文件类型筛选或搜索路径。可多选、全选当前页或选择全部筛选结果，再批量加入可信区或移出；批量失败不回滚其他文件的成功操作，请查看失败详情，刷新并核对变化的文件后再选择。

移出会撤销该文件此前下发版本的后续执行权限，包含旧会话；不会删除会话文件或中断已经启动的脚本。重新批准只允许新会话取得新授权，不恢复此前已撤销的会话。数据库 `skill_file_revocations` 与批准、审计一起备份。旧记录不需要人工迁移；没有授权序号的旧会话可按原摘要运行，直到管理员显式移出相关文件。

## 多 Agent 路径部署

内置 `image-qc` 在管理端“服务接入”中配置，其他 Agent 在此新建并启用，再把调用方 URL 更新为它的完整地址。旧全局 Card 编辑接口与顶级机器入口已删除。

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
| 用户页正常，但管理页资源、登录或功能请求 404 | 更新服务代码与前端资源，配置 `UMEKO_ADMIN_BASE_PATH`，将此路径下全部请求代理到管理端口，重启并刷新 |
| 提问请求 202，但一直没有回答 | 分开检查事件接口 `/v1/runs/{id}/events` 和模型调用结果，不能把 202 当作回答成功 |
| 回答全部结束后才一次出现 | 每层 NGINX 关闭 `proxy_buffering`，核对外层代理的缓冲和超时设置 |
| 上传文件返回 413 | 核对 NGINX 的 `client_max_body_size` 及其他入口限制；头像接口另有 2 MB 应用限制 |
| 模型 `CERTIFICATE_VERIFY_FAILED` | 配置 `MODEL_CA_FILE`，核对文件可读、模型域名、证书有效期和证书链 |
| 文件下载 `TLS_CERTIFICATE_VERIFY_FAILED` | 配置 `UMEKO_DOWNLOAD_CA_FILE`；临时兼容指定主机可用 `UMEKO_DOWNLOAD_TLS_INSECURE_HOSTS`，详见[内网文件下载](#download-network) |
| 浏览器提示网站证书不可信 | 检查网站入口的 HTTPS 证书及浏览器的公司 CA 信任；`MODEL_CA_FILE` 只影响 Python 调用模型 |
| 新进程里 Provider / 用户 / 历史消失 | `.env` 选择、实际数据目录和容器持久化挂载是否仍与原安装一致 |
| 升级后技能报 MD5 失败或 `SCRIPT_TRUST_REJECTED` | 区分新旧会话，对比会话副本、原批准记录及当前可信库，按[技能升级与排查](#skill-security-upgrade)处理，不清空记录或关闭检查 |
| 页面可以用，但管理面 9000 连不上 | 是否启用 `--no-admin`，以及管理面是否仍监听 `127.0.0.1`；它与用户面地址独立 |
| Run 接口间歇性 404，或重启后任务找不到 | 是否启用了多 worker / 多实例，或进程重启；当前 Run 状态在单进程内 |

参考：[NGINX proxy_pass](https://nginx.org/en/docs/http/ngx_http_proxy_module.html#proxy_pass)、
[FastAPI 代理与 root_path](https://fastapi.tiangolo.com/advanced/behind-a-proxy/)、
[Uvicorn 设置](https://uvicorn.dev/settings/)。
