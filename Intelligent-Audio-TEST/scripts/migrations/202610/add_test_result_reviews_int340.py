# -*- coding: utf-8 -*-
"""迁移脚本：测试结果人工复核（INT-340）

功能：
- 建 test_result_reviews 表（复核留痕，一条结果多次复核追加行不覆盖）
- 为 test_results 表追加人工复核标记列（reviewed / reviewed_by_user_id /
  reviewed_at / last_review_comment / last_review_action）

幂等，可重复执行（CREATE TABLE IF NOT EXISTS / ADD COLUMN IF NOT EXISTS）。

用法:
    python scripts/migrations/202610/add_test_result_reviews_int340.py [--dry-run]

依赖:
    pip install psycopg2-binary python-dotenv
"""
import os
import sys
import argparse

import psycopg2
from dotenv import load_dotenv
from urllib.parse import urlparse

load_dotenv()
DATABASE_URL = os.environ.get('DATABASE_URL')
if not DATABASE_URL:
    print('未配置 DATABASE_URL 环境变量（.env 或环境）', file=sys.stderr)
    sys.exit(1)
parsed = urlparse(DATABASE_URL)
DB_HOST = parsed.hostname
DB_PORT = parsed.port or 5432
DB_NAME = parsed.path.lstrip('/')
DB_USER = parsed.username
DB_PASS = parsed.password


def _table_exists(cur, table):
    cur.execute(
        "SELECT 1 FROM information_schema.tables WHERE table_name = %s", (table,)
    )
    return cur.fetchone() is not None


def _column_exists(cur, table, column):
    cur.execute(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name = %s AND column_name = %s", (table, column)
    )
    return cur.fetchone() is not None


def _index_exists(cur, index_name):
    cur.execute("SELECT 1 FROM pg_indexes WHERE indexname = %s", (index_name,))
    return cur.fetchone() is not None


def _exec(cur, conn, sql, dry_run):
    if dry_run:
        print(f"[DRY-RUN] {sql.strip()[:120]}")
        return
    print(f"[EXEC] {sql.strip()[:120]}")
    cur.execute(sql)
    conn.commit()


REVIEW_TABLE_SQL = """
    CREATE TABLE IF NOT EXISTS test_result_reviews (
        id BIGSERIAL PRIMARY KEY,
        result_id INTEGER NOT NULL,
        task_id INTEGER NOT NULL,
        test_case_id VARCHAR(50),
        field_name VARCHAR(30) NOT NULL,
        old_value VARCHAR(20),
        new_value VARCHAR(20) NOT NULL,
        comment TEXT NOT NULL,
        created_by_user_id BIGINT,
        created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT now()
    )
"""

REVIEW_INDEXES = (
    ('idx_review_task', 'CREATE INDEX IF NOT EXISTS idx_review_task ON test_result_reviews (task_id)'),
    ('idx_review_result', 'CREATE INDEX IF NOT EXISTS idx_review_result ON test_result_reviews (result_id)'),
)

# test_results 表新增列（幂等 ADD COLUMN IF NOT EXISTS）
RESULT_REVIEW_COLUMNS = (
    'reviewed INTEGER NOT NULL DEFAULT 0',
    'reviewed_by_user_id BIGINT',
    'reviewed_at TIMESTAMP WITHOUT TIME ZONE',
    'last_review_comment TEXT',
    'last_review_action VARCHAR(255)',
)

# report_summaries 表新增列（报告页「人工复核」标记，INT-340）
REPORT_SUMMARY_COLUMNS = (
    'review_count INTEGER NOT NULL DEFAULT 0',
)


def main():
    parser = argparse.ArgumentParser(description='INT-340 人工复核迁移（复核表 + TestResult 标记列）')
    parser.add_argument('--dry-run', action='store_true', help='仅预览，不实际执行')
    args = parser.parse_args()

    print(f"数据库: {DB_HOST}:{DB_PORT}/{DB_NAME}")
    print(f"模式: {'DRY-RUN' if args.dry_run else '正式执行'}\n")

    conn = psycopg2.connect(
        host=DB_HOST, port=DB_PORT, dbname=DB_NAME, user=DB_USER, password=DB_PASS)
    cur = conn.cursor()

    if _table_exists(cur, 'test_result_reviews'):
        print('  [SKIP] 表 test_result_reviews 已存在')
    else:
        _exec(cur, conn, REVIEW_TABLE_SQL, args.dry_run)

    for index_name, sql in REVIEW_INDEXES:
        if _index_exists(cur, index_name):
            continue
        _exec(cur, conn, sql, args.dry_run)

    # test_results 追加复核标记列（幂等）
    for column_sql in RESULT_REVIEW_COLUMNS:
        column_name = column_sql.split()[0]
        if _column_exists(cur, 'test_results', column_name):
            print(f"  [SKIP] test_results.{column_name} 已存在")
            continue
        _exec(cur, conn, f'ALTER TABLE test_results ADD COLUMN IF NOT EXISTS {column_sql}', args.dry_run)

    # report_summaries 追加复核条数列（幂等）
    for column_sql in REPORT_SUMMARY_COLUMNS:
        column_name = column_sql.split()[0]
        if _column_exists(cur, 'report_summaries', column_name):
            print(f"  [SKIP] report_summaries.{column_name} 已存在")
            continue
        _exec(cur, conn, f'ALTER TABLE report_summaries ADD COLUMN IF NOT EXISTS {column_sql}', args.dry_run)

    cur.close()
    conn.close()
    print('\n迁移完成!' if not args.dry_run else '\n[DRY-RUN] 未实际写入数据。')


if __name__ == '__main__':
    main()
