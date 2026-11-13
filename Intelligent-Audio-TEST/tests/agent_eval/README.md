# Agent 评测基座（INT-2454）

M0 验收用的评测集与运行器：验证上下文压缩 L1–L3 不丢关键事实、不降低任务成功率，
并为 golden tasks 提供「答案 vs 工具真实返回」的逐字段核对。

运行链路是真实的 `build_container` → 单 Agent Loop → `ContextAssembler`（含压缩）
→ `agent_*` 持久化；只有**模型**与**工具**是确定性替身（`harness.py`），因此
不需要真实 LLM Key、不写主库、可在 CI 里重复跑。

## 目录

| 文件 | 说明 |
|---|---|
| `datasets/golden_tasks.json` | 10 条 golden tasks（`platform_contract` / `task_query` / `report_query` / `platform-reference`）|
| `datasets/long_task.json` | 60 轮跨域（任务 + 报告）长任务集，含 13 条中段记忆复核 |
| `harness.py` | 确定性工具数据、模拟模型、指标口径 |
| `runner.py` | 运行器 + JSON/Markdown 报告 |
| `../unit/test_int2454_eval_baseline.py` | pytest 验收入口 |

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

## 运行

```bash
python -m tests.agent_eval.runner --out ./out
```

产物：`out/report.json`、`out/report.md`；退出码 0 表示全部验收项通过。

pytest：

```bash
python -m pytest tests/unit/test_int2454_eval_baseline.py -q
```

## 扩展

- 新 golden task：在 `datasets/golden_tasks.json` 增加条目，并在
  `harness.py` 的确定性数据里提供对应 fact（自检会拦截漂移）。
- 接真实工具：把 `EvalToolGateway` 换成 `SharedToolGateway` 即可复用同一运行器；
  模拟模型仍需按任务标记动作，适合做离线回归而不是 LLM 质量评测。
