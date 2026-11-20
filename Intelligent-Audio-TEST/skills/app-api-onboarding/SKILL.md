---
name: app-api-onboarding
description: >-
  App / API 接入全流程（onboarding）：用户说「我要测这个 App / 这个 API / 这个
  厂商接口」时，先受理确认测试目标与测量路径，用 ui_tree / ui_action 探索 App
  界面或用 api_spec 解析 OpenAPI / gRPC proto / WebSocket 契约，查同类驱动与设备
  事实，输出接入计划与缺口；确认后调 driver_propose 生成 AppDriver /
  ApiVendorAdapter / 成对交付的固定接入包（代码 + config.yaml +
  capabilities.json + test_plan.md + ui_trace.json + tests/ + smoke_case.json +
  manifest.json + onboarding_report.md），T2 编译 / 单测 / mock 契约 / 注册表
  resolve 后在 staging 目录用 task_run(mode=SMOKE) 跑冒烟，失败最多迭代 3 轮且
  每轮必须带新证据。只产提案与 staging 包，不写生产目录、不自动注册、不发布。
  触发词：接入 App、接入 API、App 接入、API 接入、接入包、onboarding、新 App
  接入、新厂商接入、测这个 App、测这个 API、厂商适配器、接入流程、测量路径、
  ASR 测量、TTS 测量、ui_trace、capabilities、冒烟用例、staging 冒烟、接入报告、
  驱动提案、元素树探索、API 契约解析、OpenAPI、proto、WebSocket 帧、AppDriver、
  ApiVendorAdapter、成对交付、接入计划、缺口清单、驱动生成、适配器生成。
  不适用：只问平台接口 / 字段 / 枚举（platform-reference）；已有驱动的设备连接、
  重启、告警（device-operations）；只做驱动代码评审不跑接入流程（driver-proposal）；
  SPL 校准（spl-calibration）；用例 / 任务 / 报告日常操作（testcase-authoring /
  task-operations / report-studio）。
version: 1.0.0
owner: agent-platform
allowed-tools:
  - ui_tree
  - ui_action
  - api_spec
  - driver_propose
  - device_query
  - testcase_generate
  - task_run
  - tool_search
permissions:
  - device:read
  - device:control
  - device:update
  - task:execute
  - testcase:read
budgets:
  maxToolCalls: 40
  maxTokens: 60000
---

# app-api-onboarding

把一个**没接入过的 App / 厂商 API** 变成一套可运行的接入包：先受理、探索、
计划，再生成、验证、迭代，最后交付。本 Skill 管流程与判断标准，**工具管校验**
（`driver_propose` 校验材料 / 能力画像 / 测量路径 / 交付包，`task_run` 管
staging 冒烟），不在 Agent 里硬编码业务规则。

## 何时用

- 用户第一次接入一个 App（设备 + 包名 / 版本），需要出 `AppDriver`；
- 用户第一次接入一个厂商 API（OpenAPI / gRPC proto / WS 帧 + 样例 + 鉴权），
  需要出 `ApiVendorAdapter`；
- 两边都要（App 走 UI、服务端走协议），需要成对交付；
- 需要判断「这个 App / API 到底测得了什么」：输入方式、采集方式、完成判定、
  时序点、指标、测试资产是否齐备；
- 已有提案但 staging 冒烟没过，需要在**带新证据**的前提下迭代。

## 何时不用

- 只问平台接口、字段、枚举、权限码：转 `platform-reference`；
- 设备连接 / 重启 / 安装 / 告警：转 `device-operations`（写操作走审批）；
- 只评审已有驱动代码、不跑接入流程：转 `driver-proposal`；
- SPL 校准 / 测试音：转 `spl-calibration`；
- 用例、任务、报告的日常读写：转对应域 Skill。

## 三个入口（先判定，不混）

| 入口 | 用户提供 | 产出 | `driver_propose.target_kind` |
|---|---|---|---|
| App | 租用设备 + 包名 / 版本，可选 UiAutoDev 元素卡片 | `AppDriver` + UI 轨迹 + 冒烟 | `DEVICE_DRIVER` |
| API | OpenAPI / proto / WS 文档 + 样例请求响应 + 鉴权 | `ApiVendorAdapter` + mock 契约 + 冒烟 | `API_ADAPTER` |
| App + API | 两者都给 | 成对交付，manifest 互相引用 | `PAIR` |

