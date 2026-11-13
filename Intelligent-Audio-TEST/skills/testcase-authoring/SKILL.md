---
name: testcase-authoring
description: >-
  用例编制口径速查：用例列表与详情、轮次配置（config.rounds 的音频 / 声压 /
  播放设备 / 逐轮评估维度）、评估维度挂载（逐轮与多轮整体）、用例算法参数、
  轮次参考参数、导入导出状态与统计；并支持由音频标注推导用例草案（只读生成，
  不落库）。
  触发词：用例、用例列表、用例详情、用例轮次、轮次配置、轮次参考参数、轮的参考参数、
  参考参数、用例参考参数、参考参数刷新、刷新状态、用例导出、导出作业、评估维度挂载、
  用例参数、用例统计、按分组、分组下的用例、分组里的用例、标注生成用例、
  生成用例草案、复制用例、用例变体。
  不适用：创建 / 修改 / 删除 / 复制用例、批量打标（写操作，M2 走提案 + 审批）；
  标签与用例分组管理（tag-group）；算法参数定义（algorithm-config）；用例执行
  与结果（task-operations）。
version: 1.0.0
owner: testcase-team
allowed-tools:
  - testcase_query
  - testcase_generate
  - tool_search
permissions:
  - testcase:read
budgets:
  maxToolCalls: 30
  maxTokens: 50000
---

# testcase-authoring

用例域的只读入口：查用例、读轮次配置、由标注推导用例草案。**M1 只读**——
创建 / 修改 / 复制 / 删除 / 批量打标都不执行（M2 走提案 + 审批），本 Skill 只
回答「用例现在怎么配的、草案长什么样」。

## 何时用

- 想知道有哪些用例、某个用例怎么配的（轮次、音频、声压、播放设备、维度、参数）；
- 解释一条用例的轮次结构：第几轮、每轮放哪些音频、逐轮评估维度挂哪几个；
- 由一批音频的**标注**推导用例草案（不落库），供人工在「新建用例」页照抄；
- 查用例统计、某轮参考参数、导出作业状态、参考参数刷新状态。

## 何时不用

- 要**新建 / 修改 / 删除 / 复制**用例：M1 只有只读能力，写操作在 M2 走提案 + 审批；
  用户要动手时，给出草案与字段口径，引导到产品「用例管理」页操作；
- 要**批量打标 / 管理标签与分组**：转 `tag-group`；
- 要查算法参数的**定义**（而不是某条用例上的取值）：转 `algorithm-config`；
- 要看任务执行结果 / 报告指标：属任务与报告域，本 Skill 不算分、不推断。

## 工具用法

### testcase_query（只读，权限 `testcase:read`）

| action | 作用 | 必填 / 可选参数 | 对应接口 |
|---|---|---|---|
| `list` | 用例列表（分页） | 可选 `page`、`per_page`、`keyword`、`tag`、`group_id`、`algorithm_type`、`dimension_id`、`lab_id`、`visibility`、`favorite`、`only_deleted`、`include_deleted` | `GET /api/v1/testcases` |
| `detail` | 用例详情（轮次 / 维度 / 音频 / 参数都在这） | 必填 `tc_id` | `GET /api/v1/testcases/{tc_id}` |
| `stats` | 用例统计（总数 / 按分组 / 最近更新） | 无 | `GET /api/v1/testcases/stats` |
| `round_ref_params` | 指定轮次的参考参数文件内容 | 必填 `tc_id`、`round_number` | `GET /api/v1/testcases/{tc_id}/rounds/{round_number}/ref-params` |
| `export_status` | 导出作业状态（进度 / 产物） | 必填 `task_id` | `GET /api/v1/testcases/export/jobs/{task_id}` |
| `refresh_status` | 参考参数刷新任务状态 | 必填 `task_id` | `GET /api/v1/testcases/refresh_task/{task_id}` |

规则：

1. **轮次配置没有独立端点**，就在 `detail` 的 `config.rounds` 里；
2. 列表**没有 `status` 过滤**：用例没有「状态」概念（状态属于任务），别传 `status`；
   `view=tag` 的标签聚合视图输出是 camelCase 的另一套形状，本工具不收；
3. `visibility` 只认 `shared` / `private`；`private` 用例详情对非 owner 按 404 收敛，
   回答「不存在或无权访问」，不要继续枚举；
4. `export_status` 需要 `testcase:import_export` 权限；没有就明确说「当前账号无权
   查看导出状态」，不要猜作业结果；作业不存在 / 已过期是 404（文案统一为
   「不存在或无权访问」），不要当成「导出失败」；
