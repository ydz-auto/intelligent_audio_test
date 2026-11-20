---
name: report-compare
description: >-
  报告对比口径：多报告并排取数（指标矩阵 / 设备与 API 统计 / 用例分类统计）、
  二次对比（对已有对比报告再做一次对比）、统计趋势序列，以及异常报告下钻。
  触发词：报告对比、对比报告、二次对比、多报告对比、并排对比、报告差异、
  指标差异、通过率对比、报告趋势、指标趋势、趋势序列、异常报告、通过率异常、
  环比、同比。
  不适用：单份报告的取数与指标解释、报告起草（report-studio 负责）；生成对比
  报告 / 二次对比报告（写操作，M2 走提案 + 审批）；任务执行（task-operations 负责）。
version: 1.0.0
owner: report-team
allowed-tools:
  - report_compare
  - report_query
  - tool_search
permissions:
  - report:read
  - report:compare
budgets:
  maxToolCalls: 30
  maxTokens: 50000
---

# report-compare

报告**对比与趋势**的只读入口。本 Skill 只回答「这几份报告各自的权威数值是多少、
趋势怎么走、异常报告是哪几份」，**不生成平台对比报告、不做二次计算**。

## 何时用

- 把 2~10 份报告并排看：通过率、用例数、指标矩阵、设备 / API 统计；
- 二次对比：对平台已有的对比 / 二次对比报告再做一次并排（例如两版对比报告之间）；
- 趋势：报告数 / 用例数 / 通过率 / 耗时随时间的变化序列；
- 异常下钻：从统计分析的异常清单定位到具体报告，再看该报告的用例明细。

## 何时不用

- 只看**一份**报告或解释单个指标口径：转 `report-studio`（`report_query` 的
  `detail` / `cases` / `statistics`）；
- 要**生成对比报告 / 二次对比报告**：平台的这两个接口会落库新建报告，属写操作，
  M1 不执行（M2 走提案 + 审批）；本 Skill 只做只读并排；
- 要跑任务或重试：转 `task-operations`；
- 要解释评估维度评分口径：转 `evaluation-config`。

## 工具用法

业务工具是 `report_compare`（只读，权限 `report:compare`；底层读的是
`GET /api/v1/reports/{id}`，还要求 `report:read`——平台角色里两个码默认一起发放）：

| action | 作用 | 必填 / 可选参数 | 底层接口 |
|---|---|---|---|
| `compare` | 多报告并排取数（任意报告类型） | 必填 `report_ids`（2~10 个，去重） | `GET /api/v1/reports/{report_id}` × N |
| `secondary_compare` | 二次对比：源报告必须是已有对比 / 二次对比报告 | 必填 `report_ids`（2~10 个） | 同上，带类型校验 |
| `trend` | 统计趋势序列 | 可选 `trend_type`（`time` / `dimension`，缺省 `time`）/ `metric` / `start_time` / `end_time` | `GET /api/v1/reports/statistics/trend` |

配套的取数工具是 `report_query`（只读，权限 `report:read`）：

- `detail` / `cases` / `cases_search`：并排之后要看某份报告的用例明细、按指标筛出
  最差用例；
- `statistics`：异常清单在返回的 `anomaly[]` 里（如 `low_pass_rate`）；
- `list`：按 `report_type` / `task_id` 找报告 ID。

规则：

1. 先拿报告 ID（用户给的是任务 ID 时用 `report_query.by_task` 或
   `list?task_id=` 换成报告 ID），再做 `compare`；
2. 一次最多 10 份；超过请分批并说明这是分批结果；
3. 二次对比前先确认源报告确实是 `comparison` / `secondary_comparison`——
   类型不符工具会直接报错，不会悄悄按普通报告对比；
4. 工具不支持的参数会直接报错（不会静默忽略）。

## 响应形态（与真实接口一致）

`compare` / `secondary_compare` 返回工具层组合后的对象：

```json
{"action": "compare",
 "report_count": 2,
 "reports": [
   {"report_id": 426, "name": "...", "type": "task", "status": "published",
    "task_id": 460, "task_name": "...", "created_at": "...", "visibility": "shared",
    "summary": {"total_cases": 2, "completed_cases": 2, "failed_cases": 0,
                "pass_rate": 100.0},
    "resources": ["..."], "resource_headers": [{"key": "...", "label": "...",
    "type": "device", "id": 9, "name": "...", "version": "1.0.0"}],
    "all_metrics": [{"id": 57, "name": "打断成功数量", "unit": "%",
                     "decimal_places": 2, "statistic_method": "ratio",
                     "agg_denominator": "round", "dimension_type": "main",
                     "parent_dimension_id": null, "parent_dimension_name": null}],
    "metric_data": [{"resource": "...", "metrics": [{"id": 57, "metric": "...",
                                                     "value": 80.28}]}],
    "tag_metric_data": [], "case_type_stats": [], "device_stats": [],
    "api_stats": []},
   {"report_id": 425, "...": "同上结构"}
 ],
 "missing": [{"report_id": 999, "status": 404, "message": "资源不存在或无权访问。"}]}
```

`secondary_compare` 的每项另带 `source_task_ids`（来自 `summaries[].metadata.task_ids`，
即该对比报告覆盖的源任务）。

