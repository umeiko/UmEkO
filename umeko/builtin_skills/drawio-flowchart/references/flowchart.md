# 流程图 XML 规则

生成未压缩的单页 `<mxfile><diagram><mxGraphModel><root>…`。固定保留 `<mxCell id="0"/>` 与 `<mxCell id="1" parent="0"/>`。节点和连线均 `parent="1"`，每个 ID 唯一，不写 `mxGeometry`，由脚本自动计算。

- 使用 `id="start"` 和 `id="end"` 的起止节点；文字可为“开始：顾客到店”或“结束：接待完成”，无需严格等于“开始/结束”。开始无入边，结束无出边。所有步骤从开始可达，且存在通向结束的路径；允许按业务要求回退和循环。
- 起止节点用 `rounded=1;arcSize=50`，处理节点 `rounded=1`，判断节点 `rhombus`。统一 `whiteSpace=wrap;html=1;fontSize=13;align=center;verticalAlign=middle;strokeColor=none;`。
- 色彩、形状与分支配色以当前 style.md 的 `[drawio:flowchart]` 段落为准；原默认风格起止浅灰、必经步骤/判断主色蓝、可选分支用指定浅色、汇合后恢复主色。示例颜色供结构参考，不覆盖实际风格规则，也不因低层细节自行增加配色。
- 每条连线使用 `edge="1" source="节点ID" target="节点ID"`，判断节点每条出边必须有非空 `value` 标签（如是/否），至少两个分支。连线样式交给脚本统一为直角走线。
- 文字忠实于输入且简短，默认用中文，明确要求的英文和必要术语除外。XML 属性中的 `& < > "` 必须转义；换行写 `&lt;br/&gt;`，不能把原始 HTML 写进属性。写 XML 文件时不要写代码围栏。
- 字体、尺寸以 `config.json` 为准，脚本会覆盖模型字体并自动布局：原规范为 `fontFamily=方正兰亭黑简体;fontSize=10.5`，节点宽 172px、最小高 28px、纵向间距 28px，横向间距 60px；菱形按 1.6 倍高度处理，多行文字只增加对应节点的高度。只把必要短标签放入节点，文字过多时先提炼，不靠增大所有框解决。
- 先总结文档再画简要流程。复杂的有标题文档最多展示到三级标题，不要求每个标题各画一个框，不把标题下的细节逐句展开为节点；合并同阶段的细碎操作、重复步骤，节点用短动作名称。
- 判断节点是可选的，不是所有流程图必备。只有改变核心路径、关键结果或结束条件的必要条件才画分支；提示、话术、常规检查点和低层异常留在作图清单，不把文档里的每个“如果”都变成判断。不额外补出通用的校验、确认、重试路径。
- 必要分支尽早汇合，共享相同后续流程；处理一致、去向相同的分支可以合并。简化不能删除影响业务结果的决策，不能把失败路径并成成功路径；用户明确要求的详细步骤、异常、并行和回退关系必须保留。

首次运行前逐项核对：唯一 ID；根单元 0/1；每条边的 source/target 已定义；判断至少两条带标签的出边；开始无入边/结束无出边；全部步骤可从开始到达并通向结束。不要用没有退出路径的循环代替结束，不要省略分支。

默认主线示例（没有必要判断时直接画线性流程；写文件时去掉代码围栏，动作换成实际作图清单）：

```xml
<mxfile host="app.diagrams.net"><diagram name="流程图" id="d1"><mxGraphModel page="0"><root>
  <mxCell id="0"/><mxCell id="1" parent="0"/>
  <mxCell id="start" value="开始" style="rounded=1;arcSize=50;whiteSpace=wrap;html=1;fillColor=#E1E4E6;fontColor=#3E4144;strokeColor=none;" vertex="1" parent="1"/>
  <mxCell id="s1" value="确认需求" style="rounded=1;whiteSpace=wrap;html=1;fillColor=#2ECBFF;fontColor=#FFFFFF;strokeColor=none;" vertex="1" parent="1"/>
  <mxCell id="s2" value="完成办理" style="rounded=1;whiteSpace=wrap;html=1;fillColor=#2ECBFF;fontColor=#FFFFFF;strokeColor=none;" vertex="1" parent="1"/>
  <mxCell id="end" value="结束" style="rounded=1;arcSize=50;whiteSpace=wrap;html=1;fillColor=#E1E4E6;fontColor=#3E4144;strokeColor=none;" vertex="1" parent="1"/>
  <mxCell id="e1" edge="1" parent="1" source="start" target="s1"/>
  <mxCell id="e2" edge="1" parent="1" source="s1" target="s2"/>
  <mxCell id="e3" edge="1" parent="1" source="s2" target="end"/>
</root></mxGraphModel></diagram></mxfile>
```

仅在真实需求确有必要分支时参考下例（不要把示例里的判断自动添加到任务里）：

```xml
<mxfile host="app.diagrams.net">
  <diagram name="流程图" id="d1">
    <mxGraphModel grid="1" gridSize="10" page="0">
      <root>
        <mxCell id="0"/>
        <mxCell id="1" parent="0"/>
        <mxCell id="start" value="开始" style="rounded=1;arcSize=50;whiteSpace=wrap;html=1;fillColor=#E1E4E6;strokeColor=none;" vertex="1" parent="1"/>
        <mxCell id="check" value="输入是否有效？" style="rhombus;whiteSpace=wrap;html=1;fillColor=#2ECBFF;fontColor=#FFFFFF;strokeColor=none;" vertex="1" parent="1"/>
        <mxCell id="process" value="处理输入" style="rounded=1;whiteSpace=wrap;html=1;fillColor=#D2E6FA;strokeColor=none;" vertex="1" parent="1"/>
        <mxCell id="end" value="结束" style="rounded=1;arcSize=50;whiteSpace=wrap;html=1;fillColor=#E1E4E6;strokeColor=none;" vertex="1" parent="1"/>
        <mxCell id="e1" edge="1" parent="1" source="start" target="check"/>
        <mxCell id="e2" value="是" edge="1" parent="1" source="check" target="process"/>
        <mxCell id="e3" value="否" edge="1" parent="1" source="check" target="end"/>
        <mxCell id="e4" edge="1" parent="1" source="process" target="end"/>
      </root>
    </mxGraphModel>
  </diagram>
</mxfile>
```
