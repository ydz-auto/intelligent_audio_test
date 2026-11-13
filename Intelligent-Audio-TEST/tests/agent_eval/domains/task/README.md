# 任务 / 日志 / 首页域评测（agent_eval / domains / task）

INT-2461 交付物之一。M1 的验收口径是「每域 10 条任务 + Skill 触发准确率 ≥ 90%」，
本目录覆盖任务 5 条 + 日志 3 条 + 首页 2 条，INT-2465（m1-08）汇总跑。

## 文件

| 文件 | 内容 |
|---|---|
| `golden_tasks.json` | 10 条 golden task（utterance → 动作 / 参数 → 目标 MCP 工具与 REST 路径；日志诊断 1 条是本地聚合）+ 两个 Skill 各自 10 条其他域负样本 |
| `test_task_domain_eval.py` | 工具契约、动作参数白名单、golden task 解析、诊断聚合（来源 ID）、ToolGateway 本地聚合、Skill L1/L2 与触发准确率、真机契约核对 |

## 跑法

```text
# 默认离线（不连栈、不连库）
python -m pytest tests/agent_eval/domains/task -q

# 真机契约核对（本机 docker 网关 15000，可用 AGENT_EVAL_BASE / USER / PASSWORD 覆盖）
$env:AGENT_EVAL_LIVE='1'; python -m pytest tests/agent_eval/domains/task -q -k live
```

## golden task 口径

- `arguments` 只用对应意图工具 Schema 里声明过的参数；
- `expected_path` 是网关真实路由 + 查询串，测试按「路径 + 查询字典」比对；
- `log-03`（`diagnose`）是本地聚合，`expected_path` 为 null：测试断言
  `resolve_rest_call` 明确把它交给 ToolGateway，而不是解析成 REST；
- 负样本按 Skill 分开（`negatives` 以 Skill 名为键），只用于触发准确率，
  不参与工具解析；
- 新增动作时同步 `golden_tasks.json` 与 `shared/agent_tools/intent_tools.py`
  的动作表，否则 `test_golden_task_actions_exist_in_action_mappings` /
  `test_task_skill_l2_documents_every_action` 会失败。
