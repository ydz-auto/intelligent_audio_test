---
name: spl-calibration
description: >-
  SPL 声压级校准口径速查：物理域 SPL 映射（播放设备 / 距离 / 测试频率 / 目标 SPL /
  校准状态 / 校准点集）与数字域 RMS→SPL 映射（被测 API / 参考 SPL / 增益限幅 /
  校准点集），以及校准历史、最新校准数据、测试音播放的只读口径与写动作边界。
  触发词：SPL 映射、声压级、SPL 校准、校准状态、校准历史、校准点集、校准数据、
  测试音、增益偏移、增益限幅、目标声压级、数字域映射、RMS 映射、播放设备校准、
  已校准、未校准。
  不适用：被测设备连接 / 重启 / 告警（device-operations 负责）；驱动代码提案
  （driver-proposal 负责）；报告里的 SPL 指标解读（report-studio 负责）。
version: 1.0.0
owner: device-team
allowed-tools:
  - device_query
  - tool_search
permissions:
  - spl:read
  - digital_spl:read
budgets:
  maxToolCalls: 30
  maxTokens: 50000
---

# spl-calibration

SPL（声压级）校准的只读解释入口。本 Skill 回答「映射怎么配的、校准状态是什么、
历史与最新校准点集是什么、要校准 / 播放测试音需要什么条件」，**不执行校准、不播放
测试音、不改映射**。

## 何时用

- 查物理域 SPL 映射列表 / 详情 / 统计（按播放设备、关键词、校准状态）；
- 查某个映射的校准历史与实际测量记录；
- 查某个映射的最新校准点集（每行一个测试音校准点：目标 SPL、增益偏移、基准 / 最终电平）；
- 查数字域 RMS→SPL 映射（按被测 API / 校准状态），理解数字校准的参考 SPL 与增益限幅；
- 解释校准状态、校准前置条件、测试音播放的写动作边界。

## 何时不用

- 连接 / 重启 / 扫描被测设备、查设备状态或告警：转 `device-operations`；
- 生成设备驱动 / API 适配器代码提案：转 `driver-proposal`；
- 解读报告或任务里的 SPL 指标结果：转对应报告 / 任务 Skill，结果数值不在这里计算。

## 工具口径（重要）

平台**没有独立的 SPL 只读意图工具**，也没有名为 `spl_query` / `digital_spl_query`
的工具——这些名字不存在，不要自造。SPL 只读能力全部是 `device_query` 的动作
（只读），按动作级权限收窄：

| action | 作用 | 参数 | 权限 | 对应接口 |
|---|---|---|---|---|
| `spl_mappings` | 物理域映射列表 | 可选 `page` / `per_page` / `keyword` / `calibration_status` / `device_id` | `spl:read` | `GET /api/v1/spl` |
| `spl_mapping` | 物理域映射详情 | 必填 `mapping_id` | `spl:read` | `GET /api/v1/spl/{mapping_id}` |
| `spl_stats` | 物理域统计 | 无 | `spl:read` | `GET /api/v1/spl/stats` |
| `spl_by_device` | 按播放设备查映射 | 必填 `device_id`（播放设备 ID） | `spl:read` | `GET /api/v1/spl/by-device/{device_id}` |
| `spl_history` | 校准历史 | 必填 `mapping_id` | `spl:read` | `GET /api/v1/spl/{mapping_id}/history` |
| `spl_calibration_data` | 最新校准点集 | 必填 `mapping_id` | `spl:read` | `GET /api/v1/spl/{mapping_id}/calibration-data` |
| `digital_spl_mappings` | 数字域映射列表 | 可选 `page` / `per_page` / `api_id` / `calibration_status` | `digital_spl:read` | `GET /api/v1/digital-spl` |
| `digital_spl_mapping` | 数字域映射详情 | 必填 `mapping_id` | `digital_spl:read` | `GET /api/v1/digital-spl/{mapping_id}` |
| `digital_spl_by_api` | 按被测 API 查数字域映射 | 必填 `api_id`（被测 API ID） | `digital_spl:read` | `GET /api/v1/digital-spl/by-api/{api_id}` |

规则：

