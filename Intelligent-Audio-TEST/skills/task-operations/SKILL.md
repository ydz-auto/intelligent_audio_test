---
name: task-operations
description: >-
  任务域的只读查询与失败诊断：任务列表与过滤、任务详情与用例清单、实时执行进度、
  用例统计与通过率、用例执行详情 / 结果、关联实验室，以及失败用例 + 真实错误日志
  的归因和重测建议。创建 / 启动 / 停止 / 重试 / 合并 / 重提取是写动作，M2 才可
  执行，本 Skill 只查询与解释，不触发重跑、不改任务状态。
  触发词：任务列表、任务详情、执行进度、任务进度、任务统计、通过率、失败用例、
  失败原因、任务诊断、任务诊断报告、重测建议、用例结果、任务实验室、重试任务、
  合并任务、创建任务。
  不适用：日志全文检索 / 日志级别统计 / 日志来源归因（log-diagnostics）、
  报告与指标取数（report-studio）、音频导入与标注（audio-import）、评估维度配置
  （evaluation-config）、算法参数与表单（algorithm-config）。
version: 1.0.0
owner: task-team
allowed-tools:
  - task_query
  - task_diagnose
  - log_diagnose
  - tool_search
permissions:
  - task:read
budgets:
  maxToolCalls: 40
  maxTokens: 40000
---

# task-operations

任务域只读入口：任务现在什么状态、执行到哪、哪些用例失败、失败能对到什么日志。
所有事实来自 `task_query` / `task_diagnose` 的真实接口返回；本 Skill 不做写操作。

## 何时用

- 查任务列表、按状态 / 执行状态 / 时间 / 可见性 / 收藏 / 合并容器过滤；
- 看单个任务的详情、用例清单、关联设备 / API / 实验室；
- 看实时执行进度（百分比、当前用例）与用例统计（通过率、失败数）；
- 看某条用例的执行详情或执行结果；
- 任务失败了要定位：哪些用例失败、失败时写了什么 error_message、日志里有哪些
  error / critical 行、该重测哪些用例。

## 何时不用

- 只是翻日志、按关键词搜日志、要日志级别统计：走 `log-diagnostics`；
- 报告事实、指标、趋势、导出：走 `report-studio` / `report-compare`；
- 音频、用例、评估维度、算法配置：分别走 `audio-import` / `testcase-authoring` /
  `evaluation-config` / `algorithm-config`；
- 要真正创建 / 启动 / 停止 / 重试 / 合并任务：M2（`task_run`）之前不可执行，
  只解释口径与所需权限，不承诺「已经提交」。

## 任务状态是三条线，不是一条

接口同时给三个状态，回答时不要混用：

| 字段 | 含义 | 取值来源 |
|---|---|---|
| `status` | 任务状态 | `pending` / `running` / `completed` / `failed` / `merged`（以及接口实际返回的其它值） |
| `execution_status` | 执行线状态 | `pending` / `queued` / `running` / `completed` / `stopped` / `failed` / `skipped` |
| `evaluation_status` | 评估线状态 | `pending` / `queued` / `running` / `calculating` / `completed` / `stopped` / `failed` / `skipped` |

执行与评估是两条独立推进的线：执行失败时评估可能显示 `skipped`（失败补写占位），
这不代表评估跑过。判断「任务是否失败」以 `execution_status` / 失败用例数为准，
不要只看 `status`。

## 查询动作

`task_query` 的 `action` 与真实接口一一对应（全部只读，权限 `task:read`）：

| action | 目标接口 | 返回形态（要点） |
|---|---|---|
| `list` | `GET /api/v1/tasks` | `{items,total,page,per_page,pages}`；行含双状态、用例数、设备 / API 简报 |
| `detail` | `GET /api/v1/tasks/{task_id}` | 任务字段 + `cases[]`（`case_id` / `name` / 双状态 / `error_message` / 轮次 / 目标）+ `devices` / `apis` / `labs` |
| `progress` | `GET /api/v1/tasks/{task_id}/progress` | `{status,execution_status,evaluation_status,total_cases,completed_cases,failed_cases,progress,current_case,updated_at}`，`progress` 是 0~100 的百分比 |
| `stats` | `GET /api/v1/tasks/{task_id}/stats` | `{total,completed,failed,pending,skipped,pass_rate,tag_stats,duration}` |
| `domain_stats` | `GET /api/v1/tasks/stats` | 任务域全量聚合 `{total,deleted_total,status_counts,trend,granularity}`，与列表筛选无关 |
| `case_detail` | `GET /api/v1/tasks/{task_id}/cases/{case_id}/detail` | 用例执行详情（`case_name`、双状态、`error_message`、`algorithm_results`、`field_mapping`、`targets` 等） |
| `case_results` | `GET /api/v1/tasks/{task_id}/cases/{case_id}/results` | `{task_id,case_id,case_name,results[]}`；每行是某个目标的一次执行结果 |
| `labs` | `GET /api/v1/tasks/{task_id}/labs` | `{task_id,labs:[{id,code,name}]}` |

### `list` 支持的过滤参数

只传接口真正生效的字段，传错字段会被网关静默忽略（工具层也会直接拒绝）：

