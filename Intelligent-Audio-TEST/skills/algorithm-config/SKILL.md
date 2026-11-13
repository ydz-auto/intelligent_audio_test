---
name: algorithm-config
description: >-
  算法配置域的查询与写操作入口：算法定义（状态、分组、草稿）、设备与 API 参数
  （含三层解析）、参考参数、参数映射、用例专属参数、表单 Schema 与下拉选项、
  算法关联的评估维度，以及热重载的前置条件；新建 / 修改 / 删除算法定义、参数、
  参考参数、映射、导入算法定义与热重载走提案 + 审批。
  触发词：算法定义、算法参数、参考参数、参数映射、参数列表、表单 Schema、表单字段、
  算法选项、算法下拉、算法分组、算法配置、算法维度、设备参数、API 参数、用例参数、
  热重载前提、改算法参数、新增算法参数、删除算法参数、改设备参数、改 API 参数、
  改参数映射、新增映射、删除映射、改参考参数、新增参考参数、删除参考参数、
  改算法定义、新增算法定义、删除算法定义、导入算法定义、热重载、重载算法配置、
  算法配置回滚、参数变更风险。
  不适用：报告与指标取数 / 导出（report-studio、report-compare）、评估维度与分类的
  配置（evaluation-config）、音频导入与标注（audio-import）、SPL 校准
  （spl-calibration）；算法计算本身的数值结论（WER / MOS / 准确率）由报告与评估
  服务给出，本 Skill 不计算、不估算。
version: 1.1.0
owner: algorithm-team
allowed-tools:
  - algorithm_query
  - algorithm_manage
  - tool_search
permissions:
  - algorithm:read
  - algorithm:definition_manage
  - algorithm:param_manage
budgets:
  maxToolCalls: 40
  maxTokens: 40000
---

# algorithm-config

算法配置域的入口：查什么、字段叫什么、默认值从哪来、为什么改了不生效，
以及怎么安全地改（一律提案 → 审批 → 执行，审批前不产生任何副作用）。
所有事实来自 `algorithm_query` / `algorithm_manage` 调用的真实接口返回。

## 何时用

- 想知道平台有哪些算法定义、某个定义的状态 / 分组 / 版本；
- 要读算法参数、参考参数、用例专属参数、参数映射，或解释「参数从哪一层来」；
- 要看某个算法的表单字段、字段类型、**默认值**、组件、校验规则；
- 要取算法下拉选项（判断某个 `algorithm_type` 是否真实存在）；
- 要查算法关联的评估维度、维度参数；
- 要解释热重载什么时候需要、前置条件是什么；
- 要新建 / 修改 / 删除算法定义、参数、参考参数、映射，导入算法定义或执行热重载
  （走 `algorithm_manage` 的提案 + 审批，见「写操作」一节）。

## 何时不用

- 报告 / 指标 / 趋势 / 导出：走 `report-studio` / `report-compare`；
- 评估维度的增删改与分类：走 `evaluation-config`；
- 音频导入、标注、元数据：走 `audio-import`；
- SPL 映射与校准：走 `spl-calibration`；
- 算法分组 / 用例专属参数 / 评估维度关联的增删改：本工具不收（产品页维护），
  不要改用别的写接口绕过审批。

## 查询动作

`algorithm_query` 的 `action` 与真实接口一一对应（全部只读，权限 `algorithm:read`）：

