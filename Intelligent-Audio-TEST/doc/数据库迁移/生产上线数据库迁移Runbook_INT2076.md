# 生产上线数据库迁移 Runbook（INT-2076 补全版）

> 方案一致性审计员 2026-10-27 评审产出。源：INT-2071（模拟上线·DB迁移，隔离库 :15435 57 步全过、
> 门禁 6 项全过）+ 负责人 yy dd「删 9 payload 列啥的是走的迁移脚本吗？我感觉好像很多都没走迁移脚本」
> + 需求规划师缺口 spec（7 加列 + 1 索引 + 3 DROP + 12 建表未入链）。
> 本文件把 INT-2075 两段式基线（A 必跑 DDL 46 / B 可跳过 seed 11）扩展为**完整生产上线 runbook**
> （Phase 0~6），是 INT-2077（隔离库补跑取证）与生产部署卡的**执行契约**。
> **不改任何迁移脚本代码、不跑迁移**；发现的脚本缺陷以实施卡登记（§10）。与 INT-2075 基线冲突以本文件为准。

## 0. 结论摘要

- 完整上线链：**Phase 0 准备 → Phase 1 A 段（46 结构/真修复）→ Phase 2 B 段（11 可跳过 seed）→
  Phase 3 部署闸口（未入链 DDL 20 个 + 部署前置核验）→ 部署新代码 → Phase 4 回填 →
  Phase 5 破坏性 DROP（3 个独立窗口）→ Phase 6 收尾（ANALYZE 幂等 + schema 对齐取证）**。
- 57 步引导链（BOOTSTRAP_STEPS）两段式拆分、A/B 分段与跳过判据沿用 INT-2075；本文件新增 Phase 3~6
  覆盖 INT-2071 未覆盖的缺口（§5~§8），并对 INT-2071 缺口 spec 做 4 处修正（§9）。
- 与缺口 spec 的 diff（修正证据，全部在 §9）：① 加列合计 **19 列**（spec 记 20，差 1）；②「两链都未登记」
  精度修正（5 个在 README 总览 / 1 个仅明细 / 6 个完全未登记，全部不在 BOOTSTRAP_STEPS）；
  ③ INT-1813 DROP 门禁缺 `--confirm-read-path` 会失败（INT-2077 计划需补）；④ 手动执行必须
  `DATABASE_URL` + `DATABASE_URI` **双设**（`fix_users_email_unique` 只读 DATABASE_URI，单设会连错库）。
- 评审发现 2 个脚本缺陷，已开实施卡（§10）：`fix_users_email_unique`（INT-84）连错库风险 P1、
  `drop_apis_api_url`（INT-1361）缺停用确认门禁 P2。

## 1. 依据

| 依据 | 说明 |
|---|---|
| `docker/db_bootstrap_entrypoint.py` BOOTSTRAP_STEPS | 57 步，唯一权威顺序（本 run 已核对 57 条全列） |
| `scripts/migrations/README.md` | 执行顺序总览 + 脚本明细 + 各步说明/幂等/门禁 |
| INT-2071 执行记录 | 隔离库（生产热备 `data - 副本 (3).rar` 恢复 + 57 步）逐步 [EXEC]/[SKIP]、门禁 6 项全过 |
| INT-2071 缺口评论（01a17c61） | 隔离库↔主库逐列 diff：7 加列 + 1 索引 + 3 DROP + 12 建表 |
| INT-2075 两段式基线 | `doc/数据库迁移/正式上线迁移执行基线_INT2075.md`（本文件扩展其 A/B 段） |

## 2. Phase 0 准备

1. **抓最新生产热备**：现有 `F:\新建文件夹\data - 副本 (3).rar` 非最新；runbook 在旧备份上已验证 =
   最坏情形（新备份只会多 SKIP）。上线前重抓一份并校验可恢复。
2. **逻辑备份预案**（破坏性步骤前置）：
   - `report_cases`（INT-1995 M1 前必备，脚本 `--confirm-backup` 以此为准）；
   - `test_result_dimensions`（INT-1813 M1 前）；
   - `apis`（drop_apis_api_url 前，回填是数据变换、备份兜底）；
   - `users`（fix_users_email_unique 前，删约束/索引）。
