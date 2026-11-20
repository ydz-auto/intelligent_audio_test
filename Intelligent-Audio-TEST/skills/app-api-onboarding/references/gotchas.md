# Onboarding gotchas（踩坑清单）

SKILL.md 的 Gotchas 是给模型的简版；本页给执行者 / 评审者的详细口径。

## 1. 入口与工具名

- 入口 `APP` / `API` / `PAIR` 是业务口径；`driver_propose` 的
  `target_kind` 是 `DEVICE_DRIVER` / `API_ADAPTER` / `PAIR`。两者不同名，
  不要互传。
- 对外唯一生成工具是 `driver_propose`；`generate_driver_from_elements` /
  `publish_driver_proposal` 是内部步骤，不是工具名。`skill` 的
  `allowed-tools` 里不能写这两个名字。
- `tool_search` 命中长尾工具后同样受权限 / Schema / 审批约束；不要拿它绕开
  `driver_propose` 的包校验。

## 2. 探索与定位

- `ui_tree` 返回裁剪树（≤200 节点），不是整页 XML；不要要求模型读原始 XML。
- 定位优先 `resource_id` / `key`；只有文本时必须写 `fallback_reason`。
  评审重点：退化比例高的驱动维护成本高，交付报告要标出来。
- `ui_action` 首个动作审批通过后，同一 run + 同一设备的探索计划自动放行；
  换 run / 换设备要重新审批。
- 预算 30 动作 / 5 分钟；`BUDGET` 停止后不要「再点一下试试」，交回用户。
- 登录、验证码、实名、支付页：`LOGIN_REQUIRED` / `CAPTCHA` 立即停止；
  绕过登录属于安全红线。
- 卸载 / 重启 / 支付 / 删账号是 `DESTRUCTIVE`，一律拒绝，不要先执行再看。

## 3. 测量路径

- 「能看见界面」≠「能评音质」。TTS 音质必须有音频采集；只有画面不行。
- 「能录屏」≠「录屏有音轨」。实际只有画面时要显式
  `capture_details.SCREEN_RECORD.audio=false`，否则会产出假音质结论。
- 录屏 / PCM 本身没有文本；要 ASR 文本必须补识别步骤
  （`extra_recognition=true` 或 `capture_details.<mode>.asr=true`）。
- 时序点不是可选项：对话延迟要 `FINAL_TEXT` / `REPLY_END`，打断要
  `PLAYBACK_START` / `PLAYBACK_END`。
- 指标词表固定（`WER` / `CER` / `SENTENCE_ACC` / `FIRST_TOKEN_LATENCY` /
  `REPLY_LATENCY` / `TTS_QUALITY` / `BARGE_IN`），不要造 `MOS` / `WER_2` 之类
  的新名字。
- 驱动只采集；WER / CER / MOS 由 algorithm_service / evaluation_service 计算。
  在驱动里算指标会被静态检查 / 评审拒绝。

## 4. 生成与审批

- `driver_propose` 是 WRITE：审批前返回 `APPROVAL_REQUIRED`，表示**提案尚未
  生成**；不要重复调用催执行。
- 审批通过后才会生成代码、跑 T2、写 staging；`validation_report` 里
  `publishable=false` 的包不能发布。
- 静态检查失败（AST / JSON / 契约 / 能力画像）→ 不产生可发布产物；按报告
  修材料后重新生成。
- T2 不可用（宿主机没有 gVisor / runsc）→ `T2_RUNTIME_UNAVAILABLE`，不得
  降级成「本地跑一下也算过」。
- 同一输入重复生成 hash 相同；要改就改材料，不要手工改生成文件。

## 5. staging 冒烟

- `task_run(mode=SMOKE)` 只读 staging，不写生产注册表；需要审批（WRITE）。
- `driver_ref` 是包内容 hash；staging 目录被清理 / 换机器后找不到，返回
  `STAGING_PACKAGE_NOT_FOUND`，按同一输入重新生成即可。
- 没有真机执行器：返回 `MOCK_PASSED` / `MOCK_FAILED`，`uncovered` 列出
  真机 UI / 音频链路 / 指标计算；**mock 不是真机通过**。
- 传了 `device_id` 但执行器未接：`NOT_EXECUTED`。不要为了「让冒烟过」把
  `device_id` 去掉再报 mock 通过；报告里必须写未覆盖项。
- 冒烟至少要有 1 个可计算指标：ASR 文本（`asr` / `text`）或 TTS 音频
  （`wav_path` / `ai_wav`）+ 时序（`start_ms` / `end_ms` 等）。
- 结果字段必须对齐现有驱动契约，不要新增 `confidence` / `score` 之类字段。

## 6. 迭代

- 最多 3 轮；第 1 轮失败可以重来，但第 2 / 3 轮必须带**新证据**（日志 / 截图 /
  元素变化 / 报文差异），证据 hash 与上一轮相同会被拒绝。
- 第 3 轮仍失败：交回诊断，保留全部证据；不要把同一失败包装成「部分通过」。
- 不收敛时更新 `test_plan.md` 的已知限制与回滚方案，而不是无限重试。

## 7. 安全与边界

- 生成代码不得含凭证、不得联网；API Key 只走现有 resolver。
- 不覆盖线上驱动 / 适配器；驱动与适配器职责不混。
- 不自动注册、不自动发布、不下发设备、不重启设备。
- 不替代 UiAutoDev：元素卡片是输入，不是新工具；元素选择仍可在 UiAutoDev 做。
- 报告里不写内部堆栈 / 凭证 / 他人资源信息；证据只引用资源 ID 与 hash。

## 8. 常见失败对照

| 现象 | 原因 | 处置 |
|---|---|---|
| `APPROVAL_REQUIRED` | 提案未生成 | 等审批；不要重复调用 |
| `INVALID_ARGUMENTS` + 指标名 | capabilities / measurement_profile 不自洽 | 改声明或降级目标 |
| `T2_RUNTIME_UNAVAILABLE` | 宿主无 gVisor | 包不可发布，明确说明 |
| `T2 FAILED` | 生成代码 / 契约 / 单测问题 | 按报告改材料重新生成 |
| `EXPLORATION_UNAVAILABLE` | 设备 UI 通道未接入 | 说明环境缺口，不伪造树 |
| `STAGING_PACKAGE_NOT_FOUND` | staging 被清理 / ref 错 | 重新生成同输入包 |
| `NOT_EXECUTED` | 真机执行器未接 | 如实写未覆盖项 |
| `MOCK_FAILED` | mock 字段 / 指标不全 | 修 smoke_case / capabilities |
