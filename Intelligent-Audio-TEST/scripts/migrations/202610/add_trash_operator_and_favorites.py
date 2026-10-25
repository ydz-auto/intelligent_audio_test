# -*- coding: utf-8 -*-
"""迁移脚本：CUD 操作人列 + 收藏表（INT-141 收藏/回收站/操作人记录）

功能：
- test_tasks / test_cases / test_reports 补 deleted_by_user_id 列
  （created_by_user_id / updated_by_user_id 由 202608/add_audit_columns.py
  补齐，本脚本幂等兜底再补一次）
- 建 favorites 表（task_service 管 task|testcase）
- 建 report_favorites 表（report_service 管 report；单库部署下
  Base.metadata 表名全局唯一，不能与 favorites 同名复用）
- 补三个主表 created_by_user_id 索引（幂等）

幂等，可重复执行。

用法:
    python scripts/migrations/202610/add_trash_operator_and_favorites.py [--dry-run]

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


FAVORITES_TABLE_SQL = """
    CREATE TABLE favorites (
        id BIGSERIAL PRIMARY KEY,
        user_id BIGINT NOT NULL,
        entity_type VARCHAR(20) NOT NULL,
        entity_id VARCHAR(64) NOT NULL,
        created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT now(),
        CONSTRAINT uq_favorite_user_entity UNIQUE (user_id, entity_type, entity_id)
    )
"""

REPORT_FAVORITES_TABLE_SQL = """
    CREATE TABLE report_favorites (
        id BIGSERIAL PRIMARY KEY,
        user_id BIGINT NOT NULL,
        entity_type VARCHAR(20) NOT NULL,
        entity_id VARCHAR(64) NOT NULL,
        created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT now(),
        CONSTRAINT uq_report_favorite_user_entity UNIQUE (user_id, entity_type, entity_id)
    )
"""

FAVORITES_INDEXES = (
    ('favorites', 'idx_favorite_user_type',
     'CREATE INDEX idx_favorite_user_type ON favorites (user_id, entity_type)'),
    # INT-1784：idx_favorite_user_id 已下线（user_id 是该复合索引的前缀）
    ('report_favorites', 'idx_report_favorite_user',
     'CREATE INDEX idx_report_favorite_user ON report_favorites (user_id, entity_type)'),
    # INT-1784：idx_report_favorite_user_id 已下线（user_id 是该复合索引的前缀）
)


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


def _create_favorites_table(cur, conn, table, sql, dry_run):
    if _table_exists(cur, table):
        print(f"[SKIP] {table} 表已存在")
        return
    _exec(cur, conn, sql, dry_run)
    print(f"[DONE] 新增表: {table}")


def main(dry_run=False):
    conn = psycopg2.connect(
        host=DB_HOST, port=DB_PORT, dbname=DB_NAME,
        user=DB_USER, password=DB_PASS,
    )
    cur = conn.cursor()

    # 1. 主表补 deleted_by_user_id（幂等兜底 created_by/updated_by）
    for table in ('test_tasks', 'test_cases', 'test_reports'):
        if not _table_exists(cur, table):
            print(f"[SKIP] 表 {table} 不存在")
            continue
        _add_column(cur, conn, table, 'deleted_by_user_id', 'BIGINT', dry_run)
        _add_column(cur, conn, table, 'created_by_user_id', 'BIGINT', dry_run)
        _add_column(cur, conn, table, 'updated_by_user_id', 'BIGINT', dry_run)
        # INT-1784：ix_{table}_created_by_user_id 不再创建——这三张表都有
        # (created_by_user_id, visibility) 复合索引（idx_*_created_visibility），
        # 单列索引只是写放大；本步只保证列存在。

    # 2. 收藏表（按服务分治）
    _create_favorites_table(cur, conn, 'favorites', FAVORITES_TABLE_SQL, dry_run)
    _create_favorites_table(cur, conn, 'report_favorites', REPORT_FAVORITES_TABLE_SQL, dry_run)
    for table, index_name, sql in FAVORITES_INDEXES:
        if not _table_exists(cur, table):
            print(f"[SKIP] 索引 {index_name}（宿主表未创建）")
            continue
        _ensure_index(cur, conn, index_name, sql, dry_run)

    cur.close()
    conn.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='CUD 操作人列 + 收藏表迁移（INT-141）')
    parser.add_argument('--dry-run', action='store_true', help='仅预览，不实际执行')
    args = parser.parse_args()

    print("=" * 60)
    print("CUD 操作人列 + 收藏表迁移（INT-141）")
    print("=" * 60)
    print(f"数据库: {parsed.username}@{parsed.hostname}:{parsed.port}/{parsed.path.lstrip('/')}")
    print(f"模式: {'DRY-RUN' if args.dry_run else '正式执行'}\n")
    main(dry_run=args.dry_run)
