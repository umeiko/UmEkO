# 文档维护

文档源文件在 `docs/`，导航与主题在 `mkdocs.yml`。GitHub Pages 只发布构建后的静态页面；不运行 UMEKO 后端。

## 本地预览与构建

使用 Python 3.11 创建独立文档环境，避免改变正在运行的服务依赖：

```sh
python -m venv .venv-docs.local
# Windows：.venv-docs.local/Scripts/python
# Linux / WSL：.venv-docs.local/bin/python
```

以下 `python` 指该环境中的解释器：

```sh
python -m pip install -r requirements-docs.txt ".[server]"
python scripts/generate_api_docs.py
python scripts/generate_api_docs.py --check
python -m mkdocs serve
python -m mkdocs build --strict
```

文档预览默认也用 8000 端口。若 Agent 服务已经占用，改成 `python -m mkdocs serve -a 127.0.0.1:8766`。构建输出 `site/`，不提交构建产物。

## API 文档同步

生成器创建临时数据库和占位模型配置，只读取应用路由和模型，不加载 `.env`、真实账号、Provider Key 或用户数据，也不发起模型调用。

它生成用户 / 管理 OpenAPI、完整接口参考和数据结构。FastAPI 不能自动推断 Cookie 中间件、原始 Request body 和 SSE，生成器显式补充这些约定。新增这类接口时，同步补充生成器和专题指南。

`--check` 比较已提交文档与当前代码，CI 会拒绝过期定义。生成环境的 FastAPI / Pydantic 版本与文档依赖保持一致，避免同一代码产生不同快照。

## 自动发布

[Documentation 工作流](https://github.com/umeiko/UmEkO/actions/workflows/docs.yml)在 main 上的文档或相关源码变化后构建、检查并发布到 [GitHub Pages](https://umeiko.github.io/UmEkO/)。PR 只构建验证，不替换正式站点；也可手动运行工作流。

仓库 Pages 的 Source 设置为 **GitHub Actions**。部署使用官方 Pages artifact 和 deploy actions，无需维护 `gh-pages` 分支。权限限定为读取源码、部署 Pages 与获取部署身份。[GitHub Pages 自定义工作流说明](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages)。

项目站有 `/UmEkO/` 前缀，`site_url` 必须保持完整路径，文档内部链接使用相对 Markdown 路径。改仓库名或绑定自定义域名时，同步更新 `site_url` 和 README 链接。

## 写作约定

- 描述已实现行为时核对代码，扩展方案标注“待实现”。
- 不在文档、截图或 OpenAPI 示例中放真实 Key、内部公司地址或用户数据。
- 接口变更同时更新专题说明与生成文件。
- 修改架构图后验证实际页面渲染；提交前运行严格构建并检查页面、搜索和移动导航。
