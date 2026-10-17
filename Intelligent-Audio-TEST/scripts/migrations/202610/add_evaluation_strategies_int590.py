# -*- coding: utf-8 -*-
"""迁移脚本：评估策略实体（INT-590）

功能（幂等，可重复执行）：
- 建 evaluation_strategies 表（策略实体归 task_service 用例域：
  整体评估维度+全局背景噪声抽为可复用策略，config JSON 与用例 config 同构）
- test_cases 加列 strategy_id（FK→evaluation_strategies.id，nullable）/
  strategy_overrides（JSON，nullable）
- 兼容现有用例：strategy_id 为空 = 未引用策略，评估字段既有数据保留在
  用例级 config.dimensions / config.background_noise，无迁移损失。

新建库由 PO 模型 create_all 直接带出（模型已同步建表/补列）；
本脚本针对既有环境，对已存在表/列自动 [SKIP]。

用法:
    python scripts/migrations/202610/add_evaluation_strategies_int590.py [--dry-run]

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


STRATEGY_TABLE_SQL = """
    CREATE TABLE IF NOT EXISTS evaluation_strategies (
        id VARCHAR(50) PRIMARY KEY,
        name VARCHAR(150) NOT NULL,
        description TEXT,
        algorithm_type VARCHAR(50),
        enabled BOOLEAN NOT NULL DEFAULT TRUE,
        config JSON NOT NULL,
        created_by_user_id BIGINT,
        updated_by_user_id BIGINT,
        created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT now(),
        updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT now(),
        deleted BOOLEAN NOT NULL DEFAULT FALSE,
        deleted_at TIMESTAMP WITHOUT TIME ZONE,
        deleted_by_user_id BIGINT
    )
"""

INDEXES = (
    ('ix_evaluation_strategies_created_by',
     'CREATE INDEX IF NOT EXISTS ix_evaluation_strategies_created_by '
     'ON evaluation_strategies (created_by_user_id)'),
    ('ix_evaluation_strategies_deleted',
     'CREATE INDEX IF NOT EXISTS ix_evaluation_strategies_deleted '
     'ON evaluation_strategies (deleted)'),
    ('ix_test_cases_strategy_id',
     'CREATE INDEX IF NOT EXISTS ix_test_cases_strategy_id '
     'ON test_cases (strategy_id)'),
)


def main(dry_run=False):
    conn = psycopg2.connect(
        host=parsed.hostname, port=parsed.port or 5432,
        dbname=parsed.path.lstrip('/'),
        user=parsed.username, password=parsed.password,
    )
    cur = conn.cursor()

    # 1. 建 evaluation_strategies 表
    if not _table_exists(cur, 'evaluation_strategies'):
        _exec(cur, conn, STRATEGY_TABLE_SQL, dry_run)
        print("[DONE] evaluation_strategies 表已创建")
    else:
        print("[SKIP] 表 evaluation_strategies 已存在")

    # 2. test_cases 补列（FK 仅在表已建时执行；列级 nullable 保证既有数据兼容）
    if _table_exists(cur, 'test_cases'):
        _add_column(cur, conn, 'test_cases', 'strategy_id', 'VARCHAR(50)', dry_run)
        _add_column(cur, conn, 'test_cases', 'strategy_overrides', 'JSON', dry_run)
    else:
        print("[SKIP] 表 test_cases 不存在（新建库由 PO create_all 带出）")

    # 3. 索引（幂等）
    for index_name, sql in INDEXES:
        if _index_exists(cur, index_name):
            print(f"[SKIP] 索引 {index_name} 已存在")
            continue
        _exec(cur, conn, sql, dry_run)
        print(f"[DONE] 索引 {index_name} 已创建")

    cur.close()
    conn.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='评估策略实体迁移（INT-590）')
    parser.add_argument('--dry-run', action='store_true', help='仅预览，不实际执行')
    args = parser.parse_args()

    print("=" * 60)
    print("评估策略实体迁移（INT-590）")
    print("=" * 60)
    print(f"数据库: {parsed.username}@{parsed.hostname}:{parsed.port}/{parsed.path.lstrip('/')}")
    print(f"模式: {'DRY-RUN' if args.dry_run else '正式执行'}\n")
    main(dry_run=args.dry_run)
