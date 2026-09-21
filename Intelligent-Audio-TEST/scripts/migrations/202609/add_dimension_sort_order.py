# -*- coding: utf-8 -*-
"""迁移脚本：dimensions 表新增 sort_order 列

评估维度在报告页的展示顺序（数值越小越靠前）。
幂等，可重复执行。

用法:
    python scripts/migrations/202609/add_dimension_sort_order.py [--dry-run]
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
        WHERE table_name = 'dimensions' AND column_name = 'sort_order'
    """)
    if cur.fetchone():
        print("[SKIP] dimensions.sort_order 已存在")
        cur.close()
        conn.close()
        return

    sql = "ALTER TABLE dimensions ADD COLUMN sort_order INTEGER NOT NULL DEFAULT 0"
    if dry_run:
        print(f"[DRY-RUN] {sql}")
    else:
        print(f"[EXEC] {sql}")
        cur.execute(sql)

    # 存量数据按 id 顺序补齐 sort_order，保证顺序稳定且与现有展示一致
    cur.execute("SELECT id FROM dimensions WHERE deleted = false ORDER BY id")
    rows = cur.fetchall()
    for idx, (dim_id,) in enumerate(rows):
        upd = "UPDATE dimensions SET sort_order = %s WHERE id = %s"
        if dry_run:
            print(f"[DRY-RUN] {upd} ({idx}, {dim_id})")
        else:
            cur.execute(upd, (idx, dim_id))

    if not dry_run:
        conn.commit()
        print(f"[DONE] 新增列: dimensions.sort_order，并按 id 顺序初始化 {len(rows)} 条存量维度")

    cur.close()
    conn.close()


if __name__ == '__main__':
    dry_run = '--dry-run' in sys.argv
    migrate(dry_run)
