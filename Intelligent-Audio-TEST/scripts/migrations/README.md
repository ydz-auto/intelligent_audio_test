# 数据库迁移脚本

本目录存放所有数据库结构变更与种子数据脚本。表结构由 [scripts/create_all_tables.py](../create_all_tables.py)（`Base.metadata.create_all()`）初始建表，**此后的模型演进（加列 / 改类型 / 建索引 / 种子数据）一律通过本目录的迁移脚本落地**，禁止回头修改建表脚本。

## 执行顺序总览

按目录时间顺序、目录内按下列编号执行。所有脚本**幂等**（`IF NOT EXISTS` / 已存在即 SKIP），可安全重复执行。

```bash
# 前置：初始建表（仅空库需要）
python scripts/create_all_tables.py

# ── 202608 ──────────────────────────────────────────────
python scripts/migrations/202608/remove_foreign_keys_and_soft_delete.py   # ① 结构基线
python scripts/migrations/202608/add_laboratory_tables.py                 # ② 实验室扩展（可选）
python scripts/migrations/202608/add_audit_columns.py                     # ③ 审计/软删除列兜底
python scripts/migrations/202608/add_reevaluated_at.py                    # ④ 重新评估列
python scripts/migrations/202608/fix_audio_tags_types.py                  # ⑤ 列类型修复（可选）
python scripts/migrations/202608/fix_partial_unique_indexes.py --apply    # ⑥ 部分唯一索引（可选）
python scripts/migrations/202608/seed_rbac.py                             # ⑦ RBAC 种子数据

# ── 202609 ──────────────────────────────────────────────
python scripts/migrations/202609/add_pass_threshold_to_eval_params.py     # ⑧ 评估阈值列
python scripts/migrations/202609/add_task_case_device_type.py             # ⑨ 用例级设备路由列（执行域 P0）
python scripts/migrations/202609/add_published_tasks.py                   # ⑩ 已发布任务表 + 日常任务追溯字段（任务发布功能）
python scripts/migrations/202609/seed_voice_llm.py                        # ⑪ 算法/维度种子（按需）

# ── 202610 ──────────────────────────────────────────────
python scripts/migrations/202610/add_timestamp_db_defaults.py             # ⑫ 时间戳列补 DB 级 DEFAULT（INT-47，既有库对齐；全新库为 no-op）
python scripts/migrations/202610/add_benchmark_tables.py                  # ⑬ Benchmark 排行 5 表 + 指标映射种子（D1 双轨排行，INT-27 + INT-481 五表缺口）
python scripts/migrations/202610/fix_users_email_unique.py --apply        # ⑭ users 空邮箱归一化 + 非空 email 部分唯一索引（INT-84；默认 dry-run）
python scripts/migrations/202610/add_device_management_tables.py          # ⑮ 设备管理 5 表 + 索引（INT-80：分组/状态历史/告警规则/告警记录）
python scripts/migrations/202610/drop_task_type_and_testcase_test_type.py # ⑯ 废弃字段收尾：按 test_tasks.type 回填 device_type 并删 task.type / test_cases.test_type（INT-79；published_tasks.type 保留不删，INT-148；**回填被 test_tasks.type 列存在性门控，列已删即整体 SKIP——历史 NULL 行由 ㉝ INT-789 补齐**）
python scripts/migrations/202610/fix_leftover_foreign_keys_and_indexes.py # ⑯ 修复 202608 基线未生效的残留约束（INT-88：补删 FK / test_case_groups.name 唯一约束 / 外键替代索引 / deleted_at 部分索引）
python scripts/migrations/202610/add_api_rms_spl_mappings.py             # ⑰ 建 api_rms_spl_mappings 表 + apis.rms_spl_mapping_id 列（INT-61 数字域灵敏度映射，UC-0902）
python scripts/migrations/202610/add_api_output_types.py                 # ⑱ apis 加 output_types 列（INT-74 多模态输出类型）
python scripts/migrations/202610/add_api_device_adapter_columns.py       # ⑲ apis 加 device_type/adapter_class/audio_config 列（INT-68 UC-0901，audio_config 未配置回退默认格式）
python scripts/migrations/202610/cleanup_compare_report_audios_dup.py --apply  # ⑳ 存量对比报告 audios 重复对象清洗（INT-135；默认 dry-run，本环境 2026-10-11 dry-run 0 受影响、无需执行）
python scripts/migrations/202610/fix_users_schema_drift.py --apply      # ㉑ users 表旧 schema 漂移收敛 + dev 引导用户种子（INT-156；默认 dry-run）
python scripts/migrations/202610/add_user_oauth_bindings.py             # ㉒ 建 user_oauth_bindings 第三方账号绑定表（INT-147 打回 F1；全新库 create_all 已含，执行为全 SKIP）
python scripts/migrations/202610/seed_turn_eval.py                      # ㉓ 逐轮话轮评估维度种子（INT-192，1 主 + 6 子；依赖 ⑪ seed_voice_llm）
python scripts/migrations/202610/seed_env_judge.py                      # ㉔ 环境理解维度种子（INT-192，3 主；依赖 ⑪ seed_voice_llm）
python scripts/migrations/202610/seed_interruption_v2.py                # ㉕ 打断指标 v2 维度种子（INT-192，11 主 + 时延容器 + 3 子；依赖 ⑪ seed_voice_llm）
python scripts/migrations/202610/backfill_report_snapshot_freeze.py --apply  # ㉖ 存量已发布任务 report_snapshot 补冻结（INT-258；默认 dry-run）
python scripts/migrations/202610/cleanup_reeval_ghost_round_rows.py --apply  # ㉗ failed 重评幽灵失败逐轮行清理（INT-364；默认 dry-run）
python scripts/migrations/202610/add_uq_task_case_route_int604.py           # ㉘ task_case_relations (task, case, 路由) 唯一索引（INT-604；建索引前先查重，存在重复即中止）
python scripts/migrations/202610/add_published_task_type_algorithm_type.py # ㉙ published_tasks 补 type/algorithm_type 两列 + idx_published_task_algorithm_type 索引 + 历史快照回填（INT-148 已发布任务类型列，INT-659 落地运行库）
python scripts/migrations/202610/add_system_options_table.py                  # ㉚ 建 system_options 表 + 系统选项默认值种子（INT-620；全新库 create_all 已含，执行为全 SKIP）
python scripts/migrations/202610/add_report_studio_tables.py                 # ㉛ Report Studio 业务资产 4 表（INT-673：documents/versions/chart_specs/export_jobs；全新库 create_all 已含，执行为全 SKIP）
python scripts/migrations/202610/add_cherry_pick_source_result_type_int577.py  # ㉜ 挑选合并购物车/挑选集条目补 source_result_type 列（INT-577 §11-5；依赖 INT-339 cherry-pick 表已建）
python scripts/migrations/202610/backfill_task_case_device_type_int789.py --apply  # ㉝ 历史 task_case_relations.device_type/device_id 按关系表回填（INT-789：⑯ 的回填被 test_tasks.type 列存在性门控 SKIP，历史 NULL 行未补齐 → 误显「API测试」；见下执行记录）
python scripts/migrations/202610/backfill_log_operator_int806.py --apply  # ㉞ 历史审计日志操作人回填（INT-806 可选回填：category∈{auth,benchmark} 且 content 可解析 JSON 且含 operator_id 的审计行 → created_by_user_id；解析失败放弃不阻塞；默认 dry-run）
python scripts/migrations/202610/add_evaluation_deleted_by_int841.py      # ㉟ evaluation categories/dimensions 补 deleted_by_user_id（INT-841，软删操作人列）
python scripts/migrations/202610/add_benchmark_operator_columns_int844.py  # ㊱ 基准线管理操作人 user_id 补齐（INT-844：benchmark_sources/benchmark_metric_mappings 补 created_by_user_id+updated_by_user_id，benchmark_baselines/benchmark_reports 补 created_by_user_id + created_by 索引）
python scripts/migrations/202610/add_api_proxy_columns.py                 # ㊲ apis 加 proxy_type/proxy_url 两列（INT-839 被测 API 网络代理；两列均可 NULL，存量行不迁移数据）
python scripts/migrations/202610/add_derived_test_type_int1469.py --apply # ㊳ test_cases 补执行口径派生列 derived_test_type + 存量回填 + 索引（INT-1469 用例域列表/统计/取 ID 的 test_type 过滤下推 SQL；回填口径 = shared.utils.testcase_helpers.derive_case_test_type；默认 dry-run）
python scripts/migrations/202610/add_report_export_records_int1555.py    # ㊴ 建 report_export_records 报告导出历史表 + 两索引（INT-1555；INT-1609 补迁移守卫缺的建表迁移；全新库 create_all 已含，执行为全 SKIP）
python scripts/migrations/202610/add_transfer_agent_tables_int1623.py     # ㊵ 建 transfer_records / transfer_chunks 传输代理两表 + 三索引 + 唯一约束（INT-1623：create_all_tables 漏导 transfer_agent PO，模型全集收口后补的建表迁移；全新库 create_all 已含，执行为全 SKIP）
python scripts/migrations/202610/add_device_kind_int1679.py --apply     # ㊶ device_status_events 补设备类型列 device_kind（INT-1679：test/playback 区分测试设备与播放设备事件，回填 INT-1579 后写入的播放控制动作；不加索引；默认 dry-run）
python scripts/migrations/202610/add_test_result_result_type_int1510.py --apply  # ㊷ test_results 补结果类型列 result_type + 存量回填（INT-1510 §8.2.3 候选行 DB-first 零 OSS；回填只读 DB 轻量 JSON，缺键保持 NULL = 「结果类型待补充」桶；默认 dry-run）
python scripts/migrations/202610/normalize_api_meta_protocol_int1770.py --apply  # ㊸ apis.meta.protocol 存量取值归一化（INT-1770；幂等）
python scripts/migrations/202610/add_pg_stat_statements_int1783.py --apply  # ㊹ 安装 pg_stat_statements 扩展（INT-1783 PG 观测基线·档 0；服务端 shared_preload_libraries 在 docker-compose.yml 的 postgres 服务；幂等，扩展已存在即 SKIP；默认 dry-run）
python scripts/migrations/202610/add_api_param_field_path_int1747.py --apply    # ㊺ algorithm_api_params 补输出字段取值路径列 field_path（INT-1747 / C2，C0 §9.2 §9.3：非空按路径从厂商原始响应取嵌套值，空 = 按 param_code 取顶层键；VARCHAR(255) NULL 无索引；lock_timeout 5s 可经 DB_MIGRATION_LOCK_TIMEOUT_MS 覆盖；幂等，全新库 create_all 已含为全 SKIP）
python scripts/migrations/202610/add_api_id_scope_int1751.py --apply  # ㊻ algorithm_api_params 补 api_id 作用域 + 唯一索引（INT-1756 C6a；幂等）
python scripts/migrations/202610/add_data_transfer_source_maps_int1760.py  # ㊼ 建 data_transfer_source_maps 离线搬运映射表 + 唯一约束 + 两索引（INT-1760 / D0 A3-A4；建表必须在 INT-1741 ANALYZE 之前；幂等）
```

