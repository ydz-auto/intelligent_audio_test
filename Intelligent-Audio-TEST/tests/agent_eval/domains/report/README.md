# 报告域只读评测（INT-2463）

评测对象两层：

1. **意图工具** `report_query` / `report_compare`：动作 → MCP 只读工具 / 本地只读
   组合 → 网关真实路由；10 条 golden tasks（取数 6 条 + 对比 4 条，见
   `fixtures.DOMAIN_TASKS`）逐条解析出目标工具、REST 路径与需要断言的返回字段；
2. **Skill** `report-studio` / `report-compare`：L1 触发词覆盖、L2 正文与实际接口
   口径一致、`allowed-tools` 只含已启用的只读工具、数值引用原文不做二次计算。

## 卡面验收锚点

| 验收项 | 落点 |
|---|---|
| 该域 10 条任务走通（取数 6 + 对比 4） | `test_report_query_tool.py::test_fetch_task_runs_through_gateway`、`test_report_compare_tool.py::test_compare_task_runs_through_gateway`、`test_report_live_contract.py` |
| 指标与 Report Service 逐字段一致（不重算 / 不四舍五入） | `test_live_report_fields_match_gateway_schema`（pass_rate / total_cases 与原始 REST 比对）、`test_compare_two_reports_returns_side_by_side_facts` |
| 2 个 Skill 触发准确率 ≥ 90% | `test_report_skill.py::test_trigger_accuracy_at_least_90_percent` |
| 无编造数值：每个数字可回溯到 REST 字段 | `test_compare_projection_is_subset_of_detail_fields` + Skill 正文「引用原文」硬规则 |

## 对比为什么不调 `POST /reports/compare`

平台的对接口径（`POST /reports/compare`、`POST /reports/secondary-compare`）会
**落库生成一份新报告**，属写操作；方案 §6.1 把 `report_compare` 定为 READ，卡面
也要求「对比产物落 artifact，不写报告」。因此 Agent 侧的 `report_compare` 是
**本地只读组合**（`kind='local'`）：逐份 `GET /reports/{id}` 取权威字段并排返回，
大结果由上下文压缩落 `context_tool_result` artifact。

外部 MCP 的 1:1 工具 `report_compare`（写接口）保持不变，只是不进 Agent 通道：
`test_local_tool_never_resolves_to_mcp_write_tool` 与
`test_compare_four_tasks_and_no_report_written`（前后 tab 计数一致）双重锁定。

## 运行

离线（默认，不连 docker）：

```bash
python -m pytest tests/agent_eval/domains/report -q
```

真实网关实测（docker 栈，网关 15000，账号 dev_user / dev_password）：

```bash
AGENT_LIVE_GATEWAY=http://127.0.0.1:15000 python -m pytest \
    tests/agent_eval/domains/report/test_report_live_contract.py -s
```

可用 `UI_TEST_USERNAME` / `UI_TEST_PASSWORD` 覆盖账号。
