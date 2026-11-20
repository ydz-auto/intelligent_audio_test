# -*- coding: utf-8 -*-
"""迁移脚本：agent_llm_provider 用户模型供应商密钥库（INT-2488 / §10）

表：agent_llm_provider（id / owner_id / tenant_id / name / protocol /
    base_url / model / api_key_ciphertext / api_key_mask / key_version /
    context_window / context_window_source / is_default / status /
    last_verified_at / created_at / updated_at）。

约束与索引：
- (owner_id, tenant_id, is_default) —— 取默认供应商；
- (owner_id, status) —— 按状态过滤；
- (owner_id, tenant_id) WHERE is_default AND status <> 'DELETED' 唯一 ——
  每用户唯一默认；逻辑删除的行不占位。

DDL 与 ORM（agent_service/infrastructure/persistence/models/agent_models.py）
逐列对齐；无外键（仓库基线：引用完整性由应用层管理）。

幂等：
- CREATE TABLE/INDEX IF NOT EXISTS；
- 全新库 create_all 已建表 / 索引，本脚本为全 [SKIP]；
- 存量库（建库早于本卡）由本脚本补建。

用法:
    python scripts/migrations/202611/add_agent_llm_provider_table.py          # dry-run
    python scripts/migrations/202611/add_agent_llm_provider_table.py --apply  # 执行
"""
import argparse
import os

import psycopg2

if not os.environ.get('DATABASE_URL'):
    os.environ['DATABASE_URL'] = os.environ.get(
        'DATABASE_URI',
        'postgresql://intelligent_audio_test:intelligent_audio_test666'
        '@localhost:5432/intelligent_audio_test')

TABLE = 'agent_llm_provider'

CREATE_TABLES = [
    (TABLE, """
CREATE TABLE IF NOT EXISTS agent_llm_provider (
    id VARCHAR(36) PRIMARY KEY,
    owner_id BIGINT NOT NULL,
    tenant_id VARCHAR(64) NOT NULL,
    name VARCHAR(100) NOT NULL,
    protocol VARCHAR(32) NOT NULL,
    base_url VARCHAR(500) NOT NULL,
    model VARCHAR(100) NOT NULL,
    api_key_ciphertext TEXT NOT NULL,
    api_key_mask VARCHAR(32) NOT NULL DEFAULT '',
    key_version INTEGER NOT NULL DEFAULT 1,
    context_window INTEGER NULL,
    context_window_source VARCHAR(20) NOT NULL,
    is_default BOOLEAN NOT NULL DEFAULT false,
    status VARCHAR(20) NOT NULL,
    last_verified_at TIMESTAMP NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
)
"""),
]

# (索引名, 表, 列, 是否唯一)
INDEXES = [
    ('ix_agent_llm_provider_owner_default', TABLE,
     'owner_id, tenant_id, is_default', False),
    ('ix_agent_llm_provider_owner_status', TABLE, 'owner_id, status', False),
]

# (索引名, 表, 列, WHERE) —— 部分唯一索引（每用户唯一默认，删除行不占位）
PARTIAL_UNIQUE_INDEXES = [
    ('uq_agent_llm_provider_default', TABLE, 'owner_id, tenant_id',
     "is_default AND status <> 'DELETED'"),
]


def _connect():
    from urllib.parse import urlparse
    parsed = urlparse(os.environ['DATABASE_URL'])
    return psycopg2.connect(
        host=parsed.hostname, port=parsed.port or 5432,
        dbname=parsed.path.lstrip('/'), user=parsed.username,
        password=parsed.password)


def _table_exists(cur, table):
    cur.execute(
        'SELECT 1 FROM information_schema.tables WHERE table_name = %s',
        (table,))
    return cur.fetchone() is not None


def _index_exists(cur, table, index):
    cur.execute(
        'SELECT 1 FROM pg_indexes WHERE tablename = %s AND indexname = %s',
        (table, index))
    return cur.fetchone() is not None


def _index_sql(name, table, cols, unique):
    kind = 'UNIQUE INDEX' if unique else 'INDEX'
    return f'CREATE {kind} IF NOT EXISTS {name} ON {table} ({cols})'


def migrate(dry_run=False):
    conn = _connect()
    conn.autocommit = True
    cur = conn.cursor()

    for table, sql in CREATE_TABLES:
        if _table_exists(cur, table):
            print(f'[SKIP] 表 {table} 已存在')
        elif dry_run:
            print(f'[DRY-RUN] CREATE TABLE {table}')
        else:
            print(f'[EXEC] CREATE TABLE {table}')
            cur.execute(sql.strip())
            print(f'[DONE] 表 {table} 已就绪')

    for name, table, cols, unique in INDEXES:
        if not _table_exists(cur, table):
            print(f'[SKIP] 索引 {name}（表 {table} 不存在）')
            continue
        if _index_exists(cur, table, name):
            print(f'[SKIP] 索引 {name} 已存在')
            continue
        sql = _index_sql(name, table, cols, unique)
        if dry_run:
            print(f'[DRY-RUN] {sql}')
        else:
            print(f'[EXEC] {sql}')
            cur.execute(sql)

    for name, table, cols, where in PARTIAL_UNIQUE_INDEXES:
        if not _table_exists(cur, table):
            print(f'[SKIP] 索引 {name}（表 {table} 不存在）')
            continue
        if _index_exists(cur, table, name):
            print(f'[SKIP] 索引 {name} 已存在')
            continue
        sql = (f'CREATE UNIQUE INDEX IF NOT EXISTS {name} '
               f'ON {table} ({cols}) WHERE {where}')
        if dry_run:
            print(f'[DRY-RUN] {sql}')
        else:
            print(f'[EXEC] {sql}')
            cur.execute(sql)

    if not dry_run:
        for table, _sql in CREATE_TABLES:
            cur.execute(
                'SELECT count(*) FROM information_schema.columns '
                'WHERE table_name = %s', (table,))
            print(f'[VERIFY] {table}: {cur.fetchone()[0]} 列')

    cur.close()
    conn.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='agent_llm_provider 用户模型供应商密钥库（INT-2488）迁移')
    parser.add_argument('--dry-run', action='store_true', help='只检查不执行')
    parser.add_argument('--apply', action='store_true', help='真正执行 DDL')
    args = parser.parse_args()
    # 默认 dry-run；引导链显式带 --apply
    migrate(dry_run=not args.apply or args.dry_run)