| action | 目标接口 | 返回形态（要点） |
|---|---|---|
| `definitions` | `GET /api/v1/algorithm/definitions` | `{items,total,page,per_page,pages}`；行里算法类型字段是 `type`，状态是 `status`（`online`/`offline`/`draft`） |
| `definition` | `GET /api/v1/algorithm/definitions/{algo_type}` | 单个定义 + 子实体（device_params / api_params / reference_params / dimension_relations） |
| `definition_draft` | `GET /api/v1/algorithm/definitions/draft/{algo_type}` | 编辑草稿快照；没有草稿时 `data` 为空对象 |
| `groups` / `group` | `GET /api/v1/algorithm/groups[/{group_id}]` | 分组列表 / 详情 |
| `params` | `GET /api/v1/algorithm/params` | 见下方「参数的三层作用域」，两种形态不同 |
| `param` | `GET /api/v1/algorithm/params/{param_id}` | 单行参数详情 |
| `reference_params` | `GET /api/v1/algorithm/reference-params` | **必须带 `algorithm_type`**，否则接口 400 |
| `reference_param` | `GET /api/v1/algorithm/reference-params/{param_id}` | 单行参考参数 |
| `mappings` | `GET /api/v1/algorithm/mappings` | 算法级返回分页信封；带 `device_id` / `api_id` 时返回裸数组 |
| `case_params` / `case_param` | `GET /api/v1/algorithm/case-params[/{id}]` | 用例专属参数（含 `scope`，如 `physical` / `common`） |
| `form_schema` | `GET /api/v1/algorithm/form-schema/{algo_type}` | 见下方「表单 Schema」 |
| `options` | `GET /api/v1/algorithm/options` | `{algorithms:[{value,name,group_id,group_name,icon}]}` |
| `dimensions` | `GET /api/v1/algorithm/dimensions/{algo_type}` | `{dimensions:[...],dimension_ids,default_dimension_id,weights}` |
| `dimension_params` | `GET /api/v1/algorithm/dimension-params/{dimension_id}` | `{params:[...]}`，参数同时给 `code` 与 `param_code` |

## 参数的三层作用域

设备参数按「算法级默认 → 设备绑定策略 → 本设备覆盖」三层解析，入口都是
`action=params`，用 `param_type` / `device_id` / `api_id` 区分：

- **不带 `device_id`**：返回算法级原始行 + 分页信封，行字段是
  `param_code` / `param_name` / `param_type` / `validation` / `default_value`；
- **带 `device_id` + `algorithm_type`**（`param_type` 必须为 `device`）：返回**裸数组**，
  行字段改为 `code` / `name` / `type` / `validation_rules`，并额外带
  `resolved_from`（本值来自哪一层）与 `profile_param_id`；
- **`param_type=api`**：必须带 `api_id`，只返回该 API 实例的字段声明行。
  `api_id` 只在 `param_type=api` 时生效：不带 `param_type`（缺省 `device`）时
  接口静默忽略 `api_id`，返回的是算法级原始行，不是 API 作用域结果。

同一个概念在两种形态里字段名不同，回答时按当前形态取，不要混用；
缺哪一层就照实说「该层没有覆盖」，不要用算法级默认值冒充设备生效值。

## 表单 Schema

`action=form_schema` 返回**camelCase** 的前端表单契约（与参数接口的 snake_case 不同）：

```json
{"algorithmType": "...", "algorithmName": "...", "description": "...",
 "groups": [{"name": "basic", "label": "基础参数",
             "fields": [{"fieldCode": "...", "fieldName": "...", "fieldType": "text",
                         "required": false, "defaultValue": 0, "component": "input",
                         "helpText": "...", "hidden": false, "uiOrder": 0,
                         "scope": "common"}]}]}
```

- `groups` 是**数组**，每组的字段在 `fields` 里；
- `defaultValue` 原样来自配置：可能是 `null`、`0`、`{}`、字符串；
  **null 就是没有默认值**，不要补 0、不要从 `helpText` 猜单位或取值；
- `component` 由 `fieldType` 映射（`select` / `input` / `textarea` / `input-number` /
  `switch` / `code-editor` / `slider`），是前端渲染提示，不是业务枚举；
- 表单里的可选项在 `options` 字段，**接口没给就是没有**，不要自己列候选值。

## 定义状态与草稿

- 状态接口值是 `online`（上线）/ `offline`（下线）/ `draft`（草稿）；
  筛选时用 `status` 参数，不要用 `active` 之类的领域枚举名。
- 草稿是编辑器约 30 秒一次的快照，**不落正式配置表、不参与执行**；
  新建 / 更新 / 全量保存成功后会清掉该类型的草稿。
  用户问「改了为什么没生效」时，先确认是不是只存了草稿、没有发布。

## 写操作：提案 → 审批 → 执行

