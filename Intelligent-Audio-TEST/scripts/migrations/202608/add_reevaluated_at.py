# -*- coding: utf-8 -*-
"""迁移脚本：为 test_tasks 表添加 reevaluated_at 和 reevaluation_count 列

ORM 模型 Task 中定义了这两个列但数据库表缺失，导致调度器启动时查询报错。

用法:
    python scripts/migrations/202608/add_reevaluated_at.py [--dry-run]
"""
import sys
import os

import psycopg2
from dotenv import load_dotenv
from urllib.parse import urlparse

load_dotenv()
DATABASE_URL = os.environ.get('DATABASE_URL')
parsed = urlparse(DATABASE_URL)
DB_HOST = parsed.hostname
DB_PORT = parsed.port or 5432
DB_NAME = parsed.path.lstrip('/')
DB_USER = parsed.username
DB_PASS = parsed.password

# 需要添加的列: (column_name, column_type, is_nullable)
COLUMNS = [
    ('reevaluated_at', 'TIMESTAMP WITHOUT TIME ZONE', True),
    ('reevaluation_count', 'INTEGER NOT NULL DEFAULT 0', False),
]


def migrate(dry_run=False):
    conn = psycopg2.connect(
        host=DB_HOST, port=DB_PORT, dbname=DB_NAME,
        user=DB_USER, password=DB_PASS,
    )
    cur = conn.cursor()

    for col_name, col_type, _nullable in COLUMNS:
        cur.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'test_tasks' AND column_name = %s
        """, (col_name,))
        if cur.fetchone():
            print(f"[SKIP] test_tasks.{col_name} 已存在")
            continue

        sql = f"ALTER TABLE test_tasks ADD COLUMN {col_name} {col_type}"
        if dry_run:
            print(f"[DRY-RUN] {sql}")
        else:
            print(f"[EXEC] {sql}")
            cur.execute(sql)
            conn.commit()
            print(f"[DONE] test_tasks.{col_name} 已添加")

    cur.close()
    conn.close()


if __name__ == '__main__':
    dry_run = '--dry-run' in sys.argv
    migrate(dry_run)
