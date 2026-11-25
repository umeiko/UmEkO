---
name: drawio-design-principle
description: 用 draw.io 绘制系统、算法、产品或机械设计的工作原理和机制示意图。适用于输入与输出、因果、状态、反馈闭环、异常保护及方案对照。交付可编辑的 .drawio，可按需导出 PNG/SVG。电路、布线和 PCB 使用相应专业工具。
---

# draw.io 设计原理图

一张图解释一个问题。先用一句话说明输入或变化怎样经过关键机制产生结果，再画必要的结构、关系和适用边界。

1. 使用 `read_pack_file` 阅读 `references/mechanism.md` 和按需阅读 `references/icons.md`。长文档可交给现有文件子 Agent 提取与问题直接相关的机制、实际依据及待验证假设。主 Agent 用摘要组织模型。
2. 按参考中的 JSON 契约写入会话 `generate/principle-model.json`。用固定 ID 表达节点和关系，用独立 `layout` 选择列、行。已有模型优先保留语义 ID 和有意调整过的位置。
3. 每条连线写明传递的量、规则或触发条件，例如“回传实际延迟”。给反馈线留出单独通道。只有输入支持或用户要求推演时才画异常路径，推演节点标 `assumed`。
4. 调用 `run_skill_script(pack="drawio-design-principle", script="generate_principle.py", args='{"model_path":"generate/principle-model.json","output_name":"principle"}')`。
5. 通过宿主文件能力交付 `files` 中列出的文件，机器任务用 `submit_results`。用户需要继续按模型迭代时可以一并提供 JSON。模型校验失败时只修复指出的字段。

## PNG 和 SVG 导出

- 默认或 `formats=[]` 时交付可编辑的 `.drawio`。用户要求 PNG 或 SVG 时分别传 `formats=["png"]` 或 `formats=["svg"]`，同时需要两种格式时传 `formats=["png","svg"]`。视觉复检需要 PNG 和可用的视觉工具。
- 图片与 `.drawio` 同名，使用已经排好版的原理图。PNG 默认以 2 倍比例导出，SVG 保持矢量。复用流程图的导出器，先按管理员 `assets/config.json` 的 `render_urls` 列表尝试网络渲染，之后使用本地 draw.io。没有可用的命令且管理员未指定路径时，可使用宿主安装的 `umeko-drawio`。按 `exports` 和 `files` 交付实际生成的文件。
- 脚本返回 `status=partial` 时，保留 `.drawio` 和成功导出的格式，按 `exports` 或 `errors` 报告失败项及原因。导出器缺失或运行报错时，交付已有文件并提示检查宿主配置。

图型按讲解目标选。流程图讲步骤先后，架构图讲系统组成，设计原理图讲结构与规则如何共同产生结果。图标只在能帮助识别语义时使用，始终配文字。
