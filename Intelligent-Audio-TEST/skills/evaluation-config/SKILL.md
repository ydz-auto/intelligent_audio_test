---
name: evaluation-config
description: >-
  评估维度配置口径速查与写操作入口：维度列表与详情、评分口径字段（分值范围 /
  单位 / 权重 / 统计方式 / 聚合分母 / 排除轮次 / 评分规则）、评估分类、可见性、
  导入导出格式、健康检查与重评估前置条件；新增 / 修改 / 删除维度、新建 / 修改 /
  删除分类、切换维度可见性、触发重评估走提案 + 审批。
  触发词：评估维度、维度配置、评分口径、评分规则、分值范围、分数单位、权重、
  统计方式、聚合分母、排除轮次、评估分类、维度可见性、导入导出维度、
  维度健康检查、重评估条件、重评估前置条件、新增维度、修改维度、删除维度、
  新建评估分类、改分类、切换维度可见性、触发重评估。
  不适用：跑评估、查看评估结果 / 报告指标（report-studio、task-operations 负责）；
  算法参数、SPL 校准、任务编排等其它配置域。
version: 1.1.0
owner: evaluation-team
allowed-tools:
  - evaluation_query
  - evaluation_manage
  - tool_search
permissions:
  - evaluation:read
budgets:
  maxToolCalls: 30
  maxTokens: 50000
---

# evaluation-config

评估维度配置的只读解释入口与写操作入口。读侧回答「维度/分类现在怎么配的、
这些配置字段是什么口径」；写侧执行维度 / 分类 CRUD、维度可见性切换与触发重评估，
**一律走提案 → 审批 → 执行，审批前不产生任何副作用**。

## 何时用

- 想知道平台有哪些评估维度、某个维度怎么配的；
- 解释「这个维度怎么打分」：分值范围、单位、小数位、权重、统计方式、聚合分母、
  排除轮次、评分规则、输入参数、输出字段；
- 查评估分类及其归属维度；
- 查维度可见性（`shared` / `private`）与归属人；
- 解释维度导入导出的文件格式、健康检查怎么看、重评估需要什么前置条件；
- 要**改**维度 / 分类（新增、修改、删除、切可见性）或触发重评估：用
  `evaluation_manage` 发起提案，由用户审批后执行（见「写操作」一节）。

## 何时不用

- 要看某个任务 / 用例的评估**结果或报告指标**：转 `report-studio` / `task-operations`，
  结果数值由报告域接口给出，本 Skill 不计算、不推断；
- 要导入 / 导出维度文件（`.xlsx` / `.json`）：导入导出有独立权限
  `evaluation:import_export`，本 Skill 只解释格式，不发起文件上传；
- 要调算法参数、SPL 校准：转 `algorithm-config` / `spl-calibration`。

## 工具用法

读侧唯一业务工具是 `evaluation_query`（只读，权限 `evaluation:read`）：

| action | 作用 | 必填 / 可选参数 | 对应接口 |
|---|---|---|---|
| `dimensions` | 维度列表（分页） | 可选 `category_id`、`search`、`page`、`per_page` | `GET /api/v1/evaluation/dimensions` |
| `dimension` | 维度详情（评分口径 / 参数 / 可见性都在这） | 必填 `dim_id` | `GET /api/v1/evaluation/dimensions/{dim_id}` |
| `categories` | 评估分类列表 | 无 | `GET /api/v1/evaluation/categories` |

写侧唯一业务工具是 `evaluation_manage`（WRITE，动作级权限见下表）：先提案、
用户审批通过后才执行。**不要**用 `tool_search` 找 `evaluation_*` 的 MCP 写工具
代替本工具——同一路由，但会绕过本工具的动作级权限收窄与 body 字段白名单。

