# -*- coding: utf-8 -*-
"""迁移脚本：新建 access_tokens 表（Access Token + skill/MCP 鉴权令牌，INT-1140）

背景（INT-1140 分道 D）：
- AccessToken PO（auth_service）新增后，仅全新库经
  scripts/create_all_tables.py 建表；存量部署缺该表导致
  Access Token CRUD / ValidateAccessToken 直接 500（UndefinedTable）。
- 本脚本对既有库补建表，DDL 与 ORM 元数据（access_token_models.py）逐列对齐：
  id BIGSERIAL PK / user_id BIGINT / name VARCHAR(100) /
  token_hash VARCHAR(64)（唯一约束 uq_access_tokens_token_hash）/
  token_hint VARCHAR(10) / scopes JSON / expires_at TIMESTAMP NULL /
  status VARCHAR(20) / last_used_at / last_used_ip VARCHAR(50) /
  created_at TIMESTAMP DEFAULT now() / deleted_at TIMESTAMP NULL；
  索引 ix_access_tokens_user_id(user_id)。
- 无外键：202608 基线后引用完整性由应用层管理。
- 全新库 create_all 已含本表，执行本脚本为全 [SKIP]。

用法:
    python scripts/migrations/202610/add_access_tokens_table.py [--dry-run]

幂等性:
    重复执行安全：表/约束/索引已存在即 [SKIP]；既有表缺
    uq_access_tokens_token_hash 约束时自动补建（自愈），不产生重复数据。
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

TABLE = 'access_tokens'
CONSTRAINT = 'uq_access_tokens_token_hash'

CREATE_TABLE_SQL = f"""
CREATE TABLE IF NOT EXISTS {TABLE} (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    name VARCHAR(100) NOT NULL,
    token_hash VARCHAR(64) NOT NULL,
    token_hint VARCHAR(10) NOT NULL,
    scopes JSON NOT NULL DEFAULT '[]',
    expires_at TIMESTAMP NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'enabled',
    last_used_at TIMESTAMP NULL,
    last_used_ip VARCHAR(50) NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    deleted_at TIMESTAMP NULL,
    CONSTRAINT {CONSTRAINT} UNIQUE (token_hash)
)
"""

INDEXES = [
    ('ix_access_tokens_user_id', TABLE, 'user_id'),
]


def _table_exists(cur, table):
    cur.execute(
        "SELECT 1 FROM information_schema.tables WHERE table_name = %s", (table,)
    )
    return cur.fetchone() is not None


def _constraint_exists(cur, table, conname):
    cur.execute(
        "SELECT 1 FROM pg_constraint WHERE conrelid = %s::regclass AND conname = %s",
        (table, conname),
    )
    return cur.fetchone() is not None


def _unique_index_on_col_exists(cur, table, col):
    """col 上是否已有唯一索引（任意命名）。"""
    cur.execute(
        """
        SELECT 1
        FROM pg_index i
        JOIN pg_class c ON c.oid = i.indrelid
        WHERE c.relname = %s
          AND i.indisunique
          AND i.indnkeyatts = 1
          AND EXISTS (SELECT 1 FROM pg_attribute a
                      WHERE a.attrelid = c.oid AND a.attname = %s AND a.attnum = i.indkey[0])
        """,
        (table, col),
    )
    return cur.fetchone() is not None


def migrate(dry_run=False):
    conn = psycopg2.connect(
        host=DB_HOST, port=DB_PORT, dbname=DB_NAME,
        user=DB_USER, password=DB_PASS,
    )
    conn.autocommit = True
    cur = conn.cursor()

    # ① 表（含 uq_access_tokens_token_hash 内联约束）
    if _table_exists(cur, TABLE):
        print(f"[SKIP] 表 {TABLE} 已存在")
    else:
        sql = CREATE_TABLE_SQL.strip()
        if dry_run:
            print(f"[DRY-RUN] CREATE TABLE IF NOT EXISTS {TABLE}"
                  f"（含 {CONSTRAINT} 唯一约束）")
        else:
            print(f"[EXEC] CREATE TABLE IF NOT EXISTS {TABLE}")
            cur.execute(sql)
            print(f"[DONE] 表 {TABLE} 已就绪")

    # ② 唯一约束自愈：表已建但缺 uq_access_tokens_token_hash 时补建
    if _table_exists(cur, TABLE) \
            and not _constraint_exists(cur, TABLE, CONSTRAINT):
        if _unique_index_on_col_exists(cur, TABLE, 'token_hash'):
            print(f"[SKIP] token_hash 已有等价唯一索引（命名不同），不重复加约束")
        else:
            alter = (f"ALTER TABLE {TABLE} "
                     f"ADD CONSTRAINT {CONSTRAINT} UNIQUE (token_hash)")
            if dry_run:
                print(f"[DRY-RUN] {alter}")
            else:
                print(f"[EXEC] {alter}")
                cur.execute(alter)
                print(f"[DONE] 约束 {CONSTRAINT} 已补建")
    else:
        print(f"[SKIP] 约束 {CONSTRAINT} 已存在（或随 ① 建表语句内联创建）")

    # ③ 索引
    for index_name, table, col_name in INDEXES:
        idx_sql = f"CREATE INDEX IF NOT EXISTS {index_name} ON {table} ({col_name})"
        if dry_run:
            print(f"[DRY-RUN] {idx_sql}")
        else:
            print(f"[EXEC] {idx_sql}")
            cur.execute(idx_sql)
            print(f"[DONE] 索引 {index_name} 已就绪")

    # ④ 结构自检（information_schema 回读）
    if not dry_run:
        cur.execute(
            "SELECT column_name, data_type, is_nullable FROM information_schema.columns "
            "WHERE table_name = %s ORDER BY ordinal_position",
            (TABLE,),
        )
        cols = cur.fetchall()
        has_uq = _constraint_exists(cur, TABLE, CONSTRAINT)
        print(f"[VERIFY] {TABLE}: {len(cols)} 列, "
              f"{CONSTRAINT} {'✓' if has_uq else '✗'}")
        for name, dtype, nullable in cols:
            print(f"  - {name} {dtype}{' NULL' if nullable == 'YES' else ' NOT NULL'}")

    cur.close()
    conn.close()


if __name__ == '__main__':
    migrate(dry_run='--dry-run' in sys.argv)
