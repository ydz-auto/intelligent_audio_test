# -*- coding: utf-8 -*-
"""迁移脚本：agent_run 补 provider_id 列（对话页供应商下拉）

背景：
- 对话页允许在多个供应商之间切换（同一 run 用所选供应商的 Key / Base URL）；
  选择结果落在 ``agent_run.provider_id``，ProviderRegistry 按 ``owner + tenant``
  校验归属后解析；空值 = 沿用 owner 默认供应商（与存量行为一致）。
- 列可 NULL；存量 run 不回填，继续按默认供应商解析。

用法:
    python scripts/migrations/202611/add_agent_run_provider_id.py [--dry-run]

幂等性:
    重复执行安全：列已存在即 [SKIP]；表不存在（全新库由 create_all 按 ORM 建表）
    也 SKIP，由 ORM 元数据直接带出该列。
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

TABLE = 'agent_run'
COLUMN = 'provider_id'
COLUMN_TYPE = 'VARCHAR(64)'


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
