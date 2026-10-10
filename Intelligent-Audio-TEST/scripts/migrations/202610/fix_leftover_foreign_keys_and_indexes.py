# -*- coding: utf-8 -*-
"""
修复 202608 基线未生效的残留约束（INT-88）
==========================================

背景：
    remove_foreign_keys_and_soft_delete.py（202608 ① 结构基线）在运行库上
    仅有列级/建表语句生效；Step 1（删全库外键）、Step 5（删 test_case_groups.name
    唯一约束）、Step 11（外键替代索引）、Step 12（deleted_at 部分索引）未生效
    （疑似建库晚于迁移执行，create_all 重建表时按 ORM 重新带出 FK / 唯一约束）。
    残留 FK 导致 tests/api 软删除重建用例违反外键
    （audio_algorithm_relations / algorithm_dimension_relations / param_mappings）。

设计依据（202608 既定决策）：
    1. 引用完整性由应用层管理：删除数据库中所有外键约束（本脚本动态枚举后逐个 DROP）。
    2. test_case_groups.name 唯一约束删除（软删除后允许同名重建）。
    3. 外键替代索引：原 FK 列上的查询索引（对应 202608 Step 11 索引清单）。
    4. deleted_at 部分索引（WHERE deleted = TRUE）：动态枚举所有同时具有
       deleted / deleted_at 列的表（对应 202608 Step 12）。

例外（有意保留，勿删）：
    - algorithm_definitions_type_key（algorithm_definitions.type 上的完整唯一约束）：
      fix_partial_unique_indexes.py 末尾注释表明 202608 有意保留——type 作为算法
      标识不应在软删除后复用，且当时被 FK 引用。本脚本不涉及任何唯一约束的删除
      （仅 test_case_groups.name 除外），该约束自然不受影响。

幂等性：脚本可重复执行，已完成的操作会被跳过；FK 删除为动态枚举，无残留时为 no-op。
锁保护：每条 DROP 以独立事务执行并设置 lock_timeout（默认 10s），取不到锁时跳过并
    汇总提示，不会无限期阻塞（参考 README「先停服务再执行」须知；被长事务阻塞时
    请处理阻塞会话后重跑本脚本）。

用法:
    python fix_leftover_foreign_keys_and_indexes.py              # 正式执行
    python fix_leftover_foreign_keys_and_indexes.py --dry-run    # 仅预览

依赖:
    pip install sqlalchemy psycopg2-binary
"""

import os
import sys
import time

from sqlalchemy import create_engine, text

# ========================================================================
# 配置
# ========================================================================

POSTGRES_URI = os.environ.get(
    'DATABASE_URI',
    'postgresql://intelligent_audio_test:intelligent_audio_test666'
    '@localhost:5432/intelligent_audio_test'
)

# 单条 DDL 的锁等待上限（秒），超时跳过该约束并在汇总中报告
LOCK_TIMEOUT_SECONDS = int(os.environ.get('MIGRATION_LOCK_TIMEOUT', '10'))

# 锁超时后重试轮数（服务健康检查可能短暂持锁，轮间隔 5s）
LOCK_RETRY_ROUNDS = int(os.environ.get('MIGRATION_LOCK_RETRY_ROUNDS', '3'))


# ========================================================================
# 辅助函数
# ========================================================================

def _table_exists(conn, table_name):
    """检查表是否存在（public schema）"""
    result = conn.execute(text(
        "SELECT to_regclass(:t)"
    ), {"t": f'public.{table_name}'})
    return result.scalar() is not None


def _index_exists(conn, index_name):
    """检查索引是否已存在"""
    result = conn.execute(text(
        "SELECT 1 FROM pg_indexes WHERE indexname = :name"
    ), {"name": index_name})
    return result.fetchone() is not None


def _is_lock_timeout_error(e):
    # 兼容服务端本地化消息（中文消息不含 "lock timeout" 字样），
    # 以 psycopg2 异常类名 LockNotAvailable 为可靠信号
    orig = getattr(e, 'orig', None)
    if orig is not None and type(orig).__name__ in ('LockNotAvailable', 'QueryCanceled'):
        return True
    msg = str(e).lower()
    return 'locknotavailable' in msg or 'querycanceled' in msg \
        or ('lock' in msg and 'timeout' in msg)


# ========================================================================
# Step 1: 删除所有残留外键约束（对齐 202608 Step 1）
# ========================================================================

