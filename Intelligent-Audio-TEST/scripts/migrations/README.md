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
python scripts/migrations/202609/seed_voice_llm.py                        # ⑨ 算法/维度种子（按需）
```

> ✅ **2026-09-07 全量迁移记录**：当前环境已执行 ①③④⑧（`remove_foreign_keys_and_soft_delete` 12 步 + `add_audit_columns` 补 24 处 + `add_reevaluated_at` + `add_pass_threshold_to_eval_params`），执行后 `UndefinedColumn` 类报错全部消除。②⑤⑥⑦⑨ 视功能需要执行。

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
| [seed_rbac.py](202608/seed_rbac.py) | RBAC 种子数据 | 86 个权限点、5 个系统角色（admin/tester/algo_engineer/device_admin/guest）及角色-权限映射；依赖 RBAC 表已存在（① 已建） |

### 202609 — 评估维度与算法种子

| 脚本 | 用途 |
|------|------|
| [add_pass_threshold_to_eval_params.py](202609/add_pass_threshold_to_eval_params.py) | `evaluation_dimension_params` 加 `pass_threshold` 列（评估通过阈值） |
| [seed_voice_llm.py](202609/seed_voice_llm.py) | voice_llm 算法全套种子：算法定义 / 用例参数 / 设备输出字段 / API 输入输出字段 / 参考参数 / 参数映射 / 算法-维度关联（`ON CONFLICT DO NOTHING`） |
| [seed_llm_judge_dimension.py](202609/seed_llm_judge_dimension.py) | LLM Judge 评估维度 |
| [seed_interruption_dimensions.py](202609/seed_interruption_dimensions.py) | 打断（tor / false_takeover / takeover_latency）维度 |
| [seed_env_sound_judge.py](202609/seed_env_sound_judge.py) | 环境音识别维度 |
| [seed_non_interactive_latency.py](202609/seed_non_interactive_latency.py) | 非交互时延维度 |
| [seed_noise_latency.py](202609/seed_noise_latency.py) | 噪声场景时延维度 |
| [seed_xiaoyi_dimensions.py](202609/seed_xiaoyi_dimensions.py) | 小艺指标维度 |

## 新增迁移脚本约定

1. 放入 `scripts/migrations/YYYYMM/`，一个变更一个脚本，文件名即意图（`add_xxx` / `fix_xxx` / `seed_xxx`）。
2. 沿用现有模板：psycopg2/SQLAlchemy 直连 + savepoint 逐表回滚 + `[SKIP]` 跳过已完成项；文件头 docstring 写明目标、幂等性、用法、依赖。
3. 必须幂等——重复执行不得报错、不得产生重复数据（种子用 `ON CONFLICT DO NOTHING`）。
4. 涉及破坏性操作（DROP / 改类型）时在 docstring 与本 README 中显著标注。
5. 执行完成后更新本 README 的「执行顺序总览」与执行记录。
