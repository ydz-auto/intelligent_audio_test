# 音频域 golden tasks（INT-2458）

M1 音频域只读卡提供的评测数据，由 m1-08 的统一评测器消费；本目录只放数据与口径，
不放可执行评测逻辑（统一 runner 归 m1-08，避免每域各写一套）。

## 文件

- `golden_tasks.json`：13 条 trigger / tool-selection 用例（10 条音频查询正例 +
  1 条写操作边界 + 2 条跨域负例），覆盖 `audio_query` 的全部 10 个动作。

## 字段

| 字段 | 含义 |
|---|---|
| `id` | 用例 ID，全局唯一 |
| `prompt` | 喂给 Agent 的用户消息原文 |
| `expect_skill` | `true` = 应激活 `audio-import`；`false` = 不应激活 |
| `expected_tool` | 期望模型最终调用的工具名（`null` = 不要求具体工具，按 notes 判定） |
| `expected_actions` | 期望的 `audio_query.action` 取值集合（可多选） |
| `expected_params` | 期望参数子集（评测按子集比对，不要求逐字相等） |
| `must_not_call` | 明确禁止调用的工具（写工具 / 跨域工具） |
| `expected_reply_contains` | 最终文本必须包含的关键词（可选） |
| `notes` | 判定补充说明；冲突时以 notes 为准 |

## 评测口径（对齐方案 §14）

- 触发准确率 = `expect_skill` 判定正确的用例数 / 总数，门槛 ≥ 90%；
- 工具选择：`expected_tool` / `expected_actions` 命中，且未调用 `must_not_call`；
- 无编造数值：工具返回之外的数字 / 字段判失败；
- 写操作边界：M1 下 `audio_import` / `audio_annotate` 必须被拒（`TOOL_NOT_ENABLED`），
  助手回复须说明未启用并给替代路径。

## 数据维护

- 音频 ID（12345 / 456 / 11~13）是**示例占位**，统一 runner 需在真实库栈上把
  `audio_id` 映射为可读的可见音频（如列表首条），否则用例会因资源不存在而误判；
- 修改 `audio_query` 动作 / 参数口径时同步更新本文件与 `notes`；
- 新增用例保持「一个动作至少一条正例」，写操作与跨域至少各留一条负例。