1. 先用 `spl_mappings` / `spl_by_device` / `digital_spl_mappings` 定位 `id`，再取详情；
2. 需要长尾只读能力时用 `tool_search` 检索；SPL 相关的长尾命中会回到
   `device_query`，仍按上表的 action 调用；
3. 动作不认识的参数会被工具层直接拒绝（网关会静默忽略，返回的不是目标结果）；
4. 权限按动作收窄：没有 `digital_spl:read` 时数字域动作会被拒绝，不要改用物理域
   端点去猜数字域数据。

## 两个 SPL 域别混用

| 维度 | 物理域 `/api/v1/spl` | 数字域 `/api/v1/digital-spl` |
|---|---|---|
| 校准对象 | 播放设备（真实扬声器 + 声级计） | 被测 API（发送已知 RMS 音频，读评估结果） |
| `device_id` 含义 | **播放设备 ID**（不是被测设备） | 无 `device_id` |
| `api_id` 含义 | 无 | 被测 API ID |
| 主要字段 | `distance` / `target_spl` / `test_frequency` / `calibration_data` | `reference_spl` / `reference_gain_linear` / `calibration_points` / `min_gain_linear` / `max_gain_linear` |
| 校准状态 | `calibration_status`：`calibrated` / `uncalibrated` | 同左 |

`calibration_status` 取值为 `calibrated` / `uncalibrated`（事实源
`shared.models.common_enums.CalibrationStatus`）；未校准不等于失败，说明还没做
测量会话。

## 响应形态（与真实接口一致）

所有列表都返回分页信封：

```json
{"success": true, "code": 0, "message": "Success",
 "data": {"items": [], "total": 0, "page": 1, "per_page": 10, "pages": 0}}
```

单条详情 / 统计 / 校准数据直接是 `data`，没有 `items` 包裹。
`spl_history` 与 `spl_by_device` 是「无分页语义的单页全量」：`total` 是条数，
`per_page` 等于 `total`（空列表时 `per_page=1`），不要据此推算真实分页。

### 物理域映射字段（SPLMapping）

| 字段 | 口径 |
|---|---|
| `id` / `name` / `description` | 映射标识、名称、描述 |
| `device_id` / `device_name` / `device_model` | **播放设备** ID / 名称 / 型号；`device` 是 `{id, name}` 子对象 |
| `device_type` | 播放设备类型原值，可能为 `null` |
| `distance` | 测量距离（米） |
| `target_spl` | 目标声压级（dB SPL） |
| `digital_gain` | 数字增益原值，可能为 `null` |
| `calibration_status` | `calibrated` / `uncalibrated` |
| `test_frequency` | 测试频率（Hz，如 1000） |
| `calibration_data` | 结构化校准数据，形如 `{"points": [...]}`（见下） |
| `is_current` | 是否为该设备当前生效映射 |
| `created_at` / `updated_at` | ISO 8601 时间 |

`spl_calibration_data` 返回 `{"points": [...]}`；每个点（测试音校准点）字段：
`spl`（目标声压级）、`gainOffset`（增益偏移）、`baseLevel`（基准电平）、
`finalLevel`（最终电平）。点集是「最新一次完整校准」的结果，**按接口原值引用，
不要插值、换算或补点**。

### 数字域映射字段（ApiRmsSplMapping）

`id` / `api_id` / `name` / `vendor` / `protocol` / `reference_spl` /
`reference_gain_linear` / `calibration_status` / `calibration_points` /
`min_gain_linear` / `max_gain_linear` / `is_calibrated` / `created_at` / `updated_at`。

`calibration_points[]` 字段：`target_spl`（目标 SPL）、`gain_linear`（线性增益）、
`rms_dbfs`（输入 RMS 电平，dBFS）。读侧是 `calibration_points`；写侧请求体是
`calibration_data.points` 且 `gain_linear` 由后端按 `rms_dbfs` 推导——本 Skill 只读，
不要用写侧字段名解释读侧数据。

## 校准历史

- `spl_history` 返回历史测量记录（`items`，可能为空数组）；
- 历史为空只表示**没有历史校准记录**，不代表「未校准」或「校准失败」，两者分别看
  `calibration_status` 与 `calibration_data`；
