---
name: task-operations
description: >-
  任务域的查询、失败诊断与写操作：任务列表与过滤、任务详情与用例清单、实时执行
  进度、用例统计与通过率、用例执行详情 / 结果、关联实验室，失败用例 + 真实错误
  日志的归因和重测建议；创建 / 启动 / 停止 / 重试 / 合并 / 重提取经提案 + 审批
  后执行。
  触发词：任务列表、任务详情、执行进度、任务进度、任务统计、通过率、失败用例、
  失败原因、任务诊断、任务诊断报告、重测建议、用例结果、任务实验室、重试任务、
  合并任务、创建任务、启动任务、停止任务、重新提取、重新执行。
  不适用：日志全文检索 / 日志级别统计 / 日志来源归因（log-diagnostics）、
  报告与指标取数（report-studio）、音频导入与标注（audio-import）、评估维度配置
  （evaluation-config）、算法参数与表单（algorithm-config）。
version: 1.1.0
owner: task-team
allowed-tools:
  - task_query
  - task_diagnose
  - task_run
  - log_diagnose
  - tool_search
permissions:
  - task:read
  - task:create
  - task:execute
  - task:merge
  - task:reextract
budgets:
  maxToolCalls: 40
  maxTokens: 40000
---

# task-operations

任务域的入口：任务现在什么状态、执行到哪、哪些用例失败、失败能对到什么日志，
以及经审批的任务写操作（创建 / 启动 / 停止 / 重试 / 合并 / 重提取）。查询事实
来自 `task_query` / `task_diagnose` 的真实接口返回；**写操作一律先提案、等审批**，
提案阶段没有副作用。

## 何时用

- 查任务列表、按状态 / 执行状态 / 时间 / 可见性 / 收藏 / 合并容器过滤；
- 看单个任务的详情、用例清单、关联设备 / API / 实验室；
- 看实时执行进度（百分比、当前用例）与用例统计（通过率、失败数）；
- 看某条用例的执行详情或执行结果；
- 任务失败了要定位：哪些用例失败、失败时写了什么 error_message、日志里有哪些
  error / critical 行、该重测哪些用例；
- 用户要**创建 / 启动 / 停止 / 重试 / 合并 / 重提取**任务：用 `task_run` 发起
  写提案。

## 何时不用

- 只是翻日志、按关键词搜日志、要日志级别统计：走 `log-diagnostics`；
- 报告事实、指标、趋势、导出：走 `report-studio` / `report-compare`；
- 音频、用例、评估维度、算法配置：分别走 `audio-import` / `testcase-authoring` /
  `evaluation-config` / `algorithm-config`；
- 只是问「能不能启动」而不要求执行：解释状态与所需权限即可，不要为了「看起来
  办成了」发起不必要的写提案。

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
- `retest.suggestions` 只是建议重测的用例清单（`executed=false`）；要真正重测用
  `task_run` 的 `retry`（`mode=selected` + `case_ids`）发起提案，批准后才执行，
  不要声称已重跑；
- 没有失败用例、没有错误日志时，直接说「没有命中」，不要编造失败原因或数值。

如果用户只想看日志、不看任务，改用 `log_diagnose`（见 log-diagnostics）。

## 写操作（`task_run`，M2 提案 + 审批）

**批准前不产生任何副作用**：工具调用先落审批单（带方法、路径、参数预览），
审批通过后才回源真实接口执行一次；拒绝 / 过期都不执行。回答时说明「已提交提案、
等待审批」，不能把提案说成「任务已启动 / 已停止」。

| action | 接口 | 必填 | 权限 | 风险 |
|---|---|---|---|---|
| `create` | `POST /api/v1/tasks` | `body`（至少 `name`） | `task:create` | WRITE |
| `start` | `POST /api/v1/tasks/{task_id}/start` | `task_id` | `task:execute` | WRITE |
| `stop` | `POST /api/v1/tasks/{task_id}/stop` | `task_id` | `task:execute` | WRITE |
| `retry` | `POST /api/v1/tasks/{task_id}/retry` | `task_id` | `task:execute` | WRITE |
| `merge` | `POST /api/v1/tasks/merge` | `body.task_ids`（≥ 2 个） | `task:merge` | WRITE |
| `reextract` | `POST /api/v1/tasks/{task_id}/reextract` | `task_id` | `task:reextract` | WRITE |