3. **环境变量约定**（本 runbook 全部脚本按此执行；**务必双设**）：
   - `DATABASE_URL` **和** `DATABASE_URI` 均指向目标库。只设 DATABASE_URL 会让
     `fix_users_email_unique.py`（只读 DATABASE_URI）连到脚本内默认 `localhost:5432` → 连错库（§10 缺陷卡）。
   - `backfill_raw_payload_pointers_int1807` 与 DROP 脚本的 `--verify-objects` 需要 OSS 凭据：
     `OSS_ENDPOINT/OSS_ACCESS_KEY/OSS_SECRET_KEY`；单桶模式必须 `OSS_BUCKET_NAME` + `OSS_KEY_PREFIX`
     （与在线服务一致，否则传到别的桶服务侧读不到，INT-1645）。
   - Windows 宿主执行加 `PYTHONIOENCODING=utf-8`（INT-2071 实测：stdout 默认 GBK，步骤 1 打印 ✅
     触发 UnicodeEncodeError）。
4. **锁风险预检**：`pg_stat_activity` 无 idle in transaction / 等锁会话；`ALTER TABLE` / `DROP CONSTRAINT`
   需 ACCESS EXCLUSIVE，生产须停业务写或低峰窗口（README 执行须知 ①）。
5. **目标库形态核对**（INT-2075 §5 三项前置，缺则 Phase 1 需插入）：
   - **INT-423 visibility 列**：旧库缺 `visibility` 列时，Phase 1 步骤 2 `remove_foreign_keys_and_soft_delete`
     无条件建 `idx_*_created_visibility` 复合索引 → UndefinedColumn。**必须在步骤 2 之前补跑**
     `scripts/migrations/202610/add_visibility_columns_int423.py`（10 表加列 + 索引）。隔离库已在 INT-2071
     补跑；全新库 create_all 已建列，无需。
   - **INT-47 时间戳 DB 级默认**：旧库时间戳列 NOT NULL 无默认时，步骤 6/14~20 等 seed 裸 INSERT →
     NotNullViolation。**必须把步骤 21 `add_timestamp_db_defaults` 提前到首个 seed（步骤 6）之前**。
   - **步骤 45 需超管**：`CREATE EXTENSION pg_stat_statements` 需超管；restored 集群
     superuser=postgres、业务账号非超管 → 以 postgres 连接执行或 DBA 完成；`shared_preload_libraries`
     须含 pg_stat_statements 才真正采集（compose postgres command 已配）。

## 3. Phase 1 A 段结构真修复（46 步）

> 判定（INT-2075 §2）：结构 DDL、schema 收敛/回填、数据真修复。全部幂等（SQLSTATE 判 SKIP，INT-1652），
> 重复执行不覆盖「比金标新」的生产数据。按 BOOTSTRAP_STEPS 编号执行，一条退出码 0 再下一条。

