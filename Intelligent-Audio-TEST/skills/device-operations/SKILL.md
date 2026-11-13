---
name: device-operations
description: >-
  被测设备运维口径速查：设备列表与详情、设备分组、在线状态与状态历史（含健康检查
  事件）、告警与告警规则、可用序列号、驱动关键词，以及连接 / 重启 / 扫描 / 安装等
  写动作的口径与前置条件（M1 只解释不执行）。
  触发词：设备列表、设备详情、设备分组、设备状态、状态历史、设备告警、告警规则、
  可用序列号、序列号列表、驱动关键词、设备实验室、设备在线、设备离线、设备占用、
  连接设备、重启设备、设备扫描、安装应用、卸载应用、健康检查状态。
  不适用：SPL 映射 / 校准 / 测试音（spl-calibration 负责）；设备驱动代码生成提案
  （driver-proposal 负责）；用例、任务、报告、音频等其它域。
version: 1.0.0
owner: device-team
allowed-tools:
  - device_query
  - tool_search
permissions:
  - device:read
budgets:
  maxToolCalls: 30
  maxTokens: 50000
---

# device-operations

被测设备（`/api/v1/test-devices`）的只读解释入口。本 Skill 只回答「设备现在是什么
状态、怎么配的、要操作之前需要满足什么条件」，**不执行任何写动作**，也不编造在线
状态或健康结论。

## 何时用

- 想知道有哪些设备、某台设备的型号 / 系统 / 版本 / 实验室 / 序列号 / 驱动；
- 查设备分组（含成员）与分组类型；
- 查设备在线状态、状态历史、最近一次健康检查事件；
- 查告警与告警规则（指标、阈值、级别、启用状态）；
- 查可用设备序列号、已注册驱动关键词；
- 解释连接 / 断开 / 重启 / 扫描 / 安装 / 卸载的前置条件与风险（只解释）。

## 何时不用

- 要校准 SPL、看 SPL 映射 / 校准历史 / 测试音校准点：转 `spl-calibration`；
- 要生成设备驱动或厂商 API 适配器代码提案：转 `driver-proposal`；
- 要看任务、报告、音频：转对应域 Skill。

## 工具用法

唯一业务工具是 `device_query`（只读，动作级权限 `device:read`）。本 Skill 只使用
设备动作；**SPL 动作属于 `spl-calibration`**，不要在这里混用。

| action | 作用 | 参数 | 对应接口 |
|---|---|---|---|
| `list` | 设备列表（分页） | 可选 `page` / `per_page` / `keyword` / `status` / `device_type` / `algorithm_type` / `lab_id` | `GET /api/v1/test-devices` |
| `detail` | 设备详情 | 必填 `device_id` | `GET /api/v1/test-devices/{device_id}` |
| `groups` | 设备分组列表 | 可选 `page` / `per_page` / `keyword` / `group_type` | `GET /api/v1/test-devices/device-groups` |
| `group` | 分组详情（含成员 ID） | 必填 `group_id` | `GET /api/v1/test-devices/device-groups/{group_id}` |
| `status` | 设备状态汇总 | 可选 `ids`（整数数组） | `GET /api/v1/test-devices/status` |
| `status_history` | 状态历史 / 健康检查事件 | 可选 `device_id`（给了就查单设备）/ `device_ids` / `event_type` / `start_time` / `end_time` / `page` / `per_page` | `GET /api/v1/test-devices/status-history` 或 `/{device_id}/status-history` |
| `alarms` | 告警列表（含统计） | 可选 `page` / `per_page` / `status` / `severity` / `device_id` | `GET /api/v1/test-devices/alarms` |
| `alarm_rules` | 告警规则列表 | 可选 `page` / `per_page` / `metric_type` / `enabled` | `GET /api/v1/test-devices/alarm-rules` |
| `serials` | 可用设备序列号（实时扫描） | 无 | `GET /api/v1/test-devices/serials` |
| `driver_keywords` | 已注册驱动关键词 | 无 | `GET /api/v1/test-devices/driver-keywords` |

规则：