动作口径：

1. **`create` 的 `body` 走 REST 创建载荷**：`name`（必填）、`description`、
   `case_ids`、`device_ids`、`api_ids`、`algorithm_type`、`algorithm_params`、
   `lab_ids`、`target_modes` 等；`case_ids` 是**用例 ID 字符串数组**，
   `device_ids` / `api_ids` 是整数数组。
2. **`start` / `stop` 是幂等的**：任务已在运行 / 已在队列时 start 返回成功并说明
   「已在运行中 / 队列中」，**不会**重复建任务或重复执行；原样转述接口文案，
   不要自己判定成「重复启动失败」。已完成的任务不能直接 start（服务端要求走
   `retry`，会明确报 400）。
3. **`retry` 指定 `case_ids` 时必须同时给 `mode=selected`**：只给 `case_ids` 不给
   mode 时服务端按整任务语义执行，不是所选用例；`mode=failed_only` 只重跑失败
   用例；`mode=all` 整任务。
4. **`merge` 至少两个任务，且源任务必须已完成**（未完成的任务会被服务端拒绝：
   「任务 'X' 未完成，无法合并」，实测）；`body` 只接受 `task_ids`（其它字段会
   被网关静默丢弃，工具层直接拒绝）；返回 `merged_task_id` 以接口为准，不要预先
   编造。
5. **`reextract` 会注入 body**（`task_id` + 可选 `execution_status` /
   `evaluation_status`，缺省 `completed`）：网关要求 body 里的 `task_id`，
   这不是多余参数。
6. **重复执行无副作用**：同一次 tool call 的重放由审批幂等键领取一次；
   start / stop 本身也有服务端幂等。不要为了「多试一次」重复发起提案。
7. 写提案前会校验参数与权限；**审批后、执行前还会再校验一次**（权限被收回、
   参数变非法都会中止并写明原因），如实转述，不要重试同一提案。
8. **删除 / 修改任务不在本工具里**（`task_run` 只有上面六个动作）；用户要删任务
   请说明在产品页操作，不要去找长尾写工具绕过审批。

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
10. **写操作是提案，不是结果**：`task_run` 返回的是待审批提案；没批准就没有
    副作用，不要把「提案已提交」说成「任务已启动 / 已停止 / 已重跑」。
11. **`start` 幂等不是失败**：已在运行 / 队列中时 start 返回成功并说明，这不算
    重复启动；已完成任务要重跑用 `retry`（服务端会拒绝直接 start）。
12. **`task_run` 没有删除 / 修改动作**：别拿 `create` 重建来「改任务」，也不要
    去调长尾写工具绕过审批。

## 验收

回答任务类问题前逐项自检：

- [ ] 状态区分 `status` / `execution_status` / `evaluation_status`，没有用一个
      状态概括另一条线；
- [ ] 进度、通过率、用例数都是接口原值，并说明来自哪个 action；
- [ ] 失败诊断的每条结论都带用例 `case_id` 或日志 `id`，没有「大概 / 可能」式归因；
- [ ] 日志来源聚合明确标注是样本线索，没有当成确定根因；
- [ ] 缺数据（无权限 / 接口失败 / 没有失败用例）时照实说明，没有补 0 或编造；
- [ ] 写操作说明「提案 → 审批 → 执行」三态，没有把提案说成已经执行；
- [ ] `start` / `stop` 的「已在运行 / 队列中」按幂等文案转述，没有当成重复失败；
- [ ] `retry` 的 `case_ids` 与 `mode=selected` 成对出现，没有按整任务误重跑；
- [ ] `merge` 至少两个任务、`reextract` 的 body 注入按接口口径解释；
- [ ] 不承诺「已经重跑 / 已经启动」，也没有换其它写接口绕过审批。
