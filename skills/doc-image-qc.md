---
name: doc-image-qc
description: 图文 Markdown 大文档的图片质检流水线。触发场景：用户要求检查文档中的图片、图文一致性核对、图片合规审查、生成质检报告，且文档大（数百 KB 或上百图）超出主 Agent 上下文时。核心约束：主 Agent 只做编排调度，永不读原文全文；子 Agent 逐图即焚；报告增量落盘支持断点续跑。
---

# 图文文档图片质检流水线

你（主 Agent）在这条流水线里**只当调度器**：建立清单 → 派发子 Agent → 汇总落盘。
**绝对禁止**：`read_document` 直接读待检文档原文（它会撑爆你的上下文）、
`force_read=true`（主 Agent 无权使用）、把子 Agent 的完整汇报原文堆进上下文。

## 角色分工

| 角色 | 职责 | 上下文预算 |
|---|---|---|
| 主 Agent（你） | 编排、派发、读结论行、写报告骨架 | 每图只保留 1 行结论 |
| 子 Agent（delegate_task） | 读原文片段 / 找图片关联描述 / 调 image_reasoning 质检 | 用完即焚，随便烧 |

## 阶段 0：准备（主 Agent 直接做）

1. `write_working_doc` 初始化进度文档（见下方模板），这是断点续跑的依据。
2. 确认视觉能力：调 `list_skill_packs`/`use_skill` 无关，直接问自己——
   若 `image_reasoning` 工具不在你的工具列表里（无视觉模型配置），**立即停止并告知用户**
   "需要配置视觉模型才能做图片质检"，不要硬跑。

## 阶段 1：提取图片清单（子 Agent #1）

派子 Agent：

> 任务：在 `<文档路径>` 中提取全部图片引用。
> 1. `grep_files` 用 pattern `!\[[^\]]*\]\([^)]+\)|<img[^>]+src="[^"]+"` 扫描该文件；
>    结果太大就分批（每次限定 pattern 片段或行号范围）。
> 2. 同时抓取每张图片所在位置的前后 10 行上下文（`grep_files` 行号 ±10 的窗口读法：
>    `read_document` 不行就用 `grep_files` 按行号正则逐段取）。
> 3. 把结果写入 `generate/qc-manifest.md`：每图一节，含
>    图片路径/文件名、所在行号、**图片关联描述原文**（上下文里的图片说明、
>    临近段落中提到该图的文字）、alt 文本。不写任何质检结论。
> 4. 汇报：图片总数、清单文件路径、有无本地文件缺失（引用了但文件不存在）。

**注意**：文档里的图片分两类——本地文件（`attachments/...`、`workspace/...` 路径）
和外链（http/https）。外链图无法用 image_reasoning 检查，清单里单独标注 `外链`。

## 阶段 2：逐图质检（子 Agent #2..N，每图一个）

主 Agent `read_working_doc` 看进度，对每个**未完成**的本地图片派一个子 Agent：

> 任务：质检图片 `<图片路径>`。
> 1. `read_document generate/qc-manifest.md`，只看该图片对应小节的关联描述。
> 2. `image_reasoning` 检查该图，prompt 模板：
>    - 「这是文档中的一张图片。文档中对它的描述如下：〈描述原文〉。
>      请检查：a) 图片内容与描述是否一致（列出不一致点）；b) 图片质量：清晰度、
>      文字可读性、构图完整性；c) 合规检查：是否含敏感信息（身份证/手机号/
>      密钥/水印遮挡）、不当内容、版权风险标志。逐项给结论，不要泛泛而谈。」
> 3. 把结论**追加**到 `generate/qc-report.md`（先 `read_document` 读末尾，
>    `replace_in_file` 或 `write_file` 追加），格式：
>    ```
>    ## <图片名>
>    - 状态：PASS / FAIL / WARN
>    - 图文一致：…
>    - 质量：…
>    - 合规：…
>    - 问题明细：…（无问题写"无"）
>    ```
> 4. 用 `write_file` 覆盖写 `generate/qc-progress.md`：先 `read_document` 该文件，
>    把本图的一行 `<图片名>|PASS/FAIL/WARN` 追加进去再整体写回（没有该文件就新建）。
> 5. 汇报只回一行：`<图片名> | PASS/FAIL/WARN | 一句话最关键问题`。

**主 Agent 纪律（省轮次，这决定流水线能跑多长）**：
- 汇报只需一行；把这一行记进 working_doc 进度表的方式是**批量**的：
  每 3~5 张图完成后再 `read_working_doc` + `replace_in_file` 一次性更新进度表，
  不要每图一更新（主 Agent 轮次有限，省着用）。
- 也可以让每个质检子 Agent 在写 qc-report.md 的同时，直接 `write_file` 覆盖
  `generate/qc-progress.md`（一行一图：`图名|状态`），主 Agent 就完全不用碰进度。
  **推荐后者**：主 Agent 只连续 `delegate_task`，需要看进度时才 `read_document`
  qc-progress.md。
- 每完成 5 张，向用户报一次进度（"已完成 x/N"）。
- 外链图片派子 Agent 仅记录"外链未检"，不调 image_reasoning。

## 阶段 3：汇总报告（主 Agent 直接做）

全部完成后：
1. `grep_files` 统计 qc-report.md 里的 PASS/FAIL/WARN 数量（pattern `状态：`）。
2. `write_file generate/qc-summary.md`（覆盖写）：
   - 检查对象、图片总数、通过/警告/失败统计
   - FAIL 与 WARN 的问题汇总（从 qc-report.md 的状态行附近 grep 出标题行）
   - 建议处理清单
3. 向用户交付：两个文件的路径 + 统计数字 + 最严重的 3 个问题（每条一句话）。

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

用户说"继续"时：`read_working_doc` → 看进度表 → 从第一个未完成图片继续阶段 2。
清单文件若不存在则重跑阶段 1。已写入 qc-report.md 的结论不重复检查。

## 失败处理

- 子 Agent 汇报 image_reasoning 报错：该图状态记 `ERROR`，继续下一张，最后汇总时列出。
- 图片文件不存在：状态 `MISSING`，同样继续。
- 单个子 Agent 反复失败 2 次：跳过并在最终汇报中说明。