def _list_all_foreign_keys(conn):
    """枚举当前数据库（全部 schema）中的外键约束"""
    rows = conn.execute(text(
        """
        SELECT nsp.nspname AS table_schema,
               cls.relname AS table_name,
               con.conname AS constraint_name,
               rcls.relname AS ref_table
        FROM pg_constraint con
        JOIN pg_class cls ON cls.oid = con.conrelid
        JOIN pg_namespace nsp ON nsp.oid = cls.relnamespace
        JOIN pg_class rcls ON rcls.oid = con.confrelid
        WHERE con.contype = 'f'
          AND nsp.nspname NOT IN ('pg_catalog', 'information_schema')
        ORDER BY nsp.nspname, cls.relname, con.conname
        """
    )).fetchall()
    return rows


def step1_drop_leftover_foreign_keys(engine, dry_run=False):
    """删除当前数据库中所有残留的外键约束（应用层管理引用完整性）"""
    print("\n" + "=" * 60)
    print("Step 1: 删除所有残留外键约束")
    print("=" * 60)

    with engine.connect() as conn:
        rows = _list_all_foreign_keys(conn)

    total = len(rows)
    print(f"  发现 {total} 个外键约束\n")

    if dry_run:
        for schema, table, constraint, ref in rows:
            print(f"  [DRY-RUN] DROP CONSTRAINT {constraint} on {schema}.{table} (->{ref})")
        return

    dropped = []
    # 剩余 FK 集合逐轮收缩；被锁跳过的下一轮重试（等持锁事务结束）
    for round_no in range(1, LOCK_RETRY_ROUNDS + 1):
        with engine.connect() as conn:
            remaining = _list_all_foreign_keys(conn)
        if not remaining:
            break
        if round_no > 1:
            print(f"\n  --- 第 {round_no} 轮重试（{len(remaining)} 个待删） ---")
        for schema, table, constraint, ref in remaining:
            fqn = f'"{schema}"."{table}"' if schema != 'public' else f'"{table}"'
            try:
                with engine.begin() as conn:
                    conn.execute(text(
                        f"SET LOCAL lock_timeout = '{LOCK_TIMEOUT_SECONDS}s'"
                    ))
                    conn.execute(text(
                        f'ALTER TABLE {fqn} DROP CONSTRAINT IF EXISTS "{constraint}"'
                    ))
                dropped.append((schema, table, constraint))
                print(f"  [OK] DROP CONSTRAINT {constraint} on {schema}.{table} (->{ref})")
            except Exception as e:
                if _is_lock_timeout_error(e):
                    print(f"  [LOCK] {constraint} on {schema}.{table} 等锁超时"
                          f"（{LOCK_TIMEOUT_SECONDS}s），稍后重试")
                else:
                    raise
        if remaining and round_no < LOCK_RETRY_ROUNDS:
            time.sleep(5)

    with engine.connect() as conn:
        still = _list_all_foreign_keys(conn)

    print(f"\n  删除外键约束: {len(dropped)} 个")
    if still:
        print(f"  [WARN] 仍残留 {len(still)} 个外键约束（被长事务阻塞，处理后重跑本脚本）:")
        for schema, table, constraint, ref in still:
            print(f"    - {schema}.{table}.{constraint} (->{ref})")
    else:
        print("  [OK] 数据库中已无外键约束")


# ========================================================================
# Step 2: 删除 test_case_groups.name 上的唯一约束（对齐 202608 Step 5）
# ========================================================================

def step2_drop_unique_on_group_name(engine, dry_run=False):
    """删除 test_case_groups.name 上的单列唯一约束（软删除后允许同名重建）"""
    print("\n" + "=" * 60)
    print("Step 2: 删除 test_case_groups.name 唯一约束")
    print("=" * 60)

    with engine.connect() as conn:
        if not _table_exists(conn, 'test_case_groups'):
            print("  [SKIP] test_case_groups 表不存在")
            return

        rows = conn.execute(text(
            """
            SELECT con.conname
            FROM pg_constraint con
            JOIN pg_class cls ON cls.oid = con.conrelid
            JOIN pg_attribute att ON att.attrelid = con.conrelid
            WHERE con.contype = 'u'
              AND cls.relname = 'test_case_groups'
              AND att.attname = 'name'
              AND array_length(con.conkey, 1) = 1
              AND att.attnum = con.conkey[1]
            """
        )).fetchall()

    uq_names = [r[0] for r in rows]
    if not uq_names:
        print("  [SKIP] test_case_groups.name 上无唯一约束")
        return

    if dry_run:
        for name in uq_names:
            print(f"  [DRY-RUN] DROP CONSTRAINT {name}")
        return

    for name in uq_names:
        for attempt in range(1, LOCK_RETRY_ROUNDS + 1):
            try:
                with engine.begin() as conn:
                    conn.execute(text(
                        f"SET LOCAL lock_timeout = '{LOCK_TIMEOUT_SECONDS}s'"
                    ))
                    conn.execute(text(
                        f'ALTER TABLE test_case_groups DROP CONSTRAINT IF EXISTS "{name}"'
                    ))
                print(f"  [OK] DROP CONSTRAINT {name}")
                break
            except Exception as e:
                if _is_lock_timeout_error(e) and attempt < LOCK_RETRY_ROUNDS:
                    print(f"  [LOCK] {name} 等锁超时，重试 {attempt}/{LOCK_RETRY_ROUNDS}")
                    time.sleep(5)
                elif _is_lock_timeout_error(e):
                    print(f"  [WARN] {name} 等锁超时放弃，请处理阻塞会话后重跑")
                else:
                    raise


