# -*- coding: utf-8 -*-
"""迁移脚本：TENANT 级 Skill 审核链 ``agent_skill_review``（INT-2551）

表 ``agent_skill_review``：提交 / 批准 / 驳回 / 撤回 / 停用各追加一行，
**只追加不更新不删除**（审批链是审计事实）。字段：

- ``skill_id`` / ``version``：版本粒度可追溯「谁批的哪一版」；
- ``action``：``SkillReviewAction``（SUBMIT / APPROVE / REJECT / WITHDRAW /
  DISABLE），枚举取值，无魔法字符串；
- ``status_from`` / ``status_to``：``SkillStatus``（状态机迁移两端）；
- ``reviewer_id`` / ``reason``：谁、什么理由；
- ``tenant_id``：待审队列按 ``(tenant_id, status_to)`` 取本租户记录，Skill
  行被删后审计链仍可查。

索引：``(skill_id, version)`` 单版本追溯、``(tenant_id, status_to)`` 待审
队列、``(skill_id, created_at)`` 单 Skill 审批链。

幂等：
- CREATE TABLE / INDEX IF NOT EXISTS；
- 全新库 ``create_all`` 已建表 / 索引，本脚本为全 [SKIP]；
- 存量库（建库早于本卡）由本脚本补建。

用法:
    python scripts/migrations/202611/add_agent_skill_review_table.py          # dry-run
    python scripts/migrations/202611/add_agent_skill_review_table.py --apply  # 执行
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
    ('agent_skill_review', """
CREATE TABLE IF NOT EXISTS agent_skill_review (
    id VARCHAR(36) PRIMARY KEY,
    skill_id VARCHAR(36) NOT NULL,
    version VARCHAR(32) NOT NULL,
    action VARCHAR(20) NOT NULL,
    status_from VARCHAR(20) NOT NULL,
    status_to VARCHAR(20) NOT NULL,
    reviewer_id BIGINT NULL,
    reason TEXT NOT NULL DEFAULT '',
    tenant_id VARCHAR(64) NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
)
"""),
]

# (索引名, 表, 列, 是否唯一, 局部谓词)
INDEXES = [
    ('ix_agent_skill_review_skill_version', 'agent_skill_review',
     'skill_id, version', False, ''),
    ('ix_agent_skill_review_tenant_status', 'agent_skill_review',
     'tenant_id, status_to', False, ''),
    ('ix_agent_skill_review_skill_time', 'agent_skill_review',
     'skill_id, created_at', False, ''),
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
    """回滚：删除本卡新增的 ``agent_skill_review``（幂等，DROP TABLE IF EXISTS）。

    只删本卡新增的独立表，不触碰 INT-2549 的三张 Skill 表。
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
        description='agent_skill_review（INT-2551）迁移')
    parser.add_argument('--dry-run', action='store_true', help='只检查不执行')
    parser.add_argument('--apply', action='store_true', help='真正执行 DDL')
    parser.add_argument('--rollback', action='store_true',
                        help='回滚：删除本卡新增表（需配合 --apply）')
    args = parser.parse_args()
    if args.rollback:
        rollback(dry_run=not args.apply)
    else:
        # 默认 dry-run；引导链显式带 --apply
        migrate(dry_run=not args.apply or args.dry_run)