写侧唯一业务工具是 `algorithm_manage`（WRITE，动作级权限见下表）：
先提案、用户审批通过后才执行，审批前不产生任何副作用。
**不要**用 `tool_search` 找 `algorithm_*` 的 MCP 写工具代替它
（会绕过参数白名单与动作级权限）。

### 动作表（与网关真实路由逐条对应）

| action | 目标接口 | 权限 | 风险 |
|---|---|---|---|
| `definition_create` | `POST /api/v1/algorithm/definitions`（body: type / name 必填） | `algorithm:definition_manage` | WRITE |
| `definition_update` | `PUT /api/v1/algorithm/definitions/{algo_type}` | `algorithm:definition_manage` | WRITE |
| `definition_save` | `PUT /api/v1/algorithm/definitions/save`（全量保存，乐观锁） | `algorithm:definition_manage` | WRITE |
| `definition_delete` | `DELETE /api/v1/algorithm/definitions/{algo_type}`（软删） | `algorithm:definition_manage` | **DESTRUCTIVE** |
| `param_create` | `POST /api/v1/algorithm/params`（设备 / API 作用域） | `algorithm:param_manage` | WRITE |
| `param_update` | `PUT /api/v1/algorithm/params/{param_id}` | `algorithm:param_manage` | WRITE |
| `param_delete` | `DELETE /api/v1/algorithm/params/{param_id}`（软删） | `algorithm:param_manage` | **DESTRUCTIVE** |
| `reference_param_create` | `POST /api/v1/algorithm/reference-params` | `algorithm:param_manage` | WRITE |
| `reference_param_update` | `PUT /api/v1/algorithm/reference-params/{param_id}` | `algorithm:param_manage` | WRITE |
| `reference_param_delete` | `DELETE /api/v1/algorithm/reference-params/{param_id}`（软删） | `algorithm:param_manage` | **DESTRUCTIVE** |
| `mapping_create` | `POST /api/v1/algorithm/mappings` | `algorithm:param_manage` | WRITE |
| `mapping_update` | `PUT /api/v1/algorithm/mappings/{mapping_id}` | `algorithm:param_manage` | WRITE |
| `mapping_delete` | `DELETE /api/v1/algorithm/mappings/{mapping_id}`（软删） | `algorithm:param_manage` | **DESTRUCTIVE** |
| `import` | `POST /api/v1/algorithm/import`（body: algorithms 数组） | `algorithm:definition_manage` | WRITE |
| `reload` | `POST /api/v1/algorithm/reload`（热重载） | `algorithm:definition_manage` | WRITE |

写入前先读：改 / 删要用 `algorithm_query` 查到的真实 ID 与当前值，禁止凭对话猜。

### 写之前必须讲清的影响面

- **定义的 create / update**：影响该 `algorithm_type` 下的参数、映射与执行配置。
  `status` 只认 `online` / `offline` / `draft`；`draft` 状态的定义不参与执行。
- **`definition_save`（全量保存）**：定义与子实体同事务落库，是产品编辑页的发布
  路径。更新已存在的定义（body 带 `id`）**必须带 `expected_updated_at`**（取自
  定义详情 `updated_at`），并发写会返回 `CONFLICT`，**不会静默覆盖**；冲突时
  让用户刷新后重新确认变更，不要换一个「不带版本」的写法硬写。
- **`definition_delete`**：只软删定义行；参数 / 映射 / 参考参数行不会随之删除。
  删除后该算法类型立即从定义列表与下拉选项消失，引用它的 API / 任务不再能取到
  配置。
- **参数变更风险**：参数是执行引擎的输入契约（`param_code` / `param_type` /
  `direction` / `required` / `default_value`）。改 `param_code`、`param_type`、
  `direction` 会让已配置该参数的 API / 设备 / 用例参数失去对应关系；改
  `required` / `default_value` 会改变未显式填值时的执行结果。**这些字段必改时，
  先说明影响对象并要求确认**。
