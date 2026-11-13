---
name: evaluation-config
description: >-
  评估维度配置口径速查：维度列表与详情、评分口径字段（分值范围 / 单位 / 权重 /
  统计方式 / 聚合分母 / 排除轮次 / 评分规则）、评估分类、可见性、导入导出格式、
  健康检查与重评估前置条件。
  触发词：评估维度、维度配置、评分口径、评分规则、分值范围、分数单位、权重、
  统计方式、聚合分母、排除轮次、评估分类、维度可见性、导入导出维度、
  维度健康检查、重评估条件、重评估前置条件。
  不适用：跑评估、查看评估结果 / 报告指标（report-studio、task-operations 负责）；
  新增 / 修改 / 删除维度、触发重评估（写操作，M2 走提案 + 审批）；算法参数、
  SPL 校准、任务编排等其它配置域。
version: 1.0.0
owner: evaluation-team
allowed-tools:
  - evaluation_query
  - tool_search
permissions:
  - evaluation:read
budgets:
  maxToolCalls: 30
  maxTokens: 50000
---

# evaluation-config

评估维度配置的只读解释入口。本 Skill 只回答「维度/分类现在怎么配的、这些配置
字段是什么口径、要改之前需要满足什么条件」，**不执行任何写操作**。

## 何时用

- 想知道平台有哪些评估维度、某个维度怎么配的；
- 解释「这个维度怎么打分」：分值范围、单位、小数位、权重、统计方式、聚合分母、
  排除轮次、评分规则、输入参数、输出字段；
- 查评估分类及其归属维度；
- 查维度可见性（`shared` / `private`）与归属人；
- 解释维度导入导出的文件格式、健康检查怎么看、重评估需要什么前置条件。

## 何时不用

- 要看某个任务 / 用例的评估**结果或报告指标**：转 `report-studio` / `task-operations`，
  结果数值由报告域接口给出，本 Skill 不计算、不推断；
- 要**修改**维度、分类或触发重评估：M1 只有只读能力，写操作在 M2 走提案 + 审批；
- 要调算法参数、SPL 校准：转 `algorithm-config` / `spl-calibration`。

## 工具用法

唯一业务工具是 `evaluation_query`（只读，权限 `evaluation:read`）：

| action | 作用 | 必填 / 可选参数 | 对应接口 |
|---|---|---|---|
| `dimensions` | 维度列表（分页） | 可选 `category_id`、`search`、`page`、`per_page` | `GET /api/v1/evaluation/dimensions` |
| `dimension` | 维度详情（评分口径 / 参数 / 可见性都在这） | 必填 `dim_id` | `GET /api/v1/evaluation/dimensions/{dim_id}` |
| `categories` | 评估分类列表 | 无 | `GET /api/v1/evaluation/categories` |

规则：

1. 评分口径、可见性、输入输出参数**都从 `dimension` 详情取**，没有单独的「评分接口」；
2. 先用 `dimensions` 定位 `id`（可按 `search` / `category_id` 过滤），再取详情；
3. 回答数字与配置时**引用接口原文**，不四舍五入、不换算、不补默认值；
4. 平台没有的能力（如「让维度重新打分」）明确说「当前阶段不支持 / 需审批」，
   不要臆造工具或接口；需要长尾只读工具时用 `tool_search` 检索。

## 响应形态（与真实接口一致）

列表与分类接口统一信封：

```json
{"success": true, "code": 0, "message": "Success",
 "data": {"items": [], "total": 0, "page": 1, "per_page": 10, "pages": 0}}
```

维度详情直接是 `data` 对象（无 `items` 包裹）。字段缺失就是缺失，不要补 `null`
以外的默认值。

### 维度字段（DimensionItem）

