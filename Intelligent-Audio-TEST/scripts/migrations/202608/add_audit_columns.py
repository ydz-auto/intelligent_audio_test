# -*- coding: utf-8 -*-
"""审计列迁移脚本：补齐 ORM 模型定义了但数据库表缺失的
created_by_user_id / updated_by_user_id / deleted / deleted_at 列。

通过扫描 ORM 模型源码中的 Column 定义，自动生成 ALTER TABLE 语句。
仅处理 ORM 中已定义审计列的表，不会给纯关联表（如 task_device_relations）加列。

用法:
    python scripts/migrations/202608/add_audit_columns.py [--dry-run]
"""
import sys
import os

import psycopg2
from dotenv import load_dotenv
from urllib.parse import urlparse

load_dotenv()
DATABASE_URL = os.environ.get('DATABASE_URL')
parsed = urlparse(DATABASE_URL)
DB_HOST = parsed.hostname
DB_PORT = parsed.port or 5432
DB_NAME = parsed.path.lstrip('/')
DB_USER = parsed.username
DB_PASS = parsed.password

# ── ORM 模型中定义了审计列的表 ──────────────────────────────────
# 格式: table_name -> [(col_name, col_type), ...]
ORM_AUDIT_TABLES = {
    # task_service / task_models
    'test_tasks':            [('created_by_user_id', 'BIGINT'), ('updated_by_user_id', 'BIGINT'),
                              ('deleted', 'BOOLEAN'), ('deleted_at', 'TIMESTAMP')],
    'task_tags':             [('created_by_user_id', 'BIGINT'), ('updated_by_user_id', 'BIGINT')],
    'task_case_relations':   [('created_by_user_id', 'BIGINT'), ('updated_by_user_id', 'BIGINT')],
    'task_merge_relations':  [('created_by_user_id', 'BIGINT'), ('updated_by_user_id', 'BIGINT')],
    # task_service / testcase_models
    'tag_categories':         [('created_by_user_id', 'BIGINT'), ('updated_by_user_id', 'BIGINT'),
                              ('deleted', 'BOOLEAN'), ('deleted_at', 'TIMESTAMP')],
    'tags':                  [('created_by_user_id', 'BIGINT'), ('updated_by_user_id', 'BIGINT'),
                              ('deleted', 'BOOLEAN'), ('deleted_at', 'TIMESTAMP')],
    'test_case_groups':      [('created_by_user_id', 'BIGINT'), ('updated_by_user_id', 'BIGINT'),
                              ('deleted', 'BOOLEAN'), ('deleted_at', 'TIMESTAMP')],
    'test_cases':            [('created_by_user_id', 'BIGINT'), ('updated_by_user_id', 'BIGINT'),
                              ('deleted', 'BOOLEAN'), ('deleted_at', 'TIMESTAMP')],
    'test_case_tags':        [('created_by_user_id', 'BIGINT'), ('updated_by_user_id', 'BIGINT')],
    # task_service / result_models
    'test_results':          [('created_by_user_id', 'BIGINT'), ('updated_by_user_id', 'BIGINT')],
    # task_service / system_models
    'logs':                  [('created_by_user_id', 'BIGINT'), ('updated_by_user_id', 'BIGINT')],
    # audio_service
    'audios':                [('created_by_user_id', 'BIGINT'), ('updated_by_user_id', 'BIGINT'),
                              ('deleted', 'BOOLEAN'), ('deleted_at', 'TIMESTAMP')],
    'audio_annotations':     [('created_by_user_id', 'BIGINT'), ('updated_by_user_id', 'BIGINT'),
                              ('deleted', 'BOOLEAN'), ('deleted_at', 'TIMESTAMP')],
    'audio_tags':            [('created_by_user_id', 'BIGINT'), ('updated_by_user_id', 'BIGINT')],
    'audio_algorithm_relations': [('created_by_user_id', 'BIGINT'), ('updated_by_user_id', 'BIGINT'),
                                  ('deleted', 'BOOLEAN'), ('deleted_at', 'TIMESTAMP')],
    'upload_tasks':          [('created_by_user_id', 'BIGINT'), ('updated_by_user_id', 'BIGINT')],
    'upload_files':          [('created_by_user_id', 'BIGINT'), ('updated_by_user_id', 'BIGINT')],
    'upload_chunks':         [('created_by_user_id', 'BIGINT'), ('updated_by_user_id', 'BIGINT')],
    # device_service
    'devices':               [('created_by_user_id', 'BIGINT'), ('updated_by_user_id', 'BIGINT'),
                              ('deleted', 'BOOLEAN'), ('deleted_at', 'TIMESTAMP')],
    'playback_devices':      [('created_by_user_id', 'BIGINT'), ('updated_by_user_id', 'BIGINT')],
    'device_tags':           [('created_by_user_id', 'BIGINT'), ('updated_by_user_id', 'BIGINT')],
    'spl_mappings':          [('created_by_user_id', 'BIGINT'), ('updated_by_user_id', 'BIGINT'),
                              ('deleted', 'BOOLEAN'), ('deleted_at', 'TIMESTAMP')],
    'calibration_history':   [('created_by_user_id', 'BIGINT'), ('updated_by_user_id', 'BIGINT')],
    # evaluation_service
    'categories':            [('created_by_user_id', 'BIGINT'), ('updated_by_user_id', 'BIGINT'),
                              ('deleted', 'BOOLEAN'), ('deleted_at', 'TIMESTAMP')],
    'dimensions':            [('created_by_user_id', 'BIGINT'), ('updated_by_user_id', 'BIGINT'),
                              ('deleted', 'BOOLEAN'), ('deleted_at', 'TIMESTAMP')],
    'test_result_dimensions': [('created_by_user_id', 'BIGINT'), ('updated_by_user_id', 'BIGINT')],
    # report_service
    'test_reports':          [('created_by_user_id', 'BIGINT'), ('updated_by_user_id', 'BIGINT'),
                              ('deleted', 'BOOLEAN'), ('deleted_at', 'TIMESTAMP')],
    'report_summaries':      [('created_by_user_id', 'BIGINT'), ('updated_by_user_id', 'BIGINT')],
    'report_summary_meta':   [('created_by_user_id', 'BIGINT'), ('updated_by_user_id', 'BIGINT')],
    'report_raw_data':       [('created_by_user_id', 'BIGINT'), ('updated_by_user_id', 'BIGINT')],
    'report_cases':          [('created_by_user_id', 'BIGINT'), ('updated_by_user_id', 'BIGINT')],
    'report_metric_stats':   [('created_by_user_id', 'BIGINT'), ('updated_by_user_id', 'BIGINT')],
    'report_comparison_matrix': [('created_by_user_id', 'BIGINT'), ('updated_by_user_id', 'BIGINT')],
    # api_test_service
    'apis':                  [('created_by_user_id', 'BIGINT'), ('updated_by_user_id', 'BIGINT'),
                              ('deleted', 'BOOLEAN'), ('deleted_at', 'TIMESTAMP')],
}