| # | 脚本（scripts/ 前缀） | 标志 | 为何必跑 / 注意 |
|---|---|---|---|
| 1 | `create_all_tables.py` | — | 初始建表（只建缺表，幂等） |
| 2 | `migrations/202608/remove_foreign_keys_and_soft_delete.py` | — | 结构基线：删 FK + 软删/审计列 + 索引；⚠️ 前置 INT-423（§2-5） |
| 3 | `migrations/202608/add_audit_columns.py` | — | 审计/软删列逐表兜底 |
| 4 | `migrations/202608/add_reevaluated_at.py` | — | 重评列 |
| 5 | `migrations/202608/add_laboratory_tables.py` | — | 实验室扩展 |
| 6 | `migrations/202608/seed_rbac.py` | — | RBAC 权限点 + 5 角色；⚠️ 前置 INT-47（§2-5） |
| 7 | `migrations/202609/add_pass_threshold_to_eval_params.py` | — | 评估阈值列 |
| 8 | `migrations/202609/add_task_case_device_type.py` | — | 用例级设备路由列 |
| 9 | `migrations/202609/add_published_tasks.py` | — | 已发布任务表 + 追溯列 |
| 10 | `migrations/202609/add_dimension_sort_order.py` | — | 维度排序列 |
| 11 | `migrations/202609/add_agg_denominator_column.py` | — | 聚合分母列 |
| 12 | `migrations/202609/add_exclude_rounds_column.py` | — | 排除轮次列 |
| 13 | `migrations/202609/add_worker_instance_id.py` | — | 执行实例列 |
| 21 | `migrations/202610/add_timestamp_db_defaults.py` | — | 时间戳 DB 级 DEFAULT（INT-47）；⚠️ 前置见 §2-5 |
| 22 | `migrations/202610/add_benchmark_tables.py` | — | Benchmark 排行表 |
| 23 | `migrations/202610/fix_leftover_foreign_keys_and_indexes.py` | — | 残留 FK/约束/索引修复（INT-88） |
| 24 | `migrations/202610/add_api_rms_spl_mappings.py` | — | 灵敏度映射表 + 列 |
| 25 | `migrations/202610/add_api_output_types.py` | — | apis.output_types 列 |
| 26 | `migrations/202610/add_api_device_adapter_columns.py` | — | apis 设备适配三列 |
| 27 | `migrations/202610/fix_users_schema_drift.py` | `--apply` | users schema 收敛 + dev 引导用户 |
| 28 | `migrations/202610/add_user_oauth_bindings.py` | — | 第三方绑定表 |
| 29 | `migrations/202610/add_access_tokens_table.py` | — | access_tokens 表 |
| 33 | `migrations/202610/add_operator_columns_int299.py` | — | CUD 操作人列 |
| 34 | `migrations/202610/add_trash_operator_and_favorites.py` | — | 收藏表 + 删除操作人列 |
| 35 | `migrations/202610/add_published_task_type_algorithm_type.py` | — | published_tasks 类型列 + 快照回填 |
| 36 | `migrations/202610/seed_custom_oauth_providers.py` | — | 自定义 OAuth 提供方；未配 client id 自动 SKIP |
| 37 | `migrations/202610/add_uq_task_case_route_int604.py` | — | 路由唯一索引（建前查重，重复即 ABORT） |
| 38 | `migrations/202610/add_derived_test_type_int1469.py` | `--apply` | 派生列 + 回填 + 索引 |
| 39 | `migrations/202610/add_report_export_records_int1555.py` | — | 导出历史表 |
| 40 | `migrations/202610/add_transfer_agent_tables_int1623.py` | — | transfer 两表 |
| 41 | `migrations/202610/add_device_kind_int1679.py` | `--apply` | 设备类型列 + 回填 |
| 42 | `migrations/202610/add_test_result_result_type_int1510.py` | `--apply` | 结果类型列 + 回填 |
| 43 | `migrations/202610/add_api_protocol_streaming_int1798.py` | `--apply` | apis 协议×流式 + 回填 + 删 meta.protocol |
| 44 | `migrations/202610/normalize_api_meta_protocol_int1770.py` | `--apply` | meta.protocol 取值归一（43 已删键则空转） |
| 45 | `migrations/202610/add_pg_stat_statements_int1783.py` | `--apply` | 装扩展；⚠️ 需超管（§2-5） |
| 46 | `migrations/202610/add_api_param_field_path_int1747.py` | `--apply` | field_path 列 |
| 47 | `migrations/202610/add_api_id_scope_int1751.py` | `--apply` | api_id 作用域 + 唯一索引拆分 |
| 48 | `migrations/202610/add_data_transfer_source_maps_int1760.py` | — | 搬运映射表；排在 57 前 |
| 49 | `migrations/202610/seed_voice_llm_device_output_int1748.py` | `--apply` | 真修复：输出声明 param_type 订正 |
| 50 | `migrations/202610/drop_redundant_indexes_int1784.py` | `--apply` | 冗余索引下线 + 废弃空表 |
| 51 | `migrations/202610/alter_report_studio_sources.py` | `--apply` | Report Studio 来源类型五列；排在 57 前 |
| 53 | `migrations/202610/add_raw_payload_pointers_int1807.py` | `--apply` | 报文指针十列；只加列（回填走 Phase 4） |
| 54 | `migrations/202610/add_merge_snapshots_int1762.py` | `--apply` | 合并快照两表 |
| 55 | `migrations/202610/add_report_case_snapshots_int1994.py` | `--apply` | 快照表 + report_cases 4 指针列（回填走 Phase 4） |
| 56 | `migrations/202610/fix_voice_llm_reference_params_definitions.py` | `--apply` | 真修复（INT-2040）：参考参数 3 列订正 |
| 57 | `migrations/202610/analyze_stale_statistics_int1741.py` | `--apply` | 统计兜底；**必须最后一步**，其后不得再跑 DDL/写迁移 |

> B 段编号 14~20、30~32、52 见 Phase 2；A 段执行完、B 段判定跳过后再进入 Phase 3。

## 4. Phase 2 B 段可跳过 seed（11 步）

