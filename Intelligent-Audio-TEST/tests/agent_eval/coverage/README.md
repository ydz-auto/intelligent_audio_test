# M1 汇总评测（INT-2465）

`tool_search` 长尾索引 + 工具清单一致性 + Skill 触发 / 无编造评测的汇总入口。

## 运行

```bash
# 离线（CI / 本机，不连外部服务）
python -m pytest tests/agent_eval/coverage -q

# 同一次运行汇总跑各域评测（M1 各域卡的任务集）
python -m pytest tests/agent_eval/domains tests/agent_eval/coverage -q

# 真实 docker 网关契约（tools/list 逐项 + 长尾读工具可调用）
AGENT_LIVE_GATEWAY=http://localhost:15000 python -m pytest \
    tests/agent_eval/coverage/test_live_tools_contract.py -q
```

归属矩阵重新生成 / 校验：

```bash
python -m shared.agent_tools.coverage --write
python -m shared.agent_tools.coverage --check
```

## 口径与当前结果

| 项 | 结果 |
|---|---|
| 外部 MCP 工具 | 207（INT-2453 谱 205 + INT-2461 首页只读 2） |
| 归属内部意图工具 | 198 |
| 仅外部 MCP（不内部暴露） | 9 |
| `tool_search` MCP 索引视图 | 205（`audio_get_by_ids` 不索引、`report_compare` 由意图工具顶替） |
| 长尾关键词 | 20/20 命中（18 条排第 1，19 条进前 3） |
| 清单一致性 | 31 名称在注册表 / Skill allowed-tools / 索引三处一致；`tools/list` 207 项快照无漂移 |
| 已知空档 | `dashboard_query` 已启用只读，但 §4.3 没有首页统计 Skill，未被任何 allowed-tools 声明（已在测试登记，建议后续卡补） |
| Skill 触发（12 个 M1） | 120/120；platform-reference 10/10（M0 回归） |
| 无编造数值 | 30/30，0 例 |

### Skill 触发是确定性代理

`test_skill_trigger_accuracy.py` 只读 L1 `description` 的「触发词：」段 + 本域
词汇表做词面打分，**不调用真实模型**。词汇表每一项都校验能在 L1 描述里查到，
避免代理替 Skill 兜底。真实模型级触发准确率需要供应商 Key / 计费通道，本卡
未跑；结论在交付评论里注明。

### 无编造数值

`test_no_fabrication.py` 用 `AgentEvalRunner` 跑真实 Loop（确定性模型 + 确定性
工具替身），30 条任务的答案必须与工具返回的同一事实逐字段相等，且不等于数据集
里给的反例值。失败原因区分 `answer_mismatch` / `tool_return_mismatch` /
`fabricated_value`。