`search`、`status`、`execution_status`、`evaluation_status`、`algorithm_type`、
`start_date` / `end_date`（创建时间，ISO 8601）、`favorite`、`deleted`（回收站）、
`merged` / `cherry_pick`（合并容器）、`merge_type`（`whole` / `picked`）、
`visibility`（`shared` / `private`）、`stats`（附带合并容器统计块）、`page` / `per_page`。

`domain_stats` 只支持 `granularity`（`day` / `week` / `month` / `year`），
其它过滤参数无效。

## 失败诊断（`task_diagnose`）

一次调用同时读四类真实数据，输出带来源 ID 的诊断：

1. 任务详情 `cases[]`：挑出 `execution_status=failed` 的用例（可只诊断某条
   `case_id`），原样带上 `error_message`；
2. 执行进度：当前 `progress`、总数 / 完成数 / 失败数、`current_case`；
3. 用例统计：`total` / `completed` / `failed` / `pending` / `skipped` / `pass_rate`；
4. 任务日志：`GET /api/v1/logs?task_id=...&level=error,critical` 的真实日志行
   （带日志 `id` / `time` / `module` / `category` / `content` / `test_case_id`）。

回答失败原因时的规则：

- 结论必须引用输出里的真实字段：用例 `case_id`、`execution_status`、
  `error_message`，或日志行 `id` + 原文片段；
- `attribution` 是按日志 `module` / `category` 聚合的**线索**（带样本日志 ID 和
  首行内容），不是根因判定；不要把它说成「确定是 X 模块的 bug」；
- `notes` 写明了哪些来源缺失（无权限 / 接口失败 / 没有失败用例），照实转述；
- `retest.suggestions` 只是建议重测的用例清单（`executed=false`），重测执行在
  M2，不要声称已重跑；
- 没有失败用例、没有错误日志时，直接说「没有命中」，不要编造失败原因或数值。

如果用户只想看日志、不看任务，改用 `log_diagnose`（见 log-diagnostics）。

## 写动作（M2 之前只解释）

| 动作 | 接口 | 权限码 |
|---|---|---|
| 创建任务 | `POST /api/v1/tasks` | `task:create` |
| 启动 / 停止 / 控制 | `POST /api/v1/tasks/{id}/start`、`/stop`、`/control` | `task:execute` |
| 重试 | `POST /api/v1/tasks/{id}/retry` | `task:execute` |
| 删除 / 修改 | `DELETE /api/v1/tasks/{id}`、`PUT /api/v1/tasks/{id}` | `task:delete` / `task:update` |
| 合并 / 挑选合并 | `POST /api/v1/tasks/merge` | `task:merge` / `task:cherry_pick` |
| 重新提取 | `POST /api/v1/tasks/{id}/reextract` | `task:reextract` |

M2 之前 `task_run` 调用返回 `TOOL_NOT_ENABLED` / `APPROVAL_REQUIRED`：
如实说明当前阶段只能解释和查询，不要换其它写接口绕过审批。

## Gotchas

1. **`progress` 是百分比（0~100），不是 0~1**；接口原样返回，不要二次换算。
2. **`task_id` 整数，`case_id` 字符串**：任务详情用例行的键是 `case_id`，
   结果行里是 `test_case_id`，别拿 `id`（结果行主键）当用例 ID。
3. **`/tasks/stats` 是任务域聚合**（`domain_stats`），`/tasks/{id}/stats` 是
   单任务用例统计（`stats`）；两者字段完全不同，别混用。
4. **`/tasks/{id}/progress` 的 `failed_cases` 与 `/stats` 的 `failed` 可能不同步**
   （一个实时、一个聚合快照）：以 `progress` 讲当前进度，以 `stats` 讲通过率，
   发现不一致就说明两个口径不同，不要自己取平均或改数。
5. **`pass_rate` 原样引用**：接口返回什么就是什么，不要根据 completed / total 重算。
6. **`cases[]` 已剔除被移除用例**（`error_message='用例已被移除'` 的行不会出现）。
7. **`start_date` / `end_date` 是创建时间**，不是执行时间；执行时间只看用例
   行的 `started_at` / `completed_at`。
8. **`favorite` / `deleted` / `merged` / `cherry_pick` 是布尔开关**：只有显式传
   `true` 才过滤，不传就是全部（`deleted=true` 才是回收站）。
9. **日志归因需要 `log:read`**：账号没有该权限时 `task_diagnose` 会跳过日志并在
   `notes` 说明；回答时不要臆测「没有日志错误」。
10. **写动作全部在 M2**：`task_run` 未启用；`task:execute` 不是读权限，别拿它
    当查询依据。

## 验收

回答任务类问题前逐项自检：

- [ ] 状态区分 `status` / `execution_status` / `evaluation_status`，没有用一个
      状态概括另一条线；
- [ ] 进度、通过率、用例数都是接口原值，并说明来自哪个 action；
- [ ] 失败诊断的每条结论都带用例 `case_id` 或日志 `id`，没有「大概 / 可能」式归因；
- [ ] 日志来源聚合明确标注是样本线索，没有当成确定根因；
- [ ] 缺数据（无权限 / 接口失败 / 没有失败用例）时照实说明，没有补 0 或编造；
- [ ] 涉及创建 / 启动 / 重试 / 合并时说明 M2 之前不可执行及所需权限；
- [ ] 不需要写接口的场合没有调用写工具，也没有承诺「已经重跑」。
