---
name: log-diagnostics
description: >-
  日志域只读查询与诊断：按级别 / 模块 / 分类 / 任务 / 用例 / 时间检索日志行，
  取真实级别统计（total / debug / info / warning / error / critical），并把错误
  日志按来源聚合成带日志 ID 的线索。不导出、不清除、不刷新、不归档日志，也不做
  逐行实时推送。
  触发词：日志查询、日志搜索、日志统计、错误日志、报错日志、异常日志、日志诊断、
  失败日志、日志级别、日志来源、日志行、日志关键词、查日志、看日志。
  不适用：任务进度 / 用例通过率 / 失败用例归因（task-operations）、报告与指标
  取数（report-studio）、设备离线告警（device-operations）、Agent 自身的运行
  事件流（Agent 页面）。
version: 1.0.0
owner: task-team
allowed-tools:
  - log_diagnose
  - tool_search
permissions:
  - log:read
budgets:
  maxToolCalls: 30
  maxTokens: 30000
---

# log-diagnostics

日志域只读入口：有哪些日志、什么级别、从哪个模块来、错误能对到哪几行。
所有事实来自 `log_diagnose` 的真实接口返回；本 Skill 不做写操作。

## 何时用

- 按关键词 / 级别 / 模块 / 分类 / 任务 / 用例 / 时间查日志行；
- 要各日志级别的行数统计（判断错误量级，而不是逐行看）；
- 任务或模块报错时，要错误的来源分布与样本行（带日志 ID）。

## 何时不用

- 要看任务进度、通过率、失败用例清单：走 `task-operations`
  （`task_diagnose` 会同时拉任务字段与错误日志）；
- 报告事实、指标、趋势：走 `report-studio` / `report-compare`；
- 设备离线 / 告警：走 `device-operations`；
- 要导出、清空、归档、刷新日志：写侧（`log:manage`），M1 不开放，不要承诺。

## 查询动作

`log_diagnose` 的 `action`（全部只读，权限 `log:read`）：

| action | 目标接口 | 返回形态（要点） |
|---|---|---|
| `search` | `GET /api/v1/logs` | `{items,total,page,per_page,pages}`；每行含 `id` / `time` / `level` / `category` / `module` / `content` / `mark` / `device_id` / `task_id` / `api_id` / `test_case_id` / `algorithm_type` / `user_id` |
| `stats` | `GET /api/v1/logs/stats` | `{total,debug,info,warning,error,critical}`，按级别计数 |
| `diagnose` | 本地聚合（`/logs/stats` + `/logs`） | `stats` 原值 + 取样级别的日志行 + 按 `module` / `category` 的来源聚合（带日志 ID）+ `notes` |

共用过滤参数（只在对应接口真支持的范围内生效）：

`keyword`（关键词）、`level`（级别，可逗号分隔多级别）、`module`（模块，`all` =
不过滤）、`category`（分类，`all` = 不过滤）、`task_id`、`start_time` / `end_time`
（ISO 8601）。

差异：`search` 还支持 `test_case_id`、`page` / `per_page`；`stats` 不支持
`test_case_id` / `page` / `per_page`（传了工具层直接报错，不会静默忽略）。

### `diagnose` 的取样口径

- 默认取样 `error`、`critical` 两级；显式传 `level` 时按传入级别取样；
- `max_rows` 是取样行数上限（默认 20，最大 100）；
- 级别统计**不带 level 过滤**，所以能看到完整 breakdown，用来判断样本覆盖率；
- `attribution` 只对**样本行**聚合，不是全量；全量错误数看 `stats` 的
  `error` / `critical`，`notes` 会写明样本与全量的关系；
- `notes` 还会列出接口不可用、没有命中行等事实，照实转述。

## 日志级别的接口口径

- 统计数据按 `total` / `debug` / `info` / `warning` / `error` / `critical` 分键；
- 列表行的 `level` 是日志原始值（可能是大写 `ERROR`），展示照原样；
- `level` 过滤大小写不敏感，支持逗号分隔多级别，例如 `error,critical`。

## Gotchas

1. **全局查询默认近 30 天**：不带 `task_id` 的列表 / 统计默认只查最近
   30 天（`LOG_AUDIT_QUERY_DEFAULT_DAYS`）；要查更早必须显式给
   `start_time` / `end_time`。说「没有日志」前先确认时间窗。
2. **带 `task_id` 时不加默认时间窗**，走任务维度合并视图（业务日志文件 +
   历史 DB 行）。
3. **`total` 可能是下界**：任务维度合并视图对 DB 侧拉取行数有上限
   （`LOG_DB_MERGE_MAX_ROWS`），触顶时 `total` 只代表已纳入的行数下界，
   不要拿它与业务总量做等号。
4. **日志 `id` 不是连续自增**：审计文件条目的 `id` 是事件时间游标（epoch
   微秒），历史 DB 行用 `CURSOR_FLOOR(10^12)` 隔开；引用 ID 时原样引用，
   不要按大小推断先后（先后看 `time`）。
5. **`module` / `category` / `algorithm_type` 的 `all` 等于不过滤**，不是
   「模块名叫 all」。
6. **`stats` 与 `search` 的筛选口径不同**：`stats` 不接受 `test_case_id` /
   分页；要按用例看日志行只能用 `search` 或 `diagnose`。
7. **不支持按操作人 `user_id` 过滤**（工具层未开放该参数）；「仅自己」视图
   是前端的能力，不要编造 `user_id` 参数。
8. **样本聚合不是根因**：`attribution` 按 `module` / `category` 计数，只是
   线索；要下结论必须引用具体日志 `id` + 原文。
9. **空结果不等于服务正常**：`notes` 会明确「该窗口内没有对应级别的行」，
   不能据此说系统没问题。
10. **导出 / 清空 / 归档 / 刷新是 `log:manage`**：M1 不开放，回答时说明
    当前只能查询，不要改用其它写接口。

## 验收

回答日志类问题前逐项自检：

- [ ] 引用的日志行都带真实 `id`，内容与接口返回一致，没有改写或合并行；
- [ ] 计数来自 `stats` 或明确的样本数，没有用「大概 / 很多」代替数字；
- [ ] 区分样本与全量：`attribution` 说明是基于样本，覆盖率看 `notes`；
- [ ] 说明查询时间窗（尤其全局查询默认近 30 天），没有把窗口外当成没有；
- [ ] `total` 触顶时说明是下界，没有当成精确总量；
- [ ] 涉及导出 / 清空 / 归档时说明 M1 不可执行及所需权限；
- [ ] 需要任务进度或失败用例清单时引导到 `task-operations`，没有用日志臆测。
