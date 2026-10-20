---
name: umeko-server-admin
description: 通过 UMEKO 管理 API 配置模型、智能体、技能、权限与服务接入，查看会话、机器任务和资源监控。用于管理服务器，不用于提交普通 MCP/A2A 业务任务。
---

# UMEKO 服务器管理

使用用户指定的 **管理服务基址**，含完整管理前缀。默认管理端口是 9000，用户/机器端口是 8000；实际地址以用户提供的入口为准。不要用 Provider 的 base_url、用户工作台或 Agent 的 MCP/A2A 地址管理服务器。

## 接入

1. 从管理入口下载 `/admin/automation/skill.zip`，解压后保留 `umeko-server-admin/` 目录。也可从 `/admin/automation` 清单逐个下载文件；清单给出版本、ZIP 和各文件 SHA-256。安装路径按所用 AI 客户端的技能约定选择。
2. 使用本地环境变量 `UMEKO_ADMIN_URL`、`UMEKO_ADMIN_USERNAME`、`UMEKO_ADMIN_PASSWORD`，或调用者已有的管理员 Cookie 会话。不要要求用户把密码、模型密钥或完整 Cookie 粘贴到对话中。凭据缺失时说明需要在本地配置，不猜默认密码。
3. 先 `GET /admin/v1/me` 验证身份，再读取受鉴权的 `GET /admin/v1/openapi.json`。以运行中服务的 schema 为参数依据；版本不一致时重新读取规范，不能靠历史印象猜字段。
4. 执行用户明确授权的管理任务。尚未收到具体变更任务时，仅验证连接与读取概览。已有明确授权无需重复请求确认；目标、删除范围或授权范围含糊时先澄清。

脚本只需 Python 3.10+，不安装第三方包：

```sh
python scripts/admin_api.py GET /admin/v1/me
python scripts/admin_api.py GET /admin/v1/openapi.json --output admin-openapi.json
python scripts/admin_api.py GET /admin/v1/providers
python scripts/admin_api.py PUT /admin/v1/models/<model_id> --json-file change.json
```

`change.json` 的并发修改示例为 `{"max_concurrent_requests":2}`。先从目录找到实际模型 ID，不把上游模型名称当作 ID。`UMEKO_ADMIN_URL` 已含前缀，命令的路径仍是 `/admin/v1/...`，只拼接一次。脚本登录后复用本次进程的 Cookie，结束时退出；不会自动重试变更。

## 操作方式

- 按当前规范读取状态、核对目标 ID，保留无关配置；更新只提交接口要求的字段。完整表单接口先读原记录再改目标字段。保存后 GET 回读，汇报具体变化及尚未验证的部分。
- **模型**：配置 Provider、模型能力与每模型并发。`0` 表示无限制。切换平台默认模型或工具回合上限会驱逐在线缓存，执行前说明对运行中任务的影响。
- **智能体与服务接入**：管理工作指引、默认主/视觉模型、技能范围、服务账号与接入方式。机器任务 Token 不能替代管理员登录；开启机器免鉴权不会开放管理 API。
- **权限**：null、空数组和明确列表意义不同；先读 [接口行为](references/api.md)。不要为了完成一次配置而给无关用户扩大权限。
- **技能**：管理员库、下发记录和旧会话副本是三个对象。更新库文件不等于更新默认下发内容；启停下发也不会回收旧副本。写文件、导入下发与审批代码是独立操作，不自动批准刚写入的代码。
- **可信代码**：只有用户授权审核/批准时才做。先读取并审核指定代码和配置，再 GET 门禁，批准用 `current.sha256`，撤销用 `approved.sha256`。409 时重新预览变更，不盲目换成新摘要重试。批量结果逐项检查，不把 HTTP 200 当作全部成功。保留旧会话与审计，不关闭门禁、不重签旧副本。脚本测试也需要整包通过校验，且不是安全沙箱。
- **监控与历史**：资源、任务、会话详情可读取。取消任务需再观察终态；驱逐缓存保留历史，删除会话/用户/服务账号会清理数据。按用户授权的明确目标操作，不扩大删除范围。

## 凭据与失败处理

调用脚本默认遮蔽响应中的密码、Provider Key 和 Token。确实需要保留一次性服务凭据时，使用用户指定的受限本地路径 `--secrets-output <新文件>` 保存完整响应，不把密钥贴回对话。`--output` 仍保存遮蔽后的 JSON。请求中的敏感值放本地 JSON 文件或从环境变量构造，避免进入命令行历史。

默认验证 HTTPS；内网 CA 可设置 `UMEKO_ADMIN_CA_FILE`，代理可设置 `UMEKO_ADMIN_PROXY`。不要关闭证书校验。

401：检查管理员身份或重新登录。400/422：按 schema 和字段错误修正。404：检查管理地址、前缀和实际 ID。409：重新读取冲突状态。超时/断连：先查询状态判断变更是否成功；创建、切换开关、轮换凭据、导入和代码执行不得盲目重复。提供具体错误，输出中不包含秘密。

全量操作、请求结构与特殊行为见 [接口参考](references/api.md) 和运行中服务的 OpenAPI。部署监听地址、TLS 和路径前缀属于启动配置，不通过此 Skill 修改；服务也不会自动执行下载到同事电脑上的脚本。

## 按任务阅读

- 了解平台、服务边界和节点生命周期：[平台介绍](references/platform.md)。
- 初次连接、配置模型、技能或权限：[配置指引](references/configuration.md)。
- 新建/更新智能体、发布入口、MCP/A2A/REST 验收：[发布与冒烟测试](references/agent-publishing.md)。
- 查某个端点、字段或约束：[完整 API 参考](references/api-reference.md)、[数据结构](references/schemas.md)、[OpenAPI 快照](references/openapi-admin.json)。实际操作优先读取在线规范；按需检索，不把所有文档一次塞进上下文。
