# -*- coding: utf-8 -*-
"""迁移脚本：自定义 Skill 三表（INT-2549 / 落地方案 §4.4 / §10）

表：
- ``agent_skill``：当前版本指针 + 元信息（scope / tenant_id / owner_id /
  name / description / version / status / content_hash / frontmatter_json /
  resources / created_by / created_at / updated_at）；
- ``agent_skill_version``：不可变版本快照（正文唯一事实源），
  ``(skill_id, version)`` 唯一；
- ``agent_run_skill``：run 激活快照（run_id / skill_id / version /
  content_hash / activated_at），一次激活追加一行。

口径：
- **正文只存版本表**：``agent_skill`` 不存 body，当前版本用 ``version``
  指针引用，不双写（卡面 §4.4 明确要求）；
- ``agent_skill.resources`` / ``agent_skill_version.resources`` 只存
  「相对路径 → 对象存储 key」；
- 唯一性用**局部唯一索引**：``(owner_id, name) WHERE scope='USER'``、
  ``(tenant_id, name) WHERE scope='TENANT'``；
- 无外键（仓库基线：引用完整性由应用层管理）。

幂等：
- CREATE TABLE / INDEX IF NOT EXISTS；局部唯一索引同样 IF NOT EXISTS；
- 全新库 ``create_all`` 已建表 / 索引，本脚本为全 [SKIP]；
- 存量库（建库早于本卡）由本脚本补建。

用法:
    python scripts/migrations/202611/add_agent_skill_tables.py          # dry-run
    python scripts/migrations/202611/add_agent_skill_tables.py --apply  # 执行
"""
import argparse
import os

import psycopg2

if not os.environ.get('DATABASE_URL'):
    os.environ['DATABASE_URL'] = os.environ.get(
        'DATABASE_URI',
        'postgresql://intelligent_audio_test:intelligent_audio_test666'
        '@localhost:5432/intelligent_audio_test')

CREATE_TABLES = [
    ('agent_skill', """
CREATE TABLE IF NOT EXISTS agent_skill (
    id VARCHAR(36) PRIMARY KEY,
    scope VARCHAR(20) NOT NULL,
    tenant_id VARCHAR(64) NULL,
    owner_id BIGINT NULL,
    name VARCHAR(64) NOT NULL,
    description TEXT NOT NULL,
    version VARCHAR(32) NOT NULL,
    status VARCHAR(20) NOT NULL,
    content_hash VARCHAR(64) NOT NULL,
    frontmatter_json JSON NULL,
    resources JSON NULL,
    created_by BIGINT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
)
"""),
    ('agent_skill_version', """
CREATE TABLE IF NOT EXISTS agent_skill_version (
    id VARCHAR(36) PRIMARY KEY,
    skill_id VARCHAR(36) NOT NULL,
    version VARCHAR(32) NOT NULL,
    content_hash VARCHAR(64) NOT NULL,
    frontmatter_json JSON NULL,
    body TEXT NOT NULL,
    resources JSON NULL,
    created_by BIGINT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
)
"""),
    ('agent_run_skill', """
CREATE TABLE IF NOT EXISTS agent_run_skill (
    id VARCHAR(36) PRIMARY KEY,
    run_id VARCHAR(36) NOT NULL,
    skill_id VARCHAR(100) NOT NULL,
    version VARCHAR(32) NOT NULL,
    content_hash VARCHAR(64) NOT NULL,
    activated_at TIMESTAMP NOT NULL DEFAULT NOW()
)
"""),
]

# (约束名, 表, 定义)
UNIQUE_CONSTRAINTS = [
    ('uq_agent_skill_version_skill_version', 'agent_skill_version',
     'skill_id, version'),
]

# (索引名, 表, 列, 是否唯一, 局部谓词)
INDEXES = [
    ('ix_agent_skill_scope_status', 'agent_skill', 'scope, status', False, ''),
    ('uq_agent_skill_owner_name', 'agent_skill', 'owner_id, name', True,
     "scope = 'USER'"),
    ('uq_agent_skill_tenant_name', 'agent_skill', 'tenant_id, name', True,
     "scope = 'TENANT'"),
    ('ix_agent_skill_version_skill', 'agent_skill_version',
     'skill_id, created_at', False, ''),
    ('ix_agent_run_skill_run', 'agent_run_skill', 'run_id, activated_at',
     False, ''),
    ('ix_agent_run_skill_skill', 'agent_run_skill', 'skill_id', False, ''),
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

    for name, table, cols, unique, where in INDEXES:
        if not _table_exists(cur, table):
            print(f'[SKIP] 索引 {name}（表 {table} 不存在）')
            continue
        if _index_exists(cur, table, name):
            print(f'[SKIP] 索引 {name} 已存在')
            continue
        kind = 'UNIQUE INDEX' if unique else 'INDEX'
        sql = f'CREATE {kind} IF NOT EXISTS {name} ON {table} ({cols})'
        if where:
            sql += f' WHERE {where}'
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


def rollback(dry_run=True):
    """回滚：删除本卡三张表（幂等，DROP TABLE IF EXISTS）。

    三张表是本卡新增的独立结构，回滚不触碰任何存量表；``agent_run_skill``
    的历史快照随表一起删除（回填不在本卡范围）。
    """
    conn = _connect()
    conn.autocommit = True
    cur = conn.cursor()
    for table, _sql in reversed(CREATE_TABLES):
        if not _table_exists(cur, table):
            print(f'[SKIP] 表 {table} 不存在')
            continue
        sql = f'DROP TABLE IF EXISTS {table}'
        if dry_run:
            print(f'[DRY-RUN] {sql}')
        else:
            print(f'[EXEC] {sql}')
            cur.execute(sql)
            print(f'[DONE] 表 {table} 已删除')
    cur.close()
    conn.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='agent_skill / agent_skill_version / agent_run_skill'
                    '（INT-2549）迁移')
    parser.add_argument('--dry-run', action='store_true', help='只检查不执行')
    parser.add_argument('--apply', action='store_true', help='真正执行 DDL')
    parser.add_argument('--rollback', action='store_true',
                        help='回滚：删除本卡三张表（需配合 --apply）')
    args = parser.parse_args()
    if args.rollback:
        rollback(dry_run=not args.apply)
    else:
        # 默认 dry-run；引导链显式带 --apply
        migrate(dry_run=not args.apply or args.dry_run)
