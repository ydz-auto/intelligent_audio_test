---
name: report-studio
description: >-
  报告取数、指标解释与报告交付口径：三类报告（任务 / 对比 / 二次对比）列表与详情、
  指标矩阵、设备与 API 统计、用例明细与用例搜索、维度统计、生成进度、页签计数、
  报告文本（描述 / 分析 / 结论）的起草与版本口径，以及生成 / 重生成报告、
  Studio 草稿与版本恢复、导出 PDF / PPTX / HTML / MD（写操作走提案 + 审批）。
  触发词：报告详情、报告指标、报告列表、报告用例、报告统计、报告进度、页签计数、
  通过率、平均分、指标单位、用例平均值、报告起草、报告版本、导出报告、报告结论、
  生成报告、重生成报告、Studio 草稿、导出 PDF、导出 PPTX、导出 HTML。
  不适用：多报告对比 / 二次对比 / 趋势（report-compare 负责）；任务执行本身
  （task-operations 负责）；评估维度评分口径（evaluation-config 负责）。
version: 1.1.0
owner: report-team
allowed-tools:
  - report_query
  - report_generate
  - report_export
  - tool_search
permissions:
  - report:read
  - report:create
  - report:studio:create
  - report:studio:edit
  - report:studio:undo
  - report:studio:export
budgets:
  maxToolCalls: 40
  maxTokens: 60000
---

# report-studio

报告域的**取数 + 指标解释 + 报告交付**入口：既回答「平台上这份报告现在是什么
数值、字段是什么口径」，也负责把结论交付出去——生成 / 重生成报告、起草 Studio
文档、编辑与版本恢复、导出 PDF / PPTX / HTML / MD。

**写操作一律走「提案 → 审批 → 执行」**：调用写工具只会生成待审批提案
（`APPROVAL_REQUIRED`，零副作用），审批通过后平台才真正执行。不要对用户说
「已经生成 / 已导出」，除非审批后拿到执行结果。

## 何时用

- 查报告列表 / 详情 / 按任务查报告，定位报告 ID；
- 解释报告里的指标：单位、小数位、统计方式、聚合分母、主维度 / 子维度归属；
- 取设备 / API 维度的统计、用例分类统计、标签指标；
- 查某份报告的用例明细、按指标筛出最差用例（异常下钻的第一跳）；
- 查报告统计（按时间 / 设备类型 / 评估维度）、页签计数、生成进度；
- 起草报告文本，把结论落成 Studio 文档并管理版本，导出交付文件。

## 何时不用

- 多份报告并排对比、二次对比、趋势序列：转 `report-compare`；
- 要跑任务 / 重试 / 看任务执行日志：转 `task-operations`；
- 要解释评估维度的评分口径（不是报告数值）：转 `evaluation-config`；
- 要修改 / 发布 / 删除 / 分享报告本身：当前没有对应意图工具，说明边界。

## 工具用法

三个业务工具：`report_query`（只读）、`report_generate`（写）、`report_export`（写）。
写工具同样只接受 Schema 里列出的参数；参数名逐字按本文档。

### 取数：`report_query`（只读，权限 `report:read`）

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

### 写：`report_generate`（生成 / Studio 文档，权限按动作收窄）

| action | 作用 | 必填 | 权限 |
|---|---|---|---|
| `generate` | 按任务生成标准报告 | `task_id`；可选 `body.name` / `body.description` | `report:create` |
| `regenerate` | 重生成任务报告 | `report_id` | `report:create` |
| `studio_draft` | 创建 Studio 文档草稿（版本 1） | `report_id`、`body.markdown_content`；可选 `body.title` / `body.chart_refs` / `body.style_prefs` | `report:studio:create` |
| `studio_edit` | 编辑 Studio 文档生成新版本 | `doc_id`、`body.expected_version`、`body.markdown_content` | `report:studio:edit` |
| `studio_restore` | 历史版本恢复为新版本（不覆盖历史） | `doc_id`、`body.version`、`body.expected_version` | `report:studio:undo` |

### 写：`report_export`（Studio 文档导出，权限 `report:studio:export`）

必填 `format`（`pdf` / `pptx` / `html` / `md`）；`doc_id` 与 `report_id` 二选一
（`doc_id` 优先，`report_id` 自动定位该报告最近更新的 Studio 文档）；可选
`version`（缺省当前版本）、`theme`。

规则：

