# 接入包规范（`onboarding/<app_type|vendor>/`）

接入包是交付物，不是代码片段。固定 10 项，缺项由 `driver_propose` 的包校验
直接拒绝。

## 1. 目录

```text
onboarding/<app_type|vendor>/
├─ driver.py / adapter.py
├─ config.yaml
├─ capabilities.json
├─ test_plan.md
├─ ui_trace.json
├─ tests/
├─ smoke_case.json
├─ manifest.json
└─ onboarding_report.md
```

- App 入口：`driver.py` + `ui_trace.json`；
- API 入口：`adapter.py`，没有 `ui_trace.json`；
- PAIR：两者都在同一包内，manifest 的 artifact 互相引用（`pair_with`）；
- 目录名 = `app_type`（App）/ `vendor`（API）/ `<app_type>_<vendor>`（PAIR），
  小写、只保留 `[a-z0-9._-]`。

## 2. 各文件内容

### driver.py / adapter.py

- `driver.py`：`AppDriver` 子类，`@register_driver` + `app_type` / `version` /
  `platform` / `display_name` / `dependencies`；生命周期 `initialize` /
  `pre_process` / `get_results` / `teardown`；`parse_result` 只映射结果字段，
  **不算指标**；
- `adapter.py`：`ApiVendorAdapter` 子类，`@register_vendor_adapter` +
  `protocol` / `vendor`；`render_request_parts` / `execute` / 流式钩子；
- 生成时是**待评审骨架**：生命周期桩 `raise NotImplementedError`，真机冒烟前
  必须补真实实现；T2 只验证结构 / 单测 / mock 契约 / 注册表 resolve。

### config.yaml

```yaml
target_kind: PAIR
capabilities: capabilities.json
driver:
  module: driver.py
  class: DoubaoV1Driver
  app_type: doubao
  version: v1
  platform: ANDROID
  registry: staging（不写生产注册表）
vendor_adapter:
  module: adapter.py
  class: OpenaiRealtimeAdapter
  protocol: realtime
  vendor: openai
  api_id: 42
  credentials: 走现有 key resolver（配置不含凭证）
smoke:
  case: smoke_case.json
  runner: task_run(mode=SMOKE)
```

### capabilities.json

六组字段见 SKILL.md；`capabilities` 是能力事实源，`driver.py` 里的
`RESULT_FIELDS` 等常量必须与它一致。

### test_plan.md

至少包含：测试目标、测量路径六项（输入 / 采集 / 完成判定 / 时序 / 指标 /
资产）、验收（结果字段对齐、至少 1 个可计算指标、平台算指标）、迭代规则。

### ui_trace.json

```json
{
  "actions": [
    {"step": 1, "action": "tap",
     "locator": {"resource_id": "com.doubao:id/input"}, "screenshot": "s1"},
    {"step": 2, "action": "tap",
     "locator": {"text": "发送", "fallback_reason": "控件无 resource_id"}}
  ],
  "pages": [{"name": "chat", "nodes": [{"text": "发送"}]}],
  "screenshots": ["s1"]
}
```

- `actions` 非空；`pages` 或 `page_tree` 至少一个；
- 定位优先 `resource_id` / `key`；退化 `text` / `label` 必须带
  `fallback_reason`。

### tests/

- 平台单测（驱动元数据 / 生命周期 / 解析）；
- mock 厂商契约测试（适配器 protocol / vendor / 请求渲染 / execute 桩）；
- 注册表 resolve（驱动 `(app_type, version, platform)`；适配器
  `(protocol, vendor)`）；
- 包内 `driver.py` / `adapter.py` 的 import 已改为包内模块名。

### smoke_case.json

```json
{
  "case_ref": "smoke-doubao",
  "target_kind": "DEVICE_DRIVER",
  "test_goals": ["ASR", "DIALOG"],
  "inputs": {"assets": ["asr_case_16k.wav"],
             "stimulus_modes": ["ACOUSTIC_PLAYBACK"]},
  "steps": ["进入功能页", "播放测试音", "采集一轮结果", "校验完成判定"],
  "expected_fields": ["asr", "message", "start_ms", "success", "text"],
  "metrics": ["WER", "SENTENCE_ACC"],
  "mock_results": {"success": true, "message": "staging mock",
                   "asr": "你好，世界", "text": "你好，世界",
                   "start_ms": 0}
}
```

- `case_ref` 唯一且在包内稳定；
- `expected_fields` ⊂ 结果契约且含 `success`；
- `metrics` 与 `capabilities.supported_metrics` 有交集；
- `mock_results` 是 staging mock 的证据（**不是真机通过证据**）。

### manifest.json

```json
{
  "target_kind": "PAIR",
  "entry": "PAIR",
  "root": "onboarding/doubao_openai",
  "package_ref": "onboarding-<hash>",
  "artifacts": [
    {"artifact_kind": "DEVICE_DRIVER", "path": "driver.py",
     "registry_key": {"app_type": "doubao", "version": "v1",
                      "platform": "ANDROID"}, "pair_with": "adapter.py"},
    {"artifact_kind": "API_ADAPTER", "path": "adapter.py",
     "registry_key": {"protocol": "realtime", "vendor": "openai"},
     "pair_with": "driver.py"}
  ],
  "capabilities": "capabilities.json",
  "source_trace": "ui_trace.json",
  "smoke_case": "smoke_case.json",
  "files": ["..."],
  "metrics": ["WER", "TTS_QUALITY"],
  "validation": {"static_check": "SUCCEEDED", "t2": "T2_RUNTIME_UNAVAILABLE",
                 "publishable": false}
}
```

### onboarding_report.md

必须含三节（缺一即校验失败）：

```markdown
## 证据
## 已知限制
## 回滚
```

建议补充「目标与入口」「测量路径」「审批」；证据写请求 / 响应、截图 /
`ui_trace` hash、T2 结论、staging 冒烟结论，不写推测。

## 3. staging 与生产

- 包只写 staging 目录（`AGENT_ONBOARDING_STAGING_DIR`，默认系统临时目录）；
- 不自动注册、不覆盖线上驱动 / 适配器；
- 合并 / 注册生产是 `DESTRUCTIVE`，需单独审批；本期发布开关
  `AGENT_DRIVER_PUBLISH_ENABLED=false`；
- `driver_ref` = 包内容 hash；staging 目录被清理后返回
  `STAGING_PACKAGE_NOT_FOUND`，同一输入重新生成即可复现。

## 4. 可复现

- 同一输入重复生成：`code_sha256` 与 `driver_ref` 相同；
- 材料变化 → hash 变化，diff 应能解释（字段 / 页面树 / 契约差异）；
- 不要手工改包内容再当交付物；改材料重新生成。