# ========================================================================
# Step 3: 创建外键替代索引（对齐 202608 Step 11 索引清单）
# ========================================================================

# 索引定义：(索引名, 表名, 列SQL, 是否部分索引, WHERE子句)
# 与 202608 remove_foreign_keys_and_soft_delete.py 的 INDEX_DEFINITIONS 保持一致。
INDEX_DEFINITIONS = [
    # ── 软删除清理索引（部分索引）──
    ('idx_tc_groups_deleted_at', 'test_case_groups', 'deleted_at', True, "WHERE deleted = TRUE"),
    ('idx_test_cases_deleted_at', 'test_cases', 'deleted_at', True, "WHERE deleted = TRUE"),

    # ── test_case_groups ──
    ('idx_tc_groups_algorithm_type', 'test_case_groups', 'algorithm_type', False, None),

    # ── test_cases ──
    ('idx_test_cases_group_id', 'test_cases', 'group_id', False, None),
    ('idx_test_cases_algorithm_type', 'test_cases', 'algorithm_type', False, None),
    ('idx_test_cases_deleted', 'test_cases', 'deleted', False, None),

    # ── test_case_tags ──
    ('idx_test_case_tags_test_case_id', 'test_case_tags', 'test_case_id', False, None),
    ('idx_test_case_tags_tag_id', 'test_case_tags', 'tag_id', False, None),

    # ── tags ──
    ('idx_tags_category_id', 'tags', 'category_id', False, None),

    # ── dimensions ──
    ('idx_dimensions_category_id', 'dimensions', 'category_id', False, None),
    ('idx_dimensions_parent_dimension_id', 'dimensions', 'parent_dimension_id', False, None),

    # ── audio_annotations ──
    ('idx_audio_annotations_audio_id', 'audio_annotations', 'audio_id', False, None),

    # ── audio_tags ──
    ('idx_audio_tags_audio_id', 'audio_tags', 'audio_id', False, None),
    ('idx_audio_tags_tag_id', 'audio_tags', 'tag_id', False, None),

    # ── audio_algorithm_relations ──
    ('idx_audio_algo_rel_audio_id', 'audio_algorithm_relations', 'audio_id', False, None),
    ('idx_audio_algo_rel_algorithm_type', 'audio_algorithm_relations', 'algorithm_type', False, None),

    # ── device_tags ──
    ('idx_device_tags_device_id', 'device_tags', 'device_id', False, None),
    ('idx_device_tags_tag_id', 'device_tags', 'tag_id', False, None),

    # ── playback_devices ──
    ('idx_playback_devices_current_spl_mapping_id', 'playback_devices', 'current_spl_mapping_id', False, None),

    # ── spl_mappings ──
    ('idx_spl_mappings_device_id', 'spl_mappings', 'device_id', False, None),

    # ── calibration_history ──
    ('idx_calibration_history_mapping_id', 'calibration_history', 'mapping_id', False, None),

    # ── task_tags ──
    ('idx_task_tags_task_id', 'task_tags', 'task_id', False, None),
    ('idx_task_tags_tag_id', 'task_tags', 'tag_id', False, None),

    # ── task_case_relations ──
    ('idx_task_case_relations_task_id', 'task_case_relations', 'task_id', False, None),
    ('idx_task_case_relations_test_case_id', 'task_case_relations', 'test_case_id', False, None),

    # ── task_device_relations ──
    ('idx_task_device_relations_task_id', 'task_device_relations', 'task_id', False, None),
    ('idx_task_device_relations_device_id', 'task_device_relations', 'device_id', False, None),

    # ── task_api_relations ──
    ('idx_task_api_relations_task_id', 'task_api_relations', 'task_id', False, None),
    ('idx_task_api_relations_api_id', 'task_api_relations', 'api_id', False, None),

    # ── task_merge_relations ──
    ('idx_task_merge_relations_merged_task_id', 'task_merge_relations', 'merged_task_id', False, None),
    ('idx_task_merge_relations_source_task_id', 'task_merge_relations', 'source_task_id', False, None),

    # ── test_results ──
    ('idx_test_results_task_id', 'test_results', 'task_id', False, None),
    ('idx_test_results_test_case_id', 'test_results', 'test_case_id', False, None),
    ('idx_test_results_device_id', 'test_results', 'device_id', False, None),
    ('idx_test_results_api_id', 'test_results', 'api_id', False, None),
    ('idx_test_results_algorithm_type', 'test_results', 'algorithm_type', False, None),

    # ── test_result_dimensions ──
    ('idx_test_result_dimensions_test_result_id', 'test_result_dimensions', 'test_result_id', False, None),
    ('idx_test_result_dimensions_dimension_id', 'test_result_dimensions', 'dimension_id', False, None),

    # ── test_reports ──
    ('idx_test_reports_task_id', 'test_reports', 'task_id', False, None),

    # ── report_cases ──
    ('idx_report_cases_report_id', 'report_cases', 'report_id', False, None),
    ('idx_report_cases_test_case_id', 'report_cases', 'test_case_id', False, None),

    # ── logs ──
    ('idx_logs_task_id', 'logs', 'task_id', False, None),
    ('idx_logs_test_case_id', 'logs', 'test_case_id', False, None),
    ('idx_logs_device_id', 'logs', 'device_id', False, None),
    ('idx_logs_api_id', 'logs', 'api_id', False, None),

    # ── user_permissions ──
    ('idx_user_permissions_user_id', 'user_permissions', 'user_id', False, None),
    ('idx_user_permissions_permission_id', 'user_permissions', 'permission_id', False, None),

    # ── upload_files / upload_chunks ──
    ('idx_upload_files_task_id', 'upload_files', 'task_id', False, None),
    ('idx_upload_chunks_file_id', 'upload_chunks', 'file_id', False, None),

    # ── case_algorithm_params ──
    ('idx_case_algorithm_params_algorithm_type', 'case_algorithm_params', 'algorithm_type', False, None),

    # ── algorithm_models 相关（algorithm_definitions 等）──
    ('idx_algorithm_definitions_group_id', 'algorithm_definitions', 'group_id', False, None),
    ('idx_algorithm_device_params_algorithm_type', 'algorithm_device_params', 'algorithm_type', False, None),
    ('idx_algorithm_api_params_algorithm_type', 'algorithm_api_params', 'algorithm_type', False, None),
    ('idx_algorithm_reference_params_algorithm_type', 'algorithm_reference_params', 'algorithm_type', False, None),
    ('idx_evaluation_dimension_params_dimension_id', 'evaluation_dimension_params', 'dimension_id', False, None),
    ('idx_param_mappings_algorithm_type', 'param_mappings', 'algorithm_type', False, None),
    ('idx_param_mappings_dimension_id', 'param_mappings', 'dimension_id', False, None),
    ('idx_algorithm_dimension_relations_algorithm_type', 'algorithm_dimension_relations', 'algorithm_type', False, None),
    ('idx_algorithm_dimension_relations_dimension_id', 'algorithm_dimension_relations', 'dimension_id', False, None),
]


