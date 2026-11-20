# -*- coding: utf-8 -*-
"""迁移脚本：agent_service 运行底座前七张表（INT-2451 / 落地方案 §10）

表：
    agent_session / agent_run / agent_run_event / agent_step /
    agent_tool_call / agent_artifact / agent_context_snapshot
（agent_approval 属 M2，本卡不建。）

约束与索引：
- (run_id, sequence) 唯一 —— SSE 严格递增、无空洞的数据库兜底；
- agent_run.idempotency_key 唯一 —— 重复提交只产生一个 run；
- (run_id, tool_call_id) 唯一 —— 断点恢复按 tool_call_id 复用结果，不重复执行；
- (run_id, index) / (run_id, version) 唯一 —— step / 上下文快照版本不重复；
- session owner、run owner/status 索引；step / 上下文快照不建普通索引 ——
  上面两条唯一约束自带的 (同列同序) 索引已覆盖前缀查询（INT-2516）。

DDL 与 ORM（agent_service/infrastructure/persistence/models/agent_models.py）
逐列对齐；无外键（仓库基线：引用完整性由应用层管理）。

幂等：
- CREATE TABLE/INDEX IF NOT EXISTS；唯一约束先查 pg_constraint 再补；
- 全新库 create_all 已建表 / 约束 / 索引，本脚本为全 [SKIP]；
- 存量库（建库早于本卡）由本脚本补建。

用法:
    python scripts/migrations/202611/add_agent_runtime_tables.py          # dry-run
    python scripts/migrations/202611/add_agent_runtime_tables.py --apply  # 执行
"""
import argparse
import os
import sys

import psycopg2

if not os.environ.get('DATABASE_URL'):
    os.environ['DATABASE_URL'] = os.environ.get(
        'DATABASE_URI',
        'postgresql://intelligent_audio_test:intelligent_audio_test666'
        '@localhost:5432/intelligent_audio_test')

CREATE_TABLES = [
    ('agent_session', """
CREATE TABLE IF NOT EXISTS agent_session (
    id VARCHAR(36) PRIMARY KEY,
    owner_id BIGINT NOT NULL,
    tenant_id VARCHAR(64) NOT NULL,
    title VARCHAR(200) NOT NULL,
    active_skill VARCHAR(100) NULL,
    model VARCHAR(100) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
)
"""),
    ('agent_run', """
CREATE TABLE IF NOT EXISTS agent_run (
    id VARCHAR(36) PRIMARY KEY,
    session_id VARCHAR(36) NOT NULL,
    owner_id BIGINT NOT NULL,
    tenant_id VARCHAR(64) NOT NULL,
    status VARCHAR(20) NOT NULL,
    model VARCHAR(100) NOT NULL,
    budget JSON NULL,
    token_in INTEGER NOT NULL DEFAULT 0,
    token_out INTEGER NOT NULL DEFAULT 0,
    idempotency_key VARCHAR(128) NULL,
    cancel_requested BOOLEAN NOT NULL DEFAULT false,
    error TEXT NULL,
    started_at TIMESTAMP NULL,
    finished_at TIMESTAMP NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
)
"""),
    ('agent_run_event', """
CREATE TABLE IF NOT EXISTS agent_run_event (
    id VARCHAR(36) PRIMARY KEY,
    run_id VARCHAR(36) NOT NULL,
    sequence BIGINT NOT NULL,
    type VARCHAR(50) NOT NULL,
    payload JSON NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_agent_run_event_sequence UNIQUE (run_id, sequence)
)
"""),
    ('agent_step', """
CREATE TABLE IF NOT EXISTS agent_step (
    id VARCHAR(36) PRIMARY KEY,
    run_id VARCHAR(36) NOT NULL,
    "index" INTEGER NOT NULL,
    plan_snapshot JSON NULL,
    status VARCHAR(20) NOT NULL,
    error TEXT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_agent_step_run_index UNIQUE (run_id, "index")
)
"""),
    ('agent_tool_call', """
CREATE TABLE IF NOT EXISTS agent_tool_call (
    id VARCHAR(36) PRIMARY KEY,
    run_id VARCHAR(36) NOT NULL,
    step_id VARCHAR(36) NULL,
    tool_call_id VARCHAR(128) NOT NULL,
    tool VARCHAR(100) NOT NULL,
    arguments JSON NULL,
    args_hash VARCHAR(64) NOT NULL,
    risk VARCHAR(20) NOT NULL,
    status VARCHAR(20) NOT NULL,
    result JSON NULL,
    result_ref TEXT NULL,
    latency_ms INTEGER NULL,
    permission_decision VARCHAR(50) NULL,
    result_code VARCHAR(50) NULL,
    error TEXT NULL,
    idempotency_key VARCHAR(255) NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_agent_tool_call_run_call UNIQUE (run_id, tool_call_id)
)
"""),
    ('agent_artifact', """
CREATE TABLE IF NOT EXISTS agent_artifact (
    id VARCHAR(36) PRIMARY KEY,
    run_id VARCHAR(36) NOT NULL,
    kind VARCHAR(50) NOT NULL,
    uri TEXT NOT NULL,
    size BIGINT NOT NULL DEFAULT 0,
    metadata JSON NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
)
"""),
    ('agent_context_snapshot', """
CREATE TABLE IF NOT EXISTS agent_context_snapshot (
    id VARCHAR(36) PRIMARY KEY,
    run_id VARCHAR(36) NOT NULL,
    version INTEGER NOT NULL,
    token_count INTEGER NOT NULL DEFAULT 0,
    dropped_ids JSON NULL,
    memo JSON NULL,
    level VARCHAR(20) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_agent_context_snapshot_version UNIQUE (run_id, version)
)
"""),
]