> ✅ **2026-09-07 全量迁移记录**：当前环境已执行 ①③④⑧（`remove_foreign_keys_and_soft_delete` 12 步 + `add_audit_columns` 补 24 处 + `add_reevaluated_at` + `add_pass_threshold_to_eval_params`），执行后 `UndefinedColumn` 类报错全部消除。②⑤⑥⑦⑨ 视功能需要执行。

> ✅ **2026-10-10 修复记录（INT-88）**：运行库（疑似晚于迁移重建，`create_all` 按 ORM 重新带出约束）残留 56 个外键、`test_case_groups.name` 唯一约束，且 202608 ① 的 Step 11 / Step 12 索引缺失——软删除重建类用例（tests/api）违反 FK。已执行 ⑯ 补删全部残留 FK（应用层管理引用完整性，202608 既定设计）、补建缺失索引；例外保留 `algorithm_definitions_type_key`（algorithm_definitions.type 完整唯一约束，fix_partial_unique_indexes.py 注明有意保留）。同批补执行 ⑯ 之外发现的未生效迁移 `202610/add_api_device_adapter_columns.py`（INT-68 三列）。同批核对确认 202608 ① 的 Step 2/3/6/7/8/9/10 在运行库均已生效；Step 4 为数据修复类语句，不在本次结构修复范围。

> ✅ **2026-10-12 修复记录（INT-156）**：快照恢复库 users 表为旧 schema（`password_hash`/`email` NOT NULL + legacy `role` NOT NULL，表 0 行），dev 登录引导建号必败（NotNullViolation，阻塞 INT-144 推送）。已对运行库执行 ㉑ `--apply`：password_hash/email 置 nullable、legacy role 列删除（表空无数据，0 行需回填）、种子 dev_user（role_id=1 admin，bcrypt 哈希）。验收实测 12:49：加密登录 200 + access_token、带 token `GET /api/v1/published-tasks` 200、重复登录幂等（users 保持 1 行）。同批在临时库完成红-绿自测（迁移前真实 handler 复现 NotNullViolation / 迁移后 OAuth 建号、bcrypt 校验、三遍幂等全过）。

> ✅ **2026-10-12 修复记录（INT-147 打回 F1）**：UserOAuthBinding PO 新增后存量部署缺 `user_oauth_bindings` 表，`GET/DELETE /oauth/bindings` 直接 500（UndefinedTable）。已补执行 ㉒：运行库执行为全 [SKIP]（验收方当日已按 PO 模型补建该表，脚本回读确认 5 列 + `uq_provider_user` + 双索引与 ORM 一致）；另在临时库完成建表路径验证（dry-run 不落 DDL / 首次执行建表 / 重复执行全 SKIP / 结构与 ORM 逐列比对一致）。

