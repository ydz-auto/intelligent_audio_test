---
name: report-studio
description: >-
  报告取数、指标解释与起草口径：三类报告（任务 / 对比 / 二次对比）列表与详情、
  指标矩阵、设备与 API 统计、用例明细与用例搜索、维度统计、生成进度、页签计数，
  以及报告文本（描述 / 分析 / 结论）的起草与版本口径。
  触发词：报告详情、报告指标、报告列表、报告用例、报告统计、报告进度、页签计数、
  通过率、平均分、指标单位、用例平均值、报告起草、报告版本、导出报告、报告结论。
  不适用：多报告对比 / 二次对比 / 趋势（report-compare 负责）；生成、重生成、
  导出文件、改报告、发布、删除、分享、Studio 文档写（写操作，M2 走提案 + 审批）；
  任务执行本身（task-operations 负责）。
version: 1.0.0
owner: report-team
allowed-tools:
  - report_query
  - tool_search
permissions:
  - report:read
budgets:
  maxToolCalls: 40
  maxTokens: 60000
---

# report-studio

报告域的**只读取数 + 指标解释 + 起草口径**入口。本 Skill 只回答「平台上这份/这些
报告现在是什么数值、这些字段是什么口径、报告文本该怎么写」，**不执行任何写操作**。

## 何时用

- 查报告列表 / 详情 / 按任务查报告，定位报告 ID；
- 解释报告里的指标：单位、小数位、统计方式、聚合分母、主维度 / 子维度归属；
- 取设备 / API 维度的统计、用例分类统计、标签指标；
- 查某份报告的用例明细、按指标筛出最差用例（异常下钻的第一跳）；
- 查报告统计（按时间 / 设备类型 / 评估维度）、页签计数、生成进度；
- 起草报告的描述 / 分析 / 结论文本，或在既有报告文本上改稿（只产出草稿文本，
  不落库）。

## 何时不用

- 多份报告并排对比、二次对比、趋势序列：转 `report-compare`；
- 要**生成 / 重生成报告、导出 PDF/PPTX/HTML/MD、修改报告、发布、删除、分享、
  写 Studio 文档**：M1 只有只读能力，写操作在 M2 走提案 + 审批，现在明确告诉
  用户「当前阶段不能执行」；
- 要跑任务 / 重试 / 看任务执行日志：转 `task-operations`；
- 要解释评估维度的评分口径（不是报告数值）：转 `evaluation-config`。

## 工具用法

唯一业务工具是 `report_query`（只读，权限 `report:read`）：

| action | 作用 | 必填 / 可选参数 | 对应接口 |
|---|---|---|---|
| `list` | 报告列表（分页 + 过滤） | 可选 `page` / `per_page` / `keyword` / `report_type` / `status` / `task_id` / `algorithm_type` / `start_time` / `end_time` / `favorite` / `deleted` | `GET /api/v1/reports` |
| `detail` | 报告详情（指标矩阵就在这里） | 必填 `report_id` | `GET /api/v1/reports/{report_id}` |
| `by_task` | 按任务取最新报告 | 必填 `task_id` | `GET /api/v1/reports/by_task/{task_id}` |
| `tab_counts` | 页签 / 类型 / 收藏计数 | 可选 `keyword` / `favorite` / `deleted` | `GET /api/v1/reports/tab-counts` |
| `statistics` | 报告统计分析（按维度聚合） | 可选 `dimension`（`time` / `device_type` / `evaluation_metric`）/ `start_time` / `end_time` / `algorithm_type` | `GET /api/v1/reports/statistics` |
| `progress` | 报告生成进度 | 必填 `report_id` | `GET /api/v1/reports/{report_id}/progress` |
| `cases` | 报告内用例（分页） | 必填 `report_id`；可选 `page` / `per_page` / `keyword` / `category` | `GET /api/v1/reports/{report_id}/cases` |
| `cases_search` | 用例搜索（标签 / 多分类 / 指标筛选 / 指标排序） | 必填 `report_id`；可选 `keyword` / `category` / `categories` / `tags` / `include_untagged` / `metrics` / `sort_by` / `sort_metric` / `sort_resource` / `sort_order` / `page` / `per_page` | `POST /api/v1/reports/{report_id}/cases/search` |
| `case_averages` | 按报告或任务聚合用例指标均值 | `report_id` 与 `task_id` **二选一**；可选 `category` / `categories` / `tags` / `include_untagged` | `POST /api/v1/reports/case-averages` |

规则：

1. 先用 `list` 定位报告 ID（可用 `keyword` / `status` / `report_type` / `task_id`
   过滤），再取 `detail`；接口返回 `total` / `pages` 判断是否还有下一页。
2. 数值一律**引用接口原文**：`pass_rate` 是接口给的百分比数值，`metric_data` 里
   的 `value` 是接口给的原值，不四舍五入、不换算单位、不跨字段推算。
3. 工具不支持的参数会直接报错（不会静默忽略），不要绕过——参数名逐字按上表。
4. 平台没有的能力明确说「当前阶段不支持 / 需审批」，不臆造工具或接口；
   长尾只读工具先用 `tool_search` 检索。

