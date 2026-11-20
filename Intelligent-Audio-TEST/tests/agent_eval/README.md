# Agent 评测基座（INT-2454 / INT-2465 / INT-2475）

M0 验收用的评测集与运行器：验证上下文压缩 L1–L3 不丢关键事实、不降低任务成功率，
并为 golden tasks 提供「答案 vs 工具真实返回」的逐字段核对。

运行链路是真实的 `build_container` → 单 Agent Loop → `ContextAssembler`（含压缩）
→ `agent_*` 持久化；只有**模型**与**工具**是确定性替身（`harness.py`），因此
不需要真实 LLM Key、不写主库、可在 CI 里重复跑。

## 目录

| 文件 | 说明 |
|---|---|
| `datasets/golden_tasks.json` | 10 条 golden tasks（`platform_contract` / `task_query` / `report_query` / `platform-reference`）|
| `datasets/long_task.json` | 68 轮跨域（任务 + 报告 + 记忆）长任务集，含中段记忆复核 |
| `datasets/e2e_cross_domain.json` | **端到端任务集清单**（中央小组维护；成员各自带 version）|
| `coverage/datasets/skill_trigger_tasks.json` | 14 个 Skill × 10 条口语任务（M1 12 + M2 1 + platform-reference）|
| `coverage/skill_trigger.py` | Skill 触发确定性词面代理（生产侧实现见 `agent_service/application/skill_trigger.py`）|
| `harness.py` | 确定性工具数据、模拟模型、指标与成本口径 |
| `runner.py` | 运行器 + JSON/Markdown 报告（golden / 长任务 / 任务集明细）|
| `gate.py` | **五层评测门禁**（端到端 / 单 Skill / 压缩 / 沙箱 / 恢复）|
| `test_int2475_gate.py` | 门禁自测（含「改坏一个 Skill 必须红」）|

## 五层评测门禁（INT-2475）

一条命令跑完方案 §14 的五个层级，产出机器可读报告；失败以非 0 退出码阻断合并。

```bash
# 五层全跑（沙箱默认 T1；报告写 tests/agent_eval/out/）
python scripts/run_agent_eval.py

# 只跑部分层 / 指定报告目录 / 指定沙箱层级（子集默认 exit 1，见「退出码」）
python scripts/run_agent_eval.py --layers e2e,skill --out ./agent_eval_out
python scripts/run_agent_eval.py --layers e2e,skill --allow-skip   # 本地排障放行
python scripts/run_agent_eval.py --sandbox-tier t2      # 需 docker 已注册 runsc

# 合并门禁：只跑变更 Skill 的对应集合（改坏一个 Skill 即 exit 1 并指出集合）
python scripts/run_agent_eval.py --changed-skills auto --base-ref V10.11.2
```

| 层 | 内容 | 门槛 | 失败集合名 |
|---|---|---|---|
| `e2e` | 跨域任务集（golden 10 + 无编造 30）走真实 Loop | 成功率 ≥95%、编造 0、越权 0 | `e2e:<dataset>` / `e2e:success_rate` / `e2e:permission_boundary` |
| `skill` | 14 个 Skill 各 ≥10 条 golden tasks | 每条 ≥10、触发准确率 ≥90%、L1 描述可追溯 | `skill:<name>` |
| `compaction` | 68 轮长任务，关/开 L1–L3 各跑一遍 | 成功率差 ≤5 点、事实召回 ≥95%、观察到压缩 | `compaction:long_task` |
| `sandbox` | T1（可选 T2）逃逸 / 联网 / 资源超限 | 100% 拦截、无跳过、无遗留容器 | `sandbox:<tier>` |
| `recovery` | kill Worker 后继续（`tests/agent_eval/auto/`） | 用例全过且「不重复写」用例在场 | `recovery:kill_worker` |

