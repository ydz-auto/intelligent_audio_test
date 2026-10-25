# -*- coding: utf-8 -*-
"""迁移脚本：建 transfer_records / transfer_chunks 两表（传输代理，INT-1623）

背景（INT-1623 缺陷）：
- transfer_agent 的两张 PO 表（`transfer_agent/infrastructure/persistence/
  models.py`：TransferRecord / TransferChunk）自落地起就不在
  `scripts/create_all_tables.py::_import_all_models()` 的导入清单里 —— 该函数
  声称注册 87 张表，实际只注册 86 张（不含这两张）。真实库有这两张表，是
  transfer_agent 自己启动时 create_all 的「次生路径」，全新库 / 重新引导的库
  走 db_bootstrap 不会有。
- 同时，INT-1565 的迁移守卫（`tests/unit/test_int1565_schema_migration_guard.py`）
  读的是进程级全局 `Base.metadata`：任一测试文件 import 了 transfer_agent
  应用层，这两张表就注册进来了，守卫随 xdist 调度红/绿不定 —— 根因是
  「模型全集」不唯一，本卡先在 create_all_tables 里收口（见该文件改动）。
- 本脚本按守卫约定补建表迁移：create_all 只建「缺失的表」，建库早于
  transfer_agent 模块的存量库由本步建表自愈；全新库 create_all 已含这两张
  表，执行本脚本为全 [SKIP]。

DDL 与 transfer_agent ORM 元数据逐列对齐（真实库 intelligent_audio_test 实测
一致：口径见 tests/unit/test_int1623_transfer_tables_migration.py 的静态比对）：
    transfer_records（19 列）
        id SERIAL PK / transfer_id VARCHAR(64) NOT NULL
        pkg_type VARCHAR(32) / src_zone VARCHAR(8) / dst_zone VARCHAR(8)
        category VARCHAR(32) / key TEXT / file_hash VARCHAR(128)
        file_size BIGINT / chunk_size INTEGER / meta TEXT NULL
        ttl_seconds INTEGER / ephemeral BOOLEAN / timestamp VARCHAR(48)
        signature VARCHAR(128) / status VARCHAR(20) / final_path TEXT NULL
        created_at / updated_at TIMESTAMP NOT NULL DEFAULT NOW()
        索引 ix_transfer_records_transfer_id（UNIQUE，幂等去重键）
             ix_transfer_records_status
    transfer_chunks（6 列）
        id SERIAL PK / transfer_id VARCHAR(64) / chunk_index INTEGER
        checksum VARCHAR(64) / size BIGINT
        received_at TIMESTAMP NOT NULL DEFAULT NOW()
        唯一约束 uq_transfer_chunk_index(transfer_id, chunk_index)
        索引 ix_transfer_chunks_transfer_id
无外键：202608 基线后引用完整性由应用层管理。

步骤（幂等）：
    ① CREATE TABLE IF NOT EXISTS 两张表（含唯一约束）
    ② CREATE INDEX IF NOT EXISTS 三个索引
    ③ 唯一约束兜底：表已存在但缺 uq_transfer_chunk_index 时补上
    ④ 结构自检（information_schema 回读列数 / 索引）

用法:
    python scripts/migrations/202610/add_transfer_agent_tables_int1623.py [--dry-run]

幂等性:
    表 / 索引 / 约束已存在即 [SKIP]，可重复执行、不产生重复数据。
"""
import argparse
import os
import sys

import psycopg2

TABLE_RECORDS = 'transfer_records'
TABLE_CHUNKS = 'transfer_chunks'

if not os.environ.get('DATABASE_URL'):
    os.environ['DATABASE_URL'] = os.environ.get(
        'DATABASE_URI',
        'postgresql://intelligent_audio_test:intelligent_audio_test666'
        '@localhost:5432/intelligent_audio_test')

CREATE_RECORDS_SQL = f"""
CREATE TABLE IF NOT EXISTS {TABLE_RECORDS} (
    id SERIAL PRIMARY KEY,
    transfer_id VARCHAR(64) NOT NULL,
    pkg_type VARCHAR(32) NOT NULL,
    src_zone VARCHAR(8) NOT NULL,
    dst_zone VARCHAR(8) NOT NULL,
    category VARCHAR(32) NOT NULL,
    key TEXT NOT NULL,
    file_hash VARCHAR(128) NOT NULL,
    file_size BIGINT NOT NULL,
    chunk_size INTEGER NOT NULL,
    meta TEXT NULL,
    ttl_seconds INTEGER NOT NULL,
    ephemeral BOOLEAN NOT NULL,
    timestamp VARCHAR(48) NOT NULL,
    signature VARCHAR(128) NOT NULL,
    status VARCHAR(20) NOT NULL,
    final_path TEXT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
)
"""

