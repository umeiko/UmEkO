---
name: drawio-flowchart
description: 先提炼需求再生成、修改简明可编辑的 draw.io 流程图和架构图，支持默认或用户指定的 style.md 风格文件，导出 PNG/SVG/PDF；用户要求复检时才做一到两轮图像检查。
---

# draw.io 图表生成

使用 draw.io 原生 mxfile XML，由文本模型编写结构、包内 Python 脚本确定性布局。复用平台现有文件子 Agent；绘图规范、配置与流程均属于本 Skill，视觉模型只用于用户要求的复检。

## 流程图为客户的可读性服务，务必精简

- 从复杂文档生成的流程图请保持简约性，不推荐节点内有过多的文字。
- 除了必须用英文的术语，或用户明确要求外，请使用中文制作流程图。
- 有标题的文档最多展示到三级标题；这只是展示深度上限，不要求每个标题都成为节点。合并同一阶段的细碎操作、同义步骤和重复描述，节点标签名称需要精炼。
- 优先一条自上而下的主线。只有改变核心路径、关键结果或结束条件的必要决策才画判断节点；说明性条件、服务话术、执行检查点和低层异常细节不逐项画成分支。
- 同一处理可合并的分支尽早汇合并共享后续节点，不复制整条后续流程；互不影响主线的细节不另开并行通道。实际存在且影响结果的决策、失败路径及用户明确要求的分支必须保留，不能为了少画线改变业务含义。
- 颜色与类别遵循预装的原始 `style.md`：按起止、必经/可选流程表达语义，只用所选风格允许的色板，不因低层细节或重复分支自行增加配色。
- 用户明确要求详细 SOP、全部异常、逐步骤展开时才提高粒度，并把必要细节完整保留。

## 生成与修改

主 Agent 只做路径定位、委派、运行脚本和交付。不要直接读取需求文档全文、原有大图 XML，或在自己的工具调用中写完整 XML；不要让子 Agent 返回这些全文。作图清单与 XML 必须由子 Agent 直接落盘。正文、附件和大 XML 留在子 Agent 的临时上下文，主 Agent 只保留简短摘要、路径与脚本结论。

1. 定位输入的会话相对路径。压缩包可先委派现有文件子 Agent 解压和定位文档，回报路径即可；不要把文档全文读到主 Agent。没有附件时只转交用户的短需求。需要修改已有图时把该 `.drawio`/XML 路径作为输入。
2. 调用 `run_skill_script(pack="drawio-flowchart", script="prepare_drawio.py", args='{"document_paths":["attachments/需求.md"],"request":"根据需求制作简明技术图","output_name":"diagram","diagram_type":"auto"}')`。只传路径和简短需求，不在 `args` 填入整份文档。用户已明确要求流程图或架构图时分别传 `flowchart` / `architecture`；没有明确图型时用 `auto`，让子 Agent 根据文档判断“步骤怎样流转”或“系统由什么组成”，不要求用户必须说出“架构图”。准备脚本分别保存两种规范，子 Agent 只加载选中图型的规范和风格段。
3. 将准备脚本返回的短任务交给 `delegate_task(task=...)`。现有文件子 Agent 通过 `read_document` 读取会话内的规则和需求，提炼作图清单并把 XML 写入准备脚本约定的 `source_path`，最终只返回选中的 `flowchart` / `architecture`、清单/XML 路径、最多 500 字摘要及未解决问题。子 Agent 不具备 `read_pack_file/run_skill_script/use_skill`，不要要求它调用这些工具；规则已由准备脚本转存成普通会话文件。
4. 主 Agent 直接调用 `run_skill_script(pack="drawio-flowchart", script="generate_drawio.py", args='{"source_path":"generate/diagram-source.xml","output_name":"diagram","diagram_type":"architecture"}')`，将路径/名称替换成准备脚本与子 Agent 回报的值，图型使用子 Agent 选中的类型，不读取 XML 全文；未传图型时脚本从 XML 层次结构识别。字体默认方正兰亭黑简体 10.5。流程图采用 172px / 最小高 28px / 纵向间距 28px，`layout` 可覆盖流程图尺寸；架构图继续使用原内核的组件 180×60、最多四列、间距 20、标题区 30，层容器等宽左对齐、子容器最多一层。需要 PDF 时可传 `formats=["png","svg","pdf"]`。
5. 脚本做结构校验和布局并导出文件。交付 `.drawio` 及实际成功导出的图片，用平台文件接口处理相对路径；不拼接 Host 或部署前缀。发生结构错误时，只把短错误、规则/清单/XML 路径转交 `delegate_task` 定向修正，之后重新运行脚本；不把 XML 搬回主 Agent，不无限重试。同一任务最多两次结构修正，仍失败则交付失败说明及保留的草稿路径。

