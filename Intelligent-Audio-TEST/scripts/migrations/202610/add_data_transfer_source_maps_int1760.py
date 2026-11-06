# -*- coding: utf-8 -*-
"""迁移脚本：建 data_transfer_source_maps 表（离线搬运 source_map，INT-1760）

背景（《任务数据离线搬运与增量回导功能设计文档》§5.3 + D0 裁定 A3/A4）：
- 整包导入发生主键冲突时，`strip_conflicting_ids` 会丢弃包内原始 id 交给 DB
  自增；B 侧因此无法反查「本地 id 对应 A 的哪个原始 id」，增量回导（链路 2）
  的 ID 翻译就断链。本表持久化四类主键的 old→new 映射。
- 唯一键是 `UNIQUE(source_server, entity_type, local_id)`（不是 source_id）：
  同一 A 任务被 B 导入两次会产生多份本地副本（一个 source_id 对多个
  local_id），唯一键放 source_id 上第二次整包导入就会炸；导出方向永远从
  local 反查 source，local 侧天然唯一。
- 映射永久保留（D0 A4 第 4 条，不做 TTL 清理）。

DDL 与 ORM 元数据逐列对齐
（`task_service/infrastructure/persistence/models/transfer_source_map_models.py`
的 DataTransferSourceMap）：
    id BIGSERIAL PK
    source_server VARCHAR(128) NOT NULL   -- 稳定服务标识（DATA_TRANSFER_SERVER_ID）
    source_task_id BIGINT NOT NULL        -- A 原始 task_id
    entity_type VARCHAR(32) NOT NULL      -- tasks/test_results/...
    source_id BIGINT NOT NULL             -- A 原始 id
    local_id BIGINT NOT NULL              -- 本端 id
    created_at / updated_at TIMESTAMP NOT NULL DEFAULT NOW()
    唯一约束 uq_transfer_source_map_local(source_server, entity_type, local_id)
    索引 idx_transfer_source_map_task(source_server, source_task_id)
         idx_transfer_source_map_source(source_server, entity_type, source_id)
无外键：202608 基线后引用完整性由应用层管理。

步骤（幂等）：
    ① CREATE TABLE IF NOT EXISTS（含唯一约束）
    ② CREATE INDEX IF NOT EXISTS 两个普通索引
    ③ 唯一约束兜底：表已存在但缺 uq_transfer_source_map_local 时补上
    ④ 结构自检（information_schema / pg_indexes 回读）

用法:
    python scripts/migrations/202610/add_data_transfer_source_maps_int1760.py [--dry-run]

幂等性:
    表 / 索引 / 约束已存在即 [SKIP]，可重复执行；全新库由
    `scripts/create_all_tables.py` 的 create_all 建表，执行本脚本为全 [SKIP]。
"""
import argparse
import os
import sys

import psycopg2

TABLE = 'data_transfer_source_maps'

if not os.environ.get('DATABASE_URL'):
    os.environ['DATABASE_URL'] = os.environ.get(
        'DATABASE_URI',
        'postgresql://intelligent_audio_test:intelligent_audio_test666'
        '@localhost:5432/intelligent_audio_test')

CREATE_TABLE_SQL = f"""
CREATE TABLE IF NOT EXISTS {TABLE} (
    id BIGSERIAL PRIMARY KEY,
    source_server VARCHAR(128) NOT NULL,
    source_task_id BIGINT NOT NULL,
    entity_type VARCHAR(32) NOT NULL,
    source_id BIGINT NOT NULL,
    local_id BIGINT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_transfer_source_map_local
        UNIQUE (source_server, entity_type, local_id)
)
"""

CREATE_TABLES = [(TABLE, CREATE_TABLE_SQL)]

# (索引名, 表, 列, 是否唯一)
INDEXES = [
    ('idx_transfer_source_map_task', TABLE, 'source_server, source_task_id', False),
    ('idx_transfer_source_map_source', TABLE,
     'source_server, entity_type, source_id', False),
]

# 表已存在（db_bootstrap 次序 / 手工建表）但唯一约束缺失时的兜底。
UNIQUE_CONSTRAINTS = [
    ('uq_transfer_source_map_local', TABLE, 'source_server, entity_type, local_id'),
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

    # ③ 唯一约束兜底（表可能是 create_all 建的，约束应已有）
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

    # ④ 结构自检（回读，审计用）
    if not dry_run:
        cur.execute(
            "SELECT column_name, data_type, is_nullable, character_maximum_length "
            "FROM information_schema.columns WHERE table_name = %s "
            "ORDER BY ordinal_position", (TABLE,))
        cols = cur.fetchall()
        print(f'[VERIFY] {TABLE}: {len(cols)} 列')
        for name, dtype, nullable, max_len in cols:
            suffix = f'({max_len})' if max_len else ''
            print(f'  - {name} {dtype}{suffix}'
                  f'{" NULL" if nullable == "YES" else " NOT NULL"}')
        cur.execute(
            "SELECT indexname FROM pg_indexes WHERE tablename = %s "
            "ORDER BY indexname", (TABLE,))
        print('  索引: ' + ', '.join(row[0] for row in cur.fetchall()))
        cur.execute(
            "SELECT c.conname, pg_get_constraintdef(c.oid) FROM pg_constraint c "
            "JOIN pg_class t ON t.oid = c.conrelid "
            "WHERE t.relname = %s AND c.contype = 'u'", (TABLE,))
        for name, definition in cur.fetchall():
            print(f'  唯一约束 {name}: {definition}')

    cur.close()
    conn.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='data_transfer_source_maps 建表迁移（INT-1760）')
    parser.add_argument('--dry-run', action='store_true', help='只检查不执行')
    args = parser.parse_args()
    migrate(dry_run=args.dry_run)
    sys.exit(0)