## 响应形态（与真实接口一致）

列表 / 用例 / 页签统一分页信封：

```json
{"success": true, "code": 0, "message": "Success",
 "data": {"items": [], "total": 0, "page": 1, "per_page": 20, "pages": 0}}
```

详情是 `data` 对象（无 `items` 包裹）。

### 报告列表项（ReportListItem）

`id`、`name`、`type`（= `report_type`）、`status`（`draft` / `published`）、
`task_id`、`task_name`、`description`、`created_at`、`updated_at`、
`visibility`（`shared` / `private`）、`created_by_user_id`、`is_favorite`、
`deleted` / `deleted_at` / `deleted_by_user_id`、
`summary{total_cases, completed_cases, failed_cases, pass_rate, review_count, task_count}`。

### 报告详情（data）

除列表项字段外还有：`analysis`、`conclusion`、`summaries[]`、`metric_stats[]`、
`raw_data[]`、`cases[]`，核心是 `summary` 对象：

| 字段 | 口径 |
|---|---|
| `total_cases` / `completed_cases` / `failed_cases` | 用例总数 / 已完成 / 失败 |
| `pass_rate` | 通过率，接口给的百分比数值（如 `93.68`），不要按 `completed_cases / total_cases` 重算 |
| `resources` / `resource_headers` | 指标矩阵的资源维度（设备 / API 名）与表头（`key` / `label` / `type` / `id` / `name` / `version`） |
| `all_metrics` | 指标定义：`id`、`name`、`unit`、`decimal_places`、`statistic_method`、`agg_denominator`、`dimension_type`（`main` / `sub`）、`parent_dimension_id` / `parent_dimension_name` |
| `metric_data` | 资源 × 指标值：`[{resource, metrics: [{id, metric, value}]}]`（报告详情形态） |
| `tag_metric_data` | 标签 × 指标值：`[{resource, tags: [{tag_id, tag_name, metrics: [...]}]}]` |
| `tag_category_metric_data` | 标签分类 × 指标值（可能为空数组） |
| `case_type_stats` | 用例分类统计：`[{group_id, group_name, metrics: [...]}]` |
| `device_stats` | 设备统计：`id`、`name`、`model`、`type`、`system`、`system_version`、`status`、`metrics{指标名: 值}`、`total_cases`、`completed_cases`、`failed_cases`、`success_rate` |
| `api_stats` | API 统计：同 `device_stats`，另含 `avg_response_time`、`stability` |
| `devices` / `apis` | 参与测试的设备 / API 元信息 |
| `all_case_tags` / `case_categories` | 用例标签 / 分类清单（顺序不保证稳定，不要依赖次序） |
| `field_mappings` | 算法字段映射（如 `voice_llm.result[]`），不是报告数值 |
| `raw_data` | 逐用例原始取值：`[{resource, metrics: [{metric, values: [...]}]}]`，体量大，只在用户要看原始分布时引用 |

### 用例项（cases / cases_search）

`id`、`name`、`description`、`category`、`tags[]`、`metrics[]`
（`[{resource, metrics: [{id, metric, value, round_number, dimension_type,
parent_dimension_id, parent_dimension_name}]}]`）、`algorithmType`、`audios`、
`referenceParams`、`results`、`algorithmResults`、`logs`。

### 生成进度（progress）

`report_id`、`task_id`、`status`（`generating` / `completed`）、`progress`（0–100）、
`report_status`（`draft` / `published`）。**`status` 是进度响应态，不是报告表的状态列**。

### 页签计数（tab_counts）

`all` / `draft` / `published` / `comparison` / `favorite`；
`types{task, comparison, secondary_comparison, benchmark}`。
`comparison` 页签 = 对比报告 + 二次对比报告；`all` 含草稿与回收站除外口径以接口为准。

### 统计分析（statistics）

`dimension`、`overview{report_count, completed_reports, total_cases,
completed_cases, failed_cases, pass_rate, duration}`、`detail[]`、
`chart{categories, series[{name, data}]}`、`anomaly[{type, report_id, report_name,
message, value}]`、`time_range{start_time, end_time}`。

`detail[]` 的元素随 `dimension` 变化：`time` / `device_type` 是
`{group, report_count, completed_reports, total_cases, completed_cases,
failed_cases, pass_rate, duration}`；`evaluation_metric` 是
`{metric, report_count, average_value, min, max}`。按返回原样引用，不要套另一种形状。

### 用例指标均值（case_averages）

`total_cases`、`total_results`、`overall_averages[{id, metric, value}]`、
`overall_averages_map{指标名: 值}`、`metric_data[{resource, categories:[{categoryId,
categoryName, metrics}]}]`、`tag_metric_data`、`raw_data`、`normal_distribution`、
`resources`、`resource_headers`、`filters`、`partial`、`missing_case_ids`、
`aggregation_degraded`、`aggregation_coverage`。

## 指标怎么解释

解释报告里的一个指标时，按下列顺序**引用接口原文**，不要自己算：

