# 来源与边界

布局与 XML 后处理抽取自用户提供的 Flowchart-cli，源版本 `20ee5e05aeccadb5e823cc22a307c0344b7d2fda`：

| 本包文件 | 来源 |
| --- | --- |
| drawio_flow.py | flowchart_agent/drawio/layout_flow.py |
| drawio_arch.py | flowchart_agent/drawio/layout.py |
| drawio_xml.py | flowchart_agent/drawio/xml.py |

这些内核只使用 Python 标准库。`generate_drawio.py` 是 UmEkO stdin/stdout 脚本契约的独立适配器；`prepare_drawio.py` 将本包规则与任务说明转存成普通会话文件，以便现有文件子 Agent 读取。生成内容与按需复检由 Skill 指引及 UmEkO 已有工具编排，不修改子 Agent 的工具表或系统提示词。

`config.json` 由管理员编辑。`drawio_path` 为服务器上 draw.io 桌面版可执行文件的绝对路径；留空时查找 `UMEKO_DRAWIO_PATH`、`DRAWIO_PATH` 及 PATH 中的 draw.io/drawio。脚本只读取这些工具配置，不读取模型密钥或 `.env` 文件。没有桌面版也可生成 `.drawio`；PNG/SVG/PDF 需要服务器具备可运行的桌面版导出环境。Linux 无显示器部署可通过管理员配置的包装程序提供虚拟显示。

`scale` 为 PNG 缩放倍数；可按已安装字体设置 `font_family` / `font_size`。只修改工具配置不需前端重新构建。管理员下发只影响新会话；停用不会移除已播种到旧会话的技能，删除、停用或自定义后重启也不自动恢复。

默认视觉配置来自源项目的 `skills/flowchart_format.md`（框宽 172px、最小高 28px、纵向间距 28px）及已生成原始 `.drawio` 中的字体字段（方正兰亭黑简体 / 10.5）。`layout` 的管理员配置为底版，调用参数只覆盖明确给出的维度；不要求模型记住或写坐标。架构组件继续沿用内核的 180×60 网格。包内不包含字体二进制；服务器需安装所配置字体，否则桌面程序可能回退字体。

简明性也对齐源项目 `skills/flowchart_format.md`：先总结为简要作图文档、最多展示至三级标题、少放节点文字、只区分必经/可选流程的颜色。本包在子 Agent 指引中明确如何合并细碎动作、选择必要判断并共享后续流程；这些是把原有简明性原则落实为可执行取舍，不是原 Agent 中存在的节点数硬上限。用户要求详细 SOP 或完整异常分支时保留相应粒度；生成脚本不按数量机械删节点或连线。

`style.md` 来自原项目 `styles/default.md`，完整保留通用视觉规范以及流程图/架构图两个 draw.io 段落的详细文字，仅保留本包适用的风格内容。`drawio_style.py` 在包内选择通用及当前图型段落，明确视觉字段由脚本应用。管理员之后可编辑本包默认风格。

`architecture.md` 使用原 `DRAWIO_ARCH_SYSTEM` 的完整 XML 模板与结构规则，适配为子 Agent 直接落盘；架构布局内核与源 `drawio/layout.py` 逐字一致。恢复原默认风格中“明确调用/数据流才连线”的例外，适配器补齐必要的边几何；默认仍无架构箭头。图型分类由现有文件子 Agent 完成，生成脚本可从 XML 层次复核，不新增独立路由模型或平台领域工具。

## 包的安装与下发

服务启动时通过通用默认 Skill 发现机制安装本包；绘图规范与内核都留在本包，不增加平台领域工具或通用 Agent 系统提示词。UmEkO 另行预装“流程图生成Agent”（`flow-chart-agent`）并选择本 Skill，首次新增依赖时启用下发；已有管理员启用/停用状态保持原样。管理员在“技能库”中可查看主文件、脚本、规范及配置，也可选择是否下发。新工作台会话收到启用的主文件，用户可以启用按需使用或明确指定该技能；其他机器智能体可在自己的 Skills 选择中勾选本 Skill。

在 UmEkO 项目根执行 `python scripts/package_drawio_skill.py` 可生成 `dist/skills/drawio-flowchart.zip`。ZIP 使用 UmEkO 原生包格式：`drawio-flowchart.md` 加同名目录。将两者一起复制到目标服务器的 `UMEKO_SKILL_DIR`，再在管理员后台导入并启用。也可解包后先用后台“导入技能”上传主文件，再在该技能的“导入文件”中上传同名目录内所有 `.py/.md/.json`；现有后台不直接接受 ZIP，不要只上传主文件。

`.drawio` 生成与缺少桌面版时的交付均可独立验证；PNG/SVG/PDF 的实际导出还依赖管理员部署的桌面版环境。图像复检规则只在主 Skill 中定义，既不进入平台文件工具说明，也不改变通用 Agent 的图像推理能力。
