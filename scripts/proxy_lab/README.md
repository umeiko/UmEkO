# 本地代理与私有证书复现实验

当前实验用于验证已修复的 UmEkO：运行时前缀、共享 Provider 注册表及模型 CA 配置。
此前的故障复现记录保留在本说明后面的历史结果中。
不会读取项目 `.env`，不会使用真实模型密钥，不会改动系统 hosts、系统证书或 Docker 数据。

## 修复验收（2026-09-30）

Docker 的前缀实例显式设置 `UMEKO_BASE_PATH` 和 `MODEL_CA_FILE`，根路径对照实例保持前缀为空。
两个实例使用隔离的数据目录，模型通过与管理面相同的 Provider 注册表配置。

- 页面全部 5 个 CSS/JS 资源正确带前缀，登录、Cookie、会话和文件下载正常。
- 实际 UmEkO Agent 使用私有 CA 假模型，回答分 3 段经两层 NGINX 抵达浏览器。
- 根路径与前缀路径的真实前端均验证了头像、文本预览和流式回答。
- 流式接口故意返回 404 时能查询最终回答；任务查询也失败时明确报错并恢复输入。
- 错误模型 CA 仍拒绝 TLS 连接，未关闭证书校验。

浏览器验收使用 `browser_verify.cjs`（需要 Playwright；可通过 `LAB_PLAYWRIGHT` 指定包路径）：

```sh
node scripts/proxy_lab/browser_verify.cjs
```

忽略的 `docker-evidence.local/` 中保存了 `report-before-fix.json`、`browser-report-before-fix.json`
以及修复后的 `report.json`、`browser-fix-report.json` 和截图；下文原始结果作为历史复现记录保留。
部署和配置迁移步骤见 [部署说明](../../docs/deployment.md)。

## DNS 和 ALB 的区别

- DNS 回答：`某个域名对应什么 IP？` 它不处理 `/doc-master/...` 这样的网页路径。
- ALB 接收真正的 HTTP/HTTPS 请求，然后按照域名、路径等规则选择后端。
- DNS 可以把域名指向 ALB 的入口，因此看起来像一件事，实际上是先找入口，再由入口转发。
- 本实验用 `localhost`，由系统解析到本机。无需额外搭 DNS 服务。
- 外层 NGINX 模拟 ALB 的 HTTPS 与路径选择；这不是云厂商的真实 ALB，不覆盖其健康检查、超时上限、HA 或多实例状态。

```text
浏览器 / 验证脚本
  https://localhost:18443/doc-master/consistency/image-text/
    ↓ 外层 NGINX：模拟 ALB，仅匹配此前缀，保留完整路径
  http://127.0.0.1:18080/doc-master/consistency/image-text/
    ↓ 内层 NGINX：移除一次此前缀
  http://127.0.0.1:18000/  隔离的 UmEkO
    ↓ 当前模型客户端
  https://localhost:19443/v1  假模型，使用另一套自建 CA
```

## Windows 运行

需要 Python 和 `uv`（无 uv 时回退到 pip）。在项目根目录执行：

```powershell
python scripts/proxy_lab/lab.py prepare
python scripts/proxy_lab/lab.py start
python scripts/proxy_lab/lab.py verify
python scripts/proxy_lab/lab.py status
python scripts/proxy_lab/lab.py stop
```

`prepare` 在 `%LOCALAPPDATA%/UmekoProxyLab/<项目路径哈希>/` 创建独立虚拟环境，
安装项目的 server 依赖、cryptography 和 psutil，并从 nginx.org 下载固定版本的 Windows NGINX。
下载 URL 和 SHA-256 保存在 `download.json`。实验服务器仅监听 `127.0.0.1`；不占用现有 `8000`。
实际目录会记录在已被 Git 忽略的 `runtime.local` 中，以兼容 Windows 应用的目录重定向。
`status` 显示当前实际目录，也可以通过 `--runtime` 显式选择另一套隔离目录。
`stop` 通过 PID 与进程创建时间确认身份，只停止本实验的进程。实验数据、报告和证书保留，方便复查。