> 判定（INT-2075 §3）：全部是「INSERT-if-missing + 已存在则按 V9.7.31 金标 UPDATE/清理」的维度/算法 seed。
> 生产库该表该维度**已有且更新于金标**时跳过；跳过判据给出可执行核对 SQL，命中即跳过，并记入执行报告。
> 跳过不破坏 A 段；B 段之间互相依赖，一并跳过即无断链。

| # | 脚本 | 跳过判据（核对 SQL，命中即跳过） | 盲跑风险 | 依赖 |
|---|---|---|---|---|
| 14 | `202609/seed_voice_llm.py` | `SELECT id FROM algorithm_definitions WHERE type='voice_llm' AND deleted=false` 有行，且 `algorithm_device_params` 已有 7 字段 | Step3/5/7 对已配库是**回退**（删会话协议字段、软删 param_mappings） | 15~20/30~32/52 的底层 |
| 15 | `202609/seed_interruption_dimensions.py` | `dimensions` 该 task_type_code 族有行 | 按金标 UPDATE | 14 |
| 16 | `202609/seed_noise_latency.py` | `task_type_code='noise_latency'` 有行 | 按金标 UPDATE | 14 |
| 17 | `202609/seed_reject_judge.py` | `task_type_code='reject_judge'` 有行 | 按金标 UPDATE | 14 |
| 18 | `202609/seed_non_interactive_latency.py` | `task_type_code='non_interactive_latency'` 有行 | 按金标 UPDATE | 14 |
| 19 | `202609/seed_xiaoyi_dimensions.py` | 6 个 task_type_code 族有行 | task_type_code 变更时**软删旧记录并新建** | 14 |
| 20 | `202609/seed_env_sound_judge.py` | `task_type_code IN ('rejection_judge','interruption_judge')` 有行 | 按金标 UPDATE | 14 |
| 30 | `202610/seed_turn_eval.py` | `task_type_code IN ('turn_eval','turn_evaluation')` 有行 | 按金标 UPDATE（UPDATE 不写 status） | 14 |
| 31 | `202610/seed_env_judge.py` | `task_type_code='env_judge'` 有行 | 全字段 UPDATE + 软删定义外残留参数 | 14 |
| 32 | `202610/seed_interruption_v2.py` | 新 11+3 名单主维度存在 | Step0 **物理删除**不在名单的旧代 interruption_metrics 树 | 14 |
| 52 | `202610/seed_api_eval_mapping_int1746.py` | `algorithm_api_params` 8 个 output 声明齐 | A 段补缺 INSERT；B 段仅对未删 llm_judge 维度 | 14 的 Step5 时序 |

> **LLM Judge 维度**（`202609/seed_llm_judge_dimension.py`）不在本 runbook（能力已裁定撤除），
> 生产库该族维度若已软删，52 的 B 段 param_mappings 自然 0 条，不补跑该 seed。

## 5. Phase 3 部署闸口（未入链 DDL 20 个 + 部署前置核验）

> 这 20 个脚本是 INT-2071 的 57 步**未覆盖**的缺口（隔离库↔主库逐列 diff 证实），全部为结构 DDL
> （建表/加列/索引/约束），新代码读写路径依赖 → **必须在部署新代码之前执行**。全部幂等；
> 隔离库上建表类脚本因表已存在将全 [SKIP]（INT-2071 门禁 4：表数 97 ≥ 89），通用老库兜底建表。
> 执行顺序：**5.1 建表类 → 5.2 加列/索引**（含依赖约束）；`--dry-run` 先预览、退出码 0 再正式执行。

### 5.1 建表类（12 个，幂等，缺表才建）

