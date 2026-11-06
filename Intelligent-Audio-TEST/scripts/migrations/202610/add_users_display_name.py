# -*- coding: utf-8 -*-
"""迁移脚本：users 表新增 display_name 列（用户显示名，INT-697）

背景（INT-697 auth_service 显示名字段支持，解决前端「显示名编辑不落库」
INT-681 P3-1）：
- User PO（auth_service）新增 display_name 列后，全新库经
  scripts/create_all_tables.py 自动带列；存量部署缺该列导致
  PUT /api/v1/auth/users/{id} 更新 display_name 时 UndefinedColumn 500。
- 本脚本对既有库补列：`ALTER TABLE users ADD COLUMN IF NOT EXISTS
  display_name VARCHAR(100) NULL`。显示名允许重复（不做唯一约束/索引），
  长度由 VARCHAR(100) DB 约束兜底，无额外格式校验。
- DDL 与 user_models.py User PO 逐列对齐：VARCHAR(100)、可空。

用法:
    python scripts/migrations/202610/add_users_display_name.py [--dry-run]

幂等性:
    重复执行安全：列已存在即 [SKIP]；information_schema 回读自检。
"""
import os
import sys

import psycopg2
from dotenv import load_dotenv
from urllib.parse import urlparse

load_dotenv()
DATABASE_URL = os.environ.get('DATABASE_URL')
if not DATABASE_URL:
    print('未配置 DATABASE_URL 环境变量（.env 或环境）', file=sys.stderr)
    sys.exit(1)
parsed = urlparse(DATABASE_URL)
DB_HOST = parsed.hostname
DB_PORT = parsed.port or 5432
DB_NAME = parsed.path.lstrip('/')
DB_USER = parsed.username
DB_PASS = parsed.password

TABLE = 'users'
COLUMN = 'display_name'


def _column_exists(cur):
    cur.execute(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name = %s AND column_name = %s",
        (TABLE, COLUMN),
    )
    return cur.fetchone() is not None


def migrate(dry_run=False):
    conn = psycopg2.connect(
        host=DB_HOST, port=DB_PORT, dbname=DB_NAME,
        user=DB_USER, password=DB_PASS,
    )
    conn.autocommit = True
    cur = conn.cursor()

    if _column_exists(cur):
        print(f"[SKIP] {TABLE}.{COLUMN} 已存在")
    else:
        sql = (f"ALTER TABLE {TABLE} "
               f"ADD COLUMN IF NOT EXISTS {COLUMN} VARCHAR(100) NULL")
        if dry_run:
            print(f"[DRY-RUN] {sql}")
        else:
            print(f"[EXEC] {sql}")
            cur.execute(sql)
            print(f"[DONE] {TABLE}.{COLUMN} 已就绪")

    # 结构自检（information_schema 回读）
    if not dry_run:
        cur.execute(
            "SELECT column_name, data_type, character_maximum_length, "
            "is_nullable FROM information_schema.columns "
            "WHERE table_name = %s AND column_name = %s",
            (TABLE, COLUMN),
        )
        row = cur.fetchone()
        if row:
            print(f"[VERIFY] {TABLE}.{COLUMN}: {row[1]}({row[2]})"
                  f"{' NULL' if row[3] == 'YES' else ' NOT NULL'}")
        else:
            print(f"[VERIFY] {TABLE}.{COLUMN} 未检出，迁移可能未生效")

    cur.close()
    conn.close()


if __name__ == '__main__':
    migrate(dry_run='--dry-run' in sys.argv)
