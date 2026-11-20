# 报告域评测（INT-2463 只读 / INT-2471 写 + Studio 链路）

评测对象两层：

1. **意图工具** `report_query` / `report_compare`（只读）与 `report_generate` /
   `report_export`（写）：动作 → MCP 工具 / 本地组合 → 网关真实路由；
   10 条只读 golden tasks（取数 6 条 + 对比 4 条，见
   `fixtures.DOMAIN_TASKS`）+ 写工具的契约与审批流用例；
2. **Skill** `report-studio` / `report-compare`：L1 触发词覆盖、L2 正文与实际接口
   口径一致、`allowed-tools` 只含已启用工具（`report-studio` 自 INT-2471 起声明
   `report_generate` / `report_export` 两个写工具，写调用一律提案 + 审批）、
   数值引用原文不做二次计算。

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
AGENT_LIVE_GATEWAY=http://127.0.0.1:15000 python -m pytest \
    tests/agent_eval/domains/report/test_report_manage_live.py -s
```

可用 `UI_TEST_USERNAME` / `UI_TEST_PASSWORD` 覆盖账号。

## 写工具与 Studio 链路（INT-2471）

- `test_report_manage_tool.py`：动作 → 网关路由映射、动作级权限、body 白名单、
  审批字段级预览、导出格式枚举与参数校验（离线）；
- `../../agent_write/test_write_report_generate_export.py`：提案 → 审批 → 执行的
  端到端审批流、`agent_session_id` 服务端注入、导出编排（定位文档 → 固定版本 →
  建作业 → 轮询）与复用、拒绝 / 权限回收 / 非法参数；
- `test_report_manage_live.py`：真实 docker 网关上的「生成 exists（不重复建报告）
  → Studio 起草 → 编辑 → 恢复 → 导出 html → 鉴权下载」链路；只写
  `接线测试_INT2471_` 前缀数据，run 结束按 doc_id 精确清理。
  PDF/PPTX 渲染与「重复导出复用同一作业」需新镜像（合入后重建 report_service）
  才能在 docker 上实测，代码层由 `tests/unit/test_report_studio.py` 覆盖。

### 手工清理（导出产物）

导出产物写在 report_service 容器内 `/app/report_studio_exports`（非宿主卷），
测试 teardown 只能删数据库行，删不掉容器里的文件。teardown 会把本 run 产出的
文件路径打印成 `docker exec <report_service 容器> rm -f <路径…>` 形式的手工命令，
需要时照抄执行即可；不复跑 live 测试时不会有新增孤儿文件。