| action | 作用 | 必填参数 | 权限 | 接口 |
|---|---|---|---|---|
| `dimension_create` | 新建维度 | `body`（至少 `name`） | `evaluation:dim_manage` | `POST /api/v1/evaluation/dimensions` |
| `dimension_update` | 修改维度 | `dim_id` + `body` | `evaluation:dim_manage` | `PUT /api/v1/evaluation/dimensions/{dim_id}` |
| `dimension_delete` | 删除维度（级联软删子维度） | `dim_id` | `evaluation:dim_manage` | `DELETE /api/v1/evaluation/dimensions/{dim_id}` |
| `dimension_visibility` | 切换维度可见性 | `dim_id` + `visibility`（`shared` / `private`） | `evaluation:share` | `PATCH /api/v1/evaluation/dimensions/{dim_id}/visibility` |
| `category_create` | 新建分类 | `body`（至少 `name`） | `evaluation:category_manage` | `POST /api/v1/evaluation/categories` |
| `category_update` | 修改分类 | `cat_id` + `body` | `evaluation:category_manage` | `PUT /api/v1/evaluation/categories/{cat_id}` |
| `category_delete` | 删除分类（软删） | `cat_id` | `evaluation:category_manage` | `DELETE /api/v1/evaluation/categories/{cat_id}` |
| `reevaluate` | 触发任务重新评估 | `body.task_id`（必填）、`body.mode` / `body.case_ids` / `body.dimension_ids` / `body.reevaluate_type` 可选 | `evaluation:execute` | `POST /api/v1/evaluation/task/reevaluate` |

`body` 只收接口真实字段（维度字段见下方字段表；分类只有
`name` / `description` / `icon` / `visibility`；重评估是
`task_id` / `reevaluate_type` / `reextract_device_output` / `case_ids` /
`dimension_ids` / `mode`）。传了接口不认识的字段会被工具层直接拒绝，
不会「看起来成功但没生效」。

规则：

1. 评分口径、可见性、输入输出参数**都从 `dimension` 详情取**，没有单独的「评分接口」；
2. 先用 `dimensions` 定位 `id`（可按 `search` / `category_id` 过滤），再取详情；
   写之前先读：改 / 删要用真实 `id` 与当前字段，禁止凭对话猜 ID；
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

`id`、`name`、`description`、`icon`、`created_at`、`updated_at`；分类**响应**没有
`status` / `visibility` 字段，不要假设有（写入时可传 `visibility=shared|private`，
用于归属与可见性校验，但列表 / 详情不回显该字段）。

## 写操作：提案 → 审批 → 执行

所有写动作都遵守同一条链，模型不得跳步：

1. **提案**：调用 `evaluation_manage`。工具层先做参数校验（动作级必填、
   `body` 字段白名单、枚举取值、每次调用按 `action` 收窄权限）。校验通过后
   生成一条待审批提案（`agent_approval`），**此时没有任何副作用**，工具返回
   `APPROVAL_REQUIRED` 与 `approval_id`；run 进入 `WAITING_APPROVAL`。
2. **审批**：用户在审批卡上看到字段级 diff（目标对象、变更字段、可见性、
   重评估范围、软删语义），选择批准 / 拒绝。提案有 TTL，过期按「未执行」结算。
3. **执行**：只有批准后才回源网关。执行前重新校验权限与实时注册状态
   （审批期间权限被收回 → `PERMISSION_DENIED`，不执行）；同一提案重复结算 /
   重复投递只执行一次（幂等键 = run + step + tool_call_id + 工具 + 参数哈希）。

模型侧的汇报口径：提案阶段说「已提交审批，等待确认」，**不要说「已创建 /
已修改 / 已删除」**；拿到 `APPROVAL_REJECTED` / `APPROVAL_EXPIRED` 说
「未执行」；只有执行返回成功后才说「已完成」。

### 修改影响面（写入前必须讲清）

- **维度新增 / 修改**：影响评分口径与后续评估（`weight` 参与总分、`rule` 决定
  得分、`statistic_method` / `agg_denominator` / `exclude_rounds` 决定聚合）。
  改已启用维度不会自动重算历史结果，需要时另行触发重评估。
