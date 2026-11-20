# MCP 工具 → 意图工具归属矩阵（INT-2465）

> 本文件由 `shared/agent_tools/coverage.py` 生成，禁止手改。重新生成：`python -m shared.agent_tools.coverage --write`。

## 口径

- 外部 MCP 工具 **207** 个（INT-2453 迁移谱 205 + INT-2461 首页只读 2）。
- 意图工具 **31** 个（方案 §6.1；含 `tool_search`，业务意图工具 25 个）。
- 内部归属 **198** 个，仅外部 MCP **9** 个。
- 结论枚举：`内部归属（<意图工具>）` / `仅外部 MCP（不内部暴露）`。
- M1 阶段写 / 破坏性 MCP 工具即使可检索，执行仍被只读门禁拒绝（`APPROVAL_REQUIRED`）；M2 按本矩阵落到意图工具动作。

## 汇总

| 指标 | 数值 |
|---|---|
| MCP 工具总数 | 207 |
| 内部归属 | 198 |
| 仅外部 MCP | 9 |
| 归属到意图工具 | 20 个 |

### 无 MCP 归属的意图工具

以下意图工具是本地能力（平台口径 / 检索 / 本地聚合 / 预留 Schema），不直接绑定 MCP 工具：

`api_spec`, `driver_propose`, `memory_search`, `memory_write`, `platform_contract`, `spl_calibrate`, `task_diagnose`, `testcase_generate`, `tool_search`, `ui_action`, `ui_tree`

## 仅外部 MCP（不内部暴露）

| MCP 工具 | 理由 |
|---|---|
| `audio_get_by_ids` | 宿主语境批量读通道（不做归属校验），Agent 侧不暴露（INT-2530） |
| `data_transfer_export` | 任务数据 ZIP 离线搬运，§6.1 无对应意图工具 |
| `data_transfer_import_preview` | 任务数据 ZIP 离线搬运，§6.1 无对应意图工具 |
| `data_transfer_import` | 任务数据 ZIP 离线搬运，§6.1 无对应意图工具 |
| `favorites_list` | 跨域个人收藏 ID 列表，§6.1 无对应意图工具 |
| `benchmark_ranking` | Benchmark 域不在 §6.1 工具表内 |
| `benchmark_ranking_compute` | Benchmark 域不在 §6.1 工具表内 |
| `benchmark_baselines` | Benchmark 域不在 §6.1 工具表内 |
| `benchmark_reports` | Benchmark 域不在 §6.1 工具表内 |

## 逐项归属

`索引` 列：`mcp` = 以 MCP 条目进入 `tool_search` 索引；`intent` = 同名意图工具顶替；`excluded` = 不进入索引。