`trend` 直接返回接口原文：

```json
{"trend_type": "time",
 "time_trend": [{"date": "2026-10-01", "report_count": 3, "total_cases": 120,
                 "pass_rate": 92.0, "duration": 9197.0}],
 "dimension_trend": [],
 "time_range": {"start_time": "...", "end_time": null}}
```

大结果（多份报告的完整矩阵）由上下文压缩落 artifact
（`context_tool_result`），后续轮次看到的是摘要 + artifact 引用，这是预期行为。

## 怎么表达对比结论

- **只并排、不派生**：把各自报告的原值并排列出（`summary.pass_rate`、
  `summary.total_cases`、`metric_data` 中同一资源同一指标的 `value`、
  `device_stats.metrics`）；
- **不要输出接口没给的数字**：差值、增长率、倍数、排名百分比都不是接口字段，
  不要自己算；需要说明差异时，写「A 报告 pass_rate=93.68，B 报告 pass_rate=84.24」
  并标明这是接口原文；
- **同量纲再比较**：先用 `all_metrics` 的 `unit` / `decimal_places` 确认两边量纲
  一致（`0.85` 与 `85` 是不同口径），不一致时先说明口径差异，不给结论；
- **资源要对齐**：`metric_data` 是按资源列的（设备 / API），两边资源集合不同时
  不能直接并列比较，先列出各自资源；
- **缺失要说清**：`missing` 非空时明确告诉用户哪几份报告不可访问，其余照常给出；
- **二次对比**的结论要说明源报告是哪几份（`source_task_ids`），以及它们本身就是
  对比报告（不是原始任务报告）。

## 异常下钻路径

1. `report_query.statistics`：看 `anomaly[]`（如 `type=low_pass_rate` 的报告及
   `value`），必要时按 `dimension` / 时间窗收窄；
2. 对候选报告 `report_query.detail`：看 `summary.pass_rate`、
   `device_stats` / `case_type_stats` 里最差的分类；
3. 用例级下钻：`report_query.cases_search`，用 `metrics` + `sort_by=metric` +
   `sort_metric` 排序，或 `category` / `tags` 过滤，找出最差用例；
4. 想知道「生成到哪一步」用 `report_query.progress`；`draft` 不等于生成中。

## Gotchas

1. **对比不落报告**：平台的 `POST /api/v1/reports/compare` 与
   `/secondary-compare` 会**新建一份报告记录**，属写操作；Agent 侧的
   `report_compare` 是只读组合（逐份读详情），不会出现在报告列表里。用户要
   「生成一份对比报告」时，说明这是 M2 审批后的写操作。
2. **同名不同物**：外部 MCP 工具列表里也有 `report_compare`（那一份是上面的写
   接口，1:1 映射保持不变）；Agent 通道里这个名字是只读组合工具，调用不会写库。
3. **`compare` 与 `secondary_compare` 的区别是源报告类型**：前者任意报告并排，
   后者只接受 `comparison` / `secondary_comparison`，混用会得到明确的类型错误。
4. **报告 ID 不是任务 ID**：`task_id` 要先用 `by_task` 或 `list?task_id=` 换成
   `report_id` 再对比；直接把任务 ID 当报告 ID 会得到「不存在或无权访问」。
5. **`type=secondary_comparison` 的报告才有 `source_task_ids`**；普通任务报告没有
   这个字段，不要臆造。
6. **`trend` 与 `statistics` 不同**：`trend` 给时间序列点（`time_trend` /
   `dimension_trend`），`statistics` 给按维度聚合的 `overview` / `detail` /
   `chart` / `anomaly`；要「趋势图数据」用 `trend`，要「某个维度下多少报告、
   通过率多少」用 `statistics`。
7. **`trend` 的指标名以接口返回为准**：`metric` 只是过滤条件，不要枚举不存在的
   指标名；`dimension_trend` 可能为空数组，空就是空。
8. **时间窗参数是字符串**：`start_time` / `end_time` 直接透传（`2026-10-01` 或
   ISO 8601），接口返回的 `time_range` 才是它实际采用的范围。
9. **`missing` 里的 403 / 404 文案统一**：「资源不存在或无权访问」是防探测口径，
   不要追问是否存在、不要枚举 ID。
10. **`private` 报告不可见**：仅归属人与 admin 能看到详情；参与对比时会被记入
    `missing`，其余报告照常返回。

## 验收

回答对比 / 趋势类问题时，逐项自检：

- [ ] 报告 ID 来自 `report_query`（`by_task` / `list`），不是猜的；
- [ ] 每个参与对比的报告都在 `reports` 或 `missing` 里出现，没有遗漏；
- [ ] 对比的每个数字都能回溯到返回字段（`summary.*` / `metric_data` /
      `device_stats.metrics` / `case_type_stats`），没有差值 / 增长率等派生数值；
- [ ] 量纲与资源对齐后再下结论，说明指标 `unit`；
- [ ] 二次对比明确说了源报告类型与 `source_task_ids`；
- [ ] 趋势回答引用 `time_trend` / `dimension_trend` 原文，没有把空数组说成 0；
- [ ] 提到「生成对比报告」时说明 M1 只读、M2 审批边界，没有假装已生成。