- **维度删除**：级联**软删**子维度及从属输入 / 输出参数、算法映射与关联；
  已产生的评估结果不自动回滚。主维度下挂子维度时，删主维度会连带删除子维度。
  对已软删的维度再次删除是**幂等成功**（不会二次删除），不必重试也不必报错。
- **分类删除**：**软删**（`deleted=true` 与 `deleted_at`），分类下维度不级联删除，
  会变成未归类（`category_id` 仍指向被删分类，查询时按接口返回原值说明）；
  对已软删的分类再次删除返回「未找到分类」（网关 400 + code 404）。
- **可见性切换**：`private` 后仅归属人与 admin 可见，其他用户按「不存在或无权
  访问」收敛；`shared` 恢复全员可见。切换不改归属人。
- **导入 / 导出**：不走本工具（独立权限 `evaluation:import_export`），本 Skill
  只解释格式（见「导入导出」）。
- 删除类动作在审批口径上是**单条审批**（§9.4），不会被批量预授权吞掉。

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
- 切换可见性是写操作（`evaluation:share` 权限），用
  `evaluation_manage` 的 `dimension_visibility` 动作；私人资源仍受
  owner 校验（非 owner 的 admin 除外）。

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
  `update_existing=true` 时按名称覆盖已存在维度。本工具链**不承载文件上传**
  （`evaluation_manage` 只收 JSON body），导入 / 导出请引导用户在产品
  「评估维度」页操作；这里只解释文件格式与前置条件。

## 健康检查

- 接口：`GET /api/v1/evaluation/dimensions/{dim_id}/health`（也接受 POST），
  权限 `evaluation:read`；
- 返回 `{"results": [{"url", "status", "status_code", "response_time", "message",
  "error"}], "overall_status": "online"}`；`overall_status` 是接口聚合值；
- 健康探测是对维度 `api_url` 的**实时外呼**，属维护动作；未把它开放为意图
  工具动作。用户要看健康状态时，引导在产品「评估维度」页执行健康探测后读取结果；
  不要凭 `api_status` 字段推断实时健康，也不要把 `api_status=online` 说成探测通过。

## 重评估（写操作）

重评估 = 只重算评估结论、不重跑执行。用 `evaluation_manage` 的 `reevaluate`
动作发起（权限 `evaluation:execute`，提案 + 审批后执行，
`POST /api/v1/evaluation/task/reevaluate`）。

前置条件（重评估前置条件共 6 条，后端逐条校验，失败信息原样转述给用户，
不要自己编原因）：

1. 任务存在且已执行：范围内必须至少有一个**执行成功**的用例，否则拒绝
   （「执行未成功的用例不参与重评」）；任务状态须是已完成 / 失败 / 停止 /
   暂停 / 跳过之一；
2. 任务不能已在重评估队列中或正在重评估，同一任务不能重复排队
   （「任务已在重新评估队列中」/「任务正在重新评估中」——这是去重成功，
   不是失败，不要重试）；
3. 要重评的维度必须存在且启用（`status=true`），并与任务/用例的算法口径匹配
   （`task_type_code` / 维度归属）；
4. 按用例选择重评时（`mode=selected`）`case_ids` 不能为空，空集会被拒绝，
   不要退化成整任务全量；
5. 重评估会先把任务状态置为 `reevaluate_queued`，完成后由评估链路回写结果；
6. 重评估只修正评估结论，不修复执行失败；执行失败的用例需要先重跑任务。

可取消 / 可追溯：

- **审批前**：提案被拒绝、过期或 run 被取消 → 不执行，无副作用；
  审批记录里保留了完整入参，可回答「谁在什么时候申请重评了什么」。
- **提交后**：重评在评估服务的任务队列里执行；要中止请停止任务
  （任务域的停止动作会联动取消该任务在途评估），不要重复发起重评来「覆盖」。