| 顺序 | 脚本 | INT | 建的表/对象 | 幂等判据 / 依赖 |
|---|---|---|---|---|
| a | `202610/add_device_management_tables.py` | 80 | device_groups / device_group_members / device_status_events / device_alarm_rules / device_alarms + 索引 | 表/索引存在即 SKIP；**先于 b** |
| b | `202610/add_device_group_parent_int832.py` | 832 | device_groups.parent_id + 两局部唯一索引（替换全局索引） | 依赖 a 的 device_groups 表；列/索引存在即 SKIP；⚠️ 基表缺失会 UndefinedTable，必须先 a |
| c | `202610/add_ai_reviews_int821.py` | 821 | ai_reviews + 2 索引 | 表/索引存在即 SKIP |
| d | `202610/add_algorithm_definition_drafts_table.py` | 589 | algorithm_definition_drafts + uq_algorithm_definition_draft_type | 表/索引存在即 SKIP |
| e | `202610/add_audio_playback_history_table.py` | 782#2 | audio_playback_history + 2 索引（含 testcase_id BIGINT→VARCHAR 返工） | 表/索引存在即 SKIP；表已存在时按类型补改 |
| f | `202610/add_cherry_pick_tables_int339.py` | 339 | cherry_pick_cart_items / task_cherry_pick_relations / cherry_pick_sets / cherry_pick_set_items | 表存在即 SKIP；**先于 g** |
| g | `202610/add_cherry_pick_source_result_type_int577.py` | 577 | 购物车/挑选集条目 source_result_type 列 | 依赖 f 的表；逐列检查 SKIP |
| h | `202610/add_report_studio_tables.py` | 673 | report_studio_documents / document_versions / chart_specs / export_jobs | 表存在即 SKIP |
| i | `202610/add_system_options_table.py` | 620 | system_options + 11 默认 KV 种子 | 表/键存在即 SKIP（不覆盖已有配置） |
| j | `202610/add_logs_query_indexes_int1468.py` | 1468 | logs 4 个函数索引（lower(level/module/category), task_id 前缀） | `CREATE INDEX IF NOT EXISTS`；logs 是最大增长表（30 万行），低峰执行 |
| k | `202609/add_test_case_params_columns.py` | V9.7.10 对齐 | test_cases.algorithm_params / reference_params 两列 | 列存在即 SKIP |
| l | `202610/fix_users_email_unique.py` | 84 | 空邮箱归一 + 删 users_email_key + 部分唯一索引 uq_users_email | **默认 dry-run，须 `--apply`**；⚠️ 只读 DATABASE_URI（§10 缺陷卡，Phase 0 双设 env 缓解）；删约束前先逻辑备份 users |

### 5.2 加列 + 索引（8 个，幂等）

| 顺序 | 脚本 | INT | 列/索引 | 注意 |
|---|---|---|---|---|
| m | `202610/add_users_display_name.py` | 697 | users.display_name VARCHAR(100) NULL | 显示名允许重复，无索引 |
| n | `202610/add_evaluation_strategies_int590.py` | 590 | evaluation_strategies 表 + test_cases.strategy_id/strategy_overrides + 3 索引 | strategy_id 可空 = 未引用策略，既有数据不迁移 |
| o | `202610/add_result_excluded_columns_int305.py` | 305 | test_results.excluded(INT NOT NULL DEFAULT 0) / excluded_by_user_id / excluded_at + idx_test_results_excluded | 报告/聚合按 excluded=1 剔除 |
| p | `202610/add_test_result_reviews_int340.py` | 340 | test_result_reviews 表 + test_results 5 复核列 + report_summaries.review_count + 2 索引 | 一条结果多次复核追加行不覆盖 |
| q | `202610/add_tag_operator_columns_int840.py` | 840 | tags/tag_categories/test_case_groups.deleted_by_user_id | 软删操作人列 |
| r | `202610/add_evaluation_deleted_by_int841.py` | 841 | categories/dimensions.deleted_by_user_id + ix_*_created_by_user_id | 软删操作人列 |
| s | `202610/add_api_proxy_columns.py` | 839 | apis.proxy_type VARCHAR(20) / proxy_url VARCHAR(255)（均可 NULL） | 存量行不迁移数据 |
| t | `202610/add_test_cases_group_id_index_int1470.py` | 1470 | idx_test_cases_group_id_active（部分索引 WHERE deleted=false） | `--analyze` 可选做 EXPLAIN 复核 |

### 5.3 部署闸口核验（部署新代码前）

1. **B 段跳过记录**：Phase 2 每步的核对 SQL 命中即跳过，命中结果写执行报告（不盲跑 seed 覆盖新值）。
2. **A 段幂等复跑**：重跑步骤 57（ANALYZE）命中 0 表 = 链完整（INT-2071 已验）。
3. **新列在位**（本轮缺口）：`users.display_name` / `test_results.excluded` / `test_results.reviewed` /
   `test_cases.strategy_id` / `report_summaries.review_count` / `tags.deleted_by_user_id` /
   `categories.deleted_by_user_id` / `apis.proxy_type` / `apis.proxy_url` 存在；
   `idx_test_cases_group_id_active` 在位；建表类脚本输出 [SKIP] 证明表已存在。
4. **门禁 6 项**（INT-2071 口径）：57 步退出码全 0 / 无 UndefinedTable·Column / 关键表计数不消失 /
   扩展已装 / 列在位 / 末步幂等。