def main():
    dry_run = '--dry-run' in sys.argv

    conn = psycopg2.connect(
        host=DB_HOST, port=DB_PORT, dbname=DB_NAME,
        user=DB_USER, password=DB_PASS,
    )
    cur = conn.cursor()

    total_missing = 0

    for table, audit_cols in ORM_AUDIT_TABLES.items():
        # 检查表是否存在
        cur.execute("""
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = %s
        """, (table,))
        if not cur.fetchone():
            print(f"[SKIP] 表 {table} 不存在于数据库中")
            continue

        # 获取已有列
        cur.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = %s
        """, (table,))
        existing_cols = {row[0] for row in cur.fetchall()}

        for col_name, col_type in audit_cols:
            if col_name not in existing_cols:
                nullable = 'NULL'
                default_clause = ''
                # BOOLEAN deleted 列加默认值 false
                if col_type == 'BOOLEAN':
                    default_clause = ' DEFAULT false'

                sql = f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {col_name} {col_type} {nullable}{default_clause}"
                print(f"  执行: {sql}")
                total_missing += 1

                if not dry_run:
                    cur.execute(sql)
                    # created_by_user_id 需要索引
                    if col_name == 'created_by_user_id':
                        idx_name = f"ix_{table}_{col_name}"
                        idx_sql = f"CREATE INDEX IF NOT EXISTS {idx_name} ON {table} ({col_name})"
                        print(f"  执行: {idx_sql}")
                        cur.execute(idx_sql)
                existing_cols.add(col_name)

    if total_missing == 0:
        print("[OK] 所有表均已包含审计列，无需迁移。")
    elif dry_run:
        print(f"[DRY-RUN] 发现 {total_missing} 处缺失，未执行实际变更。")
    else:
        conn.commit()
        print(f"[DONE] 已补齐 {total_missing} 处审计列。")

    cur.close()
    conn.close()


if __name__ == '__main__':
    main()
