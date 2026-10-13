# UmEkO Skills 发行快照

这里是从当前技能库完整提取的三个独立 Agent Skill：

| ZIP | 技能 | 随包资源 |
| --- | --- | --- |
| `doc-image-qc.zip` | 单图／多图、Markdown 文档和压缩包图文质检 | 完整检查规范、HTML/JSON/ZIP 离线报告脚本 |
| `drawio-flowchart.zip` | 简明流程图与分层架构图 | 完整原始默认 style、两类绘图规范、XML 校验与布局内核、委派及生成脚本 |
| `image-reasoning.zip` | 单图或最多 5 张图片的开放式问答 | 几何解题、跨图比较、因果推理及场景线索分析指引 |

发行地址：[umeko-skills](https://github.com/umeiko/UmEkO/releases/tag/umeko-skills)。
每个 ZIP 的根目录直接包含 `SKILL.md`，可逐个上传到 SkillHub，或解压到宿主的同名技能目录。
它们补充了 SkillHub 发布标识／展示名／版本，同时保留 Agent Skills 的名称与描述。
发布标识为 `umeiko-doc-image-qc`、`umeiko-drawio-flowchart`、`umeiko-image-reasoning`，
首次快照版本均为 `1.0.0`。没有向 SkillHub 提交上架申请，标识占用和审核由提交时检查。
绘图包已更新为 `1.0.1`：补齐 Linux 原生安装、配置 `_help`、无桌面导出包装脚本、
Docker 构建文件及无模型验收脚本。Linux 详细说明位于
[linux-deployment.md](drawio-flowchart/drawio-flowchart/linux-deployment.md)。

技能正文、附属规范和 Python 内核均来自当前运行时技能库，管理员已编辑的内容也在快照内。
提取时 `doc-image-qc` 的库文件比后台下发正文更新：本发行包采用支持单图／多图及 ZIP
报告的较新库版；后台下发的旧版正文仍保持原状。本次打包不更新运行服务的下发内容。
本次只补充宿主工具对应说明与独立脚本入口，并清空公开包的本机 `drawio_path`。
所有其他视觉配置和完整 `style.md` 保留；不包含 draw.io 程序或字体文件。
图表视觉复检仍是用户要求时一到两轮。文档与 XML 优先交给宿主已有子 Agent，
宿主不支持委派时可分段处理，但无法获得子上下文隔离效果。

Python 脚本要求 Python 3.10+，只使用标准库；PNG/SVG/PDF 导出另需 draw.io 桌面程序，
字体需在运行环境安装。图片质检和图像推理需要宿主可用的视觉能力。
详细的工具映射和运行命令位于每个包的 `references/host-compatibility.md`。

## 重新打包

从仓库内已审核的快照打包，不读取运行时目录或数据库：

```sh
python scripts/package_skillhub_skills.py
```

输出为 `dist/skills/skillhub/` 下的三个 ZIP、`manifest.json` 与 `SHA256SUMS.txt`。
ZIP 内的 `package-manifest.json` 记录源文件和发行文件的 SHA-256；打包前校验文件清单、
入口字段、UTF-8 纯文本、Python 语法，打包后检查 ZIP 完整性、文件数与大小。

需要更新管理员编辑后的技能时，**显式**传当前技能库路径，提取到全新的快照目录再比较：

```sh
python scripts/package_skillhub_skills.py --source-root skills --snapshot-dir dist/skills/next-snapshot --output-dir dist/skills/next-release --version 1.0.1
```

此命令不改写原技能库，也不读取数据库、Provider 或模型密钥。
源码快照不会随后台编辑自动同步；审核新快照后更新这里的内容及版本，再重新打包发布。
仓库当前没有许可证声明，打包不自行添加 MIT 等新的许可授权。

格式依据：[SkillHub 发布规范](https://skillhub.cn/ai/release.md)、
[Skills ZIP 文件规范](https://cloud.tencent.cn/document/product/1759/134602)。