- **可追溯**：每次写调用都有 `agent_tool_call` 审计（工具、参数哈希、权限决策、
  结果码、耗时）与 `tool_call` / `tool_result` 事件；回答「有没有提交过」时
  以审计与任务状态为准，不凭对话记忆。

## 失败处置

写操作失败时按错误码分流，不猜测、不自动重试：

| 结果 | 含义 | 处置 |
|---|---|---|
| `APPROVAL_REQUIRED` | 已提案、等待审批 | 告知用户去审批卡确认；**不要**重复调用工具 |
| `APPROVAL_REJECTED` / `APPROVAL_EXPIRED` | 审批被拒 / 过期 | 说明「未执行、无副作用」；需要时重新发起提案并说明原因 |
| `PERMISSION_DENIED` | 当前用户无该动作权限（或审批后权限被收回） | 说明缺哪个权限码；不要换工具绕过 |
| `INVALID_ARGUMENTS` | 参数 / body 字段 / 枚举不合法 | 按提示修正后重新提案；不要删掉字段硬试 |
| `UPSTREAM_ERROR`（含 400 / 409 业务拒绝） | 网关业务规则拒绝（重名、重复重评、未找到等） | 原样转述上游文案，按文案引导；重名就换名，重复重评就说「已在队列」 |
| `UPSTREAM_UNAVAILABLE` | 目标服务不可用 | 说明暂不可用，建议稍后重试；不要反复重试烧预算 |

「删除」是软删：删除后列表不再返回，但审计与历史结果仍可追溯；不要承诺
物理删除或级联删历史评估结果。

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
6. **子维度不单独发请求，但与主维度同批计算、各有输出字段与评分记录**：`dimension_type=sub` 的维度挂在主维度下，主维度承载
   公共输入 / API 配置；解释层级时读 `parent_dimension_id`，不要当成平级维度。
7. **`statistic_method` 与 `score_unit` 是两回事**：统计方式决定聚合算法，单位只是
   展示；策略聚合（`pass_rate` / `ratio` / `weighted_sum_ratio` / `weighted_wer`）
   产出通常是百分比，不要拿 `result_max` 再乘一遍。
8. **健康探测 ≠ `api_status`**：`api_status` 是配置态，实时通断必须看 health 接口
   （由用户在产品页触发）。
9. **写操作没有「直接执行」**：`evaluation_manage` 的调用点只会生成提案并返回
   `APPROVAL_REQUIRED`；报「已创建 / 已修改 / 已删除」之前必须有执行成功的结果，
   提案阶段的正确说法是「已提交审批」。没有对应权限码时是 `PERMISSION_DENIED`，
   不要用 `tool_search` 找 MCP 写工具代替 `evaluation_manage`（会丢字段白名单）。
10. **重名与重复重评是业务拒绝**：维度 / 分类重名返回 400，重评估重复排队返回
    400；两类都是「没做成但无副作用」，不要重试，按上游文案回答。
11. **字段名用服务端 snake_case**：接口返回即 snake_case，回答用户时保持原字段名，
    不要自己转 camelCase 或改写字段含义。

## 验收

回答评估配置类问题时，逐项自检：

- [ ] 先用 `evaluation_query` 取真实数据，没有凭记忆编造维度名、ID、权重或分值；
- [ ] 评分口径的每一项都能对应到详情里的字段原文（单位、范围、小数位、权重、
      统计方式、分母、排除轮次、规则、输出字段），没有二次计算；
- [ ] 维度 / 分类 / 可见性 / 时间字段名与接口一致（snake_case）；
- [ ] `private` 维度不可见时按「不存在或无权访问」回答，没有泄漏存在性；
- [ ] 写操作先说明「提交审批」、拿到执行结果后才说「已完成」，没有把提案当成
      已执行；失败按「失败处置」表转述，没有自动重试或换工具绕过；
- [ ] 讲修改影响面时说清软删、级联、可见性与重评估边界；
- [ ] 平台没有的能力（导入导出文件、健康探测触发）明确说「在产品页操作 / 不支持」，
      没有臆造接口、工具或数值。
