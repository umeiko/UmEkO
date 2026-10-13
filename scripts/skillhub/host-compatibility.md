# 独立 Agent Skill 运行约定

本包的 `SKILL.md` 保留 UmEkO 当前技能正文，所有附属规则、样式与脚本也随包提供。
工具名称是能力约定：在 UmEkO 之外使用时，映射到当前宿主实际提供的同等工具，
不要调用不存在的工具，也不需要安装整个 UmEkO 服务。

| 原工具名称 | 其他宿主中的对应方式 |
| --- | --- |
| `read_document` / `grep_files` | 宿主的文件读取、分页读取或检索工具；读取 DOCX/PDF 时使用宿主的相应文档读取能力 |
| `write_file` | 宿主的文件写入工具；完整 XML/JSON 直接落盘，主 Agent 汇报只保留短结论与路径 |
| `read_pack_file(pack, member)` | 读取技能根目录下 `<pack>/<member>`，如 `doc-image-qc/checks.md`、`drawio-flowchart/style.md` |
| `run_skill_script(pack, script, args)` | 用下方 `scripts/run.py` 运行相应脚本；`args` 内容保持原样 |
| `delegate_task(task)` | 宿主的文件子 Agent／任务委派工具，交付文件路径和短摘要。宿主没有委派能力时，明确说明上下文隔离不可用，由当前 Agent 分段处理相同任务，保留落盘与短汇报纪律 |
| `image_reasoning(prompt, image_paths)` | 宿主的多图视觉工具或当前模型的原生视觉输入；原生看图也视为视觉能力可用。不可用时按技能的缺失能力规则处理，不猜测图片 |
| `write_working_doc` / `read_working_doc` | 将进度文档写到／读自 `generate/working-doc.md`，无需平台专属的工作文档服务 |
| `archive_tool` | 宿主的压缩包列举／解压工具；保持目录层级，所有条目须落在本次任务目录内 |
| 文件元数据／交付接口 | 宿主的文件列表、附件信息与产物交付能力；汇报相对任务目录的实际文件，不构造服务器地址 |

## 工作目录与脚本

脚本只依赖 Python 3.10+ 标准库。选择一个本次任务目录作为 `--root`，其中使用
`attachments/`（输入附件）、`workspace/`（解压或辅助材料）、`generate/`（结果）。
由宿主将用户授权的输入材料放到这些目录，保留相关图片的相对位置；不要改写原始文档。
参数中的文档、风格与 XML 路径均相对该任务目录，技能文件位于独立的技能安装目录。

把原 `run_skill_script` 的 `args` JSON 对象保存为 UTF-8 文件，然后运行：

```sh
python "<技能目录>/scripts/run.py" prepare_drawio.py --root "<任务目录>" --args-file "<任务目录>/workspace/prepare-args.json"
python "<技能目录>/scripts/run.py" generate_drawio.py --root "<任务目录>" --args-file "<任务目录>/workspace/generate-args.json"
python "<技能目录>/scripts/run.py" render_report.py --root "<任务目录>" --args-file "<任务目录>/workspace/report-args.json"
```

每包只支持自己附带的脚本：前两个命令属于 `drawio-flowchart`，最后一个属于
`doc-image-qc`。短参数也可用 `--args`，根据当前 shell 正确引用 JSON；不要将用户文字拼成命令。
脚本 stdout 返回单行 JSON，`ok` 表示成功，`files` 为任务相对路径，stderr 为进度；
失败时包装入口返回非零退出码。不要仅凭进程执行过就声称成功，须检查 `ok`、实际文件及警告。

## 图表导出环境

draw.io 技能的完整原始默认样式在 `drawio-flowchart/style.md`，默认字体为方正兰亭黑简体，
字号 10.5，流程图网格 172×28、纵向间距 28，架构图组件 180×60。
字体由运行环境自行安装，安装包不分发字体或 draw.io 可执行文件。

`drawio-flowchart/config.json` 保留当前视觉配置，导出的 `drawio_path` 留空。
使用者可自行配置 draw.io 桌面程序路径，或设置 `DRAWIO_PATH`／`UMEKO_DRAWIO_PATH`，
也可使用 PATH 中的 `draw.io`／`drawio`。Linux 无显示器时需要可用的导出显示环境。
缺少桌面程序仍可生成可编辑 `.drawio`；PNG/SVG/PDF 必须以实际导出结果为准。
只生成 `.drawio` 可在生成参数中设置 `"formats": []`。

Linux 部署与配置填写见绘图包的 `drawio-flowchart/linux-deployment.md`。
`config.json` 的 `_help` 是说明字段，不参与布局；无桌面服务器的 `drawio_path`
填写已安装的 `drawio_headless.sh` 包装入口的绝对路径，不能填整条命令。
绘图包附带 `Dockerfile.linux.txt` 和 `linux_smoke.py`，可直接构建并验收两类图和三种导出。

图像复检沿用正文约定：用户要求时最多一到两轮，默认不调用视觉工具。
图像推理技能本身没有脚本或 Python 依赖，只需宿主具备视觉输入能力。

## 格式与来源

ZIP 根目录的 `SKILL.md` 使用 Agent Skills 的 `name`、`description`，并补充
SkillHub 的 `slug`、`displayName`、`version`、`summary`、`homepage`。
`package-manifest.json` 记录提取源文件的 SHA-256 与包内文件 SHA-256，明确标记入口适配
和清空本机可执行路径这两类变更。未修改 UmEkO 运行时技能或平台 Agent 工具。

来源：[UmEkO](https://github.com/umeiko/UmEkO)。图表内核的上游版本和具体来源保留在
`drawio-flowchart/provenance.md` 中（其他技能包无需该文件）。
仓库当前未声明许可证，本次打包不自行授予新的开源许可；如发布平台要求选择许可证，
由作者先确认。SkillHub 的标识是否被占用及上架审核结果以提交时的检查为准。
