---
name: doc-image-qc
description: 图文 Markdown 大文档的图片质检流水线。触发场景：用户要求检查文档中的图片、图文一致性核对、图片合规审查、生成质检报告，且文档大（数百 KB 或上百图）超出主 Agent 上下文时。核心约束：主 Agent 只做编排调度，永不读原文全文；子 Agent 逐图即焚；结论以 JSON 增量落盘支持断点续跑；最终 HTML 报告由确定性工具 render_qc_report 渲染。
---

# 图文文档图片质检流水线

你（主 Agent）在这条流水线里**只当调度器**：建立清单 → 派发子 Agent → 渲染报告。
**绝对禁止**：`read_document` 直接读待检文档原文（它会撑爆你的上下文）、
`force_read=true`（主 Agent 无权使用）、把子 Agent 的完整汇报原文堆进上下文。

## 角色分工

| 角色 | 职责 | 上下文预算 |
|---|---|---|
| 主 Agent（你） | 编排、派发、读结论行、调 render_qc_report | 每图只保留 1 行结论 |
| 子 Agent（delegate_task） | 读清单 / 质检图片 / 追加 JSON 结论 | 用完即焚，随便烧 |
| render_qc_report 工具 | JSON 数据 → HTML 报告（确定性模板） | 零推理消耗 |

## 阶段 0：准备（主 Agent 直接做）

1. `write_working_doc` 初始化进度文档（见下方模板），这是断点续跑的依据。
2. 确认视觉能力：若 `image_reasoning` 工具不在你的工具列表里（无视觉模型配置），
   **立即停止并告知用户**"需要配置视觉模型才能做图片质检"，不要硬跑。
3. **收到压缩包先解压**：用户附件若是压缩包（zip/7z/rar/tar 等），先用
   `archive_tool`（operation=`list`）查看包内结构，再 `archive_tool`（operation=`extract`）
   解压到 workspace，然后从解压出的 Markdown 文档开始质检；包内若有多份文档，
   逐份跑完整流水线，报告按文档分别生成。图片已在压缩包目录里的直接用相对路径引用，不要移动文件。

## 阶段 1：提取图片清单（子 Agent #1）

派子 Agent：

> 任务：在 `<文档路径>` 中提取全部图片引用。
> 1. `grep_files` 用 pattern `!\[[^\]]*\]\([^)]+\)|<img[^>]+src="[^"]+"` 扫描该文件；
>    结果太大就分批。
> 2. 同时抓取每张图片所在位置的前后 10 行上下文（图片说明、临近段落中提到
>    该图的文字）、alt 文本。
> 3. 写入 `generate/qc-manifest.md`：每图一节，含图片引用路径（**原样保留**，
>    如 `images/p0014_003.png`）、所在行号、关联描述原文。不写质检结论。
> 4. 按 `checks.md`（read_pack_file 可读）的分组（通用/原理图/组网图/界面截图）给每张图
>    标注适用检查项（依据 alt 文本与上下文判断图片类型，可多选）。
> 5. 汇报：图片总数、清单路径、本地/外链/缺失分类。

外链图（http/https）在清单里标注 `外链`，后续不检。

## 阶段 2：逐图质检（子 Agent #2..N，每图一个）

主 Agent `read_working_doc` 看进度，对每个**未完成**的本地图片派一个子 Agent：

> 任务：质检图片 `<图片引用路径>`（相对 Markdown 同目录解析）。
> 1. `read_document generate/qc-manifest.md`，只看该图片对应小节的关联描述。
> 2. `image_reasoning` 检查该图。**检查项以附属文档 checks.md 为准**
>    （用 `read_pack_file` 工具读：pack=`doc-image-qc`，member=`checks.md`）：通用项 C1-C3 对所有图必检；
>    原理图类加 S1-S3，组网图类加 N1-N2，界面截图类加 U 组全部（当前 U1-U5，含 U5 界面术语一致性）——按清单阶段 1
>    标注的分组选取。每项独立给 PASS/WARN/FAIL 结论与一句话依据，不要泛泛而谈；
>    事实性不一致（含术语与正文不符）一律 FAIL，遵守 checks.md 的判定级别纪律。
> 3. 把该图的结论**追加**到 `generate/qc-report.json`（先 `read_document` 读现有
>    JSON，把新条目加入 items 数组后 `write_file` 整体写回；文件不存在则新建骨架：
>    `{"document":"<文档路径>","checked_at":"<时间>","vision_model":"<模型名>","items":[]}`）。
>    条目格式：
>    ```json
>    {"image": "images/p0014_003.png", "loc": "L203 · 拉手条安装",
>     "status": "PASS|WARN|FAIL|MISSING|ERROR",
>     "checks": [{"id": "C1", "name": "图文一致", "status": "PASS", "note": "…"},
>                {"id": "N1", "name": "组网图正确性", "status": "WARN", "note": "…"}],
>     "detail": "建议（可选）"}
>    ```
>    注意 image 字段用**文档内的原始引用路径**（渲染时直接作为相对 src）。
> 4. 用 `write_file` 覆盖 `generate/qc-progress.md`（读旧内容 + 追加本图一行
>    `图名|状态` 整体写回）。
> 5. 汇报只回一行：`<图片名> | PASS/FAIL/WARN | 一句话最关键问题`。

**主 Agent 纪律（省轮次）**：
- 只连续 `delegate_task`，每图 1 轮；进度看 qc-progress.md，不要每图更新 working_doc。
- 每完成 5 张，向用户报一次进度（"已完成 x/N"）。
- 外链图片派子 Agent 仅记录"外链未检"（status 用 SKIP），不调 image_reasoning。
- 图片文件不存在：status 记 MISSING，继续下一张。
- 单个子 Agent 反复失败 2 次：status 记 ERROR，跳过。

## 阶段 3：渲染报告（主 Agent 调确定性脚本）

全部完成后，调用 `run_skill_script` 工具（一次搞定，不消耗推理）：

- pack: `doc-image-qc`
- script: `render_report.py`
- args: `{"data_path": "generate/qc-report.json", "doc_dir": "<被检 Markdown 所在的 Session 相对目录，如 workspace/md>"}`

脚本产物**只写 generate/**（不污染被检文档目录）：
1. **generate/** `qc-report-<文档名>.html` + `.json`；
2. **generate/** `qc-report-<文档名>.zip`（自包含：HTML + JSON + 全部图片按相对结构打包，下载解压后双击 HTML 即可阅读，图片正常显示）。

文档目录只读（图片从那里读取打包），任何情况下不要把产物写到文档目录。然后向用户交付：**generate/ 的 zip 路径（主交付物，提示下载解压查看）** + 统计数字（PASS/WARN/FAIL 各多少）+ 最严重的 3 个问题（每条一句话）。不要引导用户在应用内预览 HTML。

## working_doc 模板（阶段 0 初始化）

```markdown
# 图片质检进度：<文档路径>

## 状态
- 阶段：提取清单 / 质检中 / 已完成
- 图片总数：待定
- 已完成：0

## 进度表
| 图片 | 状态 | 结论行 |
|---|---|---|
```

## 断点续跑规则

用户说"继续"时：`read_working_doc` + `read_document generate/qc-progress.md`
→ 从第一个未完成图片继续阶段 2。qc-report.json 已有的条目不重复检查。阶段 3 的渲染由 run_skill_script 确定性完成。
清单文件若不存在则重跑阶段 1。
