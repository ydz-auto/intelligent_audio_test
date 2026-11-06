# -*- coding: utf-8 -*-
"""迁移脚本：挑选合并购物车/挑选集条目补 source_result_type 列（INT-577 §11-5）

功能：
- cherry_pick_cart_items 补 source_result_type VARCHAR(50) NULL（购物车条目来源结果类型快照）
- cherry_pick_set_items 补 source_result_type VARCHAR(50) NULL（挑选集条目与购物车同构）

幂等，可重复执行（逐列检查 information_schema.columns）。

用法:
    python scripts/migrations/202610/add_cherry_pick_source_result_type_int577.py [--dry-run]

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


def _column_exists(cur, table, column):
    cur.execute(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name = %s AND column_name = %s",
        (table, column),
    )
    return cur.fetchone() is not None


def _exec(cur, conn, sql, dry_run):
    if dry_run:
        print(f"[DRY-RUN] {sql.strip()[:120]}")
        return
    print(f"[EXEC] {sql.strip()[:120]}")
    cur.execute(sql)
    conn.commit()


COLUMNS = (
    ('cherry_pick_cart_items', 'source_result_type',
     'ALTER TABLE cherry_pick_cart_items '
     'ADD COLUMN source_result_type VARCHAR(50)'),
    ('cherry_pick_set_items', 'source_result_type',
     'ALTER TABLE cherry_pick_set_items '
     'ADD COLUMN source_result_type VARCHAR(50)'),
)


def main():
    parser = argparse.ArgumentParser(description='INT-577 挑选合并快照补 source_result_type 迁移')
    parser.add_argument('--dry-run', action='store_true', help='仅预览，不实际执行')
    args = parser.parse_args()

    print(f"数据库: {DB_HOST}:{DB_PORT}/{DB_NAME}")
    print(f"模式: {'DRY-RUN' if args.dry_run else '正式执行'}\n")

    conn = psycopg2.connect(
        host=DB_HOST, port=DB_PORT, dbname=DB_NAME, user=DB_USER, password=DB_PASS)
    cur = conn.cursor()

    for table, column, sql in COLUMNS:
        if _column_exists(cur, table, column):
            print(f"  [SKIP] {table}.{column} 已存在")
            continue
        _exec(cur, conn, sql, args.dry_run)

    cur.close()
    conn.close()
    print('\n迁移完成!' if not args.dry_run else '\n[DRY-RUN] 未实际写入数据。')


if __name__ == '__main__':
    main()
