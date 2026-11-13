---
name: driver-proposal
description: >-
  设备驱动与厂商 API 适配器代码提案：从 UiAutoDev 元素树 / 操作轨迹和被测 API
  契约出发，先查设备与算法事实、找同类驱动样例，产出 AppDriver / ApiVendorAdapter
  提案并在 T2 沙箱验证（只提案，不执行、不注册、不发布）。
  触发词：驱动提案、驱动代码、生成驱动、AppDriver、ApiVendorAdapter、适配器提案、
  适配器代码、UiAutoDev、元素树、操作轨迹、能力画像、驱动覆盖率、驱动模板、
  同类驱动样例、驱动生成前置条件、驱动发布。
  不适用：设备连接 / 重启 / 告警（device-operations 负责）；SPL 映射 / 校准
  （spl-calibration 负责）；用例生成与任务编排。
version: 1.1.0
owner: device-team
allowed-tools:
  - device_query
  - driver_propose
  - tool_search
permissions:
  - device:read
  - device:update
budgets:
  maxToolCalls: 30
  maxTokens: 60000
---

# driver-proposal

设备驱动（`AppDriver`）与厂商 API 适配器（`ApiVendorAdapter`）**代码提案**入口。
本 Skill 做四件事：查设备 / 算法事实、找同类驱动样例、补齐提案材料、调用
`driver_propose` 生成提案并跑 T2 验证。**生成的是待评审代码提案，不注册、不发布**。

## 何时用

- 用户要为新的 App / 设备型号 / 厂商 API 出驱动提案；
- 需要确认某台设备的型号、系统、驱动版本、驱动关键词、支持算法，作为提案输入；
- 需要找平台里已有的同类驱动 / 适配器样例，复用能力画像与元素命名；
- 需要解释提案需要哪些材料（UiAutoDev 元素树、操作轨迹、API 契约）与验收口径；
- 材料齐备后要**真正生成提案**：调 `driver_propose`（需审批）。

## 何时不用

- 要连接 / 重启 / 扫描 / 安装设备：转 `device-operations`（M1 只解释口径）；
- 要做 SPL 校准 / 看校准历史：转 `spl-calibration`；
- 要直接生成用例、跑任务、出报告：转对应用例 / 任务 / 报告 Skill。

## 工具与工具名边界（重要）

- **对外唯一工具名是 `driver_propose`**：`target_kind` = `DEVICE_DRIVER` /
  `API_ADAPTER` / `PAIR`（INT-2467 已启用；WRITE，需审批）；
- `generate_driver_from_elements` / `publish_driver_proposal` 是 `driver_propose`
  的**内部步骤**，不是对外工具，不要把它们当工具名调用；
- 本 Skill 的 `allowed-tools` 是「只读事实工具 + 提案工具」：

| 工具 | 用途 |
|---|---|
| `device_query` | `list` / `detail` 取设备型号、系统、版本、`driver_name`、`keywords`、`supported_algorithms`；`driver_keywords` 取已注册驱动关键词；`serials` 取实时扫描到的设备信息 |
| `driver_propose` | 生成设备驱动 / API 适配器代码提案（`target_kind` + 材料 → 文件清单 / diff / 依赖 / 风险 / 回滚 + T2 验证报告） |
| `tool_search` | 检索同类驱动 / 适配器样例与相关长尾只读能力（如按关键词「驱动」「适配器」） |

规则：

1. 先 `device_query` 的 `list` / `detail` 拿设备事实，再谈提案；不要凭记忆编造型号或
   驱动名；
2. 需要跨设备 / 跨版本对比时逐个 `detail`，不要假设不同设备共用驱动；
3. 工具名只认注册表里的名字；未返回的能力说明平台当前没有，不要臆造端点或类名。

## 提案输入材料

| 材料 | 来源 | 说明 |
|---|---|---|
| 设备事实 | `device_query` `detail` | `model` / `system` / `system_version` / `app_name` / `app_version` / `driver_name` / `keywords` / `supported_algorithms` |
| 驱动关键词 | `device_query` `driver_keywords` | `{name, keywords, system}`；关键词是驱动匹配的稳定标识 |
| 能力画像 `capabilities.json` | UiAutoDev 导出 / 用户提供 | 设备支持的 UI 操作、API 端点、音视频能力；提案必须按这份画像裁剪 |
| 元素树 / 操作轨迹 `ui_trace.json` | UiAutoDev 导出 / 用户提供 | 页面元素（资源 ID、文本、层级、可点击性）与操作步骤序列 |
| API 契约 | 被测 API 定义 / OpenAPI / proto / WS 文档 | `API_ADAPTER` / `PAIR` 需要端点、鉴权、请求响应样例 |
| 同类样例 | `tool_search` + 现有驱动 | 只用于对齐命名与结构，不复制另一设备的私有逻辑 |

材料不齐时先列缺口（例如「缺元素树」「缺 API 契约」），不要用假设值补全。

## 提案产物口径

`driver_propose` 的输入（材料不齐会显式拒绝，不用假设值补全）：

| 参数 | 说明 |
|---|---|
| `target_kind` | `DEVICE_DRIVER` / `API_ADAPTER` / `PAIR`（必填） |
| `capabilities` | 能力画像（必填）：`stimulus_modes` / `capture_modes` / `timing_points` / `result_fields` / `supported_metrics` / `limitations`；声明的指标必须有对应采集方式与时序点支撑，否则拒绝 |
| 设备驱动 | `app_type` / `version` / `platform`（`ANDROID` / `HARMONYOS` / `IOS`）、`ui_trace`（动作序列 + 页面树 + 截图引用） |
| API 适配器 | `api_id` / `vendor` / `protocol` / `contract`（端点 / 鉴权 / 请求响应样例） |