判定规则：

1. 用户只给 App 界面 / 设备 → App 入口；只给接口文档 → API 入口；两边都给
   且明确要端到端 → PAIR。**不要**把「只知道包名」的 App 当 API 入口。
2. UiAutoDev 元素卡片只是**可选输入**（经受认证桥接事件进入会话），不是新工具；
   元素选择仍可在 UiAutoDev 完成，Agent 自己用 `ui_tree` / `ui_action` 探索。
3. 三个入口最终都复用 `driver_propose`；`generate_driver_from_elements` /
   `publish_driver_proposal` 是内部步骤，不是可调用工具名。

## 流程（七步，按顺序）

### 1. 受理

先确认，不要直接生成：

- App：`app_type`、`version`、`platform`（`ANDROID` / `HARMONYOS` / `IOS`）、
  设备型号与租用状态；API：`vendor`、`protocol`（`http` / `websocket` /
  `realtime` / `grpc`）、`api_id`、鉴权方式、样例请求响应；
- **测试目标**：ASR / TTS / 对话 / 翻译 / 降噪 / 打断（可多选）；
- 按 §6.5.1 定：输入方式（怎么喂）、采集方式（怎么收）、完成判定、时序点、
  指标、测试资产（测试音 / 文本 / 标注）；
- 是否已有同类驱动 / 适配器（`device_query` + `tool_search`）。

用 `measurement_profile` 把结论显式传给 `driver_propose`（见下节）。材料不齐
时列缺口，不要用假设值补全。

### 2. 发现

- App：`ui_tree` 逐页读裁剪树（最多 200 节点），`ui_action` 导航并落
  `ui_trace.json`（动作序列 + 页面树 + 截图引用）。定位优先
  `resource_id` / `key`；退化到 `text` 必须写 `fallback_reason`。
- API：`api_spec` 解析端点 / 鉴权 / 样例（**只解析，不发真实请求**）；
  需要时用 `tool_search` 找同类适配器与既有命名。
- 设备事实：`device_query` 的 `list` / `detail` / `driver_keywords`；
  不要凭记忆编型号、驱动名或端点。

探索安全（卡面硬口径）：

- 必须先租用 / 锁定设备；首个 `ui_action` 走审批，同 run + 同设备的同一探索
  计划内后续动作自动放行；预演（`dry_run` / `validate`）不下发设备动作。
- 单次探索最多 30 个动作 / 5 分钟，超限以 `BUDGET` 停止并交回。
- 卸载、重启、支付、删账号等 `DESTRUCTIVE` 动作一律拒绝。
- 登录页 / 验证码 / 实名 / 支付页立即以 `LOGIN_REQUIRED` / `CAPTCHA` 停止，
  交用户接管，不尝试绕过。

### 3. 测量路径校验（生成前必须过）

测量路径不是文档，是**可测性判断**。算不出来的指标要当场拒绝或降级，并说明
原因，绝不产出假指标。五类模板与拒绝例子见
`references/measurement-paths.md`：

| 模板 | 输入 | 采集 | 适用 |
|---|---|---|---|
| UI 文本 | 声学播放 / 手动说话 | 消息列表 / 编辑器文本 | ASR 文本、对话回复 |
| 录屏音频 | 声学播放 | 每轮 mp4 → wav，首帧时间 | TTS 播放、对话回复音频 |
| PCM 抓取 | 声学播放 | `client_out.pcm` / `client_in.pcm`，RMS 判结束 | 低延迟、打断、TTS 音频 |
| App 导出 | 声学播放 | App 内转写 / 导出 / 分享 | 长录音转写、离线结果 |
| API 响应 | 文件 / 流式音频 / 文本 | JSON 文本 + 音频流 | API ASR / TTS |

`driver_propose` 会按 `capabilities` 校验指标可计算性，并在
`measurement_profile` 给定后校验本次目标。典型拒绝 / 降级：