def step3_add_fk_replacement_indexes(engine, dry_run=False):
    """创建外键替代索引（原 FK 列查询索引 + 软删除清理索引）"""
    print("\n" + "=" * 60)
    print("Step 3: 创建外键替代索引")
    print("=" * 60)

    if dry_run:
        with engine.connect() as conn:
            for idx_name, table, cols, is_partial, where in INDEX_DEFINITIONS:
                exists = _table_exists(conn, table)
                idx_exists = _index_exists(conn, idx_name)
                status = '已存在' if idx_exists else ('表缺失' if not exists else '待创建')
                print(f"  [DRY-RUN] {idx_name} on {table}({cols}): {status}")
        return

    created = 0
    skipped = 0
    with engine.begin() as conn:
        for idx_name, table, cols, is_partial, where in INDEX_DEFINITIONS:
            if not _table_exists(conn, table):
                print(f"  [SKIP] 表 {table} 不存在，跳过 {idx_name}")
                skipped += 1
                continue
            if _index_exists(conn, idx_name):
                print(f"  [SKIP] 索引 {idx_name} 已存在")
                skipped += 1
                continue
            sql = f"CREATE INDEX IF NOT EXISTS {idx_name} ON {table} ({cols})"
            if is_partial and where:
                sql += f" {where}"
            conn.execute(text(sql))
            print(f"  [OK] 创建索引: {idx_name}")
            created += 1
        print(f"\n  创建: {created}, 跳过: {skipped}")