产物：

- `target_kind=DEVICE_DRIVER`：`AppDriver` 提案（`@register_driver` + 元数据 +
  生命周期桩 + 结果解析骨架），按 `capabilities` 裁剪采集与结果字段；
- `target_kind=API_ADAPTER`：`ApiVendorAdapter` 提案（`@register_vendor_adapter` +
  `protocol` / `vendor` + `render_request_parts` / `execute`），绑定 `api_id`；
- `target_kind=PAIR`：两者同时产出，manifest 里互相引用（`pair_with`）；
- 每个提案带 `artifact_kind`（`DEVICE_DRIVER` / `API_ADAPTER`）、`source_trace`
  （UI 轨迹摘要与定位质量）、`validation_report`（静态检查 + T2）、文件清单、
  diff、依赖、风险、回滚方案，以及可复现的 `code_sha256`。

提案是**待人工评审的代码草案**：不安装、不注册到驱动注册表、不切换线上适配器、
不发布。评审通过后走人工合并与发布审批，本 Skill 不承诺自动上线。

## 审批与验证

### 何时需要审批

- `driver_propose` 是 `WRITE`：调用后返回 `APPROVAL_REQUIRED` 与 `approval_id`，
  表示**提案尚未生成**；批准后才会生成代码、跑 T2。
- 提案里能看到目标类型与材料清单，审批人确认材料来源可信后再批准。

### 破坏性操作二次确认

- `driver_propose` 本身不改生产（只产提案），审批一次即可；
- **发布 / 注册到生产注册表是单独的 `DESTRUCTIVE` 动作**：需要另行审批且二次确认
  （`confirm=true`），且本期发布开关默认关闭（`AGENT_DRIVER_PUBLISH_ENABLED=false`）。
  不要向用户承诺「批准后自动上线」。

### 回滚与失败处置

- 静态检查失败（语法 / 能力画像 / manifest / 注册契约不一致）：不产生可发布产物，
  按报告里的错误项修材料后重新生成；
- T2 不可用（`T2_RUNTIME_UNAVAILABLE`）：提案不可发布，明确说明宿主没有
  gVisor，不要谎称验证通过；
- T2 单测 / mock 契约 / 注册表 resolve 失败：按失败阶段定位（生成的是骨架，
  需要补真实实现或在合并前修），不产生可发布产物；
- 同一输入重复生成 hash 相同；要改提案就改材料重新生成，不要手工改生成文件后
  当提案交付。

## 提案验收口径（写进提案评审）

1. 设备 / API 事实与 `device_query` / API 契约逐字段一致，没有编造字段或端点；
2. 能力覆盖以 `capabilities.json` 为准，未覆盖能力显式列为缺口，不静默省略；
3. 元素定位优先稳定标识（资源 ID / key），退化到文本时 `fallback_reason` 必填；
4. API 适配器覆盖契约里的全部端点与错误码，鉴权方式与契约一致；
5. 提案标注目标 `target_kind`、材料来源与 `code_sha256`，便于复现；
6. 不包含发布 / 注册 / 生效动作，不修改生产配置。

## Gotchas

1. **`driver_propose` 需要审批**：返回 `APPROVAL_REQUIRED` 表示提案未生成；
   不要再发一次调用催执行，也不要用别的工具名代替。`TOOL_NOT_ENABLED` 只在
   驱动提案服务未装配（缺 T2 通道）时出现。
2. **内部步骤不是工具**：`generate_driver_from_elements` /
   `publish_driver_proposal` 是 `driver_propose` 内部流程，不能作为工具调用。
3. **`driver_name=null` 表示未绑定驱动**，不代表设备不可驱动；提案可以把它作为
   目标驱动。
4. **`keywords` 是匹配键**：驱动关键词用于选驱动。写提案时不要改已有驱动关键词
   的含义（会串驱动），新关键词要说明与现有词表的关系。
5. **`serials` 是实时扫描结果**：可能为空（当前没有可扫描设备），不代表平台没有
   设备；提案材料优先用已登记设备的 `detail`。
6. **设备 `type` 与用例 `DeviceType` 不是一回事**：`type` 是设备类型原值（如
   `phone`），`DeviceType` 是执行路由（`physical` / `http_api` / `websocket_api`）。
7. **`supported_algorithms` 是设备能力声明**，不是当前映射；提案里要说明依赖哪些
   算法类型及取值来源（以算法 `options` 接口为准）。
8. **SPL 的 `device_id` 是播放设备 ID**：驱动提案面向被测设备 / 被测 API，不要把
   播放设备 ID 当成被测设备 ID。
9. **不发布**：即使用户说「直接上线」，也说明本阶段只出提案、需要人工评审与
   单独的发布审批（`DESTRUCTIVE` + 二次确认），本期发布开关默认关闭。
10. **`capabilities` 里的指标要算得出来**：声明 `TTS_QUALITY` 却没有录屏 / PCM /
    API 音频采集会被拒绝；只能取 UI 文本时不要声明 TTS 音质指标，改在
    `limitations` 里写明缺口。

## 验收

回答驱动提案类问题时，逐项自检：

- [ ] 设备 / API 事实来自 `device_query` 或用户提供的契约，没有编造型号、字段、端点；
- [ ] 明确说明只提案、不执行、不注册、不发布（发布另走 DESTRUCTIVE 审批）；
- [ ] `driver_propose` 返回 `APPROVAL_REQUIRED` 时说明是「待审批提案」，
      没有把审批前当成已生成或已发布；
- [ ] 提案材料缺口被明确列出，没有用假设值补齐；
- [ ] 能力覆盖、元素定位、API 契约与验收口径都写清楚，可供人工评审。