- 只能取 `UI_TEXT` 却要 `TTS_QUALITY` → **拒绝**，说明缺音频采集；降级为
  文本 / 延迟类指标；
- 只能录屏且**无音轨**（`capture_details.SCREEN_RECORD.audio=false`）却要
  `TTS_QUALITY` → **拒绝**；降级为文本类，或补 PCM / 含音轨录屏；
- 只能录屏 / PCM 却要 ASR 文本、又没声明识别步骤 → **拒绝**；补
  `extra_recognition=true` 或 `capture_details.<mode>.asr=true`，否则只评
  延迟 / 音频质量。

### 4. 计划（用户确认后才生成）

输出接入计划与缺口清单，至少包含：

- 入口与 `target_kind`、App / API 事实（来自工具，不编造）；
- 测量路径六项（输入 / 采集 / 完成判定 / 时序 / 指标 / 资产）；
- 缺口：缺元素（无稳定定位）、缺鉴权、缺样例、缺设备、缺测试音；
- 预计交付包结构与验证方式（T2 + staging 冒烟）。

用户确认前**不要**调 `driver_propose` 生成（生成是 WRITE，需审批）。

### 5. 生成

调 `driver_propose`（WRITE，需审批），参数：

- `target_kind` + `capabilities`（六组字段，见下）；
- App：`app_type` / `version` / `platform` / `ui_trace`；
- API：`api_id` / `vendor` / `protocol` / `contract`；
- `measurement_profile`：本次测试目标与测量路径；
- `iterations`：迭代历史（第一轮不传）。

审批前返回 `APPROVAL_REQUIRED` 表示**提案尚未生成**；批准后才生成代码、跑 T2，
并把接入包写入 staging 目录（不写生产注册表）。返回里重点看：

- `artifacts` / `files` / `diff` / `code_sha256`：提案内容与可复现 hash；
- `measurement_plan`：解析后的测量路径与 `computable_metrics`；
- `onboarding`：`root`（`onboarding/<app_type|vendor>/`）、`driver_ref`、
  `items`（固定 10 项）、`staging.available`；
- `validation_report`：静态检查 + T2（导入/编译、单测、mock 契约、注册表
  resolve）与 `publishable`。

### 6. 验证与迭代

- T2 不可用（`T2_RUNTIME_UNAVAILABLE`）或失败：提案不可发布，明确说明，
  不得谎称验证通过；
- staging 冒烟：`task_run(mode=SMOKE, driver_ref=<onboarding.driver_ref>,
  case_ref=<smoke_case.case_ref>[, device_id=<租用设备>])`
  （WRITE，需审批；只读 staging，不写生产注册表）；
  - 没有真机执行器时返回 `MOCK_PASSED` / `MOCK_FAILED`，并显式列
    `uncovered`（真机 UI / 音频链路 / 平台指标计算）；
  - 传了 `device_id` 但执行器未接入 → `NOT_EXECUTED`；**不得把 mock 当
    真机通过**；
- 冒烟至少要有 1 个可计算指标（ASR 文本或 TTS 音频 + 时序）；没有就是失败；
- 失败重来必须带**新证据**：日志 / 截图 / 元素变化 / 报文差异，写进
  `iterations[].evidence`；同一证据重复提交会被拒绝；
- 最多 3 轮；第 3 轮仍不收敛 → **交回诊断**，保留全部证据，不再生成新提案。

### 7. 交付

交付接入包 + 验证报告 + 已知限制 + 回滚方案：

- 包根：`onboarding/<app_type|vendor>/`，固定 10 项（见下）；
- `onboarding_report.md` 必须含「证据」「已知限制」「回滚」三节；
- 合并 / 注册到生产是**单独的 `DESTRUCTIVE` 审批**，本期发布开关默认关闭
  （`AGENT_DRIVER_PUBLISH_ENABLED=false`），不要向用户承诺「批准后自动上线」。

## 交付包结构（固定 10 项）