1. 先 `list` 或 `status` 定位 `device_id`，再 `detail` 取详情；不要凭记忆报设备 ID；
2. 序列号 / 驱动关键词没有分页参数，结果就是接口返回的全量；
3. 动作不认识的参数会被工具层直接拒绝（网关会静默忽略），按上表传参；
4. 需要长尾只读能力时用 `tool_search` 检索，不要臆造工具名或接口。

## 响应形态（与真实接口一致）

列表统一分页信封：

```json
{"success": true, "code": 0, "message": "Success",
 "data": {"items": [], "total": 0, "page": 1, "per_page": 10, "pages": 0}}
```

`status` 返回的是 `DeviceStatusItem` 列表（`id` / `name` / `status` / `last_online_at`）；
`serials` 直接返回数组（扫描结果，可能为空）；`driver_keywords` 直接返回
`{name, keywords, system}` 数组。字段缺失就是缺失，不要补默认值。

### 设备字段（DeviceItem）

| 字段 | 口径 |
|---|---|
| `id` / `name` / `model` / `description` | 设备标识、名称、型号、描述 |
| `type` | 设备类型原值（如 `phone`），不是用例级 `DeviceType`（physical / http_api / websocket_api） |
| `system` / `system_version` | 操作系统规范值（`Android` / `HarmonyOS` / `iOS`）与版本 |
| `app_name` / `app_version` | 被测应用及版本 |
| `connection_type` | 连接方式原值（如 `usb`） |
| `keywords` | 驱动关键词（与 `driver_keywords` 的 keyword 对应） |
| `serial_number` / `ip` | 序列号 / IP（可能为 `null`） |
| `status` | 设备状态原值（如 `online` / `offline`），**以接口返回为准**，没有枚举可推 |
| `last_online_at` | 最近在线时间；`null` 表示没有记录 |
| `driver_name` | 当前驱动名；`null` 表示未绑定 |
| `supported_algorithms` | 支持的算法类型列表 |
| `lab_id` / `lab_name` | 所属实验室 ID / 名称（网关装饰） |
| `occupied_status` / `occupied_task_id` | 占用状态（如 `occupied`）与占用任务 ID；`null` = 无占用 |
| `max_audio_duration` / `needs_prompt_audio` / `prompt_config` | 音频约束与提示音配置 |
| `created_at` / `updated_at` | ISO 8601 时间 |

### 状态历史事件（DeviceStatusEvent）

`items[]` 字段：`id` / `device_id` / `device_kind`（`test`）/ `event_type` /
`from_status` / `to_status` / `source` / `success` / `detail` / `created_at`。

- `event_type` 取值：`online` / `offline` / `health_check` / `operation`；
- `success=false` 的 `health_check` 事件表示**健康检查失败**，这是历史事实，
  但它不等于「此刻设备离线」——要回答当前状态，必须再查 `status` 或 `detail`。

### 设备分组（DeviceGroup）

`id` / `name` / `parent_id` / `description` / `group_type` / `created_by_user_id` /
`updated_by_user_id` / `created_at` / `updated_at` / `device_ids` / `device_count`；
`group_type` 取值 `test`（被测设备组）/ `playback`（播放设备组）。

### 告警（Alarm）与告警规则（AlarmRule）

- 告警：`id` / `rule_id` / `rule_name` / `device_id` / `device_name` / `metric_type` /
  `severity` / `status` / `trigger_value` / `threshold_value` / `content` /
  `email_sent` / `email_error` / `triggered_at` / `acknowledged_at` /
  `acknowledged_by` / `resolved_at`；列表 `data.stats` 给
  `{active, acknowledged, resolved, total}` 计数。
- 告警规则：`id` / `name` / `metric_type` / `threshold_value` / `severity` /
  `notify_email` / `enabled` / `created_by_user_id` / `updated_by_user_id` /
  `created_at` / `updated_at`。
- 枚举：告警状态 `active` / `acknowledged` / `resolved`；级别 `info` / `warning` /
  `critical`；指标 `offline_duration` / `health_check_failures` / `cpu` / `memory` /
  `battery`。

