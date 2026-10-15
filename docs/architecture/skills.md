# 技能与脚本工具

CLI、网页和机器任务复用同一个主 Agent 工具集。`list_skill_script` 是执行引擎的工具，由主 Agent 在任务中调用；它不增加独立的 HTTP 或顶级 MCP/A2A 入口。

## 发现与执行

1. `list_skill_packs` 查看有权访问的技能名称与简介。
2. `use_skill` 读取匹配任务的完整主指引。
3. `list_skill_script(pack="doc-image-qc")` 查看该技能的脚本；传入 `script="render_report.py"` 可只看一个文件。
4. 根据返回的用途、用法、`input_schema`、`outputs` 与调用示例，准备输入文件并调用 `run_skill_script`。
5. 检查执行结果与实际产物；声明了用法不代表服务器已经安装好运行依赖。

工具只静态读取代码，不导入模块、不执行脚本，也不会为了获取帮助而运行 `--help`。每页最多 20 个文件，使用返回的 `next_offset` 继续读取；单个源码最多解析 1 MiB，元数据最多 16,000 字符，页面也有总量限制。辅助模块标记为 `support_module`，没有契约的旧入口标记为 `legacy_script`；这些标记是静态判断，不保证任意旧脚本符合运行协议。旧脚本仍可执行，但应先通过 `read_pack_file` 阅读说明或源码，不能猜测输入。

工具沿用技能披露边界：机器智能体只能查看管理员允许的技能；同时可以在管理页“工具”中单独关闭或授权该工具。发现和执行使用同一个服务器技能库，目录或脚本不能通过链接绕到其他包。

## 脚本如何声明用法

在 Python 脚本顶层添加一个字典常量 `SKILL_SCRIPT`，与代码一起维护。管理页下载的脚本模板已包含此字段。发现工具只读取字面量，不能写函数调用或引用其他变量。

```python
SKILL_SCRIPT = {
    "description": "把输入文本转为摘要文件。",
    "usage": "先在当前会话中准备文本文件，再传入 input_path。",
    "input_schema": {
        "type": "object",
        "required": ["input_path"],
        "properties": {
            "input_path": {
                "type": "string",
                "description": "当前会话内的相对路径"
            }
        }
    },
    "outputs": ["generate/summary.md：摘要文件"],
    "example_args": {"input_path": "workspace/source.txt"}
}
```

`input_schema` 描述调用者传入的 `args` 对象。`run_skill_script` 的 `args` 参数仍是 JSON 字符串，发现工具返回的 `invocation` 已按此格式构造示例。执行框架另外通过 stdin 注入 `workdir` 和 `session_root`，调用者不需要提供服务器绝对路径。

脚本在 stdout 最后一行返回 JSON：`{"ok": true, "result": "结论", "files": ["generate/summary.md"]}`，stderr 用于诊断。`outputs` 说明产物含义，统一的 `output_schema` 描述结果结构。运行工具会把结论、产物与失败诊断返回模型，而非原样返回所有 stdout 字段。元数据用于发现与说明，当前不会作为执行时的参数校验器。

内置的报告渲染、绘图任务准备和图表生成脚本均已补充契约。升级时只更新可识别的原版内置文件，保留管理员修改与删除；自定义脚本需要维护者自己补充声明。

## 工具重叠与取舍

| 工具 | 实际分工与建议 |
| --- | --- |
| `write_working_doc` / `write_file` | 前者只是覆盖产物目录下固定的 `working_doc.md`，没有额外记忆机制。新提示词优先使用通用写文件工具，旧入口暂时保留以兼容技能与独立工具授权。 |
| `read_working_doc` / `read_document` | 前者读取固定笔记；后者是通用文档读取，另有格式提取和大文件门禁。新流程优先使用后者。 |
| `use_skill("包名/成员文件")` / `read_pack_file` | 都能读附属文档；推荐 `use_skill` 专注主指引，`read_pack_file` 负责附属文档和源码，保留旧语法兼容。 |
| `list_dir` / `find_files` / `grep_files` | 分别浏览目录结构、按文件名查找、按内容搜索，保留独立入口。 |
| `write_file` / `replace_in_file` | 分别整体写入和有匹配约束的局部替换，保留。 |
| `read_image` / `image_reasoning` | 分别把图片交给当前支持视觉的模型、调用单独配置的视觉模型，不是同一路径。 |
| `file_operate` / `archive_tool` / `run_skill_script` | 分别整理文件、处理压缩包、运行技能中的确定性程序，职责不同。 |

写笔记不自动压缩上下文，也不自动把笔记放入每次请求。需要在后续任务中主动读取；对话压缩由引擎的上下文管理单独负责。彻底删除旧快捷工具还需要同步处理已有技能指引、持久化的工具授权及历史调用兼容，不能只删掉一个工具名。
