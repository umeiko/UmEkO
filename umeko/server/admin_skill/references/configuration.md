# 配置指引

阅读顺序：连接身份 → 模型 → 技能 → 智能体 → 权限与监控。只执行用户要求的部分，保留无关配置。精确字段见 [接口完整参考](api-reference.md) 和在线 `/admin/v1/openapi.json`。

## 1. 准备本地 Agent

下载 Skill.zip 并解压，保留 `umeko-server-admin/SKILL.md`、`references/`、`scripts/`。客户端支持技能安装时按其目录约定安装；也可以让能执行 HTTP 请求或 Python 的 Agent 直接读取本目录。

在 Agent 运行环境配置以下本地变量，不把凭据贴进聊天：

| 变量 | 含义 |
| --- | --- |
| `UMEKO_ADMIN_URL` | 管理外部完整基址，含可选管理前缀 |
| `UMEKO_ADMIN_USERNAME` / `UMEKO_ADMIN_PASSWORD` | 已有管理员账号 |
| `UMEKO_ADMIN_CA_FILE` | 可选，追加企业 CA PEM；仍校验主机名 |
| `UMEKO_ADMIN_PROXY` | 可选，显式代理地址；不默认使用系统代理 |

例如管理基址为 `https://admin.example.internal/operations/console`；命令路径中不再写 `/operations/console`。若本地 Agent 在另一台机器上运行，必须能访问该实际域名；`127.0.0.1` 只代表 Agent 自己所在机器。

Python 客户端无第三方依赖，Python 3.10+ 可用：

```sh
python scripts/admin_api.py GET /admin/v1/me
python scripts/admin_api.py GET /admin/v1/openapi.json --output current-openapi.json
```

每次命令在内存中完成登录、调用、退出，不持久化 Cookie。多个相关操作可导入 `AdminClient` 并在同一个 `with` 中复用会话。此管理客户端只接受 `/admin/...` 路径，不能用来直接提交机器任务；业务测试使用单独的机器客户端。

## 2. 配置模型和并发

先 GET `/admin/v1/providers` 核对已有 Provider 和模型，保存实际 ID。Provider 的 `base_url` 是上游模型服务地址；Key 从本地安全存储读取后构造请求文件。不要把脱敏后的占位字符串作为新 Key 保存。

- 创建 Provider：POST `/admin/v1/providers`，必需 name、base_url、api_key，可选 proxy。
- 新增模型：POST `/admin/v1/providers/{provider_id}/models`，使用上游 model name；`vision` 标记视觉能力，`max_concurrent_requests` 是每模型并发。
- 修改并发：PUT `/admin/v1/models/{model_id}`，请求 `{"max_concurrent_requests":2}`；`0` 表示无限。该接口支持部分更新，不提交其他字段。
- 平台默认主模型：PUT `/admin/v1/active-model`，`{"model_id":"实际ID"}`。它会重载并驱逐在线会话缓存；执行前说明影响。
- 智能体的默认主模型和默认视觉模型在智能体配置中设置，不让外部机器调用者任意选择模型。

客户端默认遮蔽 Provider Key。变更请求放 UTF-8 JSON 文件，使用 `--json-file`，响应为 204 时不解析 JSON；修改后 GET 回读。管理面健康状态不证明上游模型可用。

## 3. 维护技能

GET `/admin/v1/skill-library` 查看文件树，GET `/admin/v1/default-skills` 查看下发状态。逻辑入口 `example.md` 映射到管理员库的 `example/SKILL.md`。

1. PUT `/admin/v1/skill-source/example.md` 保存合法主指引，正文是 `{"content":"完整SKILL.md"}`。
2. Python 入口/辅助模块使用 `/admin/v1/skill-scripts/{pack}/{script_name}`，附属文本使用 `/admin/v1/skill-members/{pack}/{member_name}`；路径相对包目录。
3. 需要下发时 POST `/admin/v1/default-skills/import/example.md` 从库导入，或 PUT 下发入口同步正文。检查 imported、enabled、stale；toggle 只有目标不同才调用一次。
4. 对 `.py`、`config.json` 的批准必须有用户授权。审核源文件后 GET 门禁，POST 当前 `current.sha256`；源版本变化返回 409 时重新核对。写入文件不会自动变可信。
5. 新建会话验证；已有会话继续使用自己的副本。不要重签旧副本、清空摘要或关闭检查。

撤销用 `approved.sha256`，批量结果逐项检查。脚本测试需要整包受保护文件获准，测试不是 Python 安全沙箱。配置文件里的服务端二进制路径必须由服务器管理员按其允许的部署范围维护。

## 4. 配置用户与接入

用户工具权限 `allowed_tool_names=null` 跟随全局，`[]` 关闭可配置工具，明确数组是完整个人授权。模型权限必须同时提交供应商与模型字段；供应商 null 为全部，模型 null 为默认下发，空数组关闭相应范围，最终取交集。不得为了完成一次调用而给无关账号扩大权限。

机器鉴权 GET/PUT `/admin/v1/service-access`，required 是服务凭据，anonymous 是共享免鉴权身份；改成匿名也不会免除管理员身份检查。按用户要求保留当前模式，不为方便测试自行改成匿名。

创建/轮换服务凭据只有一次返回 Token，使用 `--secrets-output <调用者指定的新文件>` 留存；文件须放在受限目录。机器凭据不同于管理员密码，也不同于上游模型 Key，不向服务对象发放 Provider Key。

## 5. 发布与排查

按 [智能体发布与冒烟测试](agent-publishing.md) 进行发布验收。管理员可以读取资源、任务详情、上下文、工具记录和文件元数据，不需要进入用户会话运行模型。

超时先回读，尤其不要盲目重放创建、导入、toggle、轮换凭据与脚本执行。取消任务后确认终态；驱逐缓存保留历史，删除用户/会话/服务账号会清理数据，只处理明确指定的目标。

需要修改监听地址、CA、前缀或 `UMEKO_PUBLIC_URL` 时，向服务器操作者说明需调整的部署项；管理 API 不能热改这些参数。提示词中的管理基址不能冒充用户服务的公开地址。
