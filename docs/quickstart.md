# 快速上手

## 1. 安装并启动

需要 Python 3.10 或更新版本。在项目根目录执行：

```sh
uv sync --extra server
uv run python -m umeko.server --host 127.0.0.1 --port 8000
```

没有 `uv` 时：

```sh
python -m pip install -e ".[server]"
python -m umeko.server --host 127.0.0.1 --port 8000
```

服务默认提供两个入口：用户工作台 `http://127.0.0.1:8000/`，管理面 `http://127.0.0.1:9000/`。命令在前台运行，关闭终端或按 `Ctrl+C` 会停止服务。

Windows 可从 [GitHub Releases](https://github.com/umeiko/UmEkO/releases) 下载 exe；详细启动参数和升级方法见[部署指南](deployment.md)。

## 2. 配置模型

打开管理面，首次默认管理员是 **your-admin-name / your-admin-password**。这个默认值只用于没有管理员的数据库，重启不会重置已有密码。

在 Provider 页面添加模型服务地址和 API Key，再添加模型名称、视觉能力与并发上限，激活一个主模型。模型上限填 `0` 表示无限制；如果公司按模型限制同时请求数，就填该模型的额度。

模型配置保存在 `UMEKO_DATA_ROOT/umeko.db`。`.env` 只放部署类配置，例如：

```ini
UMEKO_DATA_ROOT=server_data
UMEKO_BASE_PATH=
MODEL_CA_FILE=
UMEKO_ADMIN_USERNAME=your-admin-name
UMEKO_ADMIN_PASSWORD=your-admin-password
```

如果沿用旧版 `.env` 中的模型配置，按[迁移说明](deployment.md)迁入 Provider 注册表。

## 3. 验证第一轮对话

打开用户工作台，注册或登录，创建会话并提问。看到文字逐步出现，并且最终结束，才算模型与流式链路跑通。`/health` 成功只说明 HTTP 服务在运行。

![工作台](screenshots/workspace.png)

## 4. 选择使用方式

| 需求 | 入口 |
| --- | --- |
| 多人共享、账号与管理面 | `python -m umeko.server` |
| 个人本机使用、免登录 | `python -m umeko.local --port 8765` |
| 终端对话 | `python -m umeko.cli` |
| 用程序调用 | [API 调用入门](api/quickstart.md) |

本地免登录模式允许本机命令执行，适用于个人电脑。共享服务使用带登录的 `umeko.server`。

## 5. 公司域名加路径的部署

假设用户入口是 `https://example.internal/doc-master/consistency/image-text/`：

```ini
UMEKO_BASE_PATH=/doc-master/consistency/image-text
MODEL_CA_FILE=/path/to/company-ca.pem
```

前缀用于网页资源、API、Cookie 与下载地址；CA 用于验证模型服务的 HTTPS 证书。这两项解决的是两条不同链路。代理还需正确去掉一次前缀，并关闭 SSE 缓冲，配置样例见[部署指南](deployment.md)。
