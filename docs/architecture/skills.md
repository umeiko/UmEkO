# 技能与脚本工具

CLI、网页和机器任务复用同一个主 Agent 工具集。`list_skill_script` 是执行引擎的工具，由主 Agent 在任务中调用；它不增加独立的 HTTP 或顶级 MCP/A2A 入口。

## Skill 的目录与分发

[Agent Skills 格式规范](https://agentskills.io/specification)采用一个技能一个目录：`SKILL.md` 必需，含 YAML 头部 `name` / `description` 和执行说明，其余目录按需组织。常见形式如下：

```text
flowchart-correction/
├── SKILL.md                 # 名称、适用场景、门禁和工作流
├── scripts/                 # 转换、校验等可执行脚本
├── references/              # 详细用法、输入输出说明、style.md 等
└── assets/                  # XML 模板、示例、静态配置
```

通常先披露名称和简介，命中任务再加载 `SKILL.md`，细节和脚本按需读取或执行。多个 Markdown 是附属参考资料，不必拆成多个技能，也不该每轮全量放入提示词。ZIP 只是分发容器，解开后仍是上述目录；也可以通过 Git 仓库分发。脚本语言、依赖和调用协议需另外说明；本项目的 JSON stdin/stdout 与 `SKILL_SCRIPT` 契约属于 UmEkO 运行约定，不是所有 Skill 宿主通用的接口。

UmEkO 内置模板与运行库均采用标准目录：`技能名/SKILL.md`、`scripts/`、`references/`、`assets/`。启动时将旧的 `技能名.md` 及同名目录中的文件迁入对应位置；只移动没有目标冲突的文件，冲突保留双方，不覆盖自定义内容，也不恢复已删除的资源。现有启用状态与智能体绑定不变；API 中的 `技能名.md` 仍是兼容的技能标识，已不代表实际文件路径。旧的 `member="checks.md"`、`script="render_report.py"` 调用仍能解析，也支持新的包内相对路径。

新会话获得完整技能包副本，位于 `client/skills/<技能名>/`。`use_skill`、`read_pack_file`、`list_skill_script` 和 `run_skill_script` 都使用本会话副本；主 Agent 和文件子 Agent 可以读取文件、编辑 Markdown 与普通资料。Python 文件和 `config.json` 只读，具体执行门禁见下文。编辑不会回写共享技能库或影响其他会话，重启恢复也保留允许的编辑；管理员修改共享库后，新会话才取得新版本。临时工作台仅可查看当前智能体已披露技能的文件。整包复制不代表把所有内容塞入模型上下文，仍按需加载。

自定义脚本迁入 `scripts/` 后，如通过 `__file__` 定位配套文件，应改用相对技能根目录的 `references/` 或 `assets/` 路径；原文件内容不做自动改写，迁移前备份持久化技能库与数据目录。内置脚本已适配。对外用 `scripts/package_skillhub_skills.py` 导出相同标准布局的自包含 ZIP，含宿主运行说明与独立适配器。

内置资源共享由 `umeko/builtin_skills/shared-assets.json` 明确列举：流程图修正从流程图制作的同一份源码组装风格、布局和 XML 校验模块。安装与导出均组装为自包含的包，不依赖跨包工具授权或符号链接，不额外披露绘图制作技能。安装后的资源可独立编辑；可识别的原版升级沿用已有保留管理员修改/删除的策略。

## 发现与执行

1. `list_skill_packs` 查看有权访问的技能名称与简介。
2. `use_skill` 读取匹配任务的完整主指引。
3. `list_skill_script(pack="doc-image-qc")` 查看该技能的脚本；传入 `script="render_report.py"` 可只看一个文件。
4. 根据返回的用途、用法、`input_schema`、`outputs` 与调用示例，准备输入文件并调用 `run_skill_script`。
5. 检查执行结果与实际产物；声明了用法不代表服务器已经安装好运行依赖。

工具只静态读取代码，不导入模块、不执行脚本，也不会为了获取帮助而运行 `--help`。每页最多 20 个文件，使用返回的 `next_offset` 继续读取；单个源码最多解析 1 MiB，元数据最多 16,000 字符，页面也有总量限制。辅助模块标记为 `support_module`，没有契约的旧入口标记为 `legacy_script`；这些标记是静态判断，不保证任意旧脚本符合运行协议。旧脚本仍可执行，但应先通过 `read_pack_file` 阅读说明或源码，不能猜测输入。

工具沿用技能披露边界：机器智能体只能查看管理员允许的技能；同时可以在管理页“工具”中单独关闭或授权该工具。发现和执行使用同一会话技能副本，目录或脚本不能通过链接绕到其他包；CLI 直接运行管理员维护的技能库。

## 只读代码与执行信任 {#execution-trust}

会话技能内的 `.py` 和 `config.json` 可以查看、下载，但用户和模型不能新建、覆盖、删除或改名。服务器在文本写入、替换、上传、新建、复制、移动、删除、下载落盘和原生 7-Zip 解压前统一检查；目录操作也检查所有后代文件，不能通过改后缀或整包移动绕过。`.pyw`、字节码、原生扩展和 Python 路径配置同样受保护，检查不区分扩展名大小写，拒绝 Windows 路径别名。普通工作区可以保存 Python 作为产物，但运行工具不会因此授予执行权限。

管理员维护共享技能库，服务下发时在 `UMEKO_DATA_ROOT/skill_trust/<session_id>/` 保存执行白名单和文件摘要。该目录位于用户可访问的会话目录之外，不接受用户上传的批准记录。每次执行依次检查包内固定位置、管理员白名单、MD5 和 SHA-256；辅助 Python 模块和 `config.json` 也必须匹配，缺失、多出或改变受保护文件都返回 `SCRIPT_TRUST_REJECTED`，不会启动脚本。

校验通过后，从已校验的字节生成短期私有执行副本，Python 导入也使用该副本；清除外部 Python 路径注入，避免校验后替换原文件或从工作区载入同名模块。执行结束删除副本，会话删除或临时节点回收时删除其信任记录。会话恢复保留已有摘要，不会重新认可被修改的会话代码；旧会话没有记录时只以当前管理员库为基准，不以会话文件为基准。旧代码与管理员库不一致会拒绝执行，应新建会话取得可信版本。备份数据时包含信任记录，共享技能库仍需另行备份。

网页对上述文件显示“只读”，禁用编辑保存、改名、剪切和删除。管理员的技能库维护入口仍可修改可信源文件，更新后的代码和配置供新会话下发。

这些是应用层门禁，不是操作系统沙箱。管理员批准的脚本仍以服务进程账号权限运行，必须审查脚本、依赖与其调用的外部程序，不能把任意用户代码放进管理员库直接批准。

三层信任关系、升级兼容和会话生命周期见[受控技能与执行信任](skill-security.md)；部署、升级后出现 MD5 失败时，按[技能升级与排查步骤](../deployment.md#skill-security-upgrade)处理，不能通过删除摘要或关闭校验来恢复运行。

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