> ✅ **2026-10-18 修复记录（INT-659）**：已发布任务列表 `GET /api/v1/published-tasks` 恒 400（`published_tasks.type` 不存在，INT-638 接线实测发现）。已执行 ㉘：补 `type` 列 [EXEC]（`algorithm_type` 列此前已存在 [SKIP]）、建 `idx_published_task_algorithm_type`、历史快照回填 13 行（type 按快照用例级 device_type 派生 api/e2e，algorithm_type 取快照 algorithmType）。重复执行全列 [SKIP]、回填仅触碰 algorithm_type 为 NULL 的行（快照无 algorithmType 的行写出 NULL 值无变化，幂等无报错）。同批修正 ⑯ `drop_task_type_and_testcase_test_type.py` 反向冲突：`DROP_COLUMNS` 移除 `('published_tasks', 'type')`（INT-148 裁定该列保留），dry-run 确认不再尝试删除该列；本次运行库实测该脚本 dry-run 全 [SKIP]（test_tasks.type / test_cases.test_type 此前已删除）。验收实测：真实后端带/不带 `type` 筛选参数 `GET /api/v1/published-tasks` 均恢复 200。

> ✅ **2026-10-18 执行记录（INT-673）**：Report Studio 业务资产 4 表已执行 ㉚（全新库 create_all 已含，执行为全 SKIP；运行库本次全部 APPLY 11 步：4 表 + 7 索引）。同批执行 ⑦ seed_rbac.py 注册 `report:studio:create/edit/undo/export` 4 码 + tester/algo_engineer 授权矩阵（幂等，重跑 0 新增）。临时库红-绿自测：建表路径 APPLY → 重复执行全 SKIP → 结构逐列与 ORM 对齐 → 销毁。

> ✅ **2026-10-19 执行记录（INT-789）**：任务用例被测设备类型数据回填。⑯ 的 device_type 回填被 `test_tasks.type` 列存在性门控整体 SKIP（运行库该列先删），历史 NULL 行从未补齐 → 任务列表 E2E 任务误显「API测试」。已执行 ㉝ `--apply`：按关系表确定性回填——task_api_relations→http_api、task_device_relations→physical、websocket 前缀→websocket_api，合并容器任务按设计 §3.3 不回填；device_id 一并回填（physical=task_device_relations.device_id / API=task_api_relations.api_id）。运行库本次 ① 0 行 / ② 4154 行 / ③ 0 行：执行前 `device_type` 已全量非 NULL（FEAT 评审前实测 2877 行 NULL；开发自测阶段一次 psycopg2 隐性事务回滚失败使该批提前落为 physical，值符合评审结论"本库全 dev_only"，`device_id` 全量 NULL）；执行后 `device_type` 全量 physical + `device_id` 4154 行全部回填；重复执行三步均 0 行（幂等）。临时库红-绿自测：fresh 库九分支（device-only/api-only/兼有/合并容器/既有值/无关系/ws 前缀/http 前缀/部分迁移态）全断言通过，重跑三步全 0。

> ✅ **2026-10-19 执行记录（INT-806）**：历史审计日志操作人回填 ㉞。运行库 `logs.created_by_user_id` 列已存在（列迁移先行），存量行全 NULL → 按 content JSON `operator_id` 回填（category=auth 审计行；benchmark 行 content 为用户名串无 operator_id，按脚本设计不回填）。dry-run 共 578 行：待回填 452、解析失败/无 operator_id 跳过 126；`--apply` 回填 452 行（全部 category=auth，operator=admin/183 364 行 + 其余 88 行）。执行后 `logs.created_by_user_id` NULL 计数 300,673 → 300,221，auth 行已回填 452；重跑 dry-run 待回填 0（幂等）。数据仅 UPDATE、无 DDL，无需停服务。

> ✅ **2026-10-19 执行记录（INT-844）**：基准线管理操作人 user_id 补齐 ㉟。运行库与隔离库各执行一次：benchmark_sources / benchmark_metric_mappings 补 created_by_user_id + updated_by_user_id、benchmark_baselines / benchmark_reports 补 created_by_user_id + 各 created_by 索引，重复执行全 [SKIP]（幂等）。存量旧 created_by / published_by 字符串列保留（V9.7.10 兼容，客户端自报不再作为操作人依据）。实测（report_service gRPC 直连隔离库）：带 x-user-id 创建数据源/指标映射/导入基线 → 行 created_by_user_id=当前用户；更新映射 → updated_by_user_id 正确；无 metadata（AUTH_MODE=off 等价）→ 列 NULL。同批修复 `list_baseline_versions` 的 Postgres `max(boolean)` 不兼容（is_current 转 int 聚合），此前基线导入在 Postgres 库必败（SQLite 单测未暴露）。

> ✅ **2026-10-13 移植记录（INT-192）**：补齐三族维度 seed（㉓ turn_eval / ㉔ env_judge / ㉕ interruption_v2，V9.7.10 蓝本金标对齐后移植）。运行库执行实测零插入（全原地更新/SKIP，仅 updated_at 移动，逐字段前后比对无差）；临时库（create_all + seed_voice_llm）fresh 路径实测：首轮 25 维/322 参数/110 映射全插入、重跑全 SKIP/更新零插入，临时库终态与运行库金标逐字段等价（含 api_settings deep-equal）后销毁。UPDATE 不写 status：运行库「逐轮三分类评估」status=FALSE 为现状保留（fresh 库该维为启用态，验收方如判定需对齐可手工关闭）。三个脚本依赖 ⑪ seed_voice_llm 先行（param_mappings/关联外键引用 algorithm_definitions）。



## ⚠️ 执行须知

1. **先停服务再执行**。`ALTER TABLE` / `DROP CONSTRAINT` 需要 `ACCESS EXCLUSIVE` 锁，服务运行期间会持有表锁导致迁移**无限期阻塞**（真实踩坑：`DROP CONSTRAINT` 卡死在锁等待）。已连接的空闲连接也可能阻塞 DDL，必要时重启服务释放连接。
2. **连接串**：默认连 `postgresql://intelligent_audio_test:***@localhost:5432/intelligent_audio_test`。非默认环境通过环境变量指定：
   - 多数脚本读 `DATABASE_URI`；
   - `add_audit_columns.py` 读 `.env` 的 `DATABASE_URL`（支持 `--dry-run`）；
   - `fix_audio_tags_types.py` **硬编码** `postgres/postgres@localhost`，环境不同需先改脚本。
3. **验证结果**：`python scripts/migrations/202608/add_audit_columns.py --dry-run` 输出"所有表均已包含审计列，无需迁移"即结构完整。
4. 部分脚本用法特殊：`fix_partial_unique_indexes.py` 默认 dry-run，需 `--apply` 才真正执行；`add_laboratory_tables.py` / `seed_rbac.py` 支持 `--dry-run` / `--step N`。

## 脚本明细

### 202608 — 结构基线与软删除改造