# ========================================================================
# Step 4: 给所有 deleted_at 列建部分索引（对齐 202608 Step 12）
# ========================================================================

def step4_add_deleted_at_partial_indexes(engine, dry_run=False):
    """给所有同时具有 deleted / deleted_at 列的表建部分索引（WHERE deleted = TRUE）"""
    print("\n" + "=" * 60)
    print("Step 4: 给所有 deleted_at 列建部分索引")
    print("=" * 60)

    with engine.connect() as conn:
        rows = conn.execute(text(
            """
            SELECT c1.table_name
            FROM information_schema.columns c1
            JOIN information_schema.columns c2
              ON c1.table_name = c2.table_name
             AND c2.column_name = 'deleted'
            WHERE c1.column_name = 'deleted_at'
              AND c1.table_schema = 'public'
            ORDER BY c1.table_name
            """
        )).fetchall()
    tables = [r[0] for r in rows]

    if dry_run:
        with engine.connect() as conn:
            for table in tables:
                idx_name = f"idx_{table}_deleted_at"
                idx_exists = _index_exists(conn, idx_name)
                print(f"  [DRY-RUN] {idx_name}: {'已存在' if idx_exists else '待创建'}")
        return

    created = 0
    skipped = 0
    with engine.begin() as conn:
        for table in tables:
            idx_name = f"idx_{table}_deleted_at"
            if _index_exists(conn, idx_name):
                print(f"  [SKIP] 索引 {idx_name} 已存在")
                skipped += 1
                continue
            # 202608 Step 11 已用旧名建过部分索引的表，避免重复创建
            if table == 'test_case_groups' and _index_exists(conn, 'idx_tc_groups_deleted_at'):
                print(f"  [SKIP] {table} 已有 idx_tc_groups_deleted_at 索引")
                skipped += 1
                continue
            if table == 'test_cases' and _index_exists(conn, 'idx_test_cases_deleted_at'):
                print(f"  [SKIP] {table} 已有 idx_test_cases_deleted_at 索引")
                skipped += 1
                continue
            conn.execute(text(
                f"CREATE INDEX IF NOT EXISTS {idx_name} ON {table} (deleted_at) WHERE deleted = TRUE"
            ))
            print(f"  [OK] 创建索引: {idx_name}")
            created += 1
        print(f"\n  创建: {created}, 跳过: {skipped}")


# ========================================================================
# 主流程
# ========================================================================

def main():
    dry_run = '--dry-run' in sys.argv

    print("=" * 60)
    print(f"{'[DRY-RUN] ' if dry_run else ''}修复 202608 基线未生效的残留约束（INT-88）")
    print("=" * 60)
    safe_uri = POSTGRES_URI[:POSTGRES_URI.rindex('@')] + '@localhost/...'
    print(f"数据库: {safe_uri}")
    print(f"锁超时: {LOCK_TIMEOUT_SECONDS}s x {LOCK_RETRY_ROUNDS} 轮")
    print()

    engine = create_engine(POSTGRES_URI)

    step1_drop_leftover_foreign_keys(engine, dry_run=dry_run)
    step2_drop_unique_on_group_name(engine, dry_run=dry_run)
    step3_add_fk_replacement_indexes(engine, dry_run=dry_run)
    step4_add_deleted_at_partial_indexes(engine, dry_run=dry_run)

    print("\n" + "=" * 60)
    print(f"{'[DRY-RUN] ' if dry_run else ''}迁移完成")
    print("=" * 60)
    print("\n迁移汇总：")
    print("  Step 1: 删除所有残留外键约束（202608 Step 1 补生效）")
    print("  Step 2: 删除 test_case_groups.name 唯一约束（202608 Step 5 补生效）")
    print("  Step 3: 创建外键替代索引（202608 Step 11 补生效）")
    print("  Step 4: 创建 deleted_at 部分索引（202608 Step 12 补生效）")
    print("\n例外保留：algorithm_definitions_type_key（algorithm_definitions.type 完整唯一约束，")
    print("  fix_partial_unique_indexes.py 表明 202608 有意保留，本脚本不涉及唯一约束删除）")


if __name__ == '__main__':
    main()
