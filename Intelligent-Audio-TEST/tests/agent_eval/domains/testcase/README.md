# 用例 / 标签域评测（agent_eval / domains / testcase）

INT-2460 交付物之一。M1 的验收口径是「每域 10 条任务 + Skill 触发准确率 ≥ 90%」，
本目录放用例域与标签 / 分组域的 golden tasks、工具契约断言与两个 Skill 的检查，
由 INT-2465（m1-08）的统一评测器汇总跑。

## 文件

| 文件 | 内容 |
|---|---|
| `golden_tasks.json` | 用例域 10 条（`testcase_tasks`）+ 标签 / 分组域 10 条（`tag_tasks`）、两个域的负样本与补充触发样本 |
| `fixtures.py` | 实测形状样例（用例列表项 / 详情 / 轮次配置 / 标签 / 分组 / 带标注的音频详情 / 用例参数） |
| `skill_support.py` | Skill 装载与确定性触发评测（L1 触发词 + 本域核心词，按词长加权） |
| `test_testcase_query_tool.py` | `testcase_query` 注册口径、动作 → 网关 GET 路由、10 条 golden task、校验 / 权限 / 404 口径、字段契约 |
| `test_testcase_generate_tool.py` | `testcase_generate` 纯函数推导、作用域 / 轮次口径、网关端到端只读与不落库、非法参数显式失败、引用资源（维度 / 播放设备 / 算法 / 分组）存在性校验与分组分页 |
| `test_testcase_skills.py` | 两个 Skill 的装载 / frontmatter / allowed-tools 只读、L2 字段覆盖、标签任务、触发准确率 ≥ 90% |
| `test_testcase_live_contract.py` | 真机契约核对（默认 skip） |

## 跑法

```text
# 默认离线（不连栈、不连库）
python -m pytest tests/agent_eval/domains/testcase -q

# 真机契约核对（本机 docker 网关 15000，可用 AGENT_EVAL_BASE / USER / PASSWORD 覆盖）
$env:AGENT_EVAL_LIVE='1'; python -m pytest tests/agent_eval/domains/testcase -q -k live
```

真机用例只发 GET，不写库（登录用 `dev_user`，与其它域同口径）。

## golden task 口径

- 用例域 `arguments` 只用 `testcase_query` Schema 里声明过的参数
  （`test_golden_task_arguments_only_use_declared_schema_fields` 校验），
  `expected_path` 是网关真实路由 + 查询串，按「路径 + 查询字典」比对；
- 标签域用长尾 MCP 工具 `tag_list` / `group_list`：`search_query` 是喂给
  `tool_search` 的原话，测试校验检索能命中该工具且 `build_path` 与
  `expected_path` 一致；
- 负样本只用于触发准确率，不参与工具解析；判定口径是「不得命中本域 Skill」
  （可命中别的域 Skill）；
- 新增动作时同步 `shared/agent_tools/intent_tools.TESTCASE_QUERY_ACTIONS`
  （或 `testcase_tools.TESTCASE_READ_TOOLS`），否则
  `test_actions_map_to_readonly_tools` / `test_every_action_targets_a_registered_gateway_get_route`
  会失败。
