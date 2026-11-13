# 算法域评测（agent_eval / domains / algorithm）

INT-2464 交付物之一。M1 的验收口径是「每域 10 条任务 + Skill 触发准确率 ≥ 90%」，
各域卡在自己目录下放 golden tasks 与断言，INT-2465（m1-08）汇总跑。

## 文件

| 文件 | 内容 |
|---|---|
| `golden_tasks.json` | 10 条 golden task（utterance → action / 参数 → 目标 MCP 工具与 REST 路径）+ 10 条其他域负样本 |
| `test_algorithm_domain_eval.py` | 工具契约、golden task 解析、Skill L1/L2、触发准确率、真实接口口径 |

## 跑法

```text
# 默认离线（不连栈、不连库）
python -m pytest tests/agent_eval/domains/algorithm -q

# 真机契约核对（本机 docker 网关 15000，可用 AGENT_EVAL_BASE / USER / PASSWORD 覆盖）
$env:AGENT_EVAL_LIVE='1'; python -m pytest tests/agent_eval/domains/algorithm -q -k live
```

## golden task 口径

- `arguments` 只用 `algorithm_query` Schema 里声明过的参数（`test_golden_task_arguments_only_use_declared_schema_fields` 校验）；
- `expected_path` 是网关真实路由 + 查询串；测试按「路径 + 查询字典」比对，不依赖参数顺序；
- 负样本属于其他域（报告/音频/评估/SPL/任务/日志/设备），只用于触发准确率，不参与工具解析；
- 新增动作时同步 `golden_tasks.json` 与 `shared/agent_tools/intent_tools.ALGORITHM_QUERY_ACTIONS`，否则
  `test_every_action_maps_to_readonly_mcp_tool` / `test_skill_l2_documents_every_action` 会失败。
