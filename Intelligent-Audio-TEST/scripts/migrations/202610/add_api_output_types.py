# -*- coding: utf-8 -*-
"""迁移脚本：apis 表新增 output_types 列（INT-74 枚举消费接线）

API 聚合多模态输出类型列表（OutputType 枚举值 JSON 数组，
如 ["audio", "text"]），设计依据 doc/功能设计文档/01_测试执行/
01_UseCase总览.md §0.6 / 附录A #14（原（新增）列落地）。
幂等，可重复执行。

用法:
    python scripts/migrations/202610/add_api_output_types.py [--dry-run]
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
        WHERE table_name = 'apis' AND column_name = 'output_types'
    """)
    if cur.fetchone():
        print("[SKIP] apis.output_types 已存在")
        cur.close()
        conn.close()
        return

    sql = "ALTER TABLE apis ADD COLUMN output_types JSONB NOT NULL DEFAULT '[]'::jsonb"
    if dry_run:
        print(f"[DRY-RUN] {sql}")
    else:
        print(f"[EXEC] {sql}")
        cur.execute(sql)
        conn.commit()
        print("[OK] apis.output_types 迁移完成")

    cur.close()
    conn.close()


if __name__ == '__main__':
    migrate(dry_run='--dry-run' in sys.argv)
