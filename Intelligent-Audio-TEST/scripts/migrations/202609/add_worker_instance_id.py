# -*- coding: utf-8 -*-
"""迁移脚本：为 test_tasks 表添加 worker_instance_id 列

多实例部署下，任务归属到具体执行实例（task_service:{host}:{port}:{hex}），
用于：
- 启动恢复只处理归属本实例（或未归属）的中间态任务，避免误杀其他存活实例的任务；
- 调度器/队列消费按归属校验，死实例任务可被收养重新执行。

用法:
    python scripts/migrations/202609/add_worker_instance_id.py [--dry-run]
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
    ('worker_instance_id', 'VARCHAR(100)', True),
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

        # 为归属列建索引，支撑启动恢复 / 兜底调度的归属过滤查询
        index_sql = f"CREATE INDEX IF NOT EXISTS ix_test_tasks_worker_instance_id ON test_tasks ({col_name})"
        if dry_run:
            print(f"[DRY-RUN] {index_sql}")
        else:
            print(f"[EXEC] {index_sql}")
            cur.execute(index_sql)
            conn.commit()

    cur.close()
    conn.close()


if __name__ == '__main__':
    dry_run = '--dry-run' in sys.argv
    migrate(dry_run)