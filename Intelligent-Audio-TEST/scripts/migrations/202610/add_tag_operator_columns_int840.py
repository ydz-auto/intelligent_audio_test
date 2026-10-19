# -*- coding: utf-8 -*-
"""迁移脚本：标签/标签分类/用例分组 CUD 操作人 deleted_by_user_id 补齐（INT-840）

背景（INT-840 审计）：tags / tag_categories / test_case_groups 三表已有
created_by_user_id / updated_by_user_id 列（202608/add_audit_columns.py 补齐），
但缺 deleted_by_user_id —— 软删路径无法记录操作人。本脚本为既有环境补列。

功能（幂等，可重复执行）：
- tags / tag_categories / test_case_groups 补 deleted_by_user_id（BIGINT NULL）

新建库由 PO 模型 create_all 直接带出（模型已同步补列）；
本脚本针对既有环境，对已存在列自动 [SKIP]。

用法:
    python scripts/migrations/202610/add_tag_operator_columns_int840.py [--dry-run]

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


def _table_exists(cur, table):
    cur.execute(
        "SELECT 1 FROM information_schema.tables WHERE table_name = %s", (table,)
    )
    return cur.fetchone() is not None


def _col_exists(cur, table, column):
    cur.execute(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name = %s AND column_name = %s", (table, column)
    )
    return cur.fetchone() is not None


def _exec(cur, conn, sql, dry_run):
    if dry_run:
        print(f"[DRY-RUN] {sql}")
        return
    print(f"[EXEC] {sql}")
    cur.execute(sql)
    conn.commit()


def _add_column(cur, conn, table, column, col_type, dry_run):
    if _col_exists(cur, table, column):
        print(f"[SKIP] {table}.{column} 列已存在")
        return
    sql = f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"
    _exec(cur, conn, sql, dry_run)
    print(f"[DONE] {table}.{column} 已添加")


def main(dry_run=False):
    conn = psycopg2.connect(
        host=parsed.hostname, port=parsed.port or 5432,
        dbname=parsed.path.lstrip('/'),
        user=parsed.username, password=parsed.password,
    )
    cur = conn.cursor()

    for table in ('tags', 'tag_categories', 'test_case_groups'):
        if not _table_exists(cur, table):
            print(f"[SKIP] 表 {table} 不存在")
            continue
        _add_column(cur, conn, table, 'deleted_by_user_id', 'BIGINT', dry_run)

    cur.close()
    conn.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='标签域 deleted_by_user_id 补齐迁移（INT-840）')
    parser.add_argument('--dry-run', action='store_true', help='仅预览，不实际执行')
    args = parser.parse_args()

    print("=" * 60)
    print("标签域 deleted_by_user_id 补齐迁移（INT-840）")
    print("=" * 60)
    print(f"数据库: {parsed.username}@{parsed.hostname}:{parsed.port}/{parsed.path.lstrip('/')}")
    print(f"模式: {'DRY-RUN' if args.dry_run else '正式执行'}\n")
    main(dry_run=args.dry_run)