- 历史记录字段以接口实际返回为准（不同版本可能包含距离、测试频率、操作人、时间）；
  回答时引用原字段，不要自行补算差值或趋势。

## 写动作边界（M1 不执行）

- **物理校准**：`POST /api/v1/spl/{mapping_id}/calibrate`，权限 `spl:create`；
  会播放测试音并回写测量点，改变校准状态；
- **播放 / 停止测试音**：`POST /api/v1/spl/test-tone`、`/test-tone/stop`，权限
  `spl:test_tone`；执行期间与任务音频争用扬声器，网关会校验运行中的任务；
- **数字校准**：`POST /api/v1/digital-spl/{mapping_id}/calibrate`，权限
  `digital_spl:create`；点集全量替换并有分布式锁互斥（冲突 409）；
- **映射增删改**：`spl:create` / `spl:update` / `spl:delete` 与
  `digital_spl:create` / `update` / `delete`。

M1 调这些写工具会得到 `APPROVAL_REQUIRED` 或未启用语义；只解释前置条件与影响，
不要把它说成「平台不支持校准」。`spl_calibrate` 是唯一登记过的 SPL 写意图工具
（M2 实现）；`generate_driver_from_elements` 一类名字与本域无关，不要混用。

## Gotchas

1. **没有独立 SPL 只读工具**：只读一律走 `device_query` 的 `spl_*` /
   `digital_spl_*` 动作；`spl_query`、`digital_spl_query` 都是不存在的工具名。
2. **物理域 `device_id` 是播放设备**：拿被测设备 ID 去 `spl_by_device` 会查不到或
   查错；`spl-calibration` 不负责被测设备查询，需要时转 `device-operations`。
3. **物理域详情不存在返回 400 而非 404**：`GET /api/v1/spl/{id}` 对不存在的映射
   返回「未找到 SPL 映射记录」+ 400；数字域详情返回 404。两者在工具层分别收敛为
   `UPSTREAM_ERROR` / `NOT_FOUND`，回答时说「不存在或无权访问」，不要猜测。
4. **「测试音列表」没有独立端点**：测试音是播放动作（写）；只读能拿到的是映射
   详情里的 `calibration_data.points` 与 `spl_calibration_data`，每行是一个测试音
   校准点，不是可播放的音源清单。
5. **`calibration_data` 读侧是 `points` + `spl/gainOffset/baseLevel/finalLevel`**，
   数字域读侧是 `calibration_points` + `target_spl/gain_linear/rms_dbfs`；两套字段
   名不能互换。
6. **`calibration_status` 只有两个值**：`calibrated` / `uncalibrated`；不要用
   `pending` / `failed` 等不存在的值，也不要把 `uncalibrated` 说成失败。
7. **历史为空 ≠ 未校准**：历史是测量记录，校准状态是映射上的独立字段。
8. **`spl_stats` 是全局统计**，不接受过滤参数；按设备的统计要自己看
   `spl_by_device` 的结果，不要说成接口给的筛选统计。
9. **`is_current` 是设备维度的默认映射标记**，同一播放设备可能有多条映射；回答
   「当前用哪条」要看 `is_current`，不要按 `updated_at` 排序猜。
10. **M1 写操作不可执行**：校准、测试音、映射增删改都会得到审批或未启用语义。

## 验收

回答 SPL 类问题时，逐项自检：

- [ ] 映射 / 历史 / 校准点集都来自 `device_query` 的真实返回，没有编造数值；
- [ ] 区分物理域与数字域，`device_id`（播放设备）与 `api_id`（被测 API）没有混用；
- [ ] 校准状态用 `calibrated` / `uncalibrated` 原值，没有把未校准说成失败；
- [ ] 校准点集按接口原值引用（`spl` / `gainOffset` / `baseLevel` / `finalLevel` 或
      `target_spl` / `gain_linear` / `rms_dbfs`），没有插值或二次计算；
- [ ] 提到校准 / 测试音时说明 M1 只读与审批边界，没有臆造接口或工具名；
- [ ] 历史为空时明确说「没有历史记录」，没有推断成「未校准」。
