# -*- coding: utf-8 -*-
"""迁移脚本：删除已发布任务类型列与用例执行口径派生列（task_type / test_type 概念废除）

背景：
- 任务类型（api/e2e/mixed）概念已废除：执行方式唯一依据是
  task_case_relations.device_type，列表中已提供 device_type 筛选，
  不再需要 published_tasks.type 与 test_type 过滤/统计。
- test_cases.derived_test_type 是 INT-1469 为用例列表按 test_type 过滤
  物化的冗余列；过滤入口已移除，该列不再读写，随之删除。
  用例本身纯数据化，不存储/派生 api-e2e 类型。

用法:
    python scripts/migrations/202610/drop_published_task_type_and_case_derived_test_type.py [--dry-run]

幂等性:
    重复执行安全：列/索引不存在即 [SKIP]。
"""
import os
import sys
from urllib.parse import urlparse

import psycopg2
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.environ.get('DATABASE_URL')

# 待删除列: (table, column)
DROP_COLUMNS = [
    ('published_tasks', 'type'),
    ('test_cases', 'derived_test_type'),
]

# 待删除索引（列删除时 PG 会自动级联，显式先删保证幂等日志清晰）
DROP_INDEXES = [
    'ix_test_cases_derived_test_type',
]


def column_exists(cur, table, column):
    cur.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = %s AND column_name = %s
    """, (table, column))
    return cur.fetchone() is not None


def migrate(dry_run=False):
    if not DATABASE_URL:
        print('错误: 未配置 DATABASE_URL 环境变量')
        sys.exit(1)
    parsed = urlparse(DATABASE_URL)
    conn = psycopg2.connect(
        host=parsed.hostname, port=parsed.port or 5432,
        dbname=parsed.path.lstrip('/'),
        user=parsed.username, password=parsed.password,
    )
    conn.autocommit = True
    cur = conn.cursor()

    for index_name in DROP_INDEXES:
        sql = f"DROP INDEX IF EXISTS {index_name}"
        if dry_run:
            print(f"[DRY-RUN] {sql}")
        else:
            print(f"[EXEC] {sql}")
            cur.execute(sql)

    for table, column in DROP_COLUMNS:
        if not column_exists(cur, table, column):
            print(f"[SKIP] {table}.{column} 已不存在")
            continue
        sql = f"ALTER TABLE {table} DROP COLUMN {column}"
        if dry_run:
            print(f"[DRY-RUN] {sql}")
        else:
            print(f"[EXEC] {sql}")
            cur.execute(sql)
            print(f"[DONE] {table}.{column} 已删除")

    cur.close()
    conn.close()


if __name__ == '__main__':
    migrate(dry_run='--dry-run' in sys.argv)
    print('迁移完成')
