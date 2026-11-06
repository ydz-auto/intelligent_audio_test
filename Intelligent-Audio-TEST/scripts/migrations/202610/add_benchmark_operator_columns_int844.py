# -*- coding: utf-8 -*-
"""迁移脚本：基准线管理 CRUD 补操作人 user_id（INT-844）

背景（INT-844 缺陷）：报告域已带操作人 user_id（INT-141），但基准线管理
四表缺：
- benchmark_sources.created_by 是 String(120) 旧列，存 command.created_by
  （客户端自报），非认证 user_id，违反 INT-141 红线；
- benchmark_metric_mappings / benchmark_baselines / benchmark_reports
  无 user_id 列。

功能（幂等，可重复执行）：
- benchmark_sources 补 created_by_user_id / updated_by_user_id（BIGINT）
- benchmark_metric_mappings 补 created_by_user_id / updated_by_user_id（BIGINT）
- benchmark_baselines 补 created_by_user_id（BIGINT，导入属用户操作）
- benchmark_reports 补 created_by_user_id（BIGINT，发布属用户操作）
- 补 created_by_user_id 索引（对齐 report 表操作人列索引口径，幂等）

旧 created_by / published_by 字符串列保留（V9.7.10 兼容）；客户端自报的
command.created_by 不再作为操作人依据（红线：不信任客户端自报，操作人一律
取认证 user_id；AUTH_MODE=off → None → NULL，不硬编码 0 兜底）。

新建库由 PO 模型 create_all 直接带出（模型已同步补列）；
本脚本针对既有环境，对已存在列自动 [SKIP]。

用法:
    python scripts/migrations/202610/add_benchmark_operator_columns_int844.py [--dry-run]

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
    if not _table_exists(cur, table):
        print(f"[SKIP] 表 {table} 不存在")
        return
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

    # 1. 数据源：created_by_user_id + updated_by_user_id（旧 created_by 字符串列保留）
    _add_column(cur, conn, 'benchmark_sources', 'created_by_user_id', 'BIGINT', dry_run)
    _add_column(cur, conn, 'benchmark_sources', 'updated_by_user_id', 'BIGINT', dry_run)
    _ensure_index(
        cur, conn, 'ix_benchmark_sources_created_by_user_id',
        'CREATE INDEX IF NOT EXISTS ix_benchmark_sources_created_by_user_id '
        'ON benchmark_sources (created_by_user_id)',
        dry_run)

    # 2. 指标映射：created_by_user_id + updated_by_user_id
    _add_column(cur, conn, 'benchmark_metric_mappings', 'created_by_user_id', 'BIGINT', dry_run)
    _add_column(cur, conn, 'benchmark_metric_mappings', 'updated_by_user_id', 'BIGINT', dry_run)
    _ensure_index(
        cur, conn, 'ix_benchmark_metric_mappings_created_by_user_id',
        'CREATE INDEX IF NOT EXISTS ix_benchmark_metric_mappings_created_by_user_id '
        'ON benchmark_metric_mappings (created_by_user_id)',
        dry_run)

    # 3. 基线条目：created_by_user_id（导入属用户操作）
    _add_column(cur, conn, 'benchmark_baselines', 'created_by_user_id', 'BIGINT', dry_run)
    _ensure_index(
        cur, conn, 'ix_benchmark_baselines_created_by_user_id',
        'CREATE INDEX IF NOT EXISTS ix_benchmark_baselines_created_by_user_id '
        'ON benchmark_baselines (created_by_user_id)',
        dry_run)

    # 4. Benchmark 报告发布记录：created_by_user_id（发布属用户操作；published_by 旧列保留）
    _add_column(cur, conn, 'benchmark_reports', 'created_by_user_id', 'BIGINT', dry_run)
    _ensure_index(
        cur, conn, 'ix_benchmark_reports_created_by_user_id',
        'CREATE INDEX IF NOT EXISTS ix_benchmark_reports_created_by_user_id '
        'ON benchmark_reports (created_by_user_id)',
        dry_run)

    cur.close()
    conn.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='基准线管理操作人 user_id 补齐迁移（INT-844）')
    parser.add_argument('--dry-run', action='store_true', help='仅预览，不实际执行')
    args = parser.parse_args()

    print("=" * 60)
    print("基准线管理操作人 user_id 补齐迁移（INT-844）")
    print("=" * 60)
    print(f"数据库: {parsed.username}@{parsed.hostname}:{parsed.port}/{parsed.path.lstrip('/')}")
    print(f"模式: {'DRY-RUN' if args.dry_run else '正式执行'}\n")
    main(dry_run=args.dry_run)