| 脚本 | 用途 | 关键操作 |
|------|------|----------|
| [remove_foreign_keys_and_soft_delete.py](202608/remove_foreign_keys_and_soft_delete.py) | 结构基线（12 步） | 删除全库 53 个外键约束；补 `deleted`/`deleted_at` 软删除列；补 `created_by_user_id`/`updated_by_user_id` 审计列；建 RBAC / OAuth 表；建软删除与外键列索引 |
| [add_laboratory_tables.py](202608/add_laboratory_tables.py) | 实验室扩展 | 建 `laboratories`、`task_laboratory_relations`；给 devices / playback_devices / test_results / task_case_relations / logs / task_device_relations 加 `lab_id` 及索引（spl_mappings 不加；test_cases 的 lab_id 存 config JSONB） |
| [add_audit_columns.py](202608/add_audit_columns.py) | 审计/软删除列兜底 | 以 ORM 元数据为准，逐表补齐剩余 `deleted`/`deleted_at`/`created_by_user_id`/`updated_by_user_id`（含 task_tags、test_case_tags 等关联表）并建索引；支持 `--dry-run` 预览缺失清单 |
| [add_reevaluated_at.py](202608/add_reevaluated_at.py) | 重新评估功能 | `test_tasks` 加 `reevaluated_at` / `reevaluation_count` |
| [fix_audio_tags_types.py](202608/fix_audio_tags_types.py) | 类型修复 | `audio_tags` 审计列 VARCHAR(36) → BIGINT（历史临时脚本遗留）；⚠️ 连接串硬编码 |
| [fix_partial_unique_indexes.py](202608/fix_partial_unique_indexes.py) | 唯一约束与软删除冲突 | 将 UniqueConstraint 替换为部分唯一索引（`WHERE deleted = false`），软删除记录不再占用唯一键；默认 dry-run，`--apply` 执行 |
| [seed_rbac.py](202608/seed_rbac.py) | RBAC 种子数据 | 130 个权限点、5 个系统角色（admin/tester/algo_engineer/device_admin/guest）及角色-权限映射；依赖 RBAC 表已存在（① 已建） |

### 202609 — 评估维度与算法种子

| 脚本 | 用途 |
|------|------|
| [add_pass_threshold_to_eval_params.py](202609/add_pass_threshold_to_eval_params.py) | `evaluation_dimension_params` 加 `pass_threshold` 列（评估通过阈值） |
| [add_task_case_device_type.py](202609/add_task_case_device_type.py) | `task_case_relations` 加 `device_type` / `device_id` / `lab_id` 列及索引（执行域 P0：用例级设备路由 + 实验室扩展列） |
| [add_published_tasks.py](202609/add_published_tasks.py) | 任务发布功能：建 `published_tasks` 表（不可变版本快照/版本链/归档）；`test_tasks` 加 `execution_source` / `published_task_id` / `published_task_version` 追溯列；`published_tasks.report_snapshot` 冻结报告列 |
| [seed_voice_llm.py](202609/seed_voice_llm.py) | voice_llm 算法全套种子：算法定义 / 用例参数 / 设备输出字段 / API 输入输出字段 / 参考参数 / 参数映射 / 算法-维度关联（`ON CONFLICT DO NOTHING`） |
| [seed_llm_judge_dimension.py](202609/seed_llm_judge_dimension.py) | LLM Judge 评估维度 |
| [seed_interruption_dimensions.py](202609/seed_interruption_dimensions.py) | 打断（tor / false_takeover / takeover_latency）维度 |
| [seed_env_sound_judge.py](202609/seed_env_sound_judge.py) | 环境音识别维度 |
| [seed_non_interactive_latency.py](202609/seed_non_interactive_latency.py) | 非交互时延维度 |
| [seed_noise_latency.py](202609/seed_noise_latency.py) | 噪声场景时延维度 |
| [seed_xiaoyi_dimensions.py](202609/seed_xiaoyi_dimensions.py) | 小艺指标维度 |

### 202610 — Benchmark 排行（D1 双轨排行）