| MCP 工具 | 方法 | 权限 | 风险 | 归属结论 | 索引 | 理由 |
|---|---|---|---|---|---|---|
| `task_list` | GET | task:read | READ | 内部归属（`task_query`） | mcp | task 域GET，归 task_query |
| `task_get` | GET | task:read | READ | 内部归属（`task_query`） | mcp | task 域GET，归 task_query |
| `task_create` | POST | task:create | WRITE | 内部归属（`task_run`） | mcp | task 域写动作，归 task_run |
| `task_update` | PUT | task:update | WRITE | 内部归属（`task_run`） | mcp | task 域写动作，归 task_run |
| `task_delete` | DELETE | task:delete | WRITE | 内部归属（`task_run`） | mcp | task 域写动作，归 task_run |
| `task_start` | POST | task:execute | WRITE | 内部归属（`task_run`） | mcp | task 域写动作，归 task_run |
| `task_stop` | POST | task:execute | WRITE | 内部归属（`task_run`） | mcp | task 域写动作，归 task_run |
| `task_control` | POST | task:execute | WRITE | 内部归属（`task_run`） | mcp | task 域写动作，归 task_run |
| `task_retry` | POST | task:execute | WRITE | 内部归属（`task_run`） | mcp | task 域写动作，归 task_run |
| `task_reextract` | POST | task:reextract | WRITE | 内部归属（`task_run`） | mcp | task 域写动作，归 task_run |
| `task_merge` | POST | task:merge | WRITE | 内部归属（`task_run`） | mcp | task 域写动作，归 task_run |
| `task_stats` | GET | task:read | READ | 内部归属（`task_query`） | mcp | task 域GET，归 task_query |
| `task_get_progress` | GET | task:read | READ | 内部归属（`task_query`） | mcp | task 域GET，归 task_query |
| `task_batch_action` | POST | task:batch | WRITE | 内部归属（`task_run`） | mcp | task 域写动作，归 task_run |
| `task_validate` | POST | task:create | WRITE | 内部归属（`task_run`） | mcp | task 域写动作，归 task_run |
| `task_get_labs` | GET | task:read | READ | 内部归属（`task_query`） | mcp | task 域GET，归 task_query |
| `task_get_case_detail` | GET | task:read | READ | 内部归属（`task_query`） | mcp | task 域GET，归 task_query |
| `task_get_case_results` | GET | task:read | READ | 内部归属（`task_query`） | mcp | task 域GET，归 task_query |
| `task_remove_case` | DELETE | task:execute | WRITE | 内部归属（`task_run`） | mcp | task 域写动作，归 task_run |
| `task_update_cases` | PATCH | task:update | WRITE | 内部归属（`task_run`） | mcp | task 域写动作，归 task_run |
| `task_get_stats` | GET | task:read | READ | 内部归属（`task_query`） | mcp | task 域GET，归 task_query |
| `published_task_list` | GET | published_task:read | READ | 内部归属（`task_query`） | mcp | published 域GET，归 task_query |
| `published_task_get` | GET | published_task:read | READ | 内部归属（`task_query`） | mcp | published 域GET，归 task_query |
| `published_task_execute` | POST | published_task:execute | WRITE | 内部归属（`task_run`） | mcp | published 域写动作，归 task_run |
| `testcase_list` | GET | testcase:read | READ | 内部归属（`testcase_query`） | mcp | testcase 域GET，归 testcase_query |
| `testcase_get` | GET | testcase:read | READ | 内部归属（`testcase_query`） | mcp | testcase 域GET，归 testcase_query |
| `testcase_create` | POST | testcase:create | WRITE | 内部归属（`testcase_write`） | mcp | testcase 域写动作，归 testcase_write |
| `testcase_update` | PUT | testcase:update | WRITE | 内部归属（`testcase_write`） | mcp | testcase 域写动作，归 testcase_write |
| `testcase_delete` | DELETE | testcase:delete | WRITE | 内部归属（`testcase_write`） | mcp | testcase 域写动作，归 testcase_write |
| `testcase_copy` | POST | testcase:copy | WRITE | 内部归属（`testcase_write`） | mcp | testcase 域写动作，归 testcase_write |
| `testcase_export` | POST | testcase:import_export | WRITE | 内部归属（`testcase_query`） | mcp | 导出作业状态在用例只读子集内（M1 拦截 POST） |
| `testcase_import` | POST | testcase:import_export | WRITE | 内部归属（`testcase_write`） | mcp | 导入用例数据（M2） |
| `audio_list` | GET | audio:read | READ | 内部归属（`audio_query`） | mcp | audio 域GET，归 audio_query |
| `audio_get` | GET | audio:read | READ | 内部归属（`audio_query`） | mcp | audio 域GET，归 audio_query |
| `audio_get_by_ids` | POST | audio:read | WRITE | 仅外部 MCP（不内部暴露） | excluded | 宿主语境批量读通道（不做归属校验），Agent 侧不暴露（INT-2530） |
| `audio_update_metadata` | PUT | audio:update | WRITE | 内部归属（`audio_annotate`） | mcp | audio 域写动作，归 audio_annotate |
| `audio_convert` | POST | audio:convert | WRITE | 内部归属（`audio_annotate`） | mcp | 音频转码属音频处理写动作 |
| `audio_delete` | DELETE | audio:delete | WRITE | 内部归属（`audio_annotate`） | mcp | 删除音频属音频记录写动作 |
| `audio_get_by_md5` | POST | audio:read | WRITE | 内部归属（`audio_query`） | mcp | audio 域只读权限码，归 audio_query |
| `audio_list_tags` | GET | audio:read | READ | 内部归属（`audio_query`） | mcp | audio 域GET，归 audio_query |
| `audio_upload_progress` | GET | audio:read | READ | 内部归属（`audio_query`） | mcp | audio 域GET，归 audio_query |
| `audio_url_import` | POST | audio:upload | WRITE | 内部归属（`audio_import`） | mcp | audio 域写动作，归 audio_import |
| `audio_batch_annotations` | POST | audio:update | WRITE | 内部归属（`audio_annotate`） | mcp | audio 域写动作，归 audio_annotate |
| `audio_batch_action` | POST | audio:update | WRITE | 内部归属（`audio_annotate`） | mcp | audio 域写动作，归 audio_annotate |
| `audio_features` | GET | audio:read | READ | 内部归属（`audio_query`） | mcp | audio 域GET，归 audio_query |
| `audio_quality` | GET | audio:read | READ | 内部归属（`audio_query`） | mcp | audio 域GET，归 audio_query |
| `audio_process` | POST | audio:update | WRITE | 内部归属（`audio_annotate`） | mcp | audio 域写动作，归 audio_annotate |
| `audio_get_algorithms` | GET | audio:read | READ | 内部归属（`audio_query`） | mcp | audio 域GET，归 audio_query |
| `audio_update_algorithms` | PUT | audio:update | WRITE | 内部归属（`audio_annotate`） | mcp | audio 域写动作，归 audio_annotate |
| `audio_playback_history` | GET | audio:read | READ | 内部归属（`audio_query`） | mcp | audio 域GET，归 audio_query |
| `audio_folder_tree` | POST | audio:folder | WRITE | 内部归属（`audio_annotate`） | mcp | audio 域写动作，归 audio_annotate |
| `audio_upload_init` | POST | audio:upload | WRITE | 内部归属（`audio_import`） | mcp | audio 域写动作，归 audio_import |
| `audio_upload_register` | POST | audio:upload | WRITE | 内部归属（`audio_import`） | mcp | audio 域写动作，归 audio_import |
| `audio_upload_merge` | POST | audio:upload | WRITE | 内部归属（`audio_import`） | mcp | audio 域写动作，归 audio_import |
| `audio_upload_presign` | POST | audio:upload | WRITE | 内部归属（`audio_import`） | mcp | audio 域写动作，归 audio_import |
| `audio_upload_presign_part` | POST | audio:upload | WRITE | 内部归属（`audio_import`） | mcp | audio 域写动作，归 audio_import |
| `audio_upload_complete_direct` | POST | audio:upload | WRITE | 内部归属（`audio_import`） | mcp | audio 域写动作，归 audio_import |
| `device_list` | GET | device:read | READ | 内部归属（`device_query`） | mcp | device 域GET，归 device_query |
| `device_get` | GET | device:read | READ | 内部归属（`device_query`） | mcp | device 域GET，归 device_query |
| `device_create` | POST | device:create | WRITE | 内部归属（`device_control`） | mcp | device 域写动作，归 device_control |
| `device_update` | PUT | device:update | WRITE | 内部归属（`device_control`） | mcp | device 域写动作，归 device_control |
| `device_delete` | DELETE | device:delete | WRITE | 内部归属（`device_control`） | mcp | device 域写动作，归 device_control |
| `device_connect` | POST | device:control | WRITE | 内部归属（`device_control`） | mcp | device 域写动作，归 device_control |
| `device_disconnect` | POST | device:control | WRITE | 内部归属（`device_control`） | mcp | device 域写动作，归 device_control |
| `device_reboot` | POST | device:control | WRITE | 内部归属（`device_control`） | mcp | device 域写动作，归 device_control |
| `device_health_check` | POST | device:control | WRITE | 内部归属（`device_control`） | mcp | device 域写动作，归 device_control |
| `device_status_list` | GET | device:read | READ | 内部归属（`device_query`） | mcp | device 域GET，归 device_query |
| `device_driver_keywords` | GET | device:read | READ | 内部归属（`device_query`） | mcp | device 域GET，归 device_query |
| `device_serials` | GET | device:read | READ | 内部归属（`device_query`） | mcp | device 域GET，归 device_query |
| `device_status_history` | GET | device:read | READ | 内部归属（`device_query`） | mcp | device 域GET，归 device_query |
| `device_group_list` | GET | device:read | READ | 内部归属（`device_query`） | mcp | device 域GET，归 device_query |
| `device_group_create` | POST | device:create | WRITE | 内部归属（`device_control`） | mcp | device 域写动作，归 device_control |
| `device_group_get` | GET | device:read | READ | 内部归属（`device_query`） | mcp | device 域GET，归 device_query |
| `device_group_update` | PUT | device:update | WRITE | 内部归属（`device_control`） | mcp | device 域写动作，归 device_control |
| `device_group_move` | PUT | device:update | WRITE | 内部归属（`device_control`） | mcp | device 域写动作，归 device_control |
| `device_group_delete` | DELETE | device:delete | WRITE | 内部归属（`device_control`） | mcp | device 域写动作，归 device_control |
| `device_group_add_devices` | POST | device:update | WRITE | 内部归属（`device_control`） | mcp | device 域写动作，归 device_control |
| `device_group_remove_devices` | POST | device:update | WRITE | 内部归属（`device_control`） | mcp | device 域写动作，归 device_control |
| `device_alarm_rule_list` | GET | device:read | READ | 内部归属（`device_query`） | mcp | device 域GET，归 device_query |
| `device_alarm_rule_create` | POST | device:update | WRITE | 内部归属（`device_control`） | mcp | device 域写动作，归 device_control |
| `device_alarm_rule_update` | PUT | device:update | WRITE | 内部归属（`device_control`） | mcp | device 域写动作，归 device_control |
| `device_alarm_rule_delete` | DELETE | device:update | WRITE | 内部归属（`device_control`） | mcp | device 域写动作，归 device_control |
| `device_alarm_list` | GET | device:read | READ | 内部归属（`device_query`） | mcp | device 域GET，归 device_query |
| `device_alarm_acknowledge` | POST | device:control | WRITE | 内部归属（`device_control`） | mcp | device 域写动作，归 device_control |
| `device_batch_action` | POST | device:control | WRITE | 内部归属（`device_control`） | mcp | device 域写动作，归 device_control |
| `device_scan` | POST | device:control | WRITE | 内部归属（`device_control`） | mcp | device 域写动作，归 device_control |
| `device_shutdown` | POST | device:control | WRITE | 内部归属（`device_control`） | mcp | device 域写动作，归 device_control |
| `device_install_app` | POST | device:control | WRITE | 内部归属（`device_control`） | mcp | device 域写动作，归 device_control |
| `device_uninstall_app` | POST | device:control | WRITE | 内部归属（`device_control`） | mcp | device 域写动作，归 device_control |
| `device_get_status_history` | GET | device:read | READ | 内部归属（`device_query`） | mcp | device 域GET，归 device_query |
| `device_export` | GET | device:read | READ | 内部归属（`device_query`） | mcp | device 域GET，归 device_query |
| `device_import` | POST | device:create | WRITE | 内部归属（`device_control`） | mcp | device 域写动作，归 device_control |
| `device_test` | POST | device:control | WRITE | 内部归属（`device_control`） | mcp | device 域写动作，归 device_control |
| `device_stop_test` | POST | device:control | WRITE | 内部归属（`device_control`） | mcp | device 域写动作，归 device_control |
| `evaluation_dimension_list` | GET | evaluation:read | READ | 内部归属（`evaluation_query`） | mcp | evaluation 域GET，归 evaluation_query |
| `evaluation_dimension_get` | GET | evaluation:read | READ | 内部归属（`evaluation_query`） | mcp | evaluation 域GET，归 evaluation_query |
| `evaluation_dimension_create` | POST | evaluation:dim_manage | WRITE | 内部归属（`evaluation_manage`） | mcp | evaluation 域写动作，归 evaluation_manage |
| `evaluation_dimension_update` | PUT | evaluation:dim_manage | WRITE | 内部归属（`evaluation_manage`） | mcp | evaluation 域写动作，归 evaluation_manage |
| `evaluation_dimension_delete` | DELETE | evaluation:dim_manage | WRITE | 内部归属（`evaluation_manage`） | mcp | evaluation 域写动作，归 evaluation_manage |
| `evaluation_category_list` | GET | evaluation:read | READ | 内部归属（`evaluation_query`） | mcp | evaluation 域GET，归 evaluation_query |
| `evaluation_category_create` | POST | evaluation:category_manage | WRITE | 内部归属（`evaluation_manage`） | mcp | evaluation 域写动作，归 evaluation_manage |
| `evaluation_task_reevaluate` | POST | evaluation:execute | WRITE | 内部归属（`evaluation_manage`） | mcp | evaluation 域写动作，归 evaluation_manage |
| `report_list` | GET | report:read | READ | 内部归属（`report_query`） | mcp | report 域GET，归 report_query |
| `report_get` | GET | report:read | READ | 内部归属（`report_query`） | mcp | report 域GET，归 report_query |
| `report_by_task` | GET | report:read | READ | 内部归属（`report_query`） | mcp | report 域GET，归 report_query |
| `report_generate_task` | POST | report:create | WRITE | 内部归属（`report_generate`） | mcp | 按任务生成报告 |
| `report_update` | PUT | report:update | WRITE | 内部归属（`report_generate`） | mcp | report 域写动作，归 report_generate |
| `report_delete` | DELETE | report:delete | WRITE | 内部归属（`report_generate`） | mcp | report 域写动作，归 report_generate |
| `report_publish` | POST | report:publish | WRITE | 内部归属（`report_generate`） | mcp | report 域写动作，归 report_generate |
| `report_compare` | POST | report:compare | WRITE | 内部归属（`report_compare`） | intent | 报告对比（意图工具本地组合，不落库） |
| `report_tab_counts` | GET | report:read | READ | 内部归属（`report_query`） | mcp | report 域GET，归 report_query |
| `report_export_get` | GET | report:read | READ | 内部归属（`report_export`） | mcp | 导出（GET 形态） |
| `report_statistics` | GET | report:read | READ | 内部归属（`report_query`） | mcp | report 域GET，归 report_query |
| `report_statistics_trend` | GET | report:read | READ | 内部归属（`report_query`） | mcp | report 域GET，归 report_query |
| `report_statistics_report` | POST | report:read | WRITE | 内部归属（`report_query`） | mcp | POST 但只聚合返回统计、权限仅 report:read |
| `report_batch_delete` | POST | report:delete | WRITE | 内部归属（`report_generate`） | mcp | report 域写动作，归 report_generate |
| `report_progress` | GET | report:read | READ | 内部归属（`report_query`） | mcp | report 域GET，归 report_query |
| `report_share_create` | POST | report:update | WRITE | 内部归属（`report_generate`） | mcp | report 域写动作，归 report_generate |
| `report_share_list` | GET | report:update | READ | 内部归属（`report_query`） | mcp | report 域GET，归 report_query |
| `report_share_revoke` | DELETE | report:update | WRITE | 内部归属（`report_generate`） | mcp | report 域写动作，归 report_generate |
| `report_secondary_compare` | POST | report:compare | WRITE | 内部归属（`report_compare`） | mcp | 二次对比只读取数 |
| `report_regenerate` | POST | report:create | WRITE | 内部归属（`report_generate`） | mcp | 重新生成报告 |
| `report_export` | POST | report:read | WRITE | 内部归属（`report_export`） | intent | 导出 PDF / PPTX / HTML / MD |
| `report_case_averages` | POST | report:read | WRITE | 内部归属（`report_query`） | mcp | POST 但按过滤条件取用例平均值、权限仅 report:read |
| `report_cases` | GET | report:read | READ | 内部归属（`report_query`） | mcp | report 域GET，归 report_query |
| `report_cases_search` | POST | report:read | WRITE | 内部归属（`report_query`） | mcp | POST 但只搜索报告内用例、权限仅 report:read |
| `report_case_logs` | GET | report:read | READ | 内部归属（`report_query`） | mcp | report 域GET，归 report_query |
| `algorithm_definition_list` | GET | algorithm:read | READ | 内部归属（`algorithm_query`） | mcp | algorithm 域GET，归 algorithm_query |
| `algorithm_definition_get` | GET | algorithm:read | READ | 内部归属（`algorithm_query`） | mcp | algorithm 域GET，归 algorithm_query |
| `algorithm_definition_create` | POST | algorithm:definition_manage | WRITE | 内部归属（`algorithm_manage`） | mcp | algorithm 域写动作，归 algorithm_manage |
| `algorithm_definition_update` | PUT | algorithm:definition_manage | WRITE | 内部归属（`algorithm_manage`） | mcp | algorithm 域写动作，归 algorithm_manage |
| `algorithm_definition_delete` | DELETE | algorithm:definition_manage | WRITE | 内部归属（`algorithm_manage`） | mcp | algorithm 域写动作，归 algorithm_manage |
| `algorithm_group_list` | GET | algorithm:read | READ | 内部归属（`algorithm_query`） | mcp | algorithm 域GET，归 algorithm_query |
| `algorithm_group_create` | POST | algorithm:group_manage | WRITE | 内部归属（`algorithm_manage`） | mcp | algorithm 域写动作，归 algorithm_manage |
| `algorithm_param_list` | GET | algorithm:read | READ | 内部归属（`algorithm_query`） | mcp | algorithm 域GET，归 algorithm_query |
| `algorithm_param_create` | POST | algorithm:param_manage | WRITE | 内部归属（`algorithm_manage`） | mcp | algorithm 域写动作，归 algorithm_manage |
| `algorithm_definition_save` | PUT | algorithm:definition_manage | WRITE | 内部归属（`algorithm_manage`） | mcp | algorithm 域写动作，归 algorithm_manage |
| `algorithm_definition_draft` | PUT | algorithm:definition_manage | WRITE | 内部归属（`algorithm_manage`） | mcp | algorithm 域写动作，归 algorithm_manage |
| `algorithm_definition_draft_get` | GET | algorithm:read | READ | 内部归属（`algorithm_query`） | mcp | algorithm 域GET，归 algorithm_query |
| `algorithm_group_get` | GET | algorithm:read | READ | 内部归属（`algorithm_query`） | mcp | algorithm 域GET，归 algorithm_query |
| `algorithm_group_update` | PUT | algorithm:group_manage | WRITE | 内部归属（`algorithm_manage`） | mcp | algorithm 域写动作，归 algorithm_manage |
| `algorithm_group_delete` | DELETE | algorithm:group_manage | WRITE | 内部归属（`algorithm_manage`） | mcp | algorithm 域写动作，归 algorithm_manage |
| `algorithm_param_get` | GET | algorithm:read | READ | 内部归属（`algorithm_query`） | mcp | algorithm 域GET，归 algorithm_query |
| `algorithm_param_update` | PUT | algorithm:param_manage | WRITE | 内部归属（`algorithm_manage`） | mcp | algorithm 域写动作，归 algorithm_manage |
| `algorithm_param_delete` | DELETE | algorithm:param_manage | WRITE | 内部归属（`algorithm_manage`） | mcp | algorithm 域写动作，归 algorithm_manage |
| `algorithm_case_param_list` | GET | algorithm:read | READ | 内部归属（`algorithm_query`） | mcp | algorithm 域GET，归 algorithm_query |
| `algorithm_case_param_get` | GET | algorithm:read | READ | 内部归属（`algorithm_query`） | mcp | algorithm 域GET，归 algorithm_query |
| `algorithm_case_param_create` | POST | algorithm:case_param_manage | WRITE | 内部归属（`algorithm_manage`） | mcp | algorithm 域写动作，归 algorithm_manage |
| `algorithm_case_param_update` | PUT | algorithm:case_param_manage | WRITE | 内部归属（`algorithm_manage`） | mcp | algorithm 域写动作，归 algorithm_manage |
| `algorithm_case_param_delete` | DELETE | algorithm:case_param_manage | WRITE | 内部归属（`algorithm_manage`） | mcp | algorithm 域写动作，归 algorithm_manage |
| `algorithm_reference_param_list` | GET | algorithm:read | READ | 内部归属（`algorithm_query`） | mcp | algorithm 域GET，归 algorithm_query |
| `algorithm_reference_param_get` | GET | algorithm:read | READ | 内部归属（`algorithm_query`） | mcp | algorithm 域GET，归 algorithm_query |
| `algorithm_reference_param_create` | POST | algorithm:param_manage | WRITE | 内部归属（`algorithm_manage`） | mcp | algorithm 域写动作，归 algorithm_manage |
| `algorithm_reference_param_update` | PUT | algorithm:param_manage | WRITE | 内部归属（`algorithm_manage`） | mcp | algorithm 域写动作，归 algorithm_manage |
| `algorithm_reference_param_delete` | DELETE | algorithm:param_manage | WRITE | 内部归属（`algorithm_manage`） | mcp | algorithm 域写动作，归 algorithm_manage |
| `algorithm_mapping_list` | GET | algorithm:read | READ | 内部归属（`algorithm_query`） | mcp | algorithm 域GET，归 algorithm_query |
| `algorithm_mapping_create` | POST | algorithm:definition_manage | WRITE | 内部归属（`algorithm_manage`） | mcp | algorithm 域写动作，归 algorithm_manage |
| `algorithm_mapping_update` | PUT | algorithm:definition_manage | WRITE | 内部归属（`algorithm_manage`） | mcp | algorithm 域写动作，归 algorithm_manage |
| `algorithm_mapping_delete` | DELETE | algorithm:definition_manage | WRITE | 内部归属（`algorithm_manage`） | mcp | algorithm 域写动作，归 algorithm_manage |
| `algorithm_options` | GET | algorithm:read | READ | 内部归属（`algorithm_query`） | mcp | algorithm 域GET，归 algorithm_query |
| `algorithm_form_schema` | GET | algorithm:read | READ | 内部归属（`algorithm_query`） | mcp | algorithm 域GET，归 algorithm_query |
| `algorithm_dimension_list` | GET | algorithm:read | READ | 内部归属（`algorithm_query`） | mcp | algorithm 域GET，归 algorithm_query |
| `algorithm_dimension_create` | POST | algorithm:definition_manage | WRITE | 内部归属（`algorithm_manage`） | mcp | algorithm 域写动作，归 algorithm_manage |
| `algorithm_dimension_relation_create` | POST | algorithm:definition_manage | WRITE | 内部归属（`algorithm_manage`） | mcp | algorithm 域写动作，归 algorithm_manage |
| `algorithm_dimension_relation_update` | PUT | algorithm:definition_manage | WRITE | 内部归属（`algorithm_manage`） | mcp | algorithm 域写动作，归 algorithm_manage |
| `algorithm_dimension_relation_delete` | DELETE | algorithm:definition_manage | WRITE | 内部归属（`algorithm_manage`） | mcp | algorithm 域写动作，归 algorithm_manage |
| `algorithm_reload` | POST | algorithm:definition_manage | WRITE | 内部归属（`algorithm_manage`） | mcp | algorithm 域写动作，归 algorithm_manage |
| `algorithm_import` | POST | algorithm:definition_manage | WRITE | 内部归属（`algorithm_manage`） | mcp | algorithm 域写动作，归 algorithm_manage |
| `algorithm_bulk_delete` | POST | algorithm:definition_manage | WRITE | 内部归属（`algorithm_manage`） | mcp | algorithm 域写动作，归 algorithm_manage |
| `algorithm_extract_params` | POST | algorithm:param_manage | WRITE | 内部归属（`algorithm_manage`） | mcp | algorithm 域写动作，归 algorithm_manage |
| `algorithm_dimension_params` | GET | algorithm:read | READ | 内部归属（`algorithm_query`） | mcp | algorithm 域GET，归 algorithm_query |
| `tag_list` | GET | tag:read | READ | 内部归属（`tag_group_manage`） | mcp | tag 域GET，归 tag_group_manage |
| `tag_get` | GET | tag:read | READ | 内部归属（`tag_group_manage`） | mcp | tag 域GET，归 tag_group_manage |
| `tag_create` | POST | tag:create | WRITE | 内部归属（`tag_group_manage`） | mcp | tag 域写动作，归 tag_group_manage |
| `tag_update` | PUT | tag:update | WRITE | 内部归属（`tag_group_manage`） | mcp | tag 域写动作，归 tag_group_manage |
| `tag_delete` | DELETE | tag:delete | WRITE | 内部归属（`tag_group_manage`） | mcp | tag 域写动作，归 tag_group_manage |
| `group_list` | GET | group:read | READ | 内部归属（`tag_group_manage`） | mcp | group 域GET，归 tag_group_manage |
| `group_create` | POST | group:create | WRITE | 内部归属（`tag_group_manage`） | mcp | group 域写动作，归 tag_group_manage |
| `group_update` | PUT | group:update | WRITE | 内部归属（`tag_group_manage`） | mcp | group 域写动作，归 tag_group_manage |
| `group_delete` | DELETE | group:delete | WRITE | 内部归属（`tag_group_manage`） | mcp | group 域写动作，归 tag_group_manage |
| `task_set_visibility` | PATCH | task:share | WRITE | 内部归属（`task_run`） | mcp | task 域写动作，归 task_run |
| `testcase_set_visibility` | PATCH | testcase:share | WRITE | 内部归属（`testcase_write`） | mcp | testcase 域写动作，归 testcase_write |
| `report_set_visibility` | PATCH | report:share | WRITE | 内部归属（`report_generate`） | mcp | report 域写动作，归 report_generate |
| `tag_set_visibility` | PATCH | tag:share | WRITE | 内部归属（`tag_group_manage`） | mcp | tag 域写动作，归 tag_group_manage |
| `group_set_visibility` | PATCH | group:share | WRITE | 内部归属（`tag_group_manage`） | mcp | group 域写动作，归 tag_group_manage |
| `evaluation_dimension_set_visibility` | PATCH | evaluation:share | WRITE | 内部归属（`evaluation_manage`） | mcp | evaluation 域写动作，归 evaluation_manage |
| `data_transfer_export` | POST | task:export | WRITE | 仅外部 MCP（不内部暴露） | mcp | 任务数据 ZIP 离线搬运，§6.1 无对应意图工具 |
| `data_transfer_import_preview` | POST | task:import | WRITE | 仅外部 MCP（不内部暴露） | mcp | 任务数据 ZIP 离线搬运，§6.1 无对应意图工具 |
| `data_transfer_import` | POST | task:import | WRITE | 仅外部 MCP（不内部暴露） | mcp | 任务数据 ZIP 离线搬运，§6.1 无对应意图工具 |
| `favorites_list` | GET | - | READ | 仅外部 MCP（不内部暴露） | mcp | 跨域个人收藏 ID 列表，§6.1 无对应意图工具 |
| `task_favorite` | POST | task:read | WRITE | 内部归属（`task_run`） | mcp | 收藏是写动作（M1 只读门禁拦截） |
| `task_restore` | POST | task:delete | WRITE | 内部归属（`task_run`） | mcp | task 域写动作，归 task_run |
| `task_purge` | DELETE | task:delete | WRITE | 内部归属（`task_run`） | mcp | task 域写动作，归 task_run |
| `testcase_favorite` | POST | testcase:read | WRITE | 内部归属（`testcase_write`） | mcp | 收藏是写动作（M1 只读门禁拦截） |
| `report_favorite` | POST | report:read | WRITE | 内部归属（`report_generate`） | mcp | 收藏是写动作（M1 只读门禁拦截） |
| `benchmark_ranking` | GET | benchmark:ranking:read | READ | 仅外部 MCP（不内部暴露） | mcp | Benchmark 域不在 §6.1 工具表内 |
| `benchmark_ranking_compute` | POST | benchmark:ranking:compute | WRITE | 仅外部 MCP（不内部暴露） | mcp | Benchmark 域不在 §6.1 工具表内 |
| `benchmark_baselines` | GET | benchmark:baseline:read | READ | 仅外部 MCP（不内部暴露） | mcp | Benchmark 域不在 §6.1 工具表内 |
| `benchmark_reports` | GET | benchmark:report:read | READ | 仅外部 MCP（不内部暴露） | mcp | Benchmark 域不在 §6.1 工具表内 |
| `report_studio_create_document` | POST | report:studio:create | WRITE | 内部归属（`report_generate`） | mcp | 创建 Studio 文档草稿 |
| `report_studio_get_document` | GET | report:read | READ | 内部归属（`report_query`） | mcp | 读取 Studio 文档，只读 |
| `report_studio_update_document` | PUT | report:studio:edit | WRITE | 内部归属（`report_generate`） | mcp | 编辑 Studio 文档（M2） |
| `report_studio_export_document` | POST | report:studio:export | WRITE | 内部归属（`report_export`） | mcp | Studio 导出作业 |
| `log_list` | GET | log:read | READ | 内部归属（`log_diagnose`） | mcp | log 域GET，归 log_diagnose |
| `log_stats` | GET | log:read | READ | 内部归属（`log_diagnose`） | mcp | log 域GET，归 log_diagnose |
| `home_stats_details` | GET | home:read | READ | 内部归属（`dashboard_query`） | mcp | home 域GET，归 dashboard_query |
| `home_stats_summary` | GET | home:read | READ | 内部归属（`dashboard_query`） | mcp | home 域GET，归 dashboard_query |