| 字段 | 口径 |
|---|---|
| `id` / `name` / `description` / `keywords` | 维度标识、名称、描述、搜索关键词 |
| `dimension_type` | `main` 主维度 / `sub` 子维度 |
| `parent_dimension_id` | 子维度所属主维度 ID；主维度为 `null` |
| `category_id` | 所属评估分类 ID；可能为 `null`（未归类） |
| `task_type_code` | 评估任务类型码（如 `reject_judge`） |
| `type` | 评估类型原值（如 `auto` / `manual`） |
| `api_url` / `api_endpoints` / `api_settings` / `api_status` | 第三方评估 API 配置与状态（`online` / `offline` 等原值） |
| `score_unit` | 分数单位原值（如 `%`、`ms`、`分`） |
| `result_type` | 结果类型原值整数。代码注释口径为 1 数值 / 2 布尔 / 3 文本；历史数据存在 `0`，按原值回答，不推断含义 |
| `result_min` / `result_max` | 分值下 / 上限 |
| `decimal_places` | 保留小数位 |
| `weight` | 权重（整数） |
| `sort_order` / `estimated_exec_time` | 展示顺序 / 预估执行秒数 |
| `rule` | 评分规则对象（如 `{"rules": [{"condition": ">=", "value": 90, "score": 100}], "defaultScore": 0}`） |
| `statistic_method` | 统计方式原值：`average` / `weighted_wer` / `pass_rate` / `ratio` / `weighted_sum_ratio` 等 |
| `agg_denominator` | 比率分母口径：`case`（按用例）/ `round`（按轮次） |
| `exclude_rounds` | 聚合时排除的轮次编号列表 |
| `required_inputs` | 输入参数列表（见下） |
| `output_fields` | 输出字段列表（见下） |
| `associated_algorithms` | 关联算法列表 |
| `status` | 启用状态（布尔） |
| `visibility` | `shared` / `private`；`private` 仅 owner 与 admin 可见 |
| `created_by_user_id` | 归属人（详情下发；列表可能为 `null`） |
| `created_at` / `updated_at` | ISO 8601 时间 |
| `llm_judge` | 是否 LLM 判分维度的派生布尔（不是结果类型，也不代表可选择模型 / Prompt） |

`required_inputs[]` 关键字段：`param_code`、`param_name`、`label`、`field_type`
（`text` / `number` / `audio` / `boolean` / `json` / `timestamp`）、`required`、
`default_value`、`help_text`、`ui_order`。

`output_fields[]` 关键字段：`param_code`、`param_name`、`label`、`field_path`
（如 `wer` 或 `data.result.wer`）、`field_type`、`output_role`（`main` / `aux`）、
`agg_role`（空 / `value` / `numerator` / `denominator` / `pass_*`）、
`pass_threshold`、`visible_in_report`、`ui_order`。

### 分类字段（CategoryItem）

`id`、`name`、`description`、`icon`、`created_at`、`updated_at`；分类**没有**
`status` / `visibility` 字段，不要假设有。

## 评分口径怎么解释

解释「这个维度怎么打分」时，严格按以下顺序**引用详情原文**，一项都不要自己算：

1. `statistic_method`：怎么聚合（`average` 算术平均；`pass_rate` / `ratio` /
   `weighted_sum_ratio` / `weighted_wer` 为策略聚合，产出通常是百分比）；
2. `agg_denominator`：比率的分母（`case` 按用例 / `round` 按轮次）；
3. `exclude_rounds`：哪些轮次不参与聚合；
4. `result_min` / `result_max` / `decimal_places` / `score_unit`：取值区间、精度、单位；
5. `weight`：维度在总分中的权重；
6. `rule`：规则试算的判定条件与得分；空规则也要原样说明「规则为空」；
7. `output_fields` 的 `agg_role` / `pass_threshold`：分子、分母、达标线怎么取；
8. `required_inputs`：评估需要哪些输入（音频 / 文本 / 布尔等），以及是否必填。

硬规则：

- **只引用、不推导**：接口没给的数值（平均值、通过率、总分）不得用对话里的其他
  数字算出来冒充平台结论；
- 维度配置为空（如 `rule.rules = []`、`required_inputs = []`）就回答「为空」；
- 用户问「为什么这个维度算出来是这样」但只给了结果数值时，说明本 Skill 只解释
  配置口径，结果明细看报告域，不要反推公式。

## 可见性

- `visibility = shared`：所有有 `evaluation:read` 的用户可见；
- `visibility = private`：仅归属人（`created_by_user_id`）与 admin 可见；
  他人的私有维度详情在接口层按 404 / 无权访问收敛，**不要探测或猜测是否存在**；
- 切换可见性是写操作（`evaluation:share` 权限），M1 不执行。

## 导入导出

- **导出（只读）**：`GET /api/v1/evaluation/dimensions/export`，权限
  `evaluation:import_export`；`format=json`（默认，返回维度数组）或
  `format=excel`（xlsx 文件）；`ids` 可传逗号分隔的维度 ID 导出子集。
  JSON 导出字段：`name` / `description` / `dimension_type` / `parent_name` /
  `category_id` / `type` / `api_url` / `result_type` / `weight` / `score_unit` /
  `rule` / `api_settings` / `status`。Excel 列名为中文（名称、描述、维度类型、
  所属主维度、分类ID、类型、Master入口URL、结果类型、权重、分数单位、规则、
  API配置、状态）。