| 脚本 | 用途 |
|------|------|
| [add_timestamp_db_defaults.py](202610/add_timestamp_db_defaults.py) | 时间戳列 DB 级 DEFAULT 对齐（INT-47）：以 ORM 元数据为准，对缺失 DB 级默认值的 created_at/updated_at 等时间戳列 `SET DEFAULT now()`；既有库对齐用，全新库（PO 已带 server_default）为 no-op；幂等，支持 `--dry-run` |
| [add_benchmark_tables.py](202610/add_benchmark_tables.py) | 建 `benchmark_rankings`（排行 ReadModel）/ `benchmark_metric_mappings`（指标映射单一事实源，含设计文档 §5.1 默认映射种子 13 条）/ `benchmark_sources`（外部基线数据源）/ `benchmark_baselines`（外部基线条目，导入即不可变版本快照）/ `benchmark_reports`（Benchmark 报告发布记录第五表，INT-481：发布即排行快照）五表及索引；支持 `--dry-run` |
| [add_device_management_tables.py](202610/add_device_management_tables.py) | 建 `device_groups`（设备分组，含组名未删除部分唯一索引并发兜底）/ `device_group_members`（成员关联，组内设备唯一）/ `device_status_events`（状态历史：在线/离线/健康检查/操作事件）/ `device_alarm_rules`（告警规则：离线时长/健康失败次数/CPU/内存/电池阈值）/ `device_alarms`（告警记录与确认流）五表及索引，DDL 与 device_service ORM 元数据逐列对齐；支持 `--dry-run` |
| [drop_task_type_and_testcase_test_type.py](202610/drop_task_type_and_testcase_test_type.py) | 废弃字段收尾（INT-79/差异#2） | 先按 `test_tasks.type` 回填 `task_case_relations.device_type`（api→http_api / e2e→physical / 其他→physical），再 DROP `test_tasks.type` / `test_cases.test_type`；`published_tasks.type` **保留不删**（INT-148 裁定，见 add_published_task_type_algorithm_type.py）；幂等（列已删即 SKIP）。⚠️ 回填被 `test_tasks.type` 列存在性门控——运行库该列先删即整体 SKIP，历史 NULL 行由 INT-789 ㉝ 按关系表补齐 |
| [fix_leftover_foreign_keys_and_indexes.py](202610/fix_leftover_foreign_keys_and_indexes.py) | 修复 202608 基线未生效的残留约束（INT-88） | 动态枚举并删除全库残留外键（应用层管理引用完整性，含多轮 lock_timeout 重试，被长事务阻塞时跳过并汇总）；删 `test_case_groups.name` 单列唯一约束；补建 202608 Step 11 外键替代索引清单与 Step 12 `deleted_at` 部分索引（动态枚举含 deleted/deleted_at 列的表）。例外保留 `algorithm_definitions_type_key`；支持 `--dry-run` |
| [add_api_rms_spl_mappings.py](202610/add_api_rms_spl_mappings.py) | 建 `api_rms_spl_mappings` 表 + `apis.rms_spl_mapping_id` 列（INT-61，UC-0902） | 被测 API 数字域 RMS→SPL 灵敏度映射表（API 1:N，与 E2E SPLMapping 物理域对称）及默认映射指针列；幂等，支持 `--dry-run` |
| [add_api_output_types.py](202610/add_api_output_types.py) | `apis` 加 `output_types` 列（INT-74） | 多模态输出类型 JSON 数组（OutputType 枚举值子集）；幂等，支持 `--dry-run` |
| [add_api_device_adapter_columns.py](202610/add_api_device_adapter_columns.py) | `apis` 加 `device_type` / `adapter_class` / `audio_config` 列（INT-68，UC-0901） | 被测设备类型（默认 http_api）/ 指定适配器类名 / 目标音频格式 JSON（未配置回退默认）；幂等，支持 `--dry-run`。**提测/上线窗口需人工执行**（INT-68 验收遗留提示：本环境已于 2026-10-10 随 ⑯ 修复批次补执行） |
| [cleanup_compare_report_audios_dup.py](202610/cleanup_compare_report_audios_dup.py) | 存量对比报告 `report_cases.audios` 重复对象清洗（INT-135） | INT-134 修复前落库的 comparison / secondary_comparison 报告 audios 内同一 dict 重复入列；对象级去重（保首见、保顺序，与修复后生成侧口径一致），只写 audios 字段，幂等；`--apply` 前自动备份受影响行并留档执行记录。**本环境 2026-10-11 dry-run 核查 0 受影响**（2 个存量对比报告由旧生成路径产出，不含缺陷形态数据），无需执行 |
| [add_trash_operator_and_favorites.py](202610/add_trash_operator_and_favorites.py) | CUD 操作人列 + 收藏表（INT-141） | `test_tasks`/`test_cases`/`test_reports` 补 `deleted_by_user_id`（幂等兜底补 `created_by_user_id`/`updated_by_user_id` 及索引）；建 `favorites`（task_service 管 task\|testcase）与 `report_favorites`（report_service 管 report；单库部署下 Base.metadata 表名全局唯一，不能同名复用），(user_id, entity_type, entity_id) 唯一；幂等，支持 `--dry-run` |
| [fix_users_schema_drift.py](202610/fix_users_schema_drift.py) | users 表旧 schema 漂移收敛 + dev 引导用户种子（INT-156） | 快照恢复/旧库升级场景 users 表与 ORM 模型漂移导致任何建号必败：① `password_hash` ② `email` 置 nullable（对齐 user_models.py）；③ legacy 列 `role` 按 `roles.name` 回填 `role_id` 后 **DROP COLUMN**（⚠️ 破坏性：原值删除，代码与 202608 后数据均以 role_id 为准）；④ users 表为空时种子 dev 引导用户（`DEV_DEFAULT_USERNAME`/`DEV_DEFAULT_ROLE`/`DEV_DEFAULT_PASSWORD` 环境变量可覆盖，默认 dev_user/admin/dev_password，bcrypt 哈希）。幂等（默认 dry-run，`--apply` 执行），全新库 ①②③ 为 no-op |
| [add_user_oauth_bindings.py](202610/add_user_oauth_bindings.py) | 建 `user_oauth_bindings` 第三方账号绑定表（INT-147 打回 F1） | 第三方身份绑定（user_id BIGINT / provider_id INTEGER / provider_user_id VARCHAR(255) / created_at）；`uq_provider_user (provider_id, provider_user_id)` 唯一约束——一个第三方身份至多绑定一个本地用户；索引 `ix_binding_user(user_id)` / `ix_user_oauth_bindings_provider_id(provider_id)`；无外键（应用层管理引用完整性）；幂等（缺约束自愈），支持 `--dry-run`；DDL 与 auth_service `UserOAuthBinding` ORM 元数据逐列对齐 |
| [seed_turn_eval.py](202610/seed_turn_eval.py) | 逐轮话轮评估维度种子（INT-192，移植 V9.7.10 202606） | turn_eval 主维度（仅 input+映射，无 output）+ turn_evaluation 6 子维度（三分类/接管率/未接管率/误接管率/时延均值/内容均分）；param_mappings 仅挂主维度；分类→话轮接管；INSERT 显式补 sort_order/api_status/estimated_exec_time/agg_denominator/exclude_rounds（fresh create_all 库无 DB 级默认）；UPDATE 不写 status（保留运行库现状）；幂等（运行库执行零插入） |
| [seed_env_judge.py](202610/seed_env_judge.py) | 环境理解维度种子（INT-192，移植 V9.7.10 202609） | env_judge 3 主维度（准确率 pass_rate / 平均回复时延 average / 评分 average）；case_config 轮次音频映射 3 条共享，LLM 判定维度另挂 case→correctAnswer；分类→环境理解；api_settings.group_key 仅作 V9.7.10 金标对齐保留（V9.7.31 由 task_dispatcher 运行时签名合并，不消费）；同上幂等口径 |
| [seed_interruption_v2.py](202610/seed_interruption_v2.py) | 打断指标 v2 维度种子（INT-192，移植 V9.7.10 202609） | 11 主维度（8 数量类 COUNT 模板 + 3 评分类 SCORE 模板）+「打断时延」容器 + 3 时延子维度；Step 0 物理清理旧代 interruption_metrics 树（interruption_judge 属 seed_env_sound_judge 另一族不动）；分类→打断；同上幂等口径 |
| [backfill_report_snapshot_freeze.py](202610/backfill_report_snapshot_freeze.py) | 存量已发布任务 `report_snapshot` 补冻结（INT-258） | 发布快照语义修正为「引用 + 冻结双轨」（冻结报告管理生成的真实报告 7 表渲染数据 + sourceReportId 引用）：report_snapshot 为空且源任务有未删报告 → 补冻结；存量 v1 旧结构且源报告仍在 → 升级 v2；无报告/无源任务 → 保持空态（v1 快照且报告已不在的保留原数据）；复用 task_service `freeze_report_snapshot` 单一事实源；幂等（schemaVersion=2 一律 SKIP）；默认 dry-run，`--apply` 执行 |
| [cleanup_reeval_ghost_round_rows.py](202610/cleanup_reeval_ghost_round_rows.py) | failed 重评幽灵失败逐轮行清理（INT-364，移植 V9.7.10 f02ba75e 同名脚本） | 删除「逐轮失败（round_number 非空 + failed）+ 同 (result, dimension) 整体行已 completed」的幽灵行——E2E 每轮未配评估维度 + per_round 投影残留 failed 行场景下用例被永久判 failed；随附将不再有失败维度行的用例 TaskCase 恢复 completed、限定 `--task-id` 时同步任务统计；代码侧修复（failed 重评提交前清幽灵行）已随实现落地，本脚本处理存量历史数据；缺省全库扫描（任务过滤 `%(task_id)s IS NULL OR 列 = %(task_id)s`，None 绑定 NULL 恒假的静默失效已修，审计 P3 回归 tests/unit/test_int364_cleanup_script_full_db_mode.py）；幂等，默认 dry-run，`--apply` 执行 |
| [add_uq_task_case_route_int604.py](202610/add_uq_task_case_route_int604.py) | task_case_relations (task, case, 路由) 唯一索引（INT-604 混选前置 + 评审①补录） | 同一用例可同时存在设备侧/API 侧多条 TaskCase，但 (task_id, test_case_id, COALESCE(device_type,''), COALESCE(device_id,'')) 不得重复；**建索引前先查重**——历史无 DB 唯一约束，理论存在 (task,case) 重复行，检测到即 ABORT 并列出重复行（交人工去重），避免唯一索引创建失败；幂等（索引已存在即 SKIP），支持 `--dry-run` |
| [add_cherry_pick_source_result_type_int577.py](202610/add_cherry_pick_source_result_type_int577.py) | 挑选合并购物车/挑选集条目补 `source_result_type` 列（INT-577 §11-5） | `cherry_pick_cart_items` / `cherry_pick_set_items` 各补 `source_result_type VARCHAR(50) NULL`（购物车/挑选集条目来源结果类型快照；依赖 INT-339 `add_cherry_pick_tables_int339.py` 建表先行）；幂等（逐列 information_schema 检查），支持 `--dry-run` |
| [backfill_log_operator_int806.py](202610/backfill_log_operator_int806.py) | 历史审计日志操作人回填（INT-806 可选回填） | `created_by_user_id` 为 NULL 的 category∈{auth,benchmark} 审计行：content 可解析为 JSON 且含 `operator_id`（int>0）→ 回填 `created_by_user_id=operator_id`，使「仅自己」上线即有数据；解析失败/无 operator_id 放弃不阻塞（已核验 benchmark 审计 content 为 operator 用户名串、不含 operator_id，实际只覆盖 auth 行）；幂等（非 NULL 行一律 SKIP）；默认 dry-run，`--apply` 执行 |
| [add_evaluation_deleted_by_int841.py](202610/add_evaluation_deleted_by_int841.py) | evaluation categories/dimensions 补软删操作人列（INT-841） | `categories` / `dimensions` 补 `deleted_by_user_id BIGINT NULL`（created_by/updated_by 已由 add_audit_columns 补齐；软删路径无删除人列可写）；补 `created_by_user_id` 索引兜底（幂等）；全新库 create_all 已含，执行为全 SKIP；幂等，支持 `--dry-run` |
| [add_api_proxy_columns.py](202610/add_api_proxy_columns.py) | `apis` 加网络代理两列（INT-839） | `proxy_type VARCHAR(20)`（http/https/socks5/socks5h，NULL=不用代理）+ `proxy_url VARCHAR(255)`（`user:pass@host:port`，不含 scheme，认证段必填）；两列均可 NULL，存量行不迁移数据（老数据 NULL 不报错，回归行为不变）；幂等（逐列 information_schema 检查，列已存在即 SKIP），支持 `--dry-run` |
| [add_access_tokens_table.py](202610/add_access_tokens_table.py) | 建 `access_tokens` 表（INT-1140 Access Token + skill/MCP 鉴权令牌） | 外部 agent/skill/MCP 鉴权令牌：`user_id BIGINT` / `name VARCHAR(100)` / `token_hash VARCHAR(64)`（SHA-256，`uq_access_tokens_token_hash` 唯一）/ `token_hint VARCHAR(10)`（末 4 位掩码）/ `scopes JSON`（RBAC 权限码列表，空=继承用户全部权限）/ `expires_at TIMESTAMP NULL`（NULL=永不过期）/ `status VARCHAR(20)`（enabled\|disabled）/ `last_used_at` / `last_used_ip VARCHAR(50)` / `deleted_at`（软删+status，对齐收藏/回收站语义）；索引 `ix_access_tokens_user_id(user_id)`；无外键；全新库 create_all 已含，执行为全 SKIP；幂等（缺唯一约束自愈），支持 `--dry-run` |
| [add_derived_test_type_int1469.py](202610/add_derived_test_type_int1469.py) | `test_cases` 补执行口径派生列 `derived_test_type`（INT-1469 用例域性能优化） | 用例不存储类型（⑯ 已删 `test_cases.test_type`），执行口径由 config 形态 + 上传双变体名后缀派生；列表/统计/取 ID 原先物化全量 config 后 Python 过滤（1 万用例实测 ~500ms/请求），改为写时物化该列（task_service ORM `before_insert`/`before_update` 统一刷新，口径 = `derive_case_test_type`）后 SQL 等值过滤。列 `varchar(10) NOT NULL DEFAULT 'api'` + 索引 `ix_test_cases_derived_test_type`；回填按值比对只写有差异的行；幂等，默认 dry-run，`--apply` 执行；全新库 `create_all` 已含列与索引 |