1. 先用 `list` 定位报告 ID（可用 `keyword` / `status` / `report_type` / `task_id`
   过滤），再取 `detail`；接口返回 `total` / `pages` 判断是否还有下一页。
2. 数值一律**引用接口原文**：`pass_rate` 是接口给的百分比数值，`metric_data` 里
   的 `value` 是接口给的原值，不四舍五入、不换算单位、不跨字段推算。
3. 工具不支持的参数会直接报错（不会静默忽略），不要绕过——参数名逐字按上表。
4. 平台没有的能力明确说「当前没有对应工具 / 需审批」，不臆造工具或接口；
   长尾只读工具先用 `tool_search` 检索。

## 写操作：提案、审批与幂等

1. 调用 `report_generate` / `report_export` → 平台生成**待审批提案**，
   工具结果错误码 `APPROVAL_REQUIRED`，此时**没有任何副作用**；
2. 审批通过后平台按提案参数执行一次；拒绝 / 过期则原样返回失败，不执行；
3. 幂等由平台保证：一次提案对应一次执行，重复投递不会重复执行；
4. 审批人看到的是字段级预览（动作、目标任务 / 报告 / 文档、正文长度、版本、
   格式、影响面）。正文原文在审计的工具参数里，可还原「谁、在哪个会话、
   对哪份报告、做了什么」；
5. 回答用户时：提案阶段说「已提交审批，批准后才会执行」；拿到执行结果后再
   说「已生成 / 已导出」。

## 生成新报告 vs 重生成

- `generate`（按任务生成）：任务已有报告时平台**直接返回已有报告**
  （`data.status = exists`），不会产生第二份；报告正在生成时返回
  `data.status = generating`。用户要「再出一份」时，说明已有报告并给出现有
  报告 ID，不要反复调用 generate（结果永远是同一份）。
- `regenerate`（重生成）：会**软删旧报告**（进回收站，不再是列表里的当前报告）
  并重新计算指标。只有用户明确要「重新生成 / 刷新数据」时才用；回答里要提醒
  旧报告会进回收站。
- 两类动作都只支持**任务报告**（`type=task`）；对比 / 二次对比报告的生成走
  `report-compare` 的只读结论，不在本工具范围内。
- 生成是异步的：`generating` 之后用 `report_query` 的 `progress` 查进度，
  完成后再用 `detail` 取指标；不要自己编造生成结果。

## Studio：取数 → 起草 → 版本 → 导出

链路固定四步，每一步都只做一件可追溯的事：

1. **取数**：`report_query` 的 `detail` / `cases` / `case_averages` 取真实数值，
   记住 `report_id` 与用到的指标名 / 资源名；
2. **起草**：`studio_draft`（`report_id` + 基于上文数值写出的 `markdown_content`）。
   正文里每个数字都要能对回第 1 步的返回字段；正文是 Markdown，
   表格用 `| ... |`，标题用 `# / ##`。同一报告 + 同一操作人 + **完全相同正文**
   再次起草会复用原文档（`reused=true`），不会产生第二份草稿；
3. **版本**：`studio_edit` 必须带当前 `expected_version`（来自 draft / edit 返回的
   `current_version`）。成功返回新版本（`current_version` +1）；`409` 表示他人
   已改动，按返回的 `current_version` 重新取文档后再改，**不要强行覆盖**。
   `studio_restore` 把指定历史版本恢复为**新版本**，历史版本只读不可变；
4. **导出**：`report_export` 固定「文档 + 版本 + 格式」建异步作业；
   产物通过返回的 `download_ref` 鉴权下载。

版本注意事项（OTS 口径）：

- 版本号是单调递增的整数，`expected_version` 是**乐观锁**基准，不是「想改成
  第几版」；写错会 409（不是覆盖）；
- 恢复旧版 ≠ 回滚：恢复也会产生新版本（`snapshot_reason = restore`），历史
  版本链完整保留，可再次恢复；
- 导出必须指定要导的版本（缺省当前版本）；同一版本导出后的产物是确定的，
  重复导出同一版本 + 格式会复用已有作业（`reused=true`），不产生第二个文件；
- 平台报告本身没有历史版本接口（`GET /reports/{id}` 只有当前内容）；
  历史版本只存在于 Studio 文档。

## 导出格式与失败处置

