# -*- coding: utf-8 -*-
"""迁移脚本：为 task_case_relations 表添加 device_type / device_id / lab_id 列

背景（执行域 P0，见 doc/功能设计文档/01_测试执行/02_架构设计.md §7.1）：
- task_case_relations.device_type：用例级被测设备类型（physical/http_api/websocket_api），
  执行路由由 task.type 迁移到用例级 device_type（为空时回退 task.type，保证旧任务兼容）。
- task_case_relations.device_id：用例级被测设备 ID（physical=设备ID / API 类=api.id）。
- task_case_relations.lab_id：实验室扩展列（doc/总架构/实验室扩展功能设计.md §3），
  与 add_laboratory_tables.py 的列定义一致，此处幂等补齐，便于按实验室过滤设备选择。

用法:
    python scripts/migrations/202609/add_task_case_device_type.py [--dry-run]

幂等性:
    重复执行安全：列已存在即 [SKIP]，索引已存在即跳过，不产生重复数据。
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

TABLE = 'task_case_relations'

# 需要添加的列: (column_name, column_type)
COLUMNS = [
    ('device_type', 'VARCHAR(20)'),   # physical / http_api / websocket_api
    ('device_id', 'VARCHAR(50)'),     # physical=设备ID / API 类=api.id
    ('lab_id', 'INTEGER'),            # 实验室扩展
]

INDEXES = [
    ('idx_task_case_relations_device_type', 'device_type'),
    ('idx_task_case_relations_lab_id', 'lab_id'),
]


def migrate(dry_run=False):
    conn = psycopg2.connect(
        host=DB_HOST, port=DB_PORT, dbname=DB_NAME,
        user=DB_USER, password=DB_PASS,
    )
    conn.autocommit = True
    cur = conn.cursor()

    for col_name, col_type in COLUMNS:
        cur.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = %s AND column_name = %s
        """, (TABLE, col_name))
        if cur.fetchone():
            print(f"[SKIP] {TABLE}.{col_name} 已存在")
            continue

        sql = f"ALTER TABLE {TABLE} ADD COLUMN {col_name} {col_type}"
        if dry_run:
            print(f"[DRY-RUN] {sql}")
        else:
            print(f"[EXEC] {sql}")
            cur.execute(sql)
            print(f"[DONE] {TABLE}.{col_name} 已添加")

    for index_name, col_name in INDEXES:
        sql = f"CREATE INDEX IF NOT EXISTS {index_name} ON {TABLE} ({col_name})"
        if dry_run:
            print(f"[DRY-RUN] {sql}")
        else:
            print(f"[EXEC] {sql}")
            cur.execute(sql)
            print(f"[DONE] 索引 {index_name} 已就绪")

    cur.close()
    conn.close()


if __name__ == '__main__':
    dry_run = '--dry-run' in sys.argv
    migrate(dry_run)