CREATE_CHUNKS_SQL = f"""
CREATE TABLE IF NOT EXISTS {TABLE_CHUNKS} (
    id SERIAL PRIMARY KEY,
    transfer_id VARCHAR(64) NOT NULL,
    chunk_index INTEGER NOT NULL,
    checksum VARCHAR(64) NOT NULL,
    size BIGINT NOT NULL,
    received_at TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_transfer_chunk_index UNIQUE (transfer_id, chunk_index)
)
"""

CREATE_TABLES = [
    (TABLE_RECORDS, CREATE_RECORDS_SQL),
    (TABLE_CHUNKS, CREATE_CHUNKS_SQL),
]

# (索引名, 表, 列, 是否唯一) —— unique=True 的列（transfer_records.transfer_id）
# 在 ORM 里是唯一索引，与真实库一致。
INDEXES = [
    ('ix_transfer_records_transfer_id', TABLE_RECORDS, 'transfer_id', True),
    ('ix_transfer_records_status', TABLE_RECORDS, 'status', False),
    ('ix_transfer_chunks_transfer_id', TABLE_CHUNKS, 'transfer_id', False),
]

# 表已存在（存量库由 transfer_agent create_all 建过）但唯一约束缺失时的兜底。
UNIQUE_CONSTRAINTS = [
    ('uq_transfer_chunk_index', TABLE_CHUNKS, 'transfer_id, chunk_index'),
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
        "SELECT 1 FROM information_schema.tables WHERE table_name = %s", (table,)
    )
    return cur.fetchone() is not None


def _index_exists(cur, table, index):
    cur.execute(
        "SELECT 1 FROM pg_indexes WHERE tablename = %s AND indexname = %s",
        (table, index))
    return cur.fetchone() is not None


def _constraint_exists(cur, table, constraint):
    cur.execute(
        "SELECT 1 FROM pg_constraint c JOIN pg_class t ON t.oid = c.conrelid "
        "WHERE t.relname = %s AND c.conname = %s", (table, constraint))
    return cur.fetchone() is not None


def _index_sql(index_name, table, col_name, unique):
    kind = 'UNIQUE INDEX' if unique else 'INDEX'
    return f'CREATE {kind} IF NOT EXISTS {index_name} ON {table} ({col_name})'


def migrate(dry_run=False):
    conn = _connect()
    conn.autocommit = True
    cur = conn.cursor()

    # ① 建表
    for table, sql in CREATE_TABLES:
        if _table_exists(cur, table):
            print(f'[SKIP] 表 {table} 已存在')
        elif dry_run:
            print(f'[DRY-RUN] CREATE TABLE IF NOT EXISTS {table}')
        else:
            print(f'[EXEC] CREATE TABLE IF NOT EXISTS {table}')
            cur.execute(sql.strip())
            print(f'[DONE] 表 {table} 已就绪')

    # ② 索引
    for index_name, table, col_name, unique in INDEXES:
        if _index_exists(cur, table, index_name):
            print(f'[SKIP] 索引 {index_name} 已存在')
            continue
        idx_sql = _index_sql(index_name, table, col_name, unique)
        if dry_run:
            print(f'[DRY-RUN] {idx_sql}')
        else:
            print(f'[EXEC] {idx_sql}')
            cur.execute(idx_sql)
            print(f'[DONE] 索引 {index_name} 已就绪')

    # ③ 唯一约束兜底（存量表可能是 transfer_agent create_all 建的，约束应已有）
    for constraint, table, columns in UNIQUE_CONSTRAINTS:
        if _constraint_exists(cur, table, constraint):
            print(f'[SKIP] 唯一约束 {constraint} 已存在')
            continue
        alt_sql = (f'ALTER TABLE {table} ADD CONSTRAINT {constraint} '
                   f'UNIQUE ({columns})')
        if dry_run:
            print(f'[DRY-RUN] {alt_sql}')
        else:
            print(f'[EXEC] {alt_sql}')
            cur.execute(alt_sql)
            print(f'[DONE] 唯一约束 {constraint} 已就绪')

    # ④ 结构自检（information_schema 回读）
    if not dry_run:
        for table, _sql in CREATE_TABLES:
            cur.execute(
                "SELECT column_name, data_type, is_nullable "
                "FROM information_schema.columns WHERE table_name = %s "
                "ORDER BY ordinal_position", (table,))
            cols = cur.fetchall()
            print(f'[VERIFY] {table}: {len(cols)} 列')
            for name, dtype, nullable in cols:
                print(f'  - {name} {dtype}'
                      f'{" NULL" if nullable == "YES" else " NOT NULL"}')
            cur.execute(
                "SELECT indexname FROM pg_indexes WHERE tablename = %s "
                "ORDER BY indexname", (table,))
            print('  索引: ' + ', '.join(row[0] for row in cur.fetchall()))

    cur.close()
    conn.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='transfer_records / transfer_chunks 建表迁移（INT-1623）')
    parser.add_argument('--dry-run', action='store_true', help='只检查不执行')
    args = parser.parse_args()
    migrate(dry_run=args.dry_run)
    sys.exit(0)