5. 核验通过 → **部署新代码**（checkpoint：新镜像/新代码启动，R1/C1 双写路径上线、读路径可切快照/对象）。

## 6. Phase 4 回填（DROP 之前，限流分次）

> 回填脚本按设计不进 docker 引导链（INT-1994/INT-1807 README 明示），只对存量数据有意义。
> 全部可中断、天然幂等（判据 = 指针列 IS NULL，重跑只处理剩下的）。**必须在 Phase 5 DROP 之前
> 完成并门禁归零**。生产库 TOAST 大（raw payload 约 695MB / report_cases 258MB），用 `--batch`/`--limit`
> 限流 + sleep 分次，别和在线评估抢 IO。

| 脚本 | 目的 | 执行命令（生产） | 门禁 |
|---|---|---|---|
| `202610/backfill_report_case_snapshots_int1994.py` | R1：report_cases 九字段 payload → 快照表 + 4 指针 | 先 `--gate`（0 即 OK）；`--apply`（可 `--limit 5000 --batch 200 --sleep 0.5`） | `snapshot_sha256 IS NULL` 或无快照行 = 0 才能切快照读路径 |
| `202610/backfill_raw_payload_pointers_int1807.py` | C1：原始报文 → 内容寻址对象 + 指针列 | 先 `--gate`（0 即 OK）；`--apply`（可 `--limit-groups 2000 --batch-groups 100 --sleep 1.0`）；需要 OSS_*（§2-3） | `api_raw_*_uri IS NULL` 而内容非空 = 0 才能切读写路径（C2） |
| `202610/backfill_task_case_device_type_int789.py` | 历史 task_case_relations.device_type/device_id 回填 | `--apply`（可选） | ⑯ 回填被 test_tasks.type 门控 SKIP 的历史 NULL 行补齐 |
| `202610/backfill_log_operator_int806.py` | 历史审计日志操作人回填 | `--apply`（可选） | 解析失败放弃不阻塞 |
| `202610/backfill_report_snapshot_freeze.py`（INT-258） | 存量发布报告快照补冻结 | `--apply`（可选） | schemaVersion=2 一律 SKIP |
| `202610/backfill_task_snapshot_freeze.py`（INT-303） | 存量发布任务快照补冻结 | `--apply`（可选） | taskSnapshot 已存在一律 SKIP |
| `202610/cleanup_reeval_ghost_round_rows.py`（INT-364） | failed 重评幽灵逐轮行清理 | `--apply`（可选，先 dry-run） | 幂等 |

> **不跑**：`cleanup_int185_test_residue.py` / `cleanup_int246_smoke_residue.py`（共享库测试残留清理，
> 非生产上线内容）、`cleanup_compare_report_audios_dup.py`（本环境 2026-10-11 已核查 0 受影响）。

## 7. Phase 5 破坏性 DROP（3 个独立窗口）

> 均须**低峰窗口 + 备份预案 + 幂等续跑**；`ALTER TABLE ... DROP COLUMN` 只改目录不重写数据，
> 磁盘回收靠 `VACUUM FULL`（PG 16 关键事实，不按此执行会白干）。全程 autocommit，先查
> `pg_stat_activity` 无 idle in transaction / 等锁会话（否则锁队列拖垮域 gRPC 400/60s）。
> 隔离库验证（INT-2077）与生产命令差异只在门禁确认口径：sim 库无流量用 `--ack-no-recent-traffic`，
> **生产一律 `--strict-24h`**（要求近 24h 有流量证据）。

### 7.1 drop_apis_api_url（INT-1361）——先回填 api_endpoints，后删列

- 行为：① 存量 `api_url` 非空且 `api_endpoints` 为空 → 回填首个 endpoint（结构对齐
  `_build_endpoints_list`）；② DROP apis.api_url。幂等（列已删即 SKIP）。
- 前置：Phase 3 已确认新代码（前后端）不再读写 `apis.api_url`；`apis` 逻辑备份。
- 生产命令：
  ```bash
  python scripts/migrations/202610/drop_apis_api_url.py --dry-run   # 预览回填行数
  python scripts/migrations/202610/drop_apis_api_url.py            # 正式执行
  ```
- 复查：`apis.api_url` 列不存在；回填行 `api_endpoints` 非空。
- ⚠️ **缺陷**：脚本无「代码已停用 api_url」确认门禁（§10 缺陷卡 P2），本 runbook 靠 Phase 5
  （部署后窗口）+ 前置人工确认兜底。

