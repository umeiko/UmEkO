# UmEkO 前端

此目录可以整体放入独立 Git 仓库。源码、依赖、开发代理、构建和单元测试均在本目录，
需要 Node.js 24 和 npm。后端通过 HTTP API 与前端交互。

## 开发与构建

```sh
npm ci
npm test
npm run format:check
npm run build
npm run dev
```

构建输出为本仓库的 `dist/`，包含 `index.html`、`admin.html` 和 `assets/`。
开发入口为 `http://127.0.0.1:5173/` 和 `http://127.0.0.1:5173/admin.html`。
默认代理到用户后端 8000 和管理后端 9000。可将 `.env.example` 复制为 `.env.local`，
设置两个 `UMEKO_DEV_*_TARGET` 来连接其他后端，开发后端使用根路径。
普通 Vite preview 只预览静态文件，联调使用 dev 或下方的正式装配方式。

## 发布与分仓交付

前端仓将整个 `dist/` 作为版本化发布成品，后端部署时解包到独立目录，例如
`/opt/umeko-ui/releases/1.0.0/`。在后端配置中填写
`UMEKO_UI_DIR=/opt/umeko-ui/releases/1.0.0`，或启动时传 `--ui-dir`。
切换版本后重启后端。后端运行及打包只消费成品，无需前端源码或 Node.js。

用户和管理页面由对应后端端口加载同一份成品，浏览器 API 使用对应的同源入口。
部署网关继续分别转发用户和管理服务的全部子路径，SSE 关闭缓冲。
这种方式支持源码分仓与独立构建，由后端负责最终页面入口。

前端成品保留 `__UMEKO_BASE_PATH__` 模板标记和相对 `./assets/` 地址。
后端负责注入 `umeko-base-path`、`umeko-guide-url`，
临时工作台额外注入 `umeko-temporary-path`。静态资源地址为
`<对应前缀>/static/ui/assets/…`，API 通过 `src/shared/api.js` 的 `appUrl()` 生成。
修改部署前缀只调整后端运行配置，同一份成品可用于根路径和多级前缀。
Cookie 登录、上传、文件下载和 EventSource 共用这个入口。

集成分发需要内置前端时，由后端仓运行
`python scripts/sync_ui.py --source /path/to/frontend/dist` 导入成品，
再构建 wheel 或 exe。后端仓可用 `--check` 比较已打包的版本与指定成品。

## 与后端联调验收

`npm test` 是前端独立单元测试。`npm run test:smoke` 是可选的前后端集成验收，
需要后端测试依赖与 Playwright Chromium。单仓时自动使用父目录作为后端仓。
分仓时设置 `UMEKO_BACKEND_ROOT` 为后端源码目录，`UMEKO_TEST_PYTHON` 为其虚拟环境解释器。

```sh
npx playwright install chromium
UMEKO_BACKEND_ROOT=/path/to/backend UMEKO_TEST_PYTHON=/path/to/backend/.venv/bin/python npm run test:smoke
```

验收运行后端仓的 `tests/ui_fixture.py`，加载本前端仓的 `dist/`，
使用隔离数据库与受控模型回复，覆盖根路径和用户、管理独立多级前缀。
部署时沿用的后端协议参考包括用户 `/openapi.json` 与管理 `/admin/v1/openapi.json`，
管理规范需要管理员 Cookie。
