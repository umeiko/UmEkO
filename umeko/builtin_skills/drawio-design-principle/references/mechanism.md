# 设计原理图模型

- **作用链** 让同一行的输入、核心机制和结果从左向右对齐。控制策略可放在机制上方或下方。
- **反馈闭环** 先画正向作用链，再从实际结果回到比较或决策节点，反馈线上注明观察量。判断闭环时检查回到的是可改变行为的机制。
- **方案对照** 用两行共享相同列语义，列间对齐输入、机制和结果。控制变量一致；用小字说明差异的适用条件，避免误读为并行运行。
- **保护或降级** 在主链之外标明触发条件、保护动作和受影响的结果。材料没有说明的路径可以留白或标注待验证。

模型只写用户材料支持的信息或明确标出的假设。 `basis` 可写简短来源或适用条件。对多个机制按讲解问题拆图。

## JSON 字段

| 字段 | 约定 |
| --- | --- |
| `title` | 标题，最多 40 字 |
| `principle` | 一句话讲清原理，最多 90 字 |
| `basis` | 可选，材料依据或适用条件，最多 90 字 |
| `nodes` | 2–12 个节点。每项含 `id`、`label`、`role`。可选 `detail`、`icon`、`assumed` |
| `layout` | 以节点 ID 为键，值为从零开始的 `[列, 行]`。列 0–4，行 0–3。每个槽位放一个节点 |
| `relations` | 1–20 条定向关系。每项含 `source`、`target`、`label`、`kind` |

- ID 以英文字母开头，可含数字、下划线和连字符，最长 32 字符。
- 节点 `role` 可为 `input`（输入）、`mechanism`（作用机制）、`state`（观测、状态或策略）、`output`（结果）。节点名最多 18 字，说明最多 28 字。
- 关系 `kind` 可为 `data`（传递数据、材料或能量）、`control`（控制或触发）、`feedback`（反馈）、`fallback`（保护或降级）。线标签最多 12 字，优先控制在 8 字以内。
- `icon` 使用图标表中的键。 `assumed: true` 将节点标为待验证。
- 尽量让相连节点占相邻列或同行，把有意跨行或跨列的长线留给少数关键关系。脚本给反馈分配下方回路空间，图复杂时仍要检查连线和文字是否遮挡。

## 合成示例

```json
{
  "title": "负载控制的反馈原理",
  "principle": "控制器比较实际延迟和目标，通过调整并发度限制排队增长。",
  "basis": "合成示例。负载持续超出可用容量时，仅调整并发度可能不足。",
  "nodes": [
    {"id":"request","label":"请求流入","role":"input","icon":"input"},
    {"id":"control","label":"并发控制器","role":"mechanism","detail":"对比目标并调整限额","icon":"decision"},
    {"id":"worker","label":"执行池","role":"mechanism","detail":"按当前限额接收任务","icon":"process"},
    {"id":"observe","label":"延迟观测","role":"output","icon":"measure"}
  ],
  "layout": {"request":[0,0],"control":[1,0],"worker":[2,0],"observe":[3,0]},
  "relations": [
    {"source":"request","target":"control","label":"提交请求","kind":"data"},
    {"source":"control","target":"worker","label":"调整限额","kind":"control"},
    {"source":"worker","target":"observe","label":"记录耗时","kind":"data"},
    {"source":"observe","target":"control","label":"回传实际延迟","kind":"feedback"}
  ]
}
```

## 参考来源

从上游提炼了语义模型与布局分离、为边写明传递内容以及保留依据的方法。
本技能的模型、版式和脚本独立实现。

- [上游 Diagram IR](https://github.com/Agents365-ai/drawio-skill/blob/1f59eae2ca4740ed72a195279469fb58fa39d9e0/skills/drawio-skill/references/diagram-ir.md)
- [上游原理与分析工作流参考](https://github.com/Agents365-ai/drawio-skill/blob/1f59eae2ca4740ed72a195279469fb58fa39d9e0/skills/drawio-skill/references/semantic-workflows.md)