## 使用 style.md 风格文件

本包预装 `styles/default.md` 的通用视觉规范及两个 draw.io 图型段落，完整保留这些部分的详细说明，全部采用 draw.io 原生风格格式。

未指定风格时自动使用包内 `style.md`；用户提供或点名一个风格 Markdown 时，用文件元数据工具定位会话相对路径，在 `prepare_drawio.py` 和 `generate_drawio.py` 的 `args` 中**都传同一个** `style_path`，例如 `"style_path":"attachments/style.md"`；不要让主 Agent 读取风格全文，也不要把风格文件当成需求文档总结。准备脚本把适用规则和生效配置交给子 Agent。

支持普通 Markdown，或 draw.io 风格文件格式的 frontmatter 加正文。通用视觉描述与当前图型的 `## [drawio:flowchart]` / `## [drawio:architecture]` 段落生效；另一个图型的段落不参与本次生成。选用风格可覆盖默认视觉规则；业务内容、必要分支与 XML 结构规则不因换风格而改变。

`background`、`font_family`、`font_size`、`edge_color`、`edge_width` 可在 frontmatter 中明确设置；`layout` 格式与原项目相同，如 `node_width=172,node_height=28,gap_y=28`。脚本确定性应用这些字段。正文负责节点配色、形状和装饰要求，子 Agent 将其写入 XML；连线的颜色、线宽、虚实和箭头样式会在确定性走线之后保留，不再被布局默认灰色覆盖。未指定的字体与尺寸沿用管理员配置，工具可选 `layout` 参数只覆盖明确给出的维度。详细示例见包内 `style-files.md`，普通生成无需主 Agent 加载其全文。

用户只要求换配色/风格时，委派说明中明确“仅改样式，所有节点 ID、文字、parent、连线端点及分支标签保持原样，不重新提炼或简化”。生成脚本传 `restyle_reference_path` 指向原始图，校验通过后才交付。

没有桌面版或导出失败时仍交付有效的 `.drawio`，明确说明未导出图片，不声称已经验证图像质量。字体须在服务环境中已安装；包内不分发字体文件。准备与生成脚本不调用模型或读取需求全文，不执行自动图像复检。部署配置见包内 `config.json`，详细规则是 `flowchart.md/architecture.md/delegation.md`；普通生成无需主 Agent 加载它们的全文。

## 用户要求时复检

默认生成完成即交付，不调用 `image_reasoning`，不主动启动视觉修订循环。

用户明确要求“复检 / 看图检查 / 检查布局”等时，最多执行一到两轮：

- 需要已导出的 PNG 及可用的 `image_reasoning`；缺少任一条件，说明缺失条件并交付现有文件。XML 检查不能冒充图像复检。
- 第一轮用 `image_reasoning` 检查最新 PNG，传入用户要求和子 Agent 的短摘要，重点核对遗漏、分支方向、遮挡、文字溢出和连线交叉。需要详细文档核对时委派现有子 Agent 按落盘清单和图片检查，不把需求全文搬回主 Agent。
- 若发现问题，把短反馈、规则/清单/XML 路径转交 `delegate_task` 修正，再由主 Agent 重新运行脚本。用户只要求一轮时，交付修正版并说明修改后没有再次复检；允许两轮时，对重新导出的 PNG 再检查一次。
- 第一轮没有发现问题即可结束。第二轮后结束并如实报告仍存在的问题，不把未解决的问题写成通过，不自行增加复检轮次。

图像复检由已有通用工具完成，其检查结论与确定性结构校验分开说明。
