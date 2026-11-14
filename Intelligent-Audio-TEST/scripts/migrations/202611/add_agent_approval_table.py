# -*- coding: utf-8 -*-
"""迁移脚本：agent_approval 写操作审批单（INT-2466 / INT-2571，§9.4 / §10）

表：agent_approval（id / run_id / tool_call_id / proposal / diff / status /
    expires_at / decided_by / decided_at / decision_permissions /
    batch_id / batch_index / batch_total / object_ref /
    created_at / updated_at）。

约束与索引：
- (run_id, tool_call_id, batch_index) 唯一 —— 一次 tool call 1..N 张单
  （INT-2571 §9.4.1 拆单），按 batch_index 逐张幂等；历史单张口径
  batch_index 恒为 1。旧约束 uq_agent_approval_run_call 由本脚本先删再建新，
  回滚可逆（删新约束、加回旧约束即可）；
- (status, expires_at) —— 待审批列表与过期扫描；
- (run_id, created_at) —— 按 run 回放审批历史。

``decision_permissions`` 是审批人**决策时**的实时权限快照（执行前据此重新
校验「审批后权限是否还在」），DDL 与 ORM
（agent_service/infrastructure/persistence/models/agent_models.py）逐列对齐；
无外键（仓库基线：引用完整性由应用层管理）。

幂等：
- CREATE TABLE/INDEX IF NOT EXISTS，唯一约束先查 pg_constraint 再补；
- 存量库按列存在性补 ADD COLUMN（batch_id / batch_index / batch_total /
  object_ref，默认值保证历史行落到单张口径），再替换唯一约束；
- 全新库 create_all 已建表 / 约束 / 索引，本脚本为全 [SKIP]；
- 存量库（建库早于本卡）由本脚本补齐。

用法:
    python scripts/migrations/202611/add_agent_approval_table.py          # dry-run
    python scripts/migrations/202611/add_agent_approval_table.py --apply  # 执行
"""
import argparse
import os

import psycopg2

if not os.environ.get('DATABASE_URL'):
    os.environ['DATABASE_URL'] = os.environ.get(
        'DATABASE_URI',
        'postgresql://intelligent_audio_test:intelligent_audio_test666'
        '@localhost:5432/intelligent_audio_test')

TABLE = 'agent_approval'

CREATE_TABLES = [
    (TABLE, """
CREATE TABLE IF NOT EXISTS agent_approval (
    id VARCHAR(36) PRIMARY KEY,
    run_id VARCHAR(36) NOT NULL,
    tool_call_id VARCHAR(128) NOT NULL,
    proposal JSON NOT NULL,
    diff JSON NULL,
    status VARCHAR(20) NOT NULL,
    expires_at TIMESTAMP NULL,
    decided_by BIGINT NULL,
    decided_at TIMESTAMP NULL,
    decision_permissions JSON NULL,
    batch_id VARCHAR(36) NULL,
    batch_index INTEGER NOT NULL DEFAULT 1,
    batch_total INTEGER NOT NULL DEFAULT 1,
    object_ref JSON NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
)
"""),
]

# 存量库补列（INT-2571）：列名 → 列定义（带默认值，历史行落单张口径）
ADDED_COLUMNS = [
    ('batch_id', 'VARCHAR(36) NULL'),
    ('batch_index', 'INTEGER NOT NULL DEFAULT 1'),
    ('batch_total', 'INTEGER NOT NULL DEFAULT 1'),
    ('object_ref', 'JSON NULL'),
]

# (约束名, 表, 定义)
UNIQUE_CONSTRAINTS = [
    ('uq_agent_approval_run_call_batch', TABLE,
     'run_id, tool_call_id, batch_index'),
]

# 先删的旧约束（INT-2466 的一次调用一张单口径，被首批次唯一键取代）
DROPPED_CONSTRAINTS = [
    ('uq_agent_approval_run_call', TABLE),
]

# (索引名, 表, 列, 是否唯一)
INDEXES = [
    ('ix_agent_approval_status_expires', TABLE, 'status, expires_at', False),
    ('ix_agent_approval_run', TABLE, 'run_id, created_at', False),
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


def _constraint_exists(cur, table, name):
    cur.execute(
        'SELECT 1 FROM pg_constraint WHERE conname = %s AND conrelid = '
        '(SELECT oid FROM pg_class WHERE relname = %s)',
        (name, table))
    return cur.fetchone() is not None


def _column_exists(cur, table, name):
    cur.execute(
        'SELECT 1 FROM information_schema.columns '
        'WHERE table_name = %s AND column_name = %s', (table, name))
    return cur.fetchone() is not None


def _index_exists(cur, table, index):
    cur.execute(
        'SELECT 1 FROM pg_indexes WHERE tablename = %s AND indexname = %s',
        (table, index))
    return cur.fetchone() is not None


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

    for collision in DROPPED_CONSTRAINTS:
        name, table = collision
        if not _table_exists(cur, table):
            print(f'[SKIP] 旧约束 {name}（表 {table} 不存在）')
            continue
        if not _constraint_exists(cur, table, name):
            print(f'[SKIP] 旧约束 {name} 不存在')
            continue
        sql = f'ALTER TABLE {table} DROP CONSTRAINT {name}'
        if dry_run:
            print(f'[DRY-RUN] {sql}')
        else:
            print(f'[EXEC] {sql}')
            cur.execute(sql)
            print(f'[DONE] 旧约束 {name} 已删除（唯一键改为含 batch_index）')

    for name, definition in ADDED_COLUMNS:
        if not _table_exists(cur, TABLE):
            print(f'[SKIP] 列 {name}（表 {TABLE} 不存在）')
            continue
        if _column_exists(cur, TABLE, name):
            print(f'[SKIP] 列 {name} 已存在')
            continue
        sql = f'ALTER TABLE {TABLE} ADD COLUMN {name} {definition}'
        if dry_run:
            print(f'[DRY-RUN] {sql}')
        else:
            print(f'[EXEC] {sql}')
            cur.execute(sql)

    for name, table, definition in UNIQUE_CONSTRAINTS:
        if not _table_exists(cur, table):
            print(f'[SKIP] 约束 {name}（表 {table} 不存在）')
            continue
        if _constraint_exists(cur, table, name):
            print(f'[SKIP] 约束 {name} 已存在')
            continue
        sql = (f'ALTER TABLE {table} ADD CONSTRAINT {name} '
               f'UNIQUE ({definition})')
        if dry_run:
            print(f'[DRY-RUN] {sql}')
        else:
            print(f'[EXEC] {sql}')
            cur.execute(sql)

    for name, table, cols, unique in INDEXES:
        if not _table_exists(cur, table):
            print(f'[SKIP] 索引 {name}（表 {table} 不存在）')
            continue
        if _index_exists(cur, table, name):
            print(f'[SKIP] 索引 {name} 已存在')
            continue
        kind = 'UNIQUE INDEX' if unique else 'INDEX'
        sql = f'CREATE {kind} IF NOT EXISTS {name} ON {table} ({cols})'
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
        description='agent_approval 写操作审批单（INT-2466）迁移')
    parser.add_argument('--dry-run', action='store_true', help='只检查不执行')
    parser.add_argument('--apply', action='store_true', help='真正执行 DDL')
    args = parser.parse_args()
    # 默认 dry-run；引导链显式带 --apply
    migrate(dry_run=not args.apply or args.dry_run)
