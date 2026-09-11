# Umeko 分层架构

> UMEKO — Unified Multi-agent Execution Kernel & Orchestrator
> 统一多智能体执行内核与编排器 · 架构设计 v1（2026-09-11 定稿）

## 设计目标

1. **前后端解耦**：core 不只服务 webserver，同时服务 CLI 与未来的 IDE。
2. **两类场景分层复用**：云化多租户服务 / 本地 IDE 个人使用——边界不同，
   代码最大程度共享，差异收敛为配置而不是分支。

## 四层结构

```
┌────────────────────────────────────────────────────┐
│ L3 交付层（薄适配器，不含业务逻辑）                     │
│   server/(FastAPI·云)   local.py(本地IDE)   cli.py   │
├────────────────────────────────────────────────────┤
│ L2 宿主服务层 host/（纯 Python，零 Web 框架依赖）       │
│   service.py   storage.py   profile.py               │
├────────────────────────────────────────────────────┤
│ L1 运行时                                            │
│   agent.py   sub_agent.py   session.py               │
│   events.py(事件协议)   runner.py(Run 生命周期)        │
├────────────────────────────────────────────────────┤
│ L0 内核件（领域无关，稳定不动）                         │
│   llm/   cancellation.py   images.py   skills/       │
│   skillpacks.py   skill_agent.py   prompts/          │
└────────────────────────────────────────────────────┘
```

依赖规则：只允许上层依赖下层；L2 及以下**禁止 import 任何 Web 框架**。

## 两个解耦总开关（L1）

### events.py — 统一事件协议

引擎（UmekoAgent / FileSubAgent）只 `on_event(type, data)` 产生事件，
轻量类型化（type 为字符串常量、data 为 dict，新增类型不破坏旧前端）。
各交付端各自渲染：

- CLI → 终端打印（`cli.py:_render`）
- Web → L2 合成宿主事件后经 SSE 推流（`host/service.py:on_event`）
- IDE → webview 消息（未来）

旧的分立回调（on_delta/on_tool_call 等）保留为兼容通道，与 on_event 扇出
同一份事件（`agent.py:_fanout_*`）。

### runner.py — Run 生命周期

一次用户输入 → 一个 `Run`（可取消、事件缓冲、状态机）。
`RunManager`（注册表 + 线程池）从 server 上提到 L1，CLI 与 Web 走同一条
路径，行为（取消、事件、终态）天然一致。

## L2 宿主服务（host/）

| 模块 | 职责 |
|---|---|
| `service.py` | `AgentService`：Session 装配（Session+UmekoAgent）、运行调度、工作区文件安全、Skill 资源、路径脱敏；把 L1 引擎事件合成为宿主事件（usage/workspace.changed 等） |
| `storage.py` | `Store`：用户/Session/消息/上下文摘要/Skill 挂载的 SQLite 持久化（云与本地同一 schema） |
| `profile.py` | **场景边界配置**，见下 |

## 两类场景：一个 Profile

| 边界 | 云 `CLOUD_PROFILE` | 本地 `LOCAL_PROFILE` |
|---|---|---|
| 入口 | `python -m umeko.server`（:8000） | `python -m umeko.local`（:8765） |
| 身份 | cookie 认证、多租户隔离 | 隐式单用户 `local`，免登录 |
| `run_command` | 禁（runner 被强制置 None） | 放行（`LocalCommandRunner`） |
| 路径展示 | `web_text` 脱敏为 Session 相对路径 | 真实本地路径（IDE 可跳转） |
| 存储 | 同一套 SQLite schema，users 表本地退化为单行 | 同左 |

**同一个 `create_app(profile=...)`**：FastAPI app 工厂吃 Profile；
本地模式中间件注入隐式用户，前端零改动直达工作台。
新增边界差异时优先在 Profile 加开关，而不是在交付端写 if。

## 未来 IDE 的两条接入路径

1. **本地 HTTP + webview**：直接复用 `umeko.local`（已在跑），零新代码。
2. **进程内嵌入**：`import umeko.host` 直接装配 AgentService——
   host 层不依赖 FastAPI，IDE 插件可抛开 HTTP 整层。

## 关键决策记录

- 事件协议轻量类型化（str + dict），不做每事件 dataclass——向前兼容优先。
- 存储 schema 云/本地统一，认证是可插拔层，不做两套存储。
- CLI 统一走 Runner，与 Web 行为一致（取消/事件/进度），不图轻直连。
- 领域注入点不变：`UmekoAgent(settings, session, system_prompt, extra_skills=[...])`，
  领域（如文档质检）以 system_prompt + 领域工具注入，不进内核。

## 管理面（云模式）

隐藏方式是**端口分离**而非藏路径：管理面是独立 FastAPI app
（`server/admin.py`），随 `python -m umeko.server` 同进程启动在独立端口
（默认 127.0.0.1:9000，`--admin-host/--admin-port/--no-admin` 可调）。
用户面 app 中**不存在任何 /admin 路由**（访问返回 404 而非 403），
管理面无 OpenAPI 文档暴露。

- 认证：users 表 `role` 列（旧库自动 ALTER 迁移），仅 `role='admin'` 可登录，
  独立 `umeko_admin` cookie；首个管理员由 `UMEKO_ADMIN_USERNAME`/
  `UMEKO_ADMIN_PASSWORD` 环境变量引导创建；降级/删除兜底"至少保留一个管理员"
- 用户管理：列表（含 Session 数）/新建/重置密码/角色切换/删除（驱逐内存态
  + DB 级联 + 磁盘目录）
- Session 管理：按用户列出（内存态/上下文占用）/驱逐/删除
- Provider/Model 注册表：`providers` + `provider_models` 表（多 Provider 多模型，
  模型带视觉标记）；首次启动用 .env 播种 `default` Provider。管理面左右分栏
  维护，支持粘贴 JSON 批量导入（同名合并、可带 `active` 一并激活）。
  「设为当前」后 `service.reload_config()` 重载并**驱逐全部在线 Session**；
  生效优先级：注册表激活模型 > app_config 覆盖键 > .env。
  激活模型无视觉时自动选注册表第一个视觉模型做 OCR 兜底（优先同 Provider）；
  有视觉则不再配置兜底

## 已知边界与后续项

- 本地模式文件沙箱仍与云一致（Session 三节点）；个人 IDE 按需放宽是
  Profile 的下一个候选开关。
- `LocalCommandRunner` 目前无逐条确认（个人本机 MVP）；接 IDE 时应由
  IDE 侧提供确认 UI 的 CommandRunner 实现。
- `agent.py:on_progress` 回调当前无生产者（历史遗留），暂保留。
