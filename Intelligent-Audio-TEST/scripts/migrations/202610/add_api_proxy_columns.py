# -*- coding: utf-8 -*-
"""迁移脚本：apis 表新增网络代理两列（proxy_type / proxy_url，INT-839）

背景（INT-839，见 doc/功能设计文档/01_测试执行/API测试功能设计文档.md UC-0901）：
- 被测 API 支持 http / https / socks5 / socks5h 四种代理类型，
  地址含认证 `user:pass@host:port`（不含 scheme），NULL = 不用代理。
- 代理只作用于被测 API 请求面（HTTP / WS / 健康检查 / adapter 服务），
  不影响音频 OSS/存储直传。
- 两列均可 NULL，存量行不迁移数据（老数据 NULL 不报错，回归行为不变）。

用法:
    python scripts/migrations/202610/add_api_proxy_columns.py [--dry-run]

幂等性:
    重复执行安全：列已存在即 [SKIP]。
"""
import sys
import os

import psycopg2
from dotenv import load_dotenv
from urllib.parse import urlparse

load_dotenv()
DATABASE_URL = os.environ.get('DATABASE_URL')
# 懒解析：未配置 DATABASE_URL 时保留 None，让 __main__ 给出友好报错
parsed = urlparse(DATABASE_URL) if DATABASE_URL else None
DB_HOST = parsed.hostname if parsed else None
DB_PORT = (parsed.port or 5432) if parsed else 5432
DB_NAME = parsed.path.lstrip('/') if parsed else None
DB_USER = parsed.username if parsed else None
DB_PASS = parsed.password if parsed else None

API_TABLE = 'apis'

COLUMNS = [
    (API_TABLE, 'proxy_type', 'VARCHAR(20)'),
    (API_TABLE, 'proxy_url', 'VARCHAR(255)'),
]


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

    for table, col_name, col_type in COLUMNS:
        if _column_exists(cur, table, col_name):
            print(f"[SKIP] {table}.{col_name} 已存在")
            continue
        alter = f"ALTER TABLE {table} ADD COLUMN {col_name} {col_type}"
        if dry_run:
            print(f"[DRY-RUN] {alter}")
        else:
            print(f"[EXEC] {alter}")
            cur.execute(alter)
            print(f"[DONE] {table}.{col_name} 已添加")

    cur.close()
    conn.close()


if __name__ == '__main__':
    if not DATABASE_URL:
        print('错误: 未配置 DATABASE_URL 环境变量')
        sys.exit(1)
    migrate(dry_run='--dry-run' in sys.argv)
    print('迁移完成')