| [add_logs_query_indexes_int1468.py](202610/add_logs_query_indexes_int1468.py) | logs 表过滤索引补齐（INT-1468 日志域压测） | 读侧过滤一律走 `lower(level/module/category)`，既有裸列索引匹配不上 → 全表扫描；新增函数索引 `idx_logs_lower_level_id(lower(level), id)` / `idx_logs_lower_module_id` / `idx_logs_lower_category_id`（尾列 id 覆盖 `ORDER BY id DESC` 分页序）与 `idx_logs_task_id_id(task_id, id)`（任务日志合并视图按 id 倒序拉取）；不新增 created_at 索引（读侧从不按 created_at 过滤，业务时间列 time 已有 idx_time）；幂等（`CREATE INDEX IF NOT EXISTS`），支持 `--dry-run` |
| [add_report_export_records_int1555.py](202610/add_report_export_records_int1555.py) | 建 `report_export_records` 报告导出历史表（INT-1555 导出历史接口） | 报告中心「导出历史」页签数据源：`id BIGSERIAL PK` / `report_ids JSON NOT NULL`（导出范围原始 ID 列表）/ `scope VARCHAR(255)`（范围描述：单报告名 / 已选择 N 个报告）/ `format VARCHAR(10)`（csv\|excel\|pdf\|html）/ `status VARCHAR(20)`（done\|failed）/ `error TEXT NULL` / `filename VARCHAR(255) NULL` / `created_by BIGINT NULL`（x-user-id）/ `created_at`；索引 `idx_report_export_created_at(created_at)` / `idx_report_export_created_by(created_by)`；无外键；DDL 与 `report_service` `ReportExportRecord` ORM 元数据逐列对齐；全新库 create_all 已含，执行为全 SKIP；幂等（`CREATE TABLE/INDEX IF NOT EXISTS`），支持 `--dry-run`（INT-1609 为 INT-1565 迁移守卫补的建表迁移） |
| [add_transfer_agent_tables_int1623.py](202610/add_transfer_agent_tables_int1623.py) | 建 `transfer_records` / `transfer_chunks` 传输代理两表（INT-1623 迁移守卫缺口） | `transfer_agent` 的审计流水表与已收分片表：`transfer_records`（19 列：`transfer_id VARCHAR(64)` 幂等去重键唯一索引 / `pkg_type` / `src_zone` / `dst_zone` / `category` / `key` / `file_hash` / `file_size` / `chunk_size` / `meta` / `ttl_seconds` / `ephemeral` / `timestamp` / `signature` / `status` / `final_path` / `created_at` / `updated_at`）与 `transfer_chunks`（6 列 + `uq_transfer_chunk_index(transfer_id, chunk_index)`）；索引 `ix_transfer_records_transfer_id`（UNIQUE）/ `ix_transfer_records_status` / `ix_transfer_chunks_transfer_id`；无外键；DDL 与 `transfer_agent` ORM 元数据逐列对齐；全新库 create_all（INT-1623 起含两表）已建，执行为全 SKIP；幂等（`CREATE TABLE/INDEX IF NOT EXISTS` + 约束存在性检查），支持 `--dry-run` |
| [add_device_kind_int1679.py](202610/add_device_kind_int1679.py) | `device_status_events` 补设备类型列 `device_kind`（INT-1679 播放设备事件串号缺陷） | 播放设备控制事件与测试设备事件共用 `device_status_events.device_id`，而两张源表 id 各自自增、真实库已重叠 → 播放设备的 restart / reset-config / repair 留痕会串进同 id 测试设备的状态历史与监控统计（契约 §1.2 只统计测试设备）。列 `VARCHAR(20) NOT NULL DEFAULT 'test'`（枚举 `DeviceKind`：test / playback），**不加索引**（`ix_status_event_device_time(device_id, created_at)` 已覆盖两条访问路径，kind 只是命中行上的布尔过滤，播放事件基数每日个位数）；回填只命中 `source='operation' AND detail->>'operation' IN ('restart','reset-config','re-enumerate')` 且 `device_kind='test'` 的存量行（测试设备 `DeviceOperation` 取值与之无交集，不误伤）；幂等（列存在即 SKIP、回填按值比对），默认 dry-run，`--apply` 执行 |
| [add_test_result_result_type_int1510.py](202610/add_test_result_result_type_int1510.py) | `test_results` 补结果类型列 `result_type`（INT-1510 §8.2.3 候选行 DB-first 零 OSS；INT-1669 收口） | 阶段 2 candidates 行接口的 `result_type` 改为落库列，请求路径不再按 `result_data_path` 回源对象存储：加列 `varchar(50) NULL`，写时由 `submit()` 物化（优先 `data['result_type']`，否则 `shared.utils.result_data_store.materialize_result_type` 只读 DB 轻量 JSON），存量按同口径回填（只读 DB JSON、不回源 OSS，缺键保持 NULL = 「结果类型待补充」桶，读侧统一输出 `default`）；已纳入 `docker/db_bootstrap_entrypoint.py` `BOOTSTRAP_STEPS` ㊷，**部署须重建 db_bootstrap 镜像**；幂等（列已存在即 SKIP、回填按值比对），默认 dry-run，`--apply` 执行；不建索引（缺值桶 `IS NULL OR = ''` 用不上等值索引） |
| [normalize_api_meta_protocol_int1770.py](202610/normalize_api_meta_protocol_int1770.py) | `apis.meta.protocol` 存量取值归一化（INT-1770 协议词表冲突） | 前端（旧 Vue FormField / 新 Vue deviceFields）写 http/https/ws/wss，适配器维度枚举 `AdapterProtocol` 只认 http/websocket/realtime/any，旧值在建任务选适配器时直接 `ValueError`；代码侧 `registry.infer_protocol` 已按只读兼容映射兜底（https→http、ws/wss→websocket，WARNING 不抛错），本脚本把存量值回写标准词表：只命中 `meta->>'protocol'` ∈ {https, ws, wss}（大小写不敏感）的行，**不改**其它 meta 键、不碰已标准的值；经 `meta::jsonb` 改写回 json（jsonb 规范化会重排键顺序，语义不变）；已纳入 `BOOTSTRAP_STEPS` ㊸（带 `--apply`）；幂等（归一后再次执行命中 0 行），默认 dry-run 打印「归一前后对照 + 事务内回读」后回滚 |
| [add_pg_stat_statements_int1783.py](202610/add_pg_stat_statements_int1783.py) | 安装 `pg_stat_statements` 扩展（INT-1783 PG 观测基线·档 0） | 「库很卡」此前只能凭感受：监控/索引裁决/慢 SQL 复盘都缺数据源。本步只负责库内对象 `CREATE EXTENSION IF NOT EXISTS pg_stat_statements`（已存在即 SKIP），并回读 `extversion` 与四个配置项；`shared_preload_libraries=pg_stat_statements` / `pg_stat_statements.max=5000` / `pg_stat_statements.track=all` / `log_min_duration_statement=500` 落在 `docker/docker-compose.yml` 的 postgres 服务 command（预加载是服务端启动参数，运行期无法补载），库侧读到不一致只 WARN 不阻断；已纳入 `docker/db_bootstrap_entrypoint.py` `BOOTSTRAP_STEPS` ㊹（排在 INT-1741 统计兜底 ㊽ 之前，后者必须仍是最后一步），**部署须重建 db_bootstrap 镜像**；不建表、不写业务数据、不改 shared_buffers / work_mem（档 5 未批准）；默认 dry-run，`--apply` 执行 |
| [add_api_param_field_path_int1747.py](202610/add_api_param_field_path_int1747.py) | `algorithm_api_params` 补输出字段取值路径列 `field_path`（INT-1747 / C2，C0 §9.2 §9.3） | API 输出字段声明（`direction=output`）增加 `field_path VARCHAR(255) NULL`：非空时按点号 + 数组下标（`data.events[0].text`）从厂商原始响应取嵌套值，为空保持「按 `param_code` 取顶层键」的存量行为；执行侧三条 API 链共用 `shared/utils/api_output_extractor.py`，`apis.meta.result_parser` / `asr_mapping` / `trans_mapping` 只在该算法类型零输出声明时逐键兜底。**不加索引**（列只随 `algorithm_type` 的声明表查询被读取，现有部分唯一索引已覆盖）；`lock_timeout` 默认 5s（`DB_MIGRATION_LOCK_TIMEOUT_MS` 可覆盖），失败打印持锁者 pid 而不是排队；已纳入 `BOOTSTRAP_STEPS` ㊺（带 `--apply`）；幂等（列存在即 SKIP），全新库 `create_all` 已含为全 SKIP。回滚：先回退镜像再 `DROP COLUMN` |