```text
onboarding/<app_type|vendor>/
├─ driver.py / adapter.py      # App 出 driver.py；API 出 adapter.py；PAIR 两个都出
├─ config.yaml                 # staging 配置（driver / vendor_adapter / smoke），不含凭证
├─ capabilities.json           # 能力画像（六组字段，事实源）
├─ test_plan.md                # 测量路径 + 验收 + 迭代规则
├─ ui_trace.json               # App 侧探索轨迹（API 入口没有）
├─ tests/                      # 单测 / mock 契约 / 注册表 resolve
├─ smoke_case.json             # 冒烟用例（case_ref / expected_fields / metrics / mock_results）
├─ manifest.json               # target_kind / artifacts / files / metrics / validation
└─ onboarding_report.md        # 证据 / 已知限制 / 回滚 / 审批
```

`capabilities.json` 六组字段（缺一不可）：

| 字段 | 取值 |
|---|---|
| `stimulus_modes` | `ACOUSTIC_PLAYBACK` / `VIRTUAL_MIC` / `FILE_UPLOAD` / `TEXT_INPUT` |
| `capture_modes` | `UI_TEXT` / `SCREEN_RECORD` / `PCM_CAPTURE` / `APP_EXPORT` / `API_RESPONSE` |
| `timing_points` | `PLAYBACK_START` / `PLAYBACK_END` / `FIRST_FRAME` / `FIRST_PARTIAL` / `FINAL_TEXT` / `FIRST_AUDIO_PACKET` / `REPLY_END` |
| `result_fields` | 与现有驱动契约一致：`success` / `message` / `asr` / `text` / `question` / `answer` / `wav_path` / `user_wav` / `ai_wav` / `record_path` / `start_ms` / `end_ms` / `first_frame_ms` / `latency_ms` |
| `supported_metrics` | `WER` / `CER` / `SENTENCE_ACC` / `FIRST_TOKEN_LATENCY` / `REPLY_LATENCY` / `TTS_QUALITY` / `BARGE_IN` |
| `limitations` | 字符串数组；写清「无 PCM，仅能录屏」「只能取文本，无法评 TTS 音质」等 |

硬规则：**驱动只采集文本 / 音频 / 时序，不在驱动里算 WER / MOS**；指标由
algorithm_service / evaluation_service 计算。声明的指标必须有对应采集方式与
时序点支撑，否则 `driver_propose` 直接拒绝。

`measurement_profile` 示例（App，UI 文本 + PCM 抓取，评 ASR 与延迟）：

```json
{
  "test_goals": ["ASR", "DIALOG"],
  "stimulus_modes": ["ACOUSTIC_PLAYBACK"],
  "capture_modes": ["UI_TEXT", "PCM_CAPTURE"],
  "timing_points": ["PLAYBACK_START", "FINAL_TEXT", "REPLY_END"],
  "completion": "AI 回复文本出现且播放结束",
  "assets": ["asr_case_16k.wav"],
  "extra_recognition": false
}
```

## 安全边界（硬约束）

- **不写生产目录、不自动注册、不自动发布、不下发设备、不重启设备**；
  接入包只落 staging 目录，注册 / 合并走单独的 `DESTRUCTIVE` 审批。
- 生成代码不含凭证、不联网（T2 禁网）；API Key 只走现有 key resolver。
- 未审批不执行任何写操作；`driver_propose` / `ui_action` / `task_run(mode=SMOKE)`
  都是 WRITE，必须带审批凭据。
- 设备侧必须先租用 / 锁定；登录 / 验证码 / 实名 / 支付页交回用户。
- 不覆盖线上驱动 / 适配器；驱动与适配器职责不混（驱动不写厂商报文，适配器
  不操作 UI）。
- 不替代 UiAutoDev：元素卡片只是输入，不是新工具。

## Gotchas

1. **`target_kind` 不是入口名**：入口是 `APP` / `API` / `PAIR`，工具收的是
   `DEVICE_DRIVER` / `API_ADAPTER` / `PAIR`；两者混用会被 Schema 拒绝。
2. **`driver_propose` 返回 `APPROVAL_REQUIRED` 不等于失败**：表示提案未生成；
   不要重复调用催执行，也不要把审批前当成已生成。
