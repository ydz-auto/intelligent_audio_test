# -*- coding: utf-8 -*-
"""迁移脚本：CUD 操作人列补齐（INT-299）

背景（INT-299 实测）：INT-141 只覆盖了 test_tasks / test_cases / test_reports
三表的 created_by_user_id / updated_by_user_id / deleted_by_user_id；
audios / devices / playback_devices 缺 deleted_by_user_id，
algorithm_groups / algorithm_definitions 三列全缺。

功能（幂等，可重复执行）：
- audios / devices / playback_devices 补 deleted_by_user_id
- algorithm_groups / algorithm_definitions 补
  created_by_user_id / updated_by_user_id / deleted_by_user_id
- 补 created_by_user_id 索引（幂等）

新建库由 PO 模型 create_all 直接带出（模型已同步补列）；
本脚本针对既有环境，对已存在列自动 [SKIP]。

用法:
    python scripts/migrations/202610/add_operator_columns_int299.py [--dry-run]

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


def _index_exists(cur, index_name):
    cur.execute("SELECT 1 FROM pg_indexes WHERE indexname = %s", (index_name,))
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


def _ensure_index(cur, conn, index_name, sql, dry_run):
    if _index_exists(cur, index_name):
        print(f"[SKIP] 索引 {index_name} 已存在")
        return
    _exec(cur, conn, sql, dry_run)
    print(f"[DONE] 索引 {index_name} 已创建")


def main(dry_run=False):
    conn = psycopg2.connect(
        host=parsed.hostname, port=parsed.port or 5432,
        dbname=parsed.path.lstrip('/'),
        user=parsed.username, password=parsed.password,
    )
    cur = conn.cursor()

    # 1. 已有两列的表补 deleted_by_user_id
    for table in ('audios', 'devices', 'playback_devices'):
        if not _table_exists(cur, table):
            print(f"[SKIP] 表 {table} 不存在")
            continue
        _add_column(cur, conn, table, 'deleted_by_user_id', 'BIGINT', dry_run)

    # 2. algorithm 域两表三列全补
    for table in ('algorithm_groups', 'algorithm_definitions'):
        if not _table_exists(cur, table):
            print(f"[SKIP] 表 {table} 不存在")
            continue
        _add_column(cur, conn, table, 'created_by_user_id', 'BIGINT', dry_run)
        _add_column(cur, conn, table, 'updated_by_user_id', 'BIGINT', dry_run)
        _add_column(cur, conn, table, 'deleted_by_user_id', 'BIGINT', dry_run)
        _ensure_index(
            cur, conn, f'ix_{table}_created_by_user_id',
            f'CREATE INDEX IF NOT EXISTS ix_{table}_created_by_user_id '
            f'ON {table} (created_by_user_id)',
            dry_run)

    # 3. 既有三表 created_by 索引兜底（对齐 INT-141 脚本口径，幂等）
    #    INT-1784：audios 不再兜底——ix_audios_created_by_user_id 已下线，
    #    该列由 (created_by_user_id, visibility) 复合索引覆盖。
    for table in ('devices', 'playback_devices'):
        if not _table_exists(cur, table):
            continue
        _ensure_index(
            cur, conn, f'ix_{table}_created_by_user_id',
            f'CREATE INDEX IF NOT EXISTS ix_{table}_created_by_user_id '
            f'ON {table} (created_by_user_id)',
            dry_run)

    cur.close()
    conn.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='CUD 操作人列补齐迁移（INT-299）')
    parser.add_argument('--dry-run', action='store_true', help='仅预览，不实际执行')
    args = parser.parse_args()

    print("=" * 60)
    print("CUD 操作人列补齐迁移（INT-299）")
    print("=" * 60)
    print(f"数据库: {parsed.username}@{parsed.hostname}:{parsed.port}/{parsed.path.lstrip('/')}")
    print(f"模式: {'DRY-RUN' if args.dry_run else '正式执行'}\n")
    main(dry_run=args.dry_run)