- **参数作用域**：`param_create` 必须明确作用域 —— 设备参数用
  `param_type_source=device`（可选 `device_id` 做该设备覆盖），API 参数用
  `param_type_source=api` 且**必须带 `api_id`**（API 实例作用域；算法类型级 API
  默认层已废弃）。两种作用域字段互斥，混传会被工具层拒绝。
- **参数更新**：只改本行，不允许借更新搬移作用域 / 归属（`device_id` / `api_id` /
  `algorithm_type` 不在可写字段里）；更新路径不生效的字段（如 `options_source`
  等选项来源字段）会被工具层拒绝，不会「看起来改了」。
- **参考参数**：改动影响评估时标注数据的取值（`code` / `type` /
  `annotation_code` / `field_path` / `merge_mode`）。`code` 是判重键（同算法下
  唯一），改 `code` 等于换一个参数，引用方需要同步。
- **映射变更风险**：映射决定「算法输出字段 → 评估维度参数」的取值链
  （`source_type` / `source_param` / `source_direction` / `dimension_id` /
  `target_param` / `transform_type`）。改映射会直接改变评估结果口径；历史报告的
  数值不会自动重算，需要时另行重评估或重跑。`source_type` 只认
  `case` / `reference` / `device` / `api`；`source_type=api` 必须带 `api_id`。
- **删除**：定义 / 参数 / 参考参数 / 映射都是**软删**（不进回收站、工具也不提供
  恢复）。删除动作在审批单里记为破坏性（`DESTRUCTIVE`）并标出目标 ID 与软删
  语义，审批人确认后才执行；删除前先说清「哪些 API / 设备 / 用例在用」。

### 审批链与汇报口径

1. **提案**：调用 `algorithm_manage`。工具层先做动作级校验（必填、body 字段
   白名单、枚举、权限收窄），通过后生成待审批提案（`agent_approval`），
   **此时没有任何副作用**，工具返回 `APPROVAL_REQUIRED` 与 `approval_id`，
   run 进入 `WAITING_APPROVAL`。
2. **审批**：审批卡展示字段级 diff（动作 / 目标表 / 目标 ID / 变更字段 /
   子实体条数 / 软删或热重载的影响面），删除动作标为破坏性。提案有 TTL，
   过期按「未执行」结算。
3. **执行**：批准后才回源网关。执行前重新校验权限与实时注册状态；同一提案
   重复结算 / 重复投递只执行一次（幂等键 = run + step + tool_call_id + 工具 +
   参数哈希）。

模型侧汇报口径：提案阶段说「已提交审批，等待确认」，**不要说「已创建 /
已修改 / 已删除」**；拿到 `APPROVAL_REJECTED` / `APPROVAL_EXPIRED` 说「未执行」；
只有执行返回成功后才说「已完成」。

## 导入（写操作）

`import` 的 body 是 `{"algorithms": [{"type": "...", "name": "...",
"params": [...]}]}`：

- **只增不改**：已存在的 `type` 不会按导入载荷更新（保留原定义）；新 `type`
  会创建定义；
- 每个条目必须有 `type`（缺了服务端会静默跳过，工具层提前拒绝）；
- `params` 按设备参数追加，重复导入同一批参数可能撞唯一约束而整批失败 ——
  **失败不要盲目重试**，先查现有参数；
- 返回 `imported` 是「处理过的算法类型」列表，不是「新建数量」；如实转述。

## 热重载（写操作）

热重载 = `POST /api/v1/algorithm/reload`，`algorithm_manage` 的 `reload` 动作，
权限 `algorithm:definition_manage`，提案 + 审批后执行。

1. **前置条件**：变更必须先**发布**（create / update / 全量保存），草稿不在生效
   范围内；重载从数据库重建算法配置缓存并广播失效给其它进程。
2. **幂等**：重载只重建缓存、**不改任何配置数据**，可重复执行且结果一致；
   同一审批提案重复投递也只执行一次。
3. **失败不静默**：重建异常时服务层返回失败 / 异常，工具如实返回
   `UPSTREAM_ERROR`，不要把它说成「已生效」。
4. **不是保存的替代**：写操作本身已触发缓存失效，重载用于手动恢复或跨进程对齐；
   重载不校验业务规则、不改数据，参数不合法要回到写侧改，重载救不了。