1. 在 `all_metrics` 找同名指标，读 `unit`（单位）、`decimal_places`（小数位）、
   `statistic_method`（聚合方式）、`agg_denominator`（比率分母 `case` / `round`）；
2. `dimension_type` = `main` 是主维度，`sub` 是挂在 `parent_dimension_id` 下的
   子维度；解释层级时用父维度名，不要把子维度当平级指标；
3. 值是 `metric_data` / `device_stats.metrics` / `case_type_stats` 里给出的原值；
   同一指标在不同资源下的值不同，回答时要指明是哪个资源；
4. `pass_rate` 与各分类 `success_rate` 都是接口聚合值，**不要**用用例数相除重算，
   也不要把 `0.85` 与 `85` 混用——按 `unit` 字段判断量纲；
5. 用例级数据看 `cases` / `cases_search` 的 `metrics[].value`，不要拿报告级均值
   反推单条用例。

## 报告文本起草与版本口径

- 可起草的文本字段：`description`（描述）、`analysis`（分析）、`conclusion`（结论）；
  接口返回值就是当前版本内容，改稿时**只产出新文本草稿**，不落库；
- 起草必须基于同一份报告 `detail` 里的数值与用例，写进文本的每个数字都要能对上
  返回字段（写明指标名与资源）；
- 版本：平台报告没有暴露历史版本接口；`GET /api/v1/reports/{id}` 返回的是当前
  内容。Report Studio 的文档版本（`/api/v1/report-studio/documents/{id}/versions`）
  是另一个域，M1 未开放为意图工具，写版本同样是 M2；
- 用户要求「保存 / 应用到报告」时，说明当前阶段只能给出文本草稿，落库走 M2 审批。

## Gotchas

1. **`type` 与 `report_type` 是同一个值**：接口两个字段都给，取值 `task` /
   `comparison` / `secondary_comparison` / `benchmark`；`report_service/domain`
   里的 `standard` / `detailed` 是历史词表，**不要**用来回答接口类型。
2. **`status` 只表达发布态**：只有 `draft` / `published`；「生成中」不是 status，
   要看 `progress` 动作的 `status`（`generating` / `completed`）。
3. **`metric_data` 有两种形态**：报告详情是 `{resource, metrics}`，用例均值
   （`case_averages`）是 `{resource, categories[{categoryId, categoryName, metrics}]}`
   —— 按动作区分，不要把 `categories` 当空数组处理。
4. **GET `cases` 不支持 `tags`**：网关对查询串按字符串校验会 400；按标签筛用例
   请走 `cases_search`（JSON body 支持 `tags` / `categories` 数组）。
5. **`include_untagged` 单独使用时等于「只看未打标签用例」**：与 `tags` 同用才是
   「命中标签 + 未打标签」并集（`_report_case_filters.filter_test_cases` 口径）。
6. **分页有边界**：`page ≥ 1`、`per_page ≤ 200`；工具层超界直接报错，网关本身
   不校验（`per_page=1000` 会一次返回全量，别这么用）。
7. **历史对比报告的 `case_type_stats` 形态可能不同**：在册数据里既有
   `{group_name, metrics: [...]}` 也有把键值对塞进 `metrics` 的旧形态；按返回原样引用，
   不要假设固定结构。
8. **`private` 报告详情可能是 404**：这是防探测统一口径，回答「不存在或无权访问」，
   不要继续枚举 ID。
9. **统计维度越界会被服务端拒绝**：`dimension` 只接受 `time` / `device_type` /
   `evaluation_metric`（越界 400 并回列可选值）；工具层已按枚举拦截，不要传别的。
10. **`anomaly` 是统计分析自带的可疑报告清单**（如 `low_pass_rate`），不是模型推断；
    需要下钻到具体用例再走 `cases_search`。
11. **写操作不可执行**：生成 / 重生成 / 导出 / 修改 / 发布 / 删除 / 分享 / Studio
    文档写都会得到 `APPROVAL_REQUIRED` 或未开放语义，这不是「平台不支持」。
12. **导出是二进制通道**：`/reports/export` 与 `/reports/statistics/report` 返回
    文件流，工具层不承载；告诉用户在报告中心页面下载，不要尝试用工具取文件内容。

## 验收

回答报告类问题时，逐项自检：

- [ ] 先用 `report_query` 取真实数据，没有凭记忆编造报告 ID、指标名或数值；
- [ ] 每个数字都能对应到返回字段（`summary.*` / `metric_data` /
  `device_stats.metrics` / `case_type_stats` / `cases[].metrics`），没有二次计算；
- [ ] 解释指标时说明了 `unit`、`decimal_places`、`statistic_method`、
  `agg_denominator`、主 / 子维度归属（读 `all_metrics`）；
- [ ] 「生成中」用 `progress.status` 回答，没有把 `draft` 说成生成中；
- [ ] `private` 报告不可见时按「不存在或无权访问」回答，没有泄漏存在性；
- [ ] 涉及写操作 / 导出 / 版本落库时，说明 M1 只读与 M2 审批边界；
- [ ] 字段名与接口一致（snake_case），没有臆造接口、工具或数值。
