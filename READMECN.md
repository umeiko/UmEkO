<div align="center">

# UMEKO

**统一多智能体执行内核与编排器**

[![CI](https://github.com/umeiko/UmEkO/actions/workflows/ci.yml/badge.svg)](https://github.com/umeiko/UmEkO/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/umeiko/UmEkO?include_prereleases)](https://github.com/umeiko/UmEkO/releases)
[![Python](https://img.shields.io/badge/python-3.10+-blue)](https://www.python.org)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

[English](README.md) | **简体中文**

</div>

---

一个领域无关的**通用 Agent 平台**：对话式处理文件、派发子任务、管理模型与用户——既可做云服务，也能以单文件 exe 本地部署。

| ![](docs/screenshots/workspace.png) | ![](docs/screenshots/admin.png) |
|:---:|:---:|
| 工作台：流式对话 + 工具调用实时检视 + 文件树 | 管理控制台：用户 / Session / 供应商注册表 |

## 特性

- **WebUI**：流式对话、工具调用详情（执行中实时滚动输出 + 涉及图片缩略图预览）、文件树过滤、图片/CSV/Markdown 预览、7 种界面语言
- **双 Agent**：主 Agent + 受限文件子 Agent（`delegate_task`），子 Agent 上下文汇报后销毁，保护主上下文
- **视觉管线**：`image_reasoning` 按任意 prompt 分析图片（写「提取全部文字」即 OCR），输出实时流进工具卡片
- **供应商注册表**：多 Provider 多模型、视觉能力标记、粘贴 JSON 批量导入、一键切换并全员即时生效
- **管理面**：独立端口（默认 9000）、用户/Session 管理、技能包编写（提示词 + 沙箱 Python 脚本）、配置热更新即时驱逐
- **文件工具**：沙箱读写、正则/grep 搜索、目录树（单目录 50 项折叠 + 整树上限）、7-Zip 解压、拖拽上传到指定目录
- **持久化**：工具调用历史、附件映射、配置覆盖层全部 SQLite 落盘
- **取消与流式**：协作式取消、全链路 SSE

## 快速开始

### 下载 exe（Windows）

从 [Releases](https://github.com/umeiko/UmEkO/releases) 下载 `umeko-server.exe`，放到空目录双击即用。

零配置首启：服务直接起来，默认管理员 `umeko / 1234`，自动生成 `.env` 模板——可以编辑 `.env` 配模型，也可以完全在管理面里配。

```ini
TEXT_MODEL_NAME=your-model
TEXT_MODEL_BASE_URL=https://api.example.com/v1
TEXT_MODEL_API_KEY=sk-xxx
# 可选——启用 image_reasoning：
# VISION_MODEL_NAME=your-vision-model
# VISION_MODEL_API_KEY=sk-xxx
# VISION_MODEL_BASE_URL=https://api.example.com/v1
```

```bash
umeko-server.exe --port 8000          # WebUI  http://127.0.0.1:8000
                                      # 管理面 http://127.0.0.1:9000
```

### 源码运行

```bash
git clone https://github.com/umeiko/UmEkO.git
cd UmEkO
uv sync                                   # 或 pip install -e ".[dev]"
uv run python -m umeko.server --port 8000 # 云模式（8000 + 管理面 9000）
uv run python -m umeko.local  --port 8765 # 本地模式（免登录）
```

## 架构

```
┌────────────────────── 交付层 (L3) ──────────────────────────┐
│  server/（FastAPI + WebUI + 管理面）  local.py  cli.py(REPL) │
├────────────────────── 宿主服务 (L2) ────────────────────────┤
│  service.py（Session/Run/配置）  storage.py  profile.py     │
├────────────────────── 运行时 (L1) ──────────────────────────┤
│  agent.py  sub_agent.py  runner.py（Run 生命周期）  events   │
├────────────────────── 内核件 (L0) ──────────────────────────┤
│  llm/（OpenAI 兼容，流式）  skills/  cancellation.py        │
└──────────────────────────────────────────────────────────────┘
```

单一事件通道（`events.py`）：Web、CLI 与未来的 IDE 客户端共享同一事件流。详见 [ARCHITECTURE.md](ARCHITECTURE.md)。

## 技能包

一个技能包 = 同名 `.md`（提示词）+ 同名文件夹（附属资产）：数据文档（如检查项清单，Agent 用 `read_pack_file` 按需读最新版）和沙箱 Python 脚本（`run_skill_script` 确定性执行，带超时与取消）。管理员在管理面编写、下发、启停、检测版本；用户在会话里一键挂载。

## 配置优先级

**供应商注册表（管理面）> DB 覆盖键 > .env**；配置变更立即驱逐所有在线 Session。管理员在 9000 端口的「Provider / Model」页维护注册表，运行参数（最大工具轮次，支持无限）也在管理面设置。

## 开发

```bash
uv run pytest                    # 测试
uv run pyinstaller umeko.spec    # 构建单文件服务端 exe
```

领域流程（作图、文档质检……）不进基座：以技能包注入即可。