## 回滚（参数变更历史）

- 设备 / API 作用域的参数与映射改动会写参数版本快照；
  `GET /api/v1/algorithm/param-history?scope=&scope_id=&algorithm_type=`
  查看历史，`POST /api/v1/algorithm/param-history/{history_id}/restore`
  恢复某一版。**这两个动作本工具未开放**，需要回滚时引导用户在产品页操作，
  或按历史值发起一条新的 `param_update` / `mapping_update` 提案。
- 删除是软删，但没有恢复入口：重新建等价的定义 / 参数 / 映射即可，注意
  `code` 与作用域要和原来一致。
- 热重载不改变配置数据，回滚它不是回滚手段。

## Gotchas

1. **定义列表的类型字段是 `type`**，不是 `algorithm_type`；参数 / 映射行才用 `algorithm_type`。
   定义列表的过滤只认 `status` / `group_id`，传 `algorithm_type` 会被接口静默忽略，
   需要按类型筛选请对返回行自行过滤。
2. **带 `device_id` 的参数、映射返回裸数组**，不是 `{items,...}` 信封，且字段名改成
   `code` / `name` / `type` / `validation_rules`。
3. **参考参数必须带 `algorithm_type`**：不带直接 400，这不是「列表为空」。
4. **表单 Schema 是 camelCase**（`fieldCode` / `defaultValue`），参数接口是 snake_case
   （`param_code` / `default_value`）；同一概念两套拼写，跨接口对比时先对齐。
5. **`param_type=api` 必须带 `api_id`**；`api_id` 只在 `param_type=api` 时生效，
   否则接口静默忽略它。`device_id` 只对 `param_type=device` 生效，
   且必须同时给 `algorithm_type`，否则 400。
6. **不要编造 `algorithm_type`**：合法取值只看 `action=options` 的返回；
   没出现的类型就是不存在，不要按名字猜（`asr` / `tts` 之类不保证存在）。
7. **状态是 `online` / `offline` / `draft`**：领域枚举名 `ACTIVE` / `DEPRECATED` 不是接口值。
8. **默认值不补齐**：`default_value` / `defaultValue` 为 `null` 就是没有默认值；
   不要用 0、空字符串或估算值填充。
9. **权限码是 `资源:操作`**：读是 `algorithm:read`；写侧按资源细分
   `algorithm:definition_manage` / `algorithm:param_manage` /
   `algorithm:case_param_manage` / `algorithm:group_manage`，没有笼统的算法写权限码。
10. **写操作只走 `algorithm_manage`，且必须先提案**：调用后拿到的是
    `APPROVAL_REQUIRED`（已提案、等待审批），不是「已生效」；没有审批凭据的
    直接调用会被网关拒绝。不要用 `tool_search` 找 `algorithm_*` 的 MCP 写工具
    绕开动作白名单与动作级权限。
11. **热重载不等于发布**：`reload` 只重建缓存，不校验业务规则、不改数据；
    草稿不会因为重载生效。

## 验收

回答算法配置类问题前逐项自检：

- [ ] 结论里的每个算法定义 / 参数 / 映射都来自 `algorithm_query` 的真实返回，并带上 ID 或 code；
- [ ] 参数的层（算法级 / 设备策略 / 设备覆盖 / API 实例）说清楚，没有把某层值说成最终生效值；
- [ ] `defaultValue` / `default_value` 原样引用，`null` 就说没有默认值，没有补数；
- [ ] `algorithm_type` 是 `options` 里出现过的值，没有猜类型；
- [ ] 表单字段名按 camelCase、参数行按 snake_case，没有混用；
- [ ] 涉及写操作时，说明「已提交审批、等待确认」与所需权限，没有把提案当成已完成；
- [ ] 写参数 / 映射 / 参考参数前说明了影响面（哪些 API / 设备 / 用例 / 评估口径）；
- [ ] 提到热重载时说明前置条件（先发布）、幂等（不改数据）与失败不静默；
- [ ] 平台没有的字段 / 选项直接说「接口未提供」，没有编造。