产物：`<out>/report.json`（层结果 / 失败集合 / 数据集版本 / 成本 / exit_code）
与 `<out>/report.md`。**退出码**：0 全通过（**只认五层全跑且全过**）；1 有层未通过，
或层不完整（`--layers` 子集的未跑层 / `--sandbox-tier none` 跳过的层）；2 基础设施
不可用（Docker / 镜像 / runsc / 评测集缺失）——与「用例失败」区分，便于 CI 分别处置。

层不完整默认按 1 退出，只有显式 `--allow-skip`（本地排障；CI 禁用）才返回 0。报告
顶层恒带 `layers_expected` / `layers_skipped` / `layers_missing` / `full_five` /
`degraded` / `allow_skip`，人读摘要里也有「层完整性」门槛行，因此「降级通过」在退出码
与报告上都可机器分辨。

端到端成功率与各数据集成功率共用同一条 ≥95% 阈值；门槛表按 `e2e:<dataset>` 逐数据集
出行，与失败集合名一一对应，不会出现「表格全通过、层结论未通过」。

### 评测集与版本化

评测集全部入库并带整数 `version`（`dataset_versions()` 会校验，缺 version 直接
按基础设施错误退出）。端到端任务集由 `datasets/e2e_cross_domain.json` 清单登记，
新增域只需在清单里加成员 + 数据集自带 version，不改评测代码。

### 成本与耗时

报告记录每层墙钟耗时，以及模型轮次 / 工具调用 / 输入字符（近似 token =
chars / 4）。确定性替身不产生真实计费，这些数值用于**相对**成本回归（例如改动
压缩阈值后轮次是否暴涨）。

### 口径与边界

- **Skill 触发是确定性词面代理**：只读 L1 `description` 的「触发词：」段 + 本域
  词汇表做词面打分，**不调用真实模型**。真实模型级触发准确率需要供应商 Key /
  计费通道，本门禁不冒充模型实测；报告里 `trigger_proxy: true`。
- 门禁额外校验「代理词汇表能在 L1 描述里找到依据」：改坏 Skill 正文（触发词
  丢失、描述与词汇表脱节）会直接变红，而不是被代理兜底掩盖。
- `runner.py` 的「工具选择正确率」是 Loop 派发口径（实际调用工具 == 任务声明
  工具），不是模型选工具的准确率；模型级工具选择需真实供应商参与，未纳入本门禁。

## 指标口径

- **任务成功率**：回答与事实真值一致（允许通过工具重查后再回答）；
- **事实召回率**：正确回答数 / 提问轮次，门槛 ≥ 95%；
- **重查率**：复核轮次中上下文没有事实、必须重新调用工具的比例（成本观测）；
- **压缩次数**：`agent_context_snapshot` 条数；
- **压缩前后成功率差**：同一长任务集在「关闭压缩」与「开启 L1–L3」两次运行的成功率
  差值，门槛 ≤ 5 个百分点。

每条 golden task 的 `expected_value` 会先与工具替身数据做一次一致性自检
（`_assert_dataset_truth`），运行时再要求模型答案与该工具**真实返回**的 fact 逐字段
一致，并拒绝 `forbidden_values`（常见编造值）。

## 运行（INT-2454 基线）

```bash
python -m tests.agent_eval.runner --out ./out
```

产物：`out/report.json`、`out/report.md`；退出码 0 表示全部验收项通过。

pytest：

```bash
python -m pytest tests/agent_eval -q
```

## 扩展

- 新 golden task：在对应数据集增加条目，并在 `harness.py` 的确定性数据里提供对应
  fact（自检会拦截漂移）；跨域端到端集需同步登记到 `e2e_cross_domain.json`。
- 新 Skill：在 `coverage/datasets/skill_trigger_tasks.json` 补 ≥10 条口语任务，
  并在 `coverage/skill_trigger.py` 的 `M2_SKILLS` / `DOMAIN_TERMS` 登记。
- 接真实工具：把 `EvalToolGateway` 换成 `SharedToolGateway` 即可复用同一运行器；
  模拟模型仍需按任务标记动作，适合做离线回归而不是 LLM 质量评测。