### 7.2 drop_raw_payload_columns_int1813（INT-1813 M1）——DROP 两列 + VACUUM FULL + ANALYZE

- 前置门禁（缺一不可，`--gate` 只查不写）：
  1. C2+A1 已同批部署且观察 ≥1 完整轮次 → `--confirm-deployed-round`（DB 查不出，操作人确认）；
  2. 回填门禁 0：`api_raw_response IS NOT NULL AND api_raw_response_uri IS NULL` = 0（request 同理）；
  3. 近 24h 无内联报文写入 → 生产用 `--strict-24h`；
  4. 报告读路径已走对象 → `--confirm-read-path` 或 `--verify-objects N`（需 OSS）。
- 生产命令：
  ```bash
  python scripts/migrations/202610/drop_raw_payload_columns_int1813.py --gate   # 门禁只读复查
  python scripts/migrations/202610/drop_raw_payload_columns_int1813.py --apply \
      --confirm-deployed-round --confirm-read-path --strict-24h
  ```
- 幂等续跑（VACUUM FULL 被顶掉）：`--apply --force-vacuum --confirm-deployed-round --confirm-read-path --strict-24h`
- 回滚（窗口内）：`--restore --apply`（从对象按 uri+sha256 写回两列，对象是派生物不需备份）。
- 复查：`--gate` 打印门禁 N/A + 指针分布（删列后唯一可复现的复查命令）。
- 退出码：0 完成 / 1 门禁未过 / 2 未拿锁 / 3 校验失败（含 TOAST 未回收）/ 4 前置确认缺失。

### 7.3 drop_report_cases_payload_columns_int1995（INT-1995 M1）——DROP 9 payload 列 + idx_report_cases_category + VACUUM FULL

- 前置门禁：
  1. 回填门禁 0：`snapshot_sha256 IS NULL` 行数 = 0 且无悬空快照引用；
  2. 读路径已切快照 → `--confirm-read-path`；
  3. 近 24h 无内容列写入 → 生产用 `--strict-24h`；
  4. VACUUM FULL 前逻辑备份 → `--confirm-backup`（report_cases）。
- 生产命令：
  ```bash
  python scripts/migrations/202610/drop_report_cases_payload_columns_int1995.py --gate
  python scripts/migrations/202610/drop_report_cases_payload_columns_int1995.py --apply \
      --confirm-read-path --confirm-backup --strict-24h
  ```
- 幂等续跑：`--apply --force-vacuum --confirm-read-path --confirm-backup --strict-24h`
- 复查：`--gate`（列已删 → 门禁 N/A + 指针分布）。
- 保留：`id/report_id/test_case_id/algorithm_type/logs` + 4 指针列；`idx_report_cases_report_id` /
  `idx_report_cases_test_case_id` 不动。
- 退出码：同 7.2。

### 7.4 sweep_report_case_snapshots_int1995（INT-1995 收尾，可选/月度）

- `DELETE` 孤儿快照（anti-join，子查询显式滤 NULL）；默认只打印孤儿统计，`--apply` 删除。
- 建议**月度 / hard_delete_expired 之后**手动执行；不进引导链。

## 8. Phase 6 收尾

1. **末位 ANALYZE 幂等复跑**：`analyze_stale_statistics_int1741.py --apply` 命中 0 表 = 链完整
   （Phase 5 DROP 后必须补跑一次，DROP 的 ANALYZE 之后统计已刷新）。
2. **门禁 6 项终验**（INT-2071 口径）：表数 ≥ 89 / 无 UndefinedTable·Column / 关键表计数不消失
   （users·test_cases·audios·test_results·report_cases·logs）/ 扩展已装 / 列在位 / 末步幂等。
3. **schema 对齐取证**（INT-2077）：`information_schema.columns` 主库(:15432) vs 隔离库(:15435)
   全库逐列 diff 为空（允许仅 int90_poison 测试残留）；`report_cases` 9 payload 列不存在、
   `apis.api_url` 不存在、`test_result_dimensions.api_raw_response/api_request_body` 不存在、
   `users.display_name` / `test_results.excluded` / `reviewed` / `test_cases.strategy_id` 在位、
   `idx_test_cases_group_id_active` 在位。
4. **回写 README**：`scripts/migrations/README.md` 执行记录补充生产上线批次（脚本已存在，
   补「已执行」记录与批次时间）；本 runbook 归档为生产上线唯一执行口径。
5. 部署卡闭环；清理临时备份按保留策略。

