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

脚本在 stdout 最后一行返回 JSON：`{"ok": true, "result": "结论", "files": ["generate/summary.md"]}`，stderr 用于诊断。`outputs` 说明产物含义，统一的 `output_schema` 描述结果结构。运行工具会把结论、产物与失败诊断返回模型，而非原样返回所有 stdout 字段。

### 执行前参数检查与错误诊断

执行器与发现工具共享同一份静态契约。`args` 必须是能解码成 JSON 对象的字符串；声明了 `input_schema` 的脚本还会检查必填项、类型、允许值、未知字段、数组成员、参数组合及声明的长度/数值约束。不会自动转换参数类型、填写默认值或猜测字段名。校验失败时脚本尚未执行，返回具体字段、要求与调用示例，例如：

```text
错误：参数校验失败： [SCRIPT_ARGUMENT_INVALID]
- args.formats：期望 array，实际为 string
脚本：drawio-flowchart/generate_drawio.py
阶段：执行前检查；脚本尚未执行。
```

参数名、类型和枚举以实际返回的 `list_skill_script` 为准。`input_schema` 使用 JSON Schema 2020-12，支持本地 `#/$defs` 引用，不获取外部引用；声明本身损坏时提示管理员修复契约。没有声明的旧脚本只检查 `args` 对象格式，继续兼容执行；其业务参数错误仍以脚本实际诊断为准。

错误会区分参数格式/校验、脚本定位、契约或 Python 语法、进程启动、超时、依赖加载、结果格式与脚本报告的失败，附带脚本名、阶段和适用的退出码。失败时保留 stdout/stderr 尾部、警告与已生成的产物列表。参数诊断不回显整份输入；业务错误不统一解释为路径问题。独立调用脚本时仍由脚本自己校验参数；执行器的校验不是操作系统沙箱。

脚本可用可选的结构化 `error` 返回更具体的信息：

```json
{"ok":false,"result":"输入文件的数据结构不正确","files":[],"error":{"code":"INPUT_DATA_INVALID","field":"args.data_path","message":"输入 JSON 缺少 items 数组","hint":"补齐结构化检查结果后重新渲染"}}
```

执行器展示脚本声明的错误码、字段、原因和修正建议，不凭任意文本猜测业务错误类型。仅有原始失败信息时保留其原意；标准 Python `ModuleNotFoundError`/`ImportError` 诊断会提示检查运行环境。

内置的报告渲染、绘图任务准备和图表生成脚本均已补充契约。升级时只更新可识别的原版内置文件，保留管理员修改与删除；自定义脚本需要维护者自己补充声明。

## 工具重叠与取舍

| 工具 | 实际分工与建议 |
| --- | --- |
| `write_working_doc` → `write_file` | 已移除专用入口及处理器。工作笔记是普通文本文件，服务会话写入 `generate/working_doc.md`，CLI 写入当前产物目录的 `working_doc.md`。局部修改用 `replace_in_file`。 |
| `read_working_doc` → `read_document` | 已移除专用入口及处理器，使用通用读取工具读取原笔记，沿用大文件门禁和文件边界。 |
| `use_skill("包名/成员文件")` → `read_pack_file` | 已取消附属文件读取别名；`use_skill` 只接受技能包名、加载主指引，附属文档和源码统一使用 `read_pack_file`。 |
| `list_dir` / `find_files` / `grep_files` | 分别浏览目录结构、按文件名查找、按内容搜索，保留独立入口。 |
| `write_file` / `replace_in_file` | 分别整体写入和有匹配约束的局部替换，保留。 |
| `read_image` / `image_reasoning` | 分别把图片交给当前支持视觉的模型、调用单独配置的视觉模型，不是同一路径。 |
| `file_operate` / `archive_tool` / `run_skill_script` | 分别整理文件、处理压缩包、运行技能中的确定性程序，职责不同。 |

写笔记不自动压缩上下文，也不自动把笔记放入每次请求。需要在后续任务中主动读取；对话压缩由引擎的上下文管理单独负责。

旧工作文档工具已从模型工具表、管理目录和可授予权限中移除，直接调用旧名只返回替代方式，不执行兼容处理器。已有笔记文件与历史调用记录保留。内置质检技能同步更新；管理员自定义的旧指引不覆盖，加载时会附上旧工具名的替代说明。

已有用户授权中的旧名称不再生效，也不会自动映射成范围更大的通用文件权限。管理 API 的 `allowed_tool_names` 仅返回有效工具，`retired_tool_names` 标记待清理的旧授权；权限弹窗提示管理员按需重新选择，保存后去除旧名称。只授予过旧工具的用户会得到空的可配置工具范围，不会回退成“跟随全局”。