> ✅ **2026-10-23 修复记录（INT-1565）**：㊳ 的派生列迁移脚本虽随 INT-1469 落盘（`202610/add_derived_test_type_int1469.py`），但**没接 docker db_bootstrap 引导链** —— `create_all` 只建缺失的表、不给已被 `create_all` 建过的存量表补列，真实库 / 隔离库始终没有 `test_cases.derived_test_type`，task_service 新镜像一重建即 `UndefinedColumn` 400（冒烟门禁 S2）。本卡把该步纳入 `docker/db_bootstrap_entrypoint.py` 的 `BOOTSTRAP_STEPS`（带 `--apply`，脚本默认 dry-run），存量库每次部署自动补列 + 按 `derive_case_test_type` 回填 + 建索引（幂等：列/索引存在即 SKIP、回填按值比对，全新建的库为全 SKIP）。真实 Postgres 临时库红-绿验收：`tests/integration/test_int1565_derived_test_type_migration_pg.py`（存量形态插入报 UndefinedColumn → `--apply` 后列 NOT NULL DEFAULT 'api' / 索引 / e2e 存量行回填正确 → 二次执行全 SKIP、待改 0）；静态守卫：`tests/unit/test_int1565_schema_migration_guard.py`（模型列必须有迁移脚本 + 迁移必须在引导链，基线快照 `tests/data/schema_baseline.json`）。**不跑 docker 引导链的环境（如本机 Postgres 并行栈的隔离库）仍需手工执行一次**：`DATABASE_URL=<隔离库连接串> python scripts/migrations/202610/add_derived_test_type_int1469.py --apply`。


> ✅ **2026-10-23 修复记录（INT-1609）**：INT-1555 新增整张 `report_export_records` 表时只靠 `create_all` 建表，未补建表迁移；INT-1565 的迁移守卫（基线快照采集于 INT-1555 之前，不含该表）因此把整表列判为「缺迁移」，`report_export_records.filename` / `report_export_records.report_ids` 两个列名未在迁移文本出现 → `test_every_post_baseline_column_has_migration` 红，阻断 INT-1568 集成推送。本卡补 ㊴ `add_report_export_records_int1555.py`（`CREATE TABLE/INDEX IF NOT EXISTS`，DDL 与 ORM 逐列对齐）并纳入 `docker/db_bootstrap_entrypoint.py` 的 `BOOTSTRAP_STEPS`；存量库（建库早于 INT-1555）由该步建表自愈，全新库与已含该表的库执行为全 SKIP。未改基线快照（守卫 docstring 禁止改基线绕过迁移检查）。

