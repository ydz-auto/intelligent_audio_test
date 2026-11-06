# -*- coding: utf-8 -*-
"""迁移脚本：新增设备 / API 参数变更历史表 ``param_change_history``

背景：设备参数、API 参数与映射此前没有版本概念——覆盖行删除后只能回落，
无法回看或回滚。本表按作用域（scope=device / api）+ scope_id + algorithm_type
追加版本快照，支撑「历史列表 + 回滚到任意版本」。

- 快照内容为**该作用域覆盖行**的 JSON（params / mappings），不含算法级默认与策略层；
- version 在同一 (scope, scope_id, algorithm_type) 内自增，唯一索引保证幂等追加；
- 归属网关（审计/运维上下文），由 api_gateway 直连读写，不参与 algorithm_service
  运行时解析。

DDL 只有一张表 + 两条索引，``IF NOT EXISTS`` 幂等，重复执行无副作用。

用法：
    python scripts/migrations/202611/add_param_change_history.py            # 预览
    python scripts/migrations/202611/add_param_change_history.py --apply    # 执行
    python scripts/migrations/202611/add_param_change_history.py --rollback # 回滚
"""
import argparse
import os
import sys

import psycopg2

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

if not os.environ.get('DATABASE_URL'):
    os.environ['DATABASE_URL'] = os.environ.get(
        'DATABASE_URI',
        'postgresql://intelligent_audio_test:intelligent_audio_test666'
        '@localhost:5432/intelligent_audio_test')

LOCK_TIMEOUT = '10s'

DDL_FORWARD = (
    """
    CREATE TABLE IF NOT EXISTS param_change_history (
        id BIGSERIAL PRIMARY KEY,
        scope VARCHAR(16) NOT NULL,
        scope_id INTEGER NOT NULL,
        algorithm_type VARCHAR(50) NOT NULL,
        version INTEGER NOT NULL,
        action VARCHAR(16) NOT NULL DEFAULT 'save',
        payload JSONB NOT NULL DEFAULT '{}'::jsonb,
        operator VARCHAR(100),
        created_at TIMESTAMP DEFAULT now()
    )
    """,
    """
    CREATE UNIQUE INDEX IF NOT EXISTS uq_param_change_history_version
        ON param_change_history (scope, scope_id, algorithm_type, version)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_param_change_history_scope
        ON param_change_history (scope, scope_id, algorithm_type, id DESC)
    """,
)

DDL_ROLLBACK = (
    'DROP TABLE IF EXISTS param_change_history',
)

_COUNT_SQL = {
    'param_change_history(存在)': """
        SELECT to_regclass('public.param_change_history') IS NOT NULL""",
    'param_change_history(行数)': """
        SELECT count(*) FROM param_change_history""",
}


def _connect():
    return psycopg2.connect(os.environ['DATABASE_URL'])


def _print_counts(conn):
    with conn.cursor() as cur:
        for label, sql in _COUNT_SQL.items():
            try:
                cur.execute(sql)
                print(f"[state] {label}: {cur.fetchone()[0]}")
            except Exception as exc:  # 表缺失时只提示，不阻断预览
                conn.rollback()
                print(f"[state] {label}: 跳过（{exc.__class__.__name__}）")


def apply(conn):
    with conn.cursor() as cur:
        cur.execute(f"SET lock_timeout = '{LOCK_TIMEOUT}'")
        for ddl in DDL_FORWARD:
            cur.execute(ddl)
        print(f"[ok] param_change_history 就绪（{len(DDL_FORWARD)} 条 DDL，幂等）")
    conn.commit()


def rollback(conn):
    with conn.cursor() as cur:
        cur.execute(f"SET lock_timeout = '{LOCK_TIMEOUT}'")
        for ddl in DDL_ROLLBACK:
            cur.execute(ddl)
        print(f"[ok] 已回滚（{len(DDL_ROLLBACK)} 条 DDL）")
    conn.commit()


def main():
    parser = argparse.ArgumentParser(description='参数变更历史表迁移（dry-run 默认）')
    parser.add_argument('--apply', action='store_true', help='执行迁移')
    parser.add_argument('--rollback', action='store_true', help='回滚结构')
    args = parser.parse_args()

    conn = _connect()
    try:
        if args.rollback:
            rollback(conn)
            return
        _print_counts(conn)
        if args.apply:
            apply(conn)
        else:
            print('[dry-run] 未执行；加 --apply 落库')
    finally:
        conn.close()


if __name__ == '__main__':
    main()
