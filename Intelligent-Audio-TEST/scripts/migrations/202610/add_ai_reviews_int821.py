# -*- coding: utf-8 -*-
"""迁移脚本：AI 复核记录表（INT-821/INT-800）

功能：
- 建 ai_reviews 表（AI 复核记录；机器判定，独立表不与人工复核留痕同表）
- 索引 idx_ai_review_task(task_id) / idx_ai_review_result(result_id, dimension_id)

幂等，可重复执行（CREATE TABLE IF NOT EXISTS / CREATE INDEX IF NOT EXISTS）。

用法:
    python scripts/migrations/202610/add_ai_reviews_int821.py [--dry-run]

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


AI_REVIEW_TABLE_SQL = """
    CREATE TABLE IF NOT EXISTS ai_reviews (
        id BIGSERIAL PRIMARY KEY,
        result_id INTEGER NOT NULL,
        task_id INTEGER NOT NULL,
        test_case_id VARCHAR(50),
        dimension_id INTEGER,
        status VARCHAR(20) NOT NULL DEFAULT 'pending',
        verdict VARCHAR(20),
        confidence NUMERIC(3, 2),
        reasoning TEXT,
        adopted INTEGER NOT NULL DEFAULT 0,
        adopted_by_user_id BIGINT,
        adopted_at TIMESTAMP WITHOUT TIME ZONE,
        rejected INTEGER NOT NULL DEFAULT 0,
        rejected_by_user_id BIGINT,
        rejected_at TIMESTAMP WITHOUT TIME ZONE,
        created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT now(),
        updated_at TIMESTAMP WITHOUT TIME ZONE
    )
"""

AI_REVIEW_INDEXES = (
    ('idx_ai_review_task', 'CREATE INDEX IF NOT EXISTS idx_ai_review_task ON ai_reviews (task_id)'),
    ('idx_ai_review_result', 'CREATE INDEX IF NOT EXISTS idx_ai_review_result ON ai_reviews (result_id, dimension_id)'),
)


def main():
    parser = argparse.ArgumentParser(description='INT-821 AI 复核记录迁移（ai_reviews 表 + 索引）')
    parser.add_argument('--dry-run', action='store_true', help='仅预览，不实际执行')
    args = parser.parse_args()

    print(f"数据库: {DB_HOST}:{DB_PORT}/{DB_NAME}")
    print(f"模式: {'DRY-RUN' if args.dry_run else '正式执行'}\n")

    conn = psycopg2.connect(
        host=DB_HOST, port=DB_PORT, dbname=DB_NAME, user=DB_USER, password=DB_PASS)
    cur = conn.cursor()

    if _table_exists(cur, 'ai_reviews'):
        print('  [SKIP] 表 ai_reviews 已存在')
    else:
        _exec(cur, conn, AI_REVIEW_TABLE_SQL, args.dry_run)

    for index_name, sql in AI_REVIEW_INDEXES:
        if _index_exists(cur, index_name):
            print(f'  [SKIP] 索引 {index_name} 已存在')
            continue
        _exec(cur, conn, sql, args.dry_run)

    cur.close()
    conn.close()
    print('\n迁移完成!' if not args.dry_run else '\n[DRY-RUN] 未实际写入数据。')


if __name__ == '__main__':
    main()