## 写动作口径（M1 只解释，不执行）

以下动作都需要 `device:control`，属破坏性写；M1 调用会得到
`APPROVAL_REQUIRED` 或未启用语义，**不代表平台没有该能力**。只解释前置条件：

- **连接 / 断开**：设备需已登记；远程设备要网络可达，USB 设备要已插入。连接会
  改动设备状态并写 `operation` 事件；
- **重启 / 关机**：会中断设备上正在执行的任务；执行中的任务先停止再操作；
- **扫描**：走驱动层实时扫描（ADB / HDC），结果与 `serials` 同源，不新增设备；
- **安装 / 卸载应用**：需要安装包路径 / 包名；会改动被测应用版本，影响任务基线；
- **批量操作**：按 `device_ids` 逐台执行，单台失败不回滚已成功项。

## 健康检查

- 主动健康检查是 `POST /api/v1/test-devices/health-check`，权限 `device:control`，
  属维护动作（会实时外呼并写状态事件），**M1 不开放为只读动作**；
- 只读可见的是 `status`（当前状态快照）与 `status_history`（历史事件，含
  `health_check`）；
- 不要把 `status=online` 说成「健康检查通过」，也不要把历史失败事件说成
  「现在离线」。

## 可见性与实验室

- 设备可按 `lab_id` 过滤；`lab_name` 是网关装饰字段，没绑定实验室时为 `null`；
- `occupied_status=occupied` 表示设备被任务占用（`occupied_task_id` 指向占用任务），
  回答可用设备时要明确说明占用态，不要把占用中的设备说成可用；
- 没有权限的设备 / 分组在接口层按「不存在或无权访问」收敛，不要探测存在性。

## Gotchas

1. **`device_query` 必须先给 `action`**：所有查询都是「action + 该动作允许的参数」，
   参数白名单外的参数会被工具层直接拒绝。
2. **`device_type` 是设备类型原值**（如 `phone`），不是用例的 `DeviceType`
   （`physical` / `http_api` / `websocket_api`），两者不能混用。
3. **`status` 没有枚举**：接口返回什么就答什么（常见 `online` / `offline`）；
   不要自行补「busy」「idle」等不存在的取值。占用态看 `occupied_status`。
4. **`ids` / `device_ids` 用整数数组**：工具层会按服务端契约转成逗号串；空数组会
   被拒绝（服务端把空条件当「不过滤」，会把全量当过滤结果）。
5. **`status_history` 的 `device_id` 是单设备开关**：给了查单设备端点，不给查全量
   端点；`event_type` 只接受 `online` / `offline` / `health_check` / `operation`。
6. **分组 ID 是字符串**（如 `"12"`），不是整数；`device_id` 才是整数。
7. **`serials` 是实时扫描**，可能为空、可能较慢；它不改设备状态，但也不要频繁轮询。
8. **SPL 映射里的 `device_id` 是播放设备 ID**，不是被测设备 ID；查 SPL 请转
   `spl-calibration`，不要用这里的设备 ID 去套。
9. **M1 写操作不可执行**：连接 / 重启 / 扫描 / 安装会得到审批或未启用语义，不要
   把拒绝当成「平台不支持设备控制」。
10. **字段名用服务端 snake_case**：回答用户时保持原字段名，不要转 camelCase。

## 验收

回答设备类问题时，逐项自检：

- [ ] 设备 ID / 名称 / 状态都来自 `device_query` 的真实返回，没有凭记忆编造；
- [ ] 当前状态用 `status` / `detail` 回答，历史健康检查失败事件没有被说成当前离线；
- [ ] 占用态（`occupied_status` / `occupied_task_id`）在描述可用性时明确写出；
- [ ] 告警 / 规则的级别、状态、指标用的是接口原值（info / warning / critical 等）；
- [ ] 涉及连接 / 重启 / 扫描 / 安装时，说明 M1 只读与审批边界，没有臆造接口；
- [ ] 字段名与服务端 snake_case 一致，缺失字段没有补默认值。