## 9. 与缺口 spec 的差异（评审结论 diff）

| # | spec 说法 | 审计修正（证据） | 影响 |
|---|---|---|---|
| 1 | 「差 7 个脚本的 **20 列** + 1 索引 + 3 个 DROP」 | 脚本面逐脚本核验：7 个加列脚本合计 **19 列**（users 1 / strategy 2 / excluded 3 / reviews 6（含 report_summaries.review_count）/ tags·groups 3 / eval 2 / proxy 2）。差 1，DB 侧是否多 1 列待 INT-2077 实测 `information_schema` diff 复核 | 不阻塞；执行时以实测为准 |
| 2 | 12 个建表脚本「**两链都未登记**」 | 精度修正：**5 个在 README 执行顺序总览**（⑭ fix_users_email_unique / ⑮ add_device_management_tables / ㉚ add_system_options_table / ㉛ add_report_studio_tables / ㉜ add_cherry_pick_source_result_type_int577）、**1 个仅 README 明细**（add_logs_query_indexes_int1468）、**6 个完全未登记**（add_ai_reviews_int821 / add_algorithm_definition_drafts_table / add_audio_playback_history_table / add_device_group_parent_int832 / add_cherry_pick_tables_int339 / add_test_case_params_columns）；**全部不在 BOOTSTRAP_STEPS** | 描述修正，执行集不变（20 个全跑） |
| 3 | （INT-2077 计划）INT-1813 DROP 命令 `--apply --confirm-deployed-round --ack-no-recent-traffic` | 该命令**缺 `--confirm-read-path`** → GATE-4 必失败（`--apply` 下 require_read_path=True）。须补 `--confirm-read-path`（sim 库）或 `--strict-24h`（生产） | 修正 INT-2077 执行命令（§7.2） |
| 4 | （INT-2077 计划）`$env:DATABASE_URL=...` 单设 | `fix_users_email_unique.py` 只读 `DATABASE_URI`（默认 localhost:5432）→ 单设 DATABASE_URL 连错库。Phase 0 必须**双设** | 修正执行环境（§2-3）；另开缺陷卡（§10） |
| 5 | （spec 隐含）各脚本独立可跑 | 新增依赖约束：`add_device_group_parent_int832` 依赖 `add_device_management_tables`（device_groups）；`add_cherry_pick_source_result_type_int577` 依赖 `add_cherry_pick_tables_int339`（购物车/挑选集表） | Phase 3 顺序 a→b、f→g |

## 10. 评审发现：脚本缺陷 → 实施卡

| # | 缺陷 | 严重度 | 建议修复 |
|---|---|---|---|
| 1 | `scripts/migrations/202610/fix_users_email_unique.py`（INT-84）：只读 `DATABASE_URI`、无 `DATABASE_URL` 回退，且缺省连 `localhost:5432` —— 手动执行（INT-2077 只设 DATABASE_URL）会**连错库**并删对端库的 users 唯一约束 | P1 | 改为 `DATABASE_URL` 优先、`DATABASE_URI` 兜底（对齐 drop_raw_payload_columns 模式），并去掉静默 localhost 默认（缺 env 直接报错退出） |
| 2 | `scripts/migrations/202610/drop_apis_api_url.py`（INT-1361）：无「前后端已停用 api_url」确认门禁（对齐 INT-1813/INT-1995 的 `--confirm-read-path` 模式）——部署前误跑会让旧代码 UndefinedColumn 500 | P2 | 增加 `--confirm-read-path`（或 `--confirm-code-deployed`）确认门禁，与 7.2/7.3 口径一致 |

> 实施卡已创建（§11）；INT-2077 执行不依赖上述修复（Phase 0 双设 env + Phase 5 顺序已兜底），
> 修复用于长期健壮性与通用老库迁移。

## 11. 出处

- 本 runbook：INT-2076（方案一致性审计员评审，2026-10-27）。
- 两段式基线：INT-2075（`doc/数据库迁移/正式上线迁移执行基线_INT2075.md`）。
- 隔离库验证：INT-2071（57 步全过、门禁 6 项全过）+ INT-2077（缺口补跑 + 对齐取证，待本 runbook 后启动）。
- 缺口证据：INT-2071 评论 01a17c61（隔离库↔主库逐列 diff）。
- 实施卡：待建（§10 两项）。
- 权威顺序：`docker/db_bootstrap_entrypoint.py` BOOTSTRAP_STEPS；脚本明细：`scripts/migrations/README.md`。
