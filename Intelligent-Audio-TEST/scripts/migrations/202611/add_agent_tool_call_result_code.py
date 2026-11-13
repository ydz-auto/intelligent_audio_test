# -*- coding: utf-8 -*-
"""迁移脚本：agent_tool_call 补 result_code 审计列（INT-2453）

背景（INT-2453 方案 §6.3 / §10）：
- 工具调用审计行要求字段齐全：``run_id`` / ``tool`` / ``args_hash`` /
  ``decision``（permission_decision）/ ``latency``（latency_ms）/ ``result_code``。
- ``result_code`` 记录工具结果码（OK / PERMISSION_DENIED / TOOL_NOT_ENABLED /
  INVALID_ARGUMENTS / APPROVAL_REQUIRED…），便于审计与回归检索。
- 列可 NULL；存量行为 NULL 表示「未记录结果码」，不迁移数据。

用法:
    python scripts/migrations/202611/add_agent_tool_call_result_code.py [--dry-run]

幂等性:
    重复执行安全：列已存在即 [SKIP]；表不存在（未跑 5/7 登录底座的库）也 SKIP，
    由 create_all 按 ORM 元数据建表时直接带出该列。
"""
import os
import sys
from urllib.parse import urlparse

import psycopg2
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.environ.get('DATABASE_URL')
# 懒解析：未配置 DATABASE_URL 时保留 None，让 __main__ 给出友好报错
parsed = urlparse(DATABASE_URL) if DATABASE_URL else None
DB_HOST = parsed.hostname if parsed else None
DB_PORT = (parsed.port or 5432) if parsed else 5432
DB_NAME = parsed.path.lstrip('/') if parsed else None
DB_USER = parsed.username if parsed else None
DB_PASS = parsed.password if parsed else None

TABLE = 'agent_tool_call'
COLUMN = 'result_code'
COLUMN_TYPE = 'VARCHAR(50)'


def _table_exists(cur, table):
    cur.execute("""
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = %s
    """, (table,))
    return cur.fetchone() is not None


def _column_exists(cur, table, column):
    cur.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = %s AND column_name = %s
    """, (table, column))
    return cur.fetchone() is not None


def migrate(dry_run=False):
    conn = psycopg2.connect(
        host=DB_HOST, port=DB_PORT, dbname=DB_NAME,
        user=DB_USER, password=DB_PASS,
    )
    conn.autocommit = True
    cur = conn.cursor()

    if not _table_exists(cur, TABLE):
        print(f"[SKIP] {TABLE} 不存在（create_all 会按 ORM 直接建出该列）")
    elif _column_exists(cur, TABLE, COLUMN):
        print(f"[SKIP] {TABLE}.{COLUMN} 已存在")
    else:
        alter = f"ALTER TABLE {TABLE} ADD COLUMN {COLUMN} {COLUMN_TYPE}"
        if dry_run:
            print(f"[DRY-RUN] {alter}")
        else:
            print(f"[EXEC] {alter}")
            cur.execute(alter)
            print(f"[DONE] {TABLE}.{COLUMN} 已添加")

    cur.close()
    conn.close()


if __name__ == '__main__':
    if not DATABASE_URL:
        print('错误: 未配置 DATABASE_URL 环境变量')
        sys.exit(1)
    migrate(dry_run='--dry-run' in sys.argv)
    print('迁移完成')