5. `refresh_status` 对不存在 / 已过期的任务返回 200 + `status=not_found`（带
   `message`），这是正常答复，不是接口故障；
6. `round_ref_params` 的 404 是**业务事实**（该轮未生成参考参数 / 轮次不存在），
   接口会带原文，照原文回答，不要说成「无权访问」；
7. 需要长尾只读工具（如按 ID 取用例名）时用 `tool_search` 检索，不臆造接口。

### testcase_generate（只读推导，权限 `testcase:read`）

把音频**标注**推导成用例草案，**不落库、不写任何表**。

| 参数 | 说明 |
|---|---|
| `audio_ids` | 必填，正整数数组（单次最多 20 条） |
| `algorithm_type` | 算法类型（如 `voice_llm`），用于挑选用例参数与标注 code；不存在会显式失败 |
| `device_type` | 目标设备类型：`physical` / `http_api` / `websocket_api`，缺省 `http_api` |
| `dimension_ids` | 评估维度列表：正整数 ID 或 `{id, round_scope?, device_type?}` 对象；逐项校验存在性 |
| `dimension_round_scope` | 维度口径：`single` / `per_round` 逐轮，`multi` 多轮整体 |
| `group_id` | 目标分组 ID（校验存在性，只回显，不落库） |
| `spl` / `playback_device_id` | **覆盖**标注里的声压 / 播放设备（显式值优先，标注只补缺） |
| `inherit_tags` | 是否继承音频标签（默认 true） |

返回形态：

```json
{"mode": "draft", "persisted": false, "writes": 0,
 "device_type": "http_api", "notes": [],
 "drafts": [{"name": "测试用例_xxx.wav", "config": {"rounds": []},
             "algorithm_params": null, "derived_from": {}, "notes": []}]}
```

硬规则：

- 草案**没有用例 ID**，`persisted=false`、`writes=0` 就是「没落库」的凭据；
  不要编造 ID、轮次数或维度数值；
- 轮次号来自标注 `data.round_number`（缺失按第 1 轮），**不允许**为了「看起来
  完整」多造轮次；
- 播放设备名 → ID 的解析在**创建**时才做；草案里保留 `playback_device_name`
  并在 `notes` 说明「未解析」，不要假装已经有 ID（显式给了 `playback_device_id`
  时草案直接带 ID，不再报未解析）；
- `audio_ids` 里有不存在的音频会整批失败（显式报错），不会跳过；`group_id`、
  `dimension_ids`、`playback_device_id`、`algorithm_type` 同样先校验存在性，
  不存在直接失败——先按报错修参数，不要换 ID 重试猜；
- `dimension_ids` 逐项校验：元素只能是正整数或带正整数 `id` 的对象，非法的
  `round_scope` / `device_type` 也显式报错，**不会**被静默丢弃成「没挂维度」；
- `spl` / `playback_device_id` 是**覆盖**语义：显式给定就压过标注值（与创建
  服务一致），没给才取标注，标注没有 spl 按 65.0；
- 推导要回源读音频详情、算法下拉选项与用例参数、评估维度、播放设备、分组列表，
  除本工具的 `testcase:read` 外还需要当前账号有 `audio:read` /
  `algorithm:read` / `evaluation:read` / `playback:read` / `group:read`；
  缺哪个都会显式返回「无权访问」，不要用别的字段绕过。

## 用例字段（服务端 snake_case）

### 列表项（TestCaseListItem）

`id`、`name`、`description`、`group_id`、`group_name`、`tags`（名称数组）、
`config`、`algorithm_params`、`reference_params`、`algorithm_type`、
`strategy_id` / `strategy_overrides`（评估策略引用与覆盖）、`created_at` /
`updated_at`、`is_favorite`、`deleted` / `deleted_at` / `deleted_by_user_id`、
`total_duration`（音频总时长，秒；无音频为 `null`）、`visibility`、
`created_by_user_id`、`lab_id` / `lab_name`（通用用例为 `null`）。

### 详情（TestCaseDetailData）

在列表项基础上多：`group`（`{id, name}`）、`audios`（扁平音频清单）、
`dimensions`（`[{id, name, type}]`，由 `config` 里的维度 ID 解析而来）。

- `audios[]`：`id`（序号）、`audio_id`、`audio_name`、`spl`、`playback_device_id`、
  `play_order`；
- 列表与详情是**两套装配**：列表的 `config` 是原始配置，详情的 `audios` /
  `dimensions` 是解析后的视图，回答时说明用的是哪一个。