3. **只能取 UI 文本不能评 TTS 音质**：`TTS_QUALITY` 需要
   `SCREEN_RECORD`（含音轨）/ `PCM_CAPTURE` / `API_RESPONSE`；不满足就在
   `limitations` 写明，不要声明算不出来的指标。
4. **录屏默认按「含音轨」处理**：若实际只有画面，必须显式写
   `capture_details.SCREEN_RECORD.audio=false`，并要求降级；否则会产出假
   TTS 音质结论。
5. **录屏 / PCM 出 ASR 文本必须补识别步骤**：`extra_recognition=true` 或
   `capture_details.<mode>.asr=true`，否则 `driver_propose` 拒绝。
6. **`ui_trace` 定位退化必须解释**：只有 `text` / `label` 时缺
   `fallback_reason` 会被拒绝；优先补 `resource_id` / `key`。
7. **`ui_action` 首个动作要审批**，同 run + 同设备的后续动作才自动放行；
   预算 30 动作 / 5 分钟，超限交回，不要重试绕过。
8. **设备 UI 通道未接时 `ui_tree` 返回 `EXPLORATION_UNAVAILABLE`**：这是
   环境缺口，不是 App 没有界面；不要用假设的页面树继续生成。
9. **`device_query` 的 `driver_name=null` 表示未绑定驱动**，不代表不可驱；
   `serials` 为空也可能只是当前没扫描，优先用已登记设备的 `detail`。
10. **`api_spec` 只解析不调用**：真实的鉴权 / 样例要用 `contract` 传全；
    缺样例时在计划里列缺口，不要编造端点或报文。
11. **staging 冒烟 ≠ 真机通过**：`MOCK_PASSED` 只验证结果字段与指标可算，
    `uncovered` 里的真机项必须原样交代；传 `device_id` 时执行器未接入返回
    `NOT_EXECUTED`，禁止改口径说「已通过」。
12. **`driver_ref` 有生命周期**：staging 目录被清理后 `task_run(mode=SMOKE)`
    返回 `STAGING_PACKAGE_NOT_FOUND`；按同一输入重新生成即可复现同一 ref，
    不要手工改包内容。
13. **迭代不是无限重试**：同一失败证据重复提交会被拒绝；第 3 轮仍失败只能
    交回诊断，不能继续生成。
14. **T2 不可用时不降级**：`T2_RUNTIME_UNAVAILABLE` 时包 `publishable=false`；
    真机 / mock 冒烟不能替代 T2 结论。
15. **写生产注册表是 `DESTRUCTIVE`**：本期开关默认关闭；不要在交付评论里
    承诺自动上线。

## 验收

交付接入包前逐项自检：

- [ ] 入口判定正确，App / API / PAIR 没混；材料来自工具或用户契约，没有编造型号、
      端点或样例；
- [ ] 受理阶段确认了测试目标与测量路径六项；`measurement_profile` 与
      `capabilities` 一致；
- [ ] 算不出来的指标被拒绝 / 降级并说明原因（只有 `UI_TEXT` 不声明
      `TTS_QUALITY`；无音轨录屏不评 TTS；录屏 ASR 有识别步骤）；
- [ ] 交付包 10 项齐全（`onboarding/<app_type|vendor>/`），`capabilities.json`
      六组字段自洽，结果字段对齐现有驱动契约；
- [ ] PAIR 的 manifest 两个 artifact 互相引用；App / API 各自按
      `(app_type, version, platform)` / `(protocol, vendor)` resolve；
- [ ] 同一输入重复生成 `code_sha256` / `driver_ref` 相同，差异可解释；
- [ ] T2 结论如实（不可用就写不可用）；staging 冒烟至少 1 个可计算指标，
      真机 / mock / 未覆盖项写清楚，不假通过；
- [ ] 失败迭代带新证据且 ≤3 轮；不收敛已交回诊断；
- [ ] `onboarding_report.md` 含证据、已知限制、回滚；未写生产注册表，
      未承诺自动发布；
- [ ] 生成代码无凭证、无联网依赖，未执行卸载 / 重启 / 支付 / 删账号类动作。
