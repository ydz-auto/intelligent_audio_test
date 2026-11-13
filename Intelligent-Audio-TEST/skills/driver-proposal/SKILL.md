---
name: driver-proposal
description: >-
  设备驱动与厂商 API 适配器代码提案的口径与材料准备：从 UiAutoDev 元素树 / 操作轨迹
  和被测 API 契约出发，先查设备与算法事实、找同类驱动样例，产出 AppDriver /
  ApiVendorAdapter 提案（只提案，不执行、不注册、不发布）。
  触发词：驱动提案、驱动代码、生成驱动、AppDriver、ApiVendorAdapter、适配器提案、
  适配器代码、UiAutoDev、元素树、操作轨迹、能力画像、驱动覆盖率、驱动模板、
  同类驱动样例、驱动生成前置条件、驱动发布。
  不适用：设备连接 / 重启 / 告警（device-operations 负责）；SPL 映射 / 校准
  （spl-calibration 负责）；用例生成与任务编排。
version: 1.0.0
owner: device-team
allowed-tools:
  - device_query
  - tool_search
permissions:
  - device:read
budgets:
  maxToolCalls: 30
  maxTokens: 60000
---

# driver-proposal

设备驱动（`AppDriver`）与厂商 API 适配器（`ApiVendorAdapter`）**代码提案**的只读
入口。本 Skill 只做三件事：查设备 / 算法事实、找同类驱动样例、说明提案需要哪些
材料。**不生成可执行代码、不注册驱动、不发布供应商适配器**。

## 何时用

- 用户要为新的 App / 设备型号 / 厂商 API 出驱动提案；
- 需要确认某台设备的型号、系统、驱动版本、驱动关键词、支持算法，作为提案输入；
- 需要找平台里已有的同类驱动 / 适配器样例，复用能力画像与元素命名；
- 需要解释提案需要哪些材料（UiAutoDev 元素树、操作轨迹、API 契约）与验收口径。

## 何时不用

- 要连接 / 重启 / 扫描 / 安装设备：转 `device-operations`（M1 只解释口径）；
- 要做 SPL 校准 / 看校准历史：转 `spl-calibration`；
- 要直接生成用例、跑任务、出报告：转对应用例 / 任务 / 报告 Skill。

## 工具与工具名边界（重要）

- **对外唯一工具名是 `driver_propose`**：`target_kind` = `DEVICE_DRIVER` /
  `API_ADAPTER` / `PAIR`。它属 M2（INT-2467），当前**未启用**，调用会得到
  `TOOL_NOT_ENABLED`；
- `generate_driver_from_elements` / `publish_driver_proposal` 是 `driver_propose`
  的**内部步骤**，不是对外工具，不要把它们当工具名调用；
- 本 Skill 的 `allowed-tools` 只有只读工具，M1 用它把提案材料准备齐：

| 工具 | 用途 |
|---|---|
| `device_query` | `list` / `detail` 取设备型号、系统、版本、`driver_name`、`keywords`、`supported_algorithms`；`driver_keywords` 取已注册驱动关键词；`serials` 取实时扫描到的设备信息 |
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

- `target_kind=DEVICE_DRIVER`：产出 `AppDriver` 提案（能力声明 + 元素定位 + 操作实现
  草案），带能力覆盖率（覆盖的能力 / `capabilities.json` 声明能力）；
- `target_kind=API_ADAPTER`：产出 `ApiVendorAdapter` 提案（端点映射 + 鉴权 + 请求
  响应适配），绑定 `api_id`；
- `target_kind=PAIR`：两者同时产出，并标注设备与 API 的配对关系（两者都要有材料）。

提案是**待人工评审的代码草案**：不安装、不注册到驱动注册表、不切换线上适配器、
不发布。评审通过后由 M2 的落地卡执行，本 Skill 不承诺自动上线。

## 提案验收口径（写进提案评审）

1. 设备 / API 事实与 `device_query` / API 契约逐字段一致，没有编造字段或端点；
2. 能力覆盖以 `capabilities.json` 为准，未覆盖能力显式列为缺口，不静默省略；
3. 元素定位优先稳定标识（资源 ID / 无障碍标签），文本定位要说明脆弱性；
4. API 适配器覆盖契约里的全部端点与错误码，鉴权方式与契约一致；
5. 提案标注目标 `target_kind`、依赖材料版本与生成时间，便于复现；
6. 不包含发布 / 注册 / 生效动作，不修改生产配置。

## Gotchas

1. **`driver_propose` 当前不可调用**：M1 只读，`driver_propose` 未启用；不要把
   `TOOL_NOT_ENABLED` 理解为「平台不支持驱动生成」，也不要用别的工具名代替。
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
9. **不发布**：即使用户说「直接上线」，也说明本阶段只出提案、需要人工评审与 M2
   发布流程。

## 验收

回答驱动提案类问题时，逐项自检：

- [ ] 设备 / API 事实来自 `device_query` 或用户提供的契约，没有编造型号、字段、端点；
- [ ] 明确说明只提案、不执行、不注册、不发布；
- [ ] 工具名只使用已注册的只读工具；`driver_propose` 只作为未来能力说明，没有被
      当成已可用工具调用；
- [ ] 提案材料缺口被明确列出，没有用假设值补齐；
- [ ] 能力覆盖、元素定位、API 契约与验收口径都写清楚，可供人工评审。
