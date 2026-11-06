# -*- coding: utf-8 -*-
"""迁移脚本：新建 user_oauth_bindings 表（第三方账号绑定，INT-147）

背景（INT-147 认证域对齐 V9.7.10，测试打回 F1 修复）：
- UserOAuthBinding PO（auth_service）新增后，仅全新库经
  scripts/create_all_tables.py 建表；存量部署缺该表导致
  GET/DELETE /api/v1/auth/oauth/bindings 直接 500（UndefinedTable）。
- 本脚本对既有库补建表，DDL 与 ORM 元数据（user_models.py）逐列对齐：
  id SERIAL PK / user_id BIGINT / provider_id INTEGER / provider_user_id VARCHAR(255) /
  created_at TIMESTAMP DEFAULT now()；
  UniqueConstraint uq_provider_user (provider_id, provider_user_id)
  —— 一个第三方身份至多绑定一个本地用户；
  索引 ix_binding_user(user_id)、ix_user_oauth_bindings_provider_id(provider_id)。
- 无外键：202608 基线后引用完整性由应用层管理。
- 全新库 create_all 已含本表，执行本脚本为全 [SKIP]。

用法:
    python scripts/migrations/202610/add_user_oauth_bindings.py [--dry-run]

幂等性:
    重复执行安全：表/约束/索引已存在即 [SKIP]；既有表缺 uq_provider_user
    约束时自动补建（自愈），不产生重复数据。
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

BINDING_TABLE = 'user_oauth_bindings'

CREATE_TABLE_SQL = f"""
CREATE TABLE IF NOT EXISTS {BINDING_TABLE} (
    id SERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    provider_id INTEGER NOT NULL,
    provider_user_id VARCHAR(255) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_provider_user UNIQUE (provider_id, provider_user_id)
)
"""

INDEXES = [
    ('ix_binding_user', BINDING_TABLE, 'user_id'),
    ('ix_user_oauth_bindings_provider_id', BINDING_TABLE, 'provider_id'),
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


def _unique_covering_index_exists(cur, table, first_col, second_col):
    """(first_col, second_col) 上是否已有唯一索引（任意命名）。"""
    cur.execute(
        """
        SELECT 1
        FROM pg_index i
        JOIN pg_class c ON c.oid = i.indrelid
        WHERE c.relname = %s
          AND i.indisunique
          AND i.indnkeyatts = 2
          AND EXISTS (SELECT 1 FROM pg_attribute a
                      WHERE a.attrelid = c.oid AND a.attname = %s AND a.attnum = i.indkey[0])
          AND EXISTS (SELECT 1 FROM pg_attribute a
                      WHERE a.attrelid = c.oid AND a.attname = %s AND a.attnum = i.indkey[1])
        """,
        (table, first_col, second_col),
    )
    return cur.fetchone() is not None


def migrate(dry_run=False):
    conn = psycopg2.connect(
        host=DB_HOST, port=DB_PORT, dbname=DB_NAME,
        user=DB_USER, password=DB_PASS,
    )
    conn.autocommit = True
    cur = conn.cursor()

    # ① 表（含 uq_provider_user 内联约束）
    if _table_exists(cur, BINDING_TABLE):
        print(f"[SKIP] 表 {BINDING_TABLE} 已存在")
    else:
        sql = CREATE_TABLE_SQL.strip()
        if dry_run:
            print(f"[DRY-RUN] CREATE TABLE IF NOT EXISTS {BINDING_TABLE}"
                  f"（含 uq_provider_user 唯一约束）")
        else:
            print(f"[EXEC] CREATE TABLE IF NOT EXISTS {BINDING_TABLE}")
            cur.execute(sql)
            print(f"[DONE] 表 {BINDING_TABLE} 已就绪")

    # ② 唯一约束自愈：表已建但缺 uq_provider_user（历史建表路径差异）时补建
    if _table_exists(cur, BINDING_TABLE) \
            and not _constraint_exists(cur, BINDING_TABLE, 'uq_provider_user'):
        if _unique_covering_index_exists(cur, BINDING_TABLE, 'provider_id', 'provider_user_id'):
            print("[SKIP] (provider_id, provider_user_id) 已有等价唯一索引（命名不同），不重复加约束")
        else:
            alter = (f"ALTER TABLE {BINDING_TABLE} "
                     f"ADD CONSTRAINT uq_provider_user UNIQUE (provider_id, provider_user_id)")
            if dry_run:
                print(f"[DRY-RUN] {alter}")
            else:
                print(f"[EXEC] {alter}")
                cur.execute(alter)
                print("[DONE] 约束 uq_provider_user 已补建")
    else:
        print("[SKIP] 约束 uq_provider_user 已存在（或随 ① 建表语句内联创建）")

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
            (BINDING_TABLE,),
        )
        cols = cur.fetchall()
        has_uq = _constraint_exists(cur, BINDING_TABLE, 'uq_provider_user')
        print(f"[VERIFY] {BINDING_TABLE}: {len(cols)} 列, "
              f"uq_provider_user {'✓' if has_uq else '✗'}")
        for name, dtype, nullable in cols:
            print(f"  - {name} {dtype}{' NULL' if nullable == 'YES' else ' NOT NULL'}")

    cur.close()
    conn.close()


if __name__ == '__main__':
    migrate(dry_run='--dry-run' in sys.argv)
