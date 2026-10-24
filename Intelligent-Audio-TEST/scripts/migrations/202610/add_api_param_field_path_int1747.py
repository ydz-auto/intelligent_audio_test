# -*- coding: utf-8 -*-
"""迁移脚本：algorithm_api_params 补输出字段取值路径列 field_path（INT-1747 / C2）

背景（C0 / INT-1745 裁定 §9.2 §9.3）：
API 输出字段只能按顶层键取值，厂商响应里的嵌套字段（``data.translation.text``、
``data.events[0].text``）取不到。本迁移给 ``algorithm_api_params`` 补
``field_path``：非空时按路径从厂商原始响应取值，为空保持「按 param_code 取
顶层键」的存量行为（存量行零改动）。

DDL 与 algorithm_service/infrastructure/persistence/models/algorithm_models.py 的
AlgorithmApiParam 元数据逐列对齐：
    field_path VARCHAR(255) NULL（无默认值、无索引：仅输出声明提取读取，
    按 algorithm_type 的查询已由 uq_algorithm_api_param_direction 覆盖）

锁预算（INT-1652 口径）：
    lock_timeout 默认 5s（DB_MIGRATION_LOCK_TIMEOUT_MS 可覆盖）——拿不到
    ACCESS EXCLUSIVE 就失败退出并打印持锁者，绝不排队堵住整张表；脚本同时
    打印加列耗时与是否发生等锁，供卡面「迁移在真实库上的耗时与锁等待」记录。

回滚说明：
    新代码先不读该列即可回退代码；列本身可保留（NULL，旧代码 SELECT 不感知）。
    确需回滚结构时执行：
        ALTER TABLE algorithm_api_params DROP COLUMN IF EXISTS field_path;
    顺序：先回退镜像，再删列（新镜像读旧库会 UndefinedColumn）。

用法：
    python scripts/migrations/202610/add_api_param_field_path_int1747.py            # 预览
    python scripts/migrations/202610/add_api_param_field_path_int1747.py --apply    # 执行

幂等性：列已存在即 SKIP。全新库 create_all 已含该列，执行为全 [SKIP]。
"""
import argparse
import os
import sys
import time

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

TABLE = 'algorithm_api_params'
COLUMN = 'field_path'
DEFAULT_LOCK_TIMEOUT_MS = 5000
DEFAULT_STATEMENT_TIMEOUT_MS = 300000

COLUMN_DDL = (f'ALTER TABLE {TABLE} ADD COLUMN IF NOT EXISTS {COLUMN} '
              'VARCHAR(255)')


def _int_env(name, default):
    """读取正整数环境变量，非法值回落默认。"""
    raw = os.environ.get(name)
    if raw is None or str(raw).strip() == '':
        return default
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def _connect():
    from urllib.parse import urlparse
    parsed = urlparse(os.environ['DATABASE_URL'])
    return psycopg2.connect(
        host=parsed.hostname, port=parsed.port or 5432,
        dbname=parsed.path.lstrip('/'), user=parsed.username,
        password=parsed.password, application_name='migration_int1747')


def _table_exists(cur) -> bool:
    cur.execute(
        'SELECT 1 FROM information_schema.tables WHERE table_name = %s', (TABLE,))
    return cur.fetchone() is not None


def _column_exists(cur) -> bool:
    cur.execute(
        'SELECT 1 FROM information_schema.columns '
        'WHERE table_name = %s AND column_name = %s', (TABLE, COLUMN))
    return cur.fetchone() is not None


def _waiting_lock_pids(cur):
    """当前在该表上等锁的后端 pid（只用于失败诊断，不参与判定）。"""
    cur.execute(
        "SELECT pid FROM pg_locks WHERE NOT granted AND relation = %s::regclass",
        (TABLE,))
    return [row[0] for row in cur.fetchall()]


def _blocking_pids(cur):
    """持锁阻塞别人的后端 pid（诊断用）。"""
    cur.execute(
        "SELECT DISTINCT l.pid FROM pg_locks l "
        "JOIN pg_stat_activity a ON a.pid = l.pid "
        "WHERE l.granted AND l.relation = %s::regclass AND a.pid <> pg_backend_pid()",
        (TABLE,))
    return [row[0] for row in cur.fetchall()]


def _verify(cur):
    cur.execute(
        'SELECT data_type, character_maximum_length, is_nullable, column_default '
        'FROM information_schema.columns '
        'WHERE table_name = %s AND column_name = %s', (TABLE, COLUMN))
    row = cur.fetchone()
    if not row:
        print(f'[VERIFY][FAIL] {TABLE}.{COLUMN} 不存在')
        return False
    data_type, max_length, nullable, default = row
    print(f'[VERIFY] {TABLE}.{COLUMN}: {data_type}({max_length}) '
          f'{"NULL" if nullable == "YES" else "NOT NULL"} DEFAULT {default}')
    return nullable == 'YES'


def migrate(dry_run=True):
    lock_timeout_ms = _int_env('DB_MIGRATION_LOCK_TIMEOUT_MS',
                               DEFAULT_LOCK_TIMEOUT_MS)
    statement_timeout_ms = _int_env('DB_MIGRATION_STATEMENT_TIMEOUT_MS',
                                    DEFAULT_STATEMENT_TIMEOUT_MS)
    conn = _connect()
    try:
        conn.autocommit = False
        cur = conn.cursor()
        cur.execute(f'SET lock_timeout = {lock_timeout_ms}')
        cur.execute(f'SET statement_timeout = {statement_timeout_ms}')

        if not _table_exists(cur):
            print(f'[SKIP] 表 {TABLE} 不存在（空库请先 create_all_tables.py）')
            return

        if _column_exists(cur):
            print(f'[SKIP] 列 {COLUMN} 已存在')
            _verify(cur)
            return

        waiting = _waiting_lock_pids(cur)
        if waiting:
            print(f'[WARN] 迁移前该表已有等锁后端 pid={waiting}')

        print(f"[{'DRY' if dry_run else 'APPLY'}] {COLUMN_DDL}")
        if dry_run:
            print('[DRY] 未执行 DDL；--apply 时按 lock_timeout='
                  f'{lock_timeout_ms}ms / statement_timeout='
                  f'{statement_timeout_ms}ms 执行')
            return

        started = time.monotonic()
        try:
            cur.execute(COLUMN_DDL)
            conn.commit()
        except psycopg2.errors.LockNotAvailable:
            conn.rollback()
            print(f'[FAIL] {lock_timeout_ms}ms 内未拿到 ACCESS EXCLUSIVE 锁；'
                  f'持锁者 pid={_blocking_pids(cur)}，等锁者 pid='
                  f'{_waiting_lock_pids(cur)}')
            raise SystemExit(2)
        elapsed_ms = int((time.monotonic() - started) * 1000)
        # 加列耗时含等锁时间；lock_timeout 未触发即等锁 < 预算
        print(f'[APPLY] 加列完成，耗时 {elapsed_ms}ms'
              f'（lock_timeout={lock_timeout_ms}ms，未触发=等锁低于预算）')

        if not _verify(cur):
            raise SystemExit(3)
        cur.close()
    finally:
        conn.close()


def main():
    ap = argparse.ArgumentParser(
        description='algorithm_api_params 补输出字段取值路径列 field_path'
                    '（INT-1747）')
    ap.add_argument('--apply', action='store_true', help='执行（默认 dry-run 预览）')
    args = ap.parse_args()
    migrate(dry_run=not args.apply)


if __name__ == '__main__':
    main()
