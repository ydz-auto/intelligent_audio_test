# -*- coding: utf-8 -*-
"""迁移脚本：新增设备 → 参数策略绑定表 ``device_param_bindings``

背景：设备级参数配置原先只有「算法类型级默认 + 设备覆盖」两层；本轮补齐
「设备绑定 scope=device 策略」一层，解析优先级变为：

    设备覆盖 > 设备绑定策略 > 算法类型级默认

结构与 ``api_param_bindings`` 同构（绑定归 algorithm_service，运行时按
``device_id`` 解析策略，不跨服务读 device_service 的库）；设备级差异仍写在
``algorithm_device_params`` / ``param_mappings`` 的 device_id 行。

DDL 只有一张表 + 一个部分唯一索引；``IF NOT EXISTS`` 幂等，重复执行无副作用。
全新库由 ``scripts/create_all_tables.py`` 的 ``Base.metadata.create_all`` 带出，
本脚本在引导链里对存量库补建（执行结果为 SKIP）。

用法：
    python scripts/migrations/202611/add_device_param_bindings.py            # 预览
    python scripts/migrations/202611/add_device_param_bindings.py --apply    # 执行
    python scripts/migrations/202611/add_device_param_bindings.py --rollback # 回滚
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
    CREATE TABLE IF NOT EXISTS device_param_bindings (
        id SERIAL PRIMARY KEY,
        device_id INTEGER NOT NULL,
        profile_id INTEGER NOT NULL,
        deleted BOOLEAN DEFAULT false,
        created_at TIMESTAMP DEFAULT now(),
        updated_at TIMESTAMP DEFAULT now()
    )
    """,
    """
    CREATE UNIQUE INDEX IF NOT EXISTS uq_device_param_binding_device
        ON device_param_bindings (device_id) WHERE deleted = false
    """,
    # 与 api_param_bindings 同口径：deleted 列补 DB 默认值，避免历史 INSERT 落 NULL
    # 后被读侧 ``filter_by(deleted=False)`` 整表滤掉。
    'ALTER TABLE device_param_bindings ALTER COLUMN deleted SET DEFAULT false',
    'UPDATE device_param_bindings SET deleted = false WHERE deleted IS NULL',
)

DDL_ROLLBACK = (
    'DROP TABLE IF EXISTS device_param_bindings',
)

_COUNT_SQL = {
    'device_param_bindings(存在)': """
        SELECT to_regclass('public.device_param_bindings') IS NOT NULL""",
    'device_param_bindings(deleted=false)': """
        SELECT count(*) FROM device_param_bindings WHERE deleted = false""",
    'device_param_bindings(deleted IS NULL)': """
        SELECT count(*) FROM device_param_bindings WHERE deleted IS NULL""",
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
        print(f"[ok] device_param_bindings 就绪（{len(DDL_FORWARD)} 条 DDL，幂等）")
    conn.commit()


def rollback(conn):
    with conn.cursor() as cur:
        cur.execute(f"SET lock_timeout = '{LOCK_TIMEOUT}'")
        for ddl in DDL_ROLLBACK:
            cur.execute(ddl)
        print(f"[ok] 已回滚（{len(DDL_ROLLBACK)} 条 DDL）")
    conn.commit()


def main():
    parser = argparse.ArgumentParser(description='设备参数策略绑定表迁移（dry-run 默认）')
    parser.add_argument('--apply', action='store_true', help='执行迁移')
    parser.add_argument('--rollback', action='store_true', help='回滚结构')
    args = parser.parse_args()

    conn = _connect()
    try:
        if args.rollback:
            rollback(conn)
            return
        _print_counts(conn)
        if not args.apply:
            print('[dry-run] 未修改数据库；加 --apply 执行')
            return
        apply(conn)
    finally:
        conn.close()


if __name__ == '__main__':
    main()