- **导入（写）**：`POST /api/v1/evaluation/dimensions/import`，权限
  `evaluation:import_export`，接受 Excel（`.xlsx` / `.xls`）或 JSON 文件，
  `update_existing=true` 时按名称覆盖已存在维度。M1 不执行，属于 M2 写操作；
  现在只解释文件格式与前置条件。

## 健康检查

- 接口：`GET /api/v1/evaluation/dimensions/{dim_id}/health`（也接受 POST），
  权限 `evaluation:read`；
- 返回 `{"results": [{"url", "status", "status_code", "response_time", "message",
  "error"}], "overall_status": "online"}`；`overall_status` 是接口聚合值；
- 健康探测是对维度 `api_url` 的**实时外呼**，属维护动作；M1 未把它开放为意图
  工具动作。用户要看健康状态时，引导在产品「评估维度」页执行健康探测后读取结果；
  不要凭 `api_status` 字段推断实时健康，也不要把 `api_status=online` 说成探测通过。

## 重评估前置条件

重评估 = 只重算评估结论、不重跑执行。M1 只解释条件，不触发（触发是写操作，
`POST /api/v1/evaluation/task/reevaluate`，权限 `evaluation:execute`，M2 审批后执行）：

1. 任务存在且已执行：范围内必须至少有一个**执行成功**的用例，否则拒绝
   （「执行未成功的用例不参与重评」）；
2. 任务不能已在重评估队列中或正在重评估，同一任务不能重复排队；
3. 要重评的维度必须存在且启用（`status=true`），并与任务/用例的算法口径匹配
   （`task_type_code` / 维度归属）；
4. 按用例选择重评时 `case_ids` 不能为空（`mode=selected` 空集会被拒绝）；
5. 重评估会先把任务状态置为 `reevaluate_queued`，完成后由评估链路回写结果；
6. 重评估只修正评估结论，不修复执行失败；执行失败的用例需要先重跑任务。

## Gotchas

1. **评分口径没有独立接口**：`score_unit` / `result_min` / `result_max` /
   `decimal_places` / `weight` / `statistic_method` / `agg_denominator` /
   `exclude_rounds` / `rule` / `output_fields` 都在维度详情里，别去找
   `/scores` 之类的端点。
2. **列表 `search` 不是 `keyword`**：真实接口参数是 `search`（外加
   `category_id` / `page` / `per_page`），传 `keyword` 不会生效，会静默返回全量。
3. **`result_type` 是原值整数**：0/1/2/3 都可能出现在历史数据里；不要用
   `llm_judge` 代替结果类型，也不要自行把 0 解释成某种类型。
4. **`visibility=private` 的详情可能是 404**：这是防探测的统一口径，不是「维度
   被删了」，回答时说「不存在或无权访问」，不要继续枚举。
5. **分类没有 `status`**：分类只有 `id/name/description/icon/时间`；分类下维度用
   `dimensions?category_id=` 查。
6. **子维度不独立算分**：`dimension_type=sub` 的维度挂在主维度下，主维度承载
   公共输入 / API 配置；解释层级时读 `parent_dimension_id`，不要当成平级维度。
7. **`statistic_method` 与 `score_unit` 是两回事**：统计方式决定聚合算法，单位只是
   展示；策略聚合（`pass_rate` / `ratio` / `weighted_sum_ratio` / `weighted_wer`）
   产出通常是百分比，不要拿 `result_max` 再乘一遍。
8. **健康探测 ≠ `api_status`**：`api_status` 是配置态，实时通断必须看 health 接口
   （M1 由用户在产品页触发）。
9. **M1 写操作不可执行**：维度/分类增删改、可见性切换、导入、触发重评估都会得到
   `APPROVAL_REQUIRED` 或未开放语义，不要把它当成「平台不支持配置」。
10. **字段名用服务端 snake_case**：接口返回即 snake_case，回答用户时保持原字段名，
    不要自己转 camelCase 或改写字段含义。

## 验收

回答评估配置类问题时，逐项自检：

- [ ] 先用 `evaluation_query` 取真实数据，没有凭记忆编造维度名、ID、权重或分值；
- [ ] 评分口径的每一项都能对应到详情里的字段原文（单位、范围、小数位、权重、
      统计方式、分母、排除轮次、规则、输出字段），没有二次计算；
- [ ] 维度 / 分类 / 可见性 / 时间字段名与接口一致（snake_case）；
- [ ] `private` 维度不可见时按「不存在或无权访问」回答，没有泄漏存在性；
- [ ] 提到导入导出 / 健康检查 / 重评估时，说明当前 M1 只读口径与 M2 审批边界；
- [ ] 平台没有的能力明确说「不支持」，没有臆造接口、工具或数值。
