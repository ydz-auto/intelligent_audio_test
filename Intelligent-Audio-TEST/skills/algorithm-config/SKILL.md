---
name: algorithm-config
description: >-
  算法配置域的只读查询与解释：算法定义（状态、分组、草稿）、设备与 API 参数
  （含三层解析）、参考参数、参数映射、用例专属参数、表单 Schema 与下拉选项、
  算法关联的评估维度，以及热重载的前置条件。写定义/参数/映射与执行热重载在 M2，
  本 Skill 当前只查询和解释，不改任何数据。
  触发词：算法定义、算法参数、参考参数、参数映射、参数列表、表单 Schema、表单字段、
  算法选项、算法下拉、算法分组、算法配置、算法维度、设备参数、API 参数、用例参数、
  热重载前提。
  不适用：报告与指标取数 / 导出（report-studio、report-compare）、评估维度与分类的
  配置（evaluation-config）、音频导入与标注（audio-import）、SPL 校准
  （spl-calibration）；算法计算本身的数值结论（WER / MOS / 准确率）由报告与评估
  服务给出，本 Skill 不计算、不估算。
version: 1.0.0
owner: algorithm-team
allowed-tools:
  - algorithm_query
  - tool_search
permissions:
  - algorithm:read
budgets:
  maxToolCalls: 40
  maxTokens: 40000
---

# algorithm-config

算法配置域的只读入口：查什么、字段叫什么、默认值从哪来、为什么改了不生效。
所有事实来自 `algorithm_query` 调用的真实接口返回；本 Skill 不做任何写操作。

## 何时用

- 想知道平台有哪些算法定义、某个定义的状态 / 分组 / 版本；
- 要读算法参数、参考参数、用例专属参数、参数映射，或解释「参数从哪一层来」；
- 要看某个算法的表单字段、字段类型、**默认值**、组件、校验规则；
- 要取算法下拉选项（判断某个 `algorithm_type` 是否真实存在）；
- 要查算法关联的评估维度、维度参数；
- 要解释热重载什么时候需要、前置条件是什么（执行本身在 M2）。

## 何时不用

- 报告 / 指标 / 趋势 / 导出：走 `report-studio` / `report-compare`；
- 评估维度的增删改与分类：走 `evaluation-config`；
- 音频导入、标注、元数据：走 `audio-import`；
- SPL 映射与校准：走 `spl-calibration`；
- 要改算法定义、参数、映射，或执行热重载：M2（INT-2470）之前不可执行，
  不要承诺「已经改好」，也不要改用别的写接口绕过审批。

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

## 热重载前置条件（执行在 M2）

热重载（`POST /api/v1/algorithm/reload`）是**写侧**动作，需要
`algorithm:definition_manage`；当前 M2 之前不可执行，只能解释条件：

1. 变更必须先**发布**（新建 / 更新 / 全量保存），草稿不在生效范围内；
2. 重载从数据库重建算法配置缓存，并广播失效给其它进程；
3. 写操作本身已经会触发失效，重载用于手动恢复或跨进程对齐，**不是保存的替代**；
4. 重载不校验业务规则、不改数据；参数不合法要回到写侧改，重载救不了。

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
10. **M2 之前写操作不生效**：`algorithm_manage` 调用会得到 `TOOL_NOT_ENABLED` /
    `APPROVAL_REQUIRED`；如实说明「当前阶段只能提案」，不要换个工具硬写。

## 验收

回答算法配置类问题前逐项自检：

- [ ] 结论里的每个算法定义 / 参数 / 映射都来自 `algorithm_query` 的真实返回，并带上 ID 或 code；
- [ ] 参数的层（算法级 / 设备策略 / 设备覆盖 / API 实例）说清楚，没有把某层值说成最终生效值；
- [ ] `defaultValue` / `default_value` 原样引用，`null` 就说没有默认值，没有补数；
- [ ] `algorithm_type` 是 `options` 里出现过的值，没有猜类型；
- [ ] 表单字段名按 camelCase、参数行按 snake_case，没有混用；
- [ ] 涉及写操作或热重载时，说明当前阶段不可执行及所需权限，没有承诺已生效；
- [ ] 平台没有的字段 / 选项直接说「接口未提供」，没有编造。
