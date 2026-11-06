# -*- coding: utf-8 -*-
"""迁移脚本：dimensions 表新增 agg_denominator 列

比率统计分母口径: round=按轮次 / case=按用例（默认）。
幂等，可重复执行。

用法:
    python scripts/migrations/202609/add_agg_denominator_column.py [--dry-run]
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


def migrate(dry_run=False):
    conn = psycopg2.connect(
        host=DB_HOST, port=DB_PORT, dbname=DB_NAME,
        user=DB_USER, password=DB_PASS,
    )
    cur = conn.cursor()

    cur.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'dimensions' AND column_name = 'agg_denominator'
    """)
    if cur.fetchone():
        # 列已存在：全新库经 create_all_tables（ORM nullable=False 但无 server
        # default）建列时缺服务端默认值——202609 种子（seed_interruption_dimensions
        # 等）以原生 SQL INSERT 不带 agg_denominator，NOT NULL 无默认必败
        # （INT-993 隔离栈全新库实测 NotNullViolation）。补 server default。
        cur.execute("""
            SELECT column_default FROM information_schema.columns
            WHERE table_name = 'dimensions' AND column_name = 'agg_denominator'
        """)
        has_default = cur.fetchone()[0]
        if not has_default:
            sql = "ALTER TABLE dimensions ALTER COLUMN agg_denominator SET DEFAULT 'case'"
            if dry_run:
                print(f"[DRY-RUN] {sql}")
            else:
                print(f"[EXEC] {sql}")
                cur.execute(sql)
                conn.commit()
        print("[SKIP] dimensions.agg_denominator 已存在（已确保 server default）")
        cur.close()
        conn.close()
        return

    sql = "ALTER TABLE dimensions ADD COLUMN agg_denominator VARCHAR(20) NOT NULL DEFAULT 'case'"
    if dry_run:
        print(f"[DRY-RUN] {sql}")
    else:
        print(f"[EXEC] {sql}")
        cur.execute(sql)
        conn.commit()
        print("[DONE] 新增列: dimensions.agg_denominator (默认 'case'=按用例)")

    cur.close()
    conn.close()


if __name__ == '__main__':
    dry_run = '--dry-run' in sys.argv
    migrate(dry_run)
