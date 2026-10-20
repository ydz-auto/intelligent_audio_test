# -*- coding: utf-8 -*-
"""迁移脚本：数据可见性基座列补齐（INT-423 一期）

背景：INT-423 数据可见性体系一期基座是 shared 层产物（Visibility 枚举 +
visibility_filter 行级过滤助手 + 审计事件），业务服务的读写路径改造在
423-2/3/4 各自进行。本脚本为既有环境补齐数据面：
- 10 张资源表加 visibility 列（VARCHAR(20) NOT NULL DEFAULT 'shared'，
  存量行为即共享，零回归）
- published_tasks 补 created_by_user_id（存量不回填——保持共享现状）
- 各表 visibility 单列索引 + 高频列表表（test_tasks/test_cases/test_reports/
  audios/dimensions）的 (created_by_user_id, visibility) 复合索引

新建库由 PO 模型 create_all 直接带出（模型在 423-2/3/4 逐服务同步补列）；
本脚本针对既有环境，对已存在列/索引自动 [SKIP]，幂等重跑不报错。

用法:
    python scripts/migrations/202610/add_visibility_columns_int423.py [--dry-run]

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

# 需要加 visibility 列的资源表（INT-423 一期范围）
VISIBILITY_TABLES = (
    'test_tasks', 'test_cases', 'test_case_groups', 'tags', 'tag_categories',
    'published_tasks', 'audios', 'test_reports', 'dimensions', 'categories',
)
# 高频列表表：额外补 (created_by_user_id, visibility) 复合索引
COMPOSITE_INDEX_TABLES = (
    'test_tasks', 'test_cases', 'test_reports', 'audios', 'dimensions',
)

VISIBILITY_COLUMN_TYPE = "VARCHAR(20) NOT NULL DEFAULT 'shared'"


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

    # 1. 10 张资源表加 visibility 列（存量默认 shared，零回归）
    for table in VISIBILITY_TABLES:
        if not _table_exists(cur, table):
            print(f"[SKIP] 表 {table} 不存在")
            continue
        _add_column(cur, conn, table, 'visibility', VISIBILITY_COLUMN_TYPE, dry_run)

    # 2. published_tasks 补 created_by_user_id（存量不回填，保持共享现状）
    if _table_exists(cur, 'published_tasks'):
        _add_column(cur, conn, 'published_tasks', 'created_by_user_id', 'BIGINT NULL', dry_run)
        # INT-463：published_tasks owner 索引（新建库由 PO __table_args__ 带出）
        if _col_exists(cur, 'published_tasks', 'created_by_user_id'):
            _ensure_index(
                cur, conn, 'idx_published_task_created_by_user_id',
                'CREATE INDEX IF NOT EXISTS idx_published_task_created_by_user_id '
                'ON published_tasks (created_by_user_id)',
                dry_run)

    # 3. 各表 visibility 单列索引（幂等）
    for table in VISIBILITY_TABLES:
        if not _table_exists(cur, table):
            continue
        _ensure_index(
            cur, conn, f'idx_{table}_visibility',
            f'CREATE INDEX IF NOT EXISTS idx_{table}_visibility '
            f'ON {table} (visibility)',
            dry_run)

    # 4. 高频列表表复合索引 (created_by_user_id, visibility)
    for table in COMPOSITE_INDEX_TABLES:
        if not _table_exists(cur, table):
            continue
        if not _col_exists(cur, table, 'created_by_user_id'):
            print(f"[SKIP] {table} 缺 created_by_user_id 列，跳过复合索引")
            continue
        _ensure_index(
            cur, conn, f'idx_{table}_created_visibility',
            f'CREATE INDEX IF NOT EXISTS idx_{table}_created_visibility '
            f'ON {table} (created_by_user_id, visibility)',
            dry_run)

    cur.close()
    conn.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='数据可见性基座列补齐迁移（INT-423）')
    parser.add_argument('--dry-run', action='store_true', help='仅预览，不实际执行')
    args = parser.parse_args()

    print("=" * 60)
    print("数据可见性基座列补齐迁移（INT-423）")
    print("=" * 60)
    print(f"数据库: {parsed.username}@{parsed.hostname}:{parsed.port}/{parsed.path.lstrip('/')}")
    print(f"模式: {'DRY-RUN' if args.dry_run else '正式执行'}\n")
    main(dry_run=args.dry_run)