# (索引名, 表, 列, 是否唯一)
# agent_step / agent_context_snapshot 不再建普通索引：(run_id, "index") /
# (run_id, version) 的唯一约束已带同列同序索引，普通索引纯写放大（INT-2516）。
INDEXES = [
    ('ix_agent_session_owner', 'agent_session', 'owner_id, created_at', False),
    ('ix_agent_session_tenant', 'agent_session', 'tenant_id, owner_id', False),
    ('ix_agent_run_owner_status', 'agent_run', 'owner_id, status', False),
    ('ix_agent_run_session', 'agent_run', 'session_id, created_at', False),
    ('uq_agent_run_idempotency', 'agent_run', 'idempotency_key', True),
    ('ix_agent_tool_call_run', 'agent_tool_call', 'run_id, created_at', False),
    ('uq_agent_tool_call_idempotency', 'agent_tool_call',
     'idempotency_key', True),
    ('ix_agent_artifact_run', 'agent_artifact', 'run_id, created_at', False),
]

# (约束名, 表, 列) —— 存量表缺约束时补（全新库由 CREATE TABLE / create_all 带出）
UNIQUE_CONSTRAINTS = [
    ('uq_agent_run_event_sequence', 'agent_run_event', 'run_id, sequence'),
    ('uq_agent_step_run_index', 'agent_step', 'run_id, "index"'),
    ('uq_agent_tool_call_run_call', 'agent_tool_call', 'run_id, tool_call_id'),
    ('uq_agent_context_snapshot_version', 'agent_context_snapshot',
     'run_id, version'),
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


def _constraint_exists(cur, table, name):
    cur.execute(
        'SELECT 1 FROM pg_constraint WHERE conname = %s AND conrelid = '
        'to_regclass(%s)', (name, table))
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

    for name, table, cols in UNIQUE_CONSTRAINTS:
        if not _table_exists(cur, table):
            print(f'[SKIP] 约束 {name}（表 {table} 不存在）')
            continue
        if _constraint_exists(cur, table, name):
            print(f'[SKIP] 约束 {name} 已存在')
            continue
        sql = f'ALTER TABLE {table} ADD CONSTRAINT {name} UNIQUE ({cols})'
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
        sql = _index_sql(name, table, cols, unique)
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
        description='agent_service 运行底座七表（INT-2451）迁移')
    parser.add_argument('--dry-run', action='store_true', help='只检查不执行')
    parser.add_argument('--apply', action='store_true', help='真正执行 DDL')
    args = parser.parse_args()
    # 默认 dry-run；引导链显式带 --apply
    migrate(dry_run=not args.apply or args.dry_run)