| 格式 | 产物 | 说明 |
|---|---|---|
| `pdf` | A4 PDF | 中文用内置 CID 字体，表格自动分页 |
| `pptx` | 16:9 幻灯片 | 标题页 + 按 `#` / `##` 分节；表格超过 12 行截断并注明 |
| `html` | 单文件 HTML | 受控渲染：正文全部转义、无脚本、无外链资源 |
| `md` | Markdown 原文 | 即文档该版本的正文（不做加工） |

- 返回 `status = done` 才算导出成功，给用户 `download_ref`（需登录态下载）；
- `status = pending / running`：作业还在渲染，**如实告诉用户稍后重试**；
  再用**同一组参数**调用一次 `report_export` 会复用并查询同一作业，
  不要改格式 / 版本重试（那会建新作业）；
- `status = failed`：看返回的 `error`（如「PPTX 渲染依赖缺失」/「版本不存在」），
  按原因处理；修复后同一参数重试会新建作业；
- `404` 提示报告还没有 Studio 文档 → 先 `studio_draft` 起草；
- `403` 说明缺少 `report:studio:export`（或文档不属于当前用户），说明权限
  边界，不枚举文档 ID；
- 平台报告中心的导出（csv / excel / pdf 列表汇总）走页面下载，不在本工具范围。


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
  平台报告本身没有暴露历史版本接口，`GET /api/v1/reports/{id}` 只有当前内容；
- 起草必须基于同一份报告 `detail` 里的数值与用例，写进文本的每个数字都要能对上
  返回字段（写明指标名与资源）；
- 要落库 / 交付时写入 Studio 文档：`studio_draft` 建草稿（版本 1），
  `studio_edit` 带 `expected_version` 生成新版本，`studio_restore` 把历史版本
  恢复为新版本；版本链只追加、不覆盖（见上文「Studio」与「OTS 口径」）；
- 用户要求「保存 / 应用到报告」时，明确说明落到 Studio 文档（附 `doc_id` 与
  `current_version`），不声称改写了平台报告本身。

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
11. **写操作是「提案」不是「已执行」**：`report_generate` / `report_export` 在审批
    前只得到 `APPROVAL_REQUIRED`，此时没有生成报告、没有建文档、没有导出文件。
    把提案说成「已完成」是严重口径错误。
12. **`generate` 已有报告时不会新建**：返回 `data.status = exists`（附已有报告
    ID）；用户想要刷新数据要用 `regenerate`（旧报告进回收站）。
13. **`regenerate` 有破坏性**：软删旧报告后重建；不要在没有用户明确要求时调用。
14. **`expected_version` 是乐观锁**：`studio_edit` / `studio_restore` 版本不一致
    直接 `409` + 当前版本与差异，**不要**重读到新版本后静默重试覆盖他人改动；
    先向用户说明冲突。
15. **导出是异步作业**：`pending` / `running` 不是失败；同一组参数再调一次即
    复用 / 查询同一作业，产物通过 `download_ref` 鉴权下载（工具不返回二进制）。
16. **平台汇总导出不在工具范围**：`/reports/export`（csv / excel / pdf 列表汇总）
    是页面下载通道，工具层不承载；Studio 文档导出走 `report_export`。

## 验收

回答报告类问题时，逐项自检：

- [ ] 先用 `report_query` 取真实数据，没有凭记忆编造报告 ID、指标名或数值；
- [ ] 每个数字都能对应到返回字段（`summary.*` / `metric_data` /
  `device_stats.metrics` / `case_type_stats` / `cases[].metrics`），没有二次计算；
- [ ] 解释指标时说明了 `unit`、`decimal_places`、`statistic_method`、
  `agg_denominator`、主 / 子维度归属（读 `all_metrics`）；
- [ ] 「生成中」用 `progress.status` 回答，没有把 `draft` 说成生成中；
- [ ] `private` 报告不可见时按「不存在或无权访问」回答，没有泄漏存在性；
- [ ] 写操作如实区分「已提交审批」与「审批后已执行」，没有把提案说成完成；
- [ ] 生成 / 重生成的差异说清楚了（exists 复用 vs 软删重建）；
- [ ] 起草正文的每个数字都能回溯到 `report_query` 的返回字段；
- [ ] Studio 编辑带 `expected_version`，409 时说明冲突而不是覆盖；
- [ ] 导出说明了格式、版本与作业状态（done / pending / failed），给了
  `download_ref`，没有谎报产物已可用；
- [ ] 字段名与接口一致（snake_case），没有臆造接口、工具或数值。