> ✅ **2026-10-23 修复记录（INT-1623）**：`scripts/create_all_tables.py::_import_all_models()` 从未导入 `transfer_agent` 的 PO（`TransferRecord` / `TransferChunk`），注册 87 张表、比真实全集（89 张）少两张；`tests/data/schema_baseline.json` 按这份不完整元数据采集，同样漏收这两张表。真实库有表是 `transfer_agent` 启动时自行 `create_all` 的次生路径，全新库 / 重引导库没有。更麻烦的是：INT-1565 守卫读进程级全局 `Base.metadata`，任一测试 import transfer_agent 应用层就注册进这两张表，`-n 8 --dist loadgroup` 下守卫随调度红/绿不定，阻塞 INT-1568 推送。本卡：① `create_all_tables.py` 补导入两表 + `EXPECTED_TABLE_COUNT=89`（模型全集唯一来源，漏登记即被 `tests/unit/test_int1623_transfer_tables_migration.py` 的仓库 PO 扫描抓红）；② 补 ㊵ `add_transfer_agent_tables_int1623.py` 并纳入 `BOOTSTRAP_STEPS`（存量库兜底建表，全新库全 SKIP）；③ 两表登记进基线快照（属快照漏收的存量表，不是本批新增列，登记不算绕过）。真实 Postgres 临时库实测：dry-run 全列举 → 建表/索引 → 二次执行全 SKIP → 25 列（19+6）与生产库 `information_schema` 逐项一致 → ORM 写入读回正常，用后即删。

> ✅ **2026-10-23 修复记录（INT-1652）**：db_bootstrap 的 DDL 没有锁预算 —— `ALTER TABLE` 要 `ACCESS EXCLUSIVE`，被一条应用层 `idle in transaction` 的 `ACCESS SHARE` 一挡就无限等待；发起它的 run 容器被删后 Postgres 后端不退出，永久占住 `case_algorithm_params` 的锁队列头部，algorithm_service 所有查该表的 SELECT 全部排在它后面，`/algorithm/*` 全站 60s 超时（`DEADLINE_EXCEEDED`）。修复：① `docker/db_bootstrap_entrypoint.py` 给每个迁移子进程注入 `PGOPTIONS`（`lock_timeout=5s` / `statement_timeout=300s` / `idle_in_transaction_session_timeout=60s`，可用 `DB_BOOTSTRAP_LOCK_TIMEOUT_MS` / `DB_BOOTSTRAP_STATEMENT_TIMEOUT_MS` / `DB_BOOTSTRAP_IDLE_IN_TX_TIMEOUT_MS` / `DB_BOOTSTRAP_STEP_TIMEOUT_SECONDS` 覆盖），外加 `application_name=db_bootstrap`；单步另有进程级超时兜底，失败时打印锁诊断（表名 + 持锁者 pid）并定向 terminate 本 job 的 `idle in transaction` 后端，非零退出。② 迁移脚本里「已存在即跳过」的判断一律改成 SQLSTATE（`42701`/`42P07`/`42710` 等），不再按异常文本匹配 —— SQLAlchemy 的异常串带原 SQL，`ADD COLUMN IF NOT EXISTS ...` 会让 `'exists'` 命中**所有**错误，`lock_timeout`（`55P03`）被当成「列已存在」吞掉、迁移报 SKIP 却什么都没建成（本次实测复现）。真实 Postgres 临时库验收：`tests/integration/test_int1652_ddl_lock_timeout_pg.py`（持 `ACCESS EXCLUSIVE` → DDL 在 3s 预算内失败退出 → 放锁后同一 DDL 成功 → 不留 `idle in transaction`），静态/接线守卫见 `tests/unit/test_int1652_ddl_lock_budget.py`。

> ✅ **2026-10-24 实施记录（INT-1679）**：`device_status_events` 以前没有设备类型列，而 `devices` / `playback_devices` 的 id 各自自增、真实主库已重叠（`devices` 活跃 `[9,10,11,12]`，`playback_devices` `[1..14,54..81]`），INT-1579 落的播放设备控制事件会串进同 id 测试设备的状态历史与监控统计。本卡补 ㊶ `add_device_kind_int1679.py`（`VARCHAR(20) NOT NULL DEFAULT 'test'`，**不加索引**：现有 `ix_status_event_device_time(device_id, created_at)` 已覆盖两条访问路径，kind 只是命中行上的布尔过滤）并纳入 `BOOTSTRAP_STEPS`（带 `--apply`）。实测：**真实主库只跑 dry-run** 报「列未创建、按播放控制动作预检待回填 0 行」——主库未加列、未回填，事件总数 6972 / max id 7295 前后一致。**隔离库**（`int1679_verify`，`pg_dump` 复制主库 `devices` + `device_status_events` 两表、6972 条真实事件、基线 schema 无设备类型列）红-绿：① 按旧写入形态插 3 条播放控制动作（restart / reset-config / re-enumerate）+ 1 条测试设备 `connect`；② dry-run 报待回填 3 行 → `--apply` 加列 + 回填 3 行（`connect` 保持 `test`）→ 重复 `--apply` 全 SKIP、待改 0 行；列回读 `character varying(20) NOT NULL DEFAULT 'test'`；③ 新代码读侧复核：状态历史只命中 `connect`（3 条 playback 不入）、当日 `operations=1` 不受影响；走真实播放写入口 `PlaybackCommandService._record_control_event` 再落 1 条 kind=`playback`、再落 1 条失败 playback operation 后，状态历史 / `operations` / `errors` 均不变；④ 反向回归：测试设备自己的 operation 事件仍可见、`operations` +1。隔离库与临时脚本用后即删。

## 新增迁移脚本约定
1. 放入 `scripts/migrations/YYYYMM/`，一个变更一个脚本，文件名即意图（`add_xxx` / `fix_xxx` / `seed_xxx`）。
2. 沿用现有模板：psycopg2/SQLAlchemy 直连 + savepoint 逐表回滚 + `[SKIP]` 跳过已完成项；文件头 docstring 写明目标、幂等性、用法、依赖。
3. 必须幂等——重复执行不得报错、不得产生重复数据（种子用 `ON CONFLICT DO NOTHING`）。
4. 涉及破坏性操作（DROP / 改类型）时在 docstring 与本 README 中显著标注。
5. 执行完成后更新本 README 的「执行顺序总览」与执行记录。
6. 「已就绪即跳过」只能按 SQLSTATE 判定（`42701` duplicate_column / `42P07` duplicate_table / `42710` duplicate_object / `42703` undefined_column / `42P01` undefined_table / `42704` undefined_object 等），**禁止按异常文本匹配**：SQLAlchemy 异常串里带原 SQL，`IF NOT EXISTS` 会让 `'exists'` 命中所有错误，把锁超时（`55P03`）当成「已存在」吞掉（INT-1652）。
