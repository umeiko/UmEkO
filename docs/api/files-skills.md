# 文件与技能

每个会话有独立目录。API 使用相对路径与资源 ID，不要求调用方知道服务器绝对路径。以下 `{sid}` 代表 `session_id`。

## 对话附件与产物

| 方法 | 路径 | 请求 / 响应 |
| --- | --- | --- |
| POST | `/v1/sessions/{sid}/files?filename=sample.png` | 原始字节体；`201 FileView` |
| POST | `/v1/sessions/{sid}/files/from-workspace` | `{"path":"workspace/sample.png"}`；`201 FileView` |
| GET | `/v1/sessions/{sid}/artifacts` | `ArtifactView[]` |
| GET | `/v1/sessions/{sid}/artifacts/{artifact_id}/content` | 文件内容 |

`FileView` 包含 `id`、`filename` 和字节数 `size`。附件上传后，创建 Run 时传 `attachments: [id]`，不能把服务器路径当成文件 ID。

`ArtifactView` 包含 `id`、`name`、`kind`、`size` 和 `download_url`。下载地址已包含服务前缀，调用程序将它与公共域名组合，不再次添加前缀；仍需发送登录 Cookie。

## 工作区

| 方法 | 路径 | 请求 / 说明 |
| --- | --- | --- |
| GET | `/v1/sessions/{sid}/workspace/tree` | 可选 `filter`，返回 `WorkspaceNode[]` |
| POST | `/v1/sessions/{sid}/workspace/files` | 查询 `filename` 与可选 `path`；原始字节体 |
| GET | `/v1/sessions/{sid}/workspace/files/content` | 查询 `path`，读取文件 |
| GET | `/v1/sessions/{sid}/workspace/files/raw/{file_path}` | 支持文件的相对资源 URL，例如 HTML 的图片 |
| GET | `/v1/sessions/{sid}/workspace/files/download` | 查询 `path`，文件直接下载，目录打 ZIP |
| POST | `/v1/sessions/{sid}/workspace/entries` | 新建文件或目录 |
| DELETE | `/v1/sessions/{sid}/workspace/entries` | 查询 `path`，删除条目，`204` |
| POST | `/v1/sessions/{sid}/workspace/transfer` | 复制或移动 |
| POST | `/v1/sessions/{sid}/workspace/extract` | 使用原生 7-Zip 解压 |

工作区路径带虚拟根，例如 `workspace/data.csv`、`attachments/sample.png`、`generate/report.html`。文件树可能标记 `truncated`，不能据一个已截断列表判断整个目录没有其他文件。

上传接口的 `path` 是已经存在的目标目录，可为 `workspace`、`attachments`、`generate` 或其子目录；省略时保存到 `workspace`。上传同名文件会自动追加 `_1`、`_2` 等后缀，返回实际 `path` 和 `filename`，不会覆盖原文件。空文件和无效目录返回 `400`。允许向顶层目录上传文件，但顶层目录本身仍不能移动或删除。

新建：

```json
{"path": "workspace/input", "type": "directory"}
```

复制 / 移动：

```json
{"source": "workspace/data.csv", "target": "workspace/archive/data.csv", "operation": "copy"}
```

解压：

```json
{"path": "workspace/input.zip"}
```

文件修改遇到会话执行锁可能返回 `409`；不是所有写接口都有相同的锁检查。调用方应避免在 Agent 正在处理的文件上并发修改。

网页与模型的 `archive_tool` 统一使用原生 7-Zip 列表、解压和 ZIP 打包，目录下载也使用同一后端；不使用 Python 解压实现。解压到压缩包同级的同名目录，已有目录时自动追加序号，单一顶层文件夹通常会提升一层。每层压缩包一次批量解压，不逐文件启动程序；TAR.GZ/TGZ、TAR.BZ2/TBZ2、TAR.XZ/TXZ 由 7-Zip 依次处理压缩层与 TAR 层，中间文件自动清理。解压前校验包内路径，拒绝绝对路径、目录穿越、符号链接、硬链接与特殊文件；每层上限为 5000 条目、512 MiB 解压内容，全程 5 分钟，失败或取消会清理本次生成的目录。安装与格式说明见[部署指南](../deployment.md#archive-support)。

模型通过 `file_operate` 管理目录项，与网页复制、移动、删除共用边界检查和文件操作实现。它是模型工具，不是新增 HTTP 路由。主 Agent、文件子 Agent、Web 与 REST/MCP/A2A 所调用的 Agent 都可使用；机器协议继续通过任务执行访问这些工具，不开放任意服务器文件访问。

| operation | 含义 | 示例参数 |
| --- | --- | --- |
| `cp` | 复制 | `{"operation":"cp","path":"attachments/input.png","target":"workspace/input.png"}` |
| `mv` | 移动或重命名 | `{"operation":"mv","path":"workspace/input.png","target":"workspace/renamed.png"}` |
| `rm` | 删除文件或目录 | `{"operation":"rm","path":"generate/old","recursive":true}` |
| `mkdir` | 创建目录 | `{"operation":"mkdir","path":"workspace/reports/images","recursive":true}` |

`target` 是完整目标路径，不会自动把文件放入某个已存在目录。复制目录与递归删除需要 `recursive: true`；默认不覆盖，仅文件可显式设置 `overwrite: true`。工作区、附件和产物顶层节点不能修改，路径及目录中的链接会被拒绝。移动会更新内存与数据库中的附件 ID 映射；删除会移除映射，避免重启后恢复失效附件。文本内容编辑继续使用 `write_file` 和 `replace_in_file`，压缩操作继续使用 `archive_tool`。

## 会话技能

`kind` 当前只支持 **`skills`**。下列接口管理单个会话中的技能，与管理员全局默认技能不是同一作用域。

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/v1/sessions/{sid}/client/{kind}` | 列表，含按需启用和内置标记 |
| GET | `/v1/sessions/{sid}/client/{kind}/{name}` | 读取内容 |
| POST | `/v1/sessions/{sid}/client/{kind}?filename=sample.md` | UTF-8 原始文本，`201` |
| POST | `/v1/sessions/{sid}/client/{kind}/generate` | JSON `{name, description}`，调用模型生成，`201` |
| PATCH | `/v1/sessions/{sid}/client/{kind}/{name}` | JSON `{content, mounted}`，可更新部分字段 |
| DELETE | `/v1/sessions/{sid}/client/{kind}/{name}` | 删除，`204` |

技能内容须符合项目技能包格式，不能把普通任意 Markdown 当作有效技能。运行中的会话修改技能返回 `409`。

`ClientResourceView` 为 `kind`、`name`、`mounted`、`builtin`、可空 `content`。详细字段见[数据结构](schemas.md)，完整参数见[用户参考](reference-user.md)。

`mounted: true` 表示**启用按需使用**：名称与简介进入当前会话的技能目录，相关任务才读取完整指引。它不强制每轮执行、不自动把全文追加到用户消息。设为 `false` 会从自动目录中移除，文件仍保留，可通过工具发现和明确指定使用；这不是权限开关。

同一 Run 中重复 `use_skill` 复用相同版本的正文；结束后工作上下文只留下短引用，完整工具日志仍可查看。REST / MCP / A2A 的机器任务无需调用这个会话开关，它们自动提供对应 Agent 所选技能的简介，使用相同的[按需加载机制](../architecture/index.md#skill-loading)。