### 轮次配置（`config`）

| 字段 | 口径 |
|---|---|
| `config.rounds[]` | 轮次数组，每项 `{round_number, audios[], background_noise, evaluation}` |
| `rounds[].round_number` | 轮次号，从 1 开始 |
| `rounds[].audios[]` | 本轮音频：`audio_id`、`audio_name`、`spl`、`play_order`、`playback_device_id` 或 `playback_speaker_group_id`、`background_noise`（轮内噪声）、`interferers`（干扰人） |
| `rounds[].evaluation.dimensions` | **逐轮**评估维度：`{id, name, weight, threshold, device_type, round_scope}` |
| `config.dimensions` | **多轮整体**评估维度（`round_scope=multi`），物理设备整体评估只认这里 |
| `config.background_noise` | 用例级背景噪声：`{audio_id, spl, device_ids, loop}` |
| `config.source_audio` / `auto_generated` | 来源音频名 / 是否自动生成 |

### 参数列

- `algorithm_params`：按轮分组 `[{round_number, params: [{field_code, field_value}]}]`，
  **不在** `config.rounds` 里；
- `reference_params`：按轮分组 `[{round_number, reference_params_path}]`，同样独立成列；
  文件内容用 `round_ref_params` 读。

## 维度与轮次怎么解释

1. 先看 `config.rounds[]` 有几轮、每轮哪些音频（`audios[]`）；
2. 逐轮维度看 `rounds[].evaluation.dimensions`，整体维度看 `config.dimensions`；
3. 维度条目上的 `round_scope`：`multi` = 多轮整体，`single` / `per_round` / 空 = 逐轮；
4. 维度条目上的 `device_type`：空 = 对所有设备类型生效，否则只对该设备类型生效；
5. 维度名称 / 权重 / 阈值在详情 `dimensions[]` 与 `config` 条目里都有，**以接口
   返回为准**；缺字段就说缺，不要补默认值。

## 复制与变体（M2）

复制用例是写操作（`POST /api/v1/testcases/{tc_id}/copy`，权限 `testcase:copy`），
M1 不执行。用户问「复制一份改参数」时：说明复制会连轮次 / 音频 / 维度 / 参数一起
复制，改完参数需重新确认参考参数；实际复制在产品「用例管理」页操作。

## Gotchas

1. **轮次配置在详情里，没有 `/rounds` 列表端点**：要读轮次就读 `detail` 的
   `config.rounds`；只有**参考参数文件**才有按轮的读取端点。
2. **列表不接受 `status`**：MCP `testcase_list` 声明了 `status`，但网关
   `TestCaseListQuery` 是 `extra='ignore'`，传了会被静默丢弃并返回全量。本工具
   直接报错，别改成别的参数绕过。
3. **逐轮维度 vs 整体维度是两处**：`round_scope=multi` 写在 `config.dimensions`，
   只在 `rounds[].evaluation.dimensions` 里找会「看不到维度」。
4. **`algorithm_params` 不在 config 里**：它是独立列，按 `round_number` 分组；
   别去 `config.rounds` 里翻参数。
5. **`private` 用例详情可能是 404**：这是防探测统一口径，不是「用例被删了」。
6. **参考参数 404 是正常的读未命中**：该轮没有参考参数文件 / 轮次不存在，原文
   会带在错误里。
7. **草案不是用例**：`testcase_generate` 只推导不落库，没有 ID；把草案说成
   「已创建」、或拿草案里的名字当既有用例去查，都是错的。
8. **播放设备名未解析**：草案里 `playback_device_name` 只是标注原文，创建时才
   按名解析成 ID。
9. **字段名保持 snake_case**：接口返回即 snake_case，回答时不要转成 camelCase。

## 验收

- [ ] 用例数量、ID、名称、轮次都来自 `testcase_query` 的真实返回，没有编造；
- [ ] 轮次结构与 `config.rounds` 逐字段对应（轮次号、音频、声压、设备、逐轮维度）；
- [ ] 整体维度与逐轮维度分开说，`round_scope` / `device_type` 原值引用；
- [ ] `algorithm_params` / `reference_params` 按「独立列」口径解释；
- [ ] `private` / 404 按「不存在或无权访问」回答，没有泄漏存在性；
- [ ] 涉及创建 / 修改 / 复制 / 批量打标时，明确说 M1 不执行、属 M2 审批范围；
- [ ] 草案回答标注 `persisted=false`，没有把草案当已存在的用例。