启动后可以在浏览器访问：

- `http://localhost:18080/doc-master/consistency/image-text/`：不涉及浏览器证书信任，直观看到原网页资源加载失败。
- `https://localhost:18443/doc-master/consistency/image-text/`：完整两层代理链路。浏览器未信任实验 CA 时会先显示证书提示；这是额外的浏览器信任问题。

验证脚本会显式加载实验 CA，并保持证书验证开启，因此它可以独立验证 HTTPS 链路。
无需把实验 CA 导入 Windows 系统证书库。证书有效期 30 天；过期后为实验换一个新的 `--runtime` 目录。

## Docker 中运行红帽 UBI 9

需要 Docker Desktop 的 Linux 引擎正常响应 `docker info`。UBI 9 是[红帽公开提供的 RHEL 9](https://access.redhat.com/articles/4238681)
容器基础镜像；容器不是完整虚拟机。本实验在此基础上安装 Python 和 NGINX。

在项目根目录执行。所有命令都显式指定实验的 env 文件，避免读取项目 `.env`：

```powershell
docker compose --env-file scripts/proxy_lab/docker.env -f scripts/proxy_lab/compose.yaml build app
docker compose --env-file scripts/proxy_lab/docker.env -f scripts/proxy_lab/compose.yaml up -d app root-app model web-proxy edge baseline
docker compose --env-file scripts/proxy_lab/docker.env -f scripts/proxy_lab/compose.yaml ps
docker compose --env-file scripts/proxy_lab/docker.env -f scripts/proxy_lab/compose.yaml run --rm verifier
```

`docker.env` 中的 `LAB_BUILD_PROXY` 仅供镜像构建下载依赖。本次按用户提供的 Windows
`127.0.0.1:7890` 代理，使用容器内可识别的 `host.docker.internal:7890`；不需要代理时将其值留空。
该代理不会设置到项目运行容器。容器内部的 `127.0.0.1` 表示这个容器自己，不能代指 Windows。

四个运行容器通过 Docker 的服务名解析相互访问：

```text
Windows 浏览器 https://localhost:28443/doc-master/consistency/image-text/
  → edge:18443       外层 NGINX 模拟 ALB：匹配并保留前缀
  → web-proxy:18080  内层 NGINX：移除一次前缀
  → app:18000        实际 UmEkO 后端（运行时前缀 + 模型 CA）
  → model:19443      HTTPS 假模型，使用独立 CA
```

Docker DNS 只把 `app`、`model` 等服务名换成容器 IP；NGINX 才负责转发网页路径。
浏览器可先访问 `http://localhost:28080/doc-master/consistency/image-text/` 检查网页与资源正常加载，
再使用 HTTPS 入口。HTTPS 浏览器证书提示与模型服务器的证书问题是两件事。

部署复现入口的两个代理端口和原界面对照端口均只发布到 Windows 的 `127.0.0.1`，后端和假模型只连接隔离的内部网络。
项目代码只读挂载，实验数据与证书在本实验专用的 Docker volume 中。
当前验证器输出 `PASS` 表示修复后的链路或严格证书校验的正反例通过；仍使用假模型。

查看日志或停止本实验（保留实验 volume）：

```powershell
docker compose --env-file scripts/proxy_lab/docker.env -f scripts/proxy_lab/compose.yaml logs --tail 40 edge web-proxy app model
docker compose --env-file scripts/proxy_lab/docker.env -f scripts/proxy_lab/compose.yaml down
```

Windows 便携实验与 Docker 实验使用不同端口，可以同时运行。

### 历史复现：为什么故障页面看起来完全不同

`28080/doc-master/consistency/image-text/` 返回的 HTML 与项目的 `umeko/server/static/index.html`
内容相同。它里面却写着 `/static/app.css`、`/static/app.js` 等从网站根目录开始的地址，
浏览器因此请求 `28080/static/...`，而不是 `28080/doc-master/consistency/image-text/static/...`。
这些请求没有匹配代理中的项目前缀，全部返回 404。

HTML 像页面的骨架，CSS 决定布局、颜色和样式，JavaScript 提供交互。
骨架拿到了，后两者没拿到，浏览器就显示一个样式全无、无法正常操作的页面。
这就是前缀故障造成的外观，不是替换了项目的前端。

原始复现阶段增加了 `baseline` 对照代理，连接同一个 `app` 容器。
当前修复验收改用独立的 `root-app`，保持前缀为空，与前缀实例共用相同生产源码：

- `http://localhost:28081/`：不带前缀的项目界面。
- `http://localhost:28080/doc-master/consistency/image-text/`：带前缀的修复验收入口。

以下是原始复现记录：当时两个入口的 HTML 都与项目源文件一致；对照入口的 5 个静态资源均返回 200，
CSS 已应用，JavaScript 未产生页面异常。证据在 `docker-evidence.local/frontend-comparison.json`
和 `baseline-frontend.png`；故障入口的同一组静态资源返回 404。

## WSL 运行同一实验

需要一个可用的 Ubuntu 等 WSL 发行版，而非仅有 Docker 管理的 `docker-desktop`。
Windows 便携版验证不能作为 WSL 实测结果。

在所选 WSL 发行版中安装 Python venv 和 NGINX（需管理员权限），然后在项目根目录运行：

```bash
sudo apt-get update
sudo apt-get install nginx python3-venv
python3 scripts/proxy_lab/lab.py prepare --nginx /usr/sbin/nginx
python3 scripts/proxy_lab/lab.py start
python3 scripts/proxy_lab/lab.py verify
python3 scripts/proxy_lab/lab.py stop
```

本实验启动自己的 NGINX 配置和 PID，不修改 `/etc/nginx/`。Linux 运行时目录默认是
`~/.local/share/UmekoProxyLab/<项目路径哈希>/`。首次安装系统 NGINX 时发行版可能启动默认服务，
它不属于本实验；不要用本实验的停止命令管理它。
Windows 是否能通过 localhost 访问 WSL，取决于 WSL 的网络模式和本机配置；先在 WSL 内验证，再测跨系统访问。

## 如何判读 verify 的结果

当前每项 `PASS` 表示修复后的成功链路或严格证书校验的预期拒绝已得到证据：

1. 网站 CA 正确时，两层代理与 `/health` 正常。
2. HTML 的 5 个 CSS/JS 地址全部正确带前缀并返回 200；根目录的同类地址仍不匹配项目路由。
3. 带前缀的注册、登录、Cookie、会话、上传和下载可用。
4. 用假事件驱动真实 UmEkO SSE 接口，检查三个增量分批到达及保活；该检查不依赖模型。
5. 实际项目 Agent 从 Provider 注册表取得模型配置，并用显式模型 CA 成功调用私有 HTTPS 假模型；三个回答增量分批到达。
6. 分别观察当前 SDK 和 HTTPX 对 `SSL_CERT_FILE` 的行为；不能仅凭 `trust_env=False` 断言所有 SDK、操作系统都忽略该证书文件。
7. 仅信任网站 CA 无法验证假模型，证明两条 HTTPS 链路的信任配置独立。
8. 修复后的项目客户端在 CA 正确时流式调用成功，在 CA 错误时仍拒绝连接。

最终证据在运行时目录的 `report.json`、`logs/nginx-access.log`、`logs/umeko.log` 和 `logs/fake-model.log`。
NGINX 日志以 `18443` / `18080` 标识入口和内层，可观察前缀在哪一层被移除。
浏览器验收脚本进一步检查实际 UI 的根路径和前缀路径、头像、预览和连接失败后的处理；
真实生产模型、企业 CA、云 ALB 规则和多实例状态仍需在对应环境验收。

## 历史故障复现：Windows（2026-09-30）

- Windows 便携版 NGINX 1.28.3，两层代理，Python 3.14.7；NGINX 配置检查成功。
- 浏览器通过 HTTPS 入口拿到首页（200），随后 5 个 JS/CSS 请求因缺少前缀返回 404。
- 验证脚本显式信任网站 CA；正确前缀的资源、登录、会话、上传、下载成功。
- 假事件经过真实 UmEkO SSE 接口和两层代理，三个增量分批到达，并收到保活。
- 当前 Agent 调用自建 CA 假模型，复现 `run.failed`；项目客户端直接检查得到 `CERTIFICATE_VERIFY_FAILED`。
- 在 Windows 中，设置 `SSL_CERT_FILE` 后当前客户端仍失败；SDK 显式加载模型 CA 后，假模型流式响应成功。
- 停止与重新启动已实测；只新增实验文件，项目生产代码未改动。
- Windows 便携实验最初因 Docker Desktop 的 `sailor-ingest.sock` 重命名失败而作为替代验证；该阶段没有 Linux 容器运行证据。

浏览器截图 `browser-reproduction.png` 与请求列表 `browser-report.json` 保存在运行时目录。
该浏览器截图检查仅为观察路径错误而忽略了浏览器的本地证书提示；HTTPS 证书正反例由上述验证脚本独立检查。

## 历史故障复现：Docker 红帽（2026-09-30）

- 开始此次尝试时 Docker 引擎已经恢复响应，服务端版本为 29.7.2。
- 官方镜像 `registry.access.redhat.com/ubi9/ubi:latest` 的直接下载最初停滞；
  后使用用户提供的 `127.0.0.1:7890` 代理下载官方镜像文件，校验 manifest、配置和层的 SHA-256，
  按 OCI 格式导入；随后 `docker pull` 成功。基础镜像摘要已固定在 `docker.env` 中。
- 容器内为 RHEL 9.8，Python 3.11.13，NGINX 1.20.1。
  两个 NGINX、项目后端、假模型四个运行容器均通过健康检查。
- 11 项验证成功，包括容器 DNS、两层 HTTPS 代理、原 UI 的路径故障、正确前缀的登录和文件传输。
- Windows 浏览器通过 Docker 发布的 HTTP 端口取得首页（200），5 个 JS/CSS 返回 404；此项检查路径和端口发布。
  Windows Python 显式加载网站 CA 并保持证书验证开启，通过 HTTPS 发布端口 28443 访问 `/health` 返回 200。
- 真实项目 SSE 接口的三个假事件在约 0.51、1.01、1.26 秒分批到达，收到 5 次保活。
- 原项目 Agent 未配置模型 CA 时调用失败；仅信任网站 CA 也不能验证模型。
  显式信任模型 CA 的 SDK 对照获得三个模型增量，约在 0.36、0.71、1.06 秒到达。
- 本次 OpenAI SDK 3.22.1 的默认客户端继承自 HTTPX2 2.13.1，使用 truststore 0.10.4。
  Linux 上设置 `SSL_CERT_FILE` 后该客户端调用成功；同环境的 HTTPX 0.28.1 配合
  `trust_env=False` 仍拒绝证书。检查安装源码发现 Linux truststore 通过 OpenSSL 默认路径读取证书环境变量。
  因此 Windows 结果不能直接推广到 Linux，生产环境还需核对实际 SDK 和系统。

Docker 报告和浏览器证据已导出到被 Git 忽略的 `scripts/proxy_lab/docker-evidence.local/`：
`report.json`、`browser-report.json`、`browser-reproduction.png` 和 `docker-metadata.json`。
也可以从容器再次导出报告：

```powershell
docker compose --env-file scripts/proxy_lab/docker.env -f scripts/proxy_lab/compose.yaml cp app:/runtime/report.json scripts/proxy_lab/docker-evidence.local/report.json
```

上述历史阶段完成的是故障复现和对照验证，当时生产代码未修改。当前修复验收见本文件开头；实际企业模型和云 ALB 尚未访问。
