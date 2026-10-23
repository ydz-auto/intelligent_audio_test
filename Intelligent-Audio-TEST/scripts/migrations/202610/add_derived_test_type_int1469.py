# -*- coding: utf-8 -*-
"""迁移脚本：test_cases 补执行口径派生列 derived_test_type（INT-1469）

背景（INT-1469 用例域性能优化）：
- 用例不存储类型（INT-79/差异#2 收尾已删 test_cases.test_type），执行口径
  由 config 形态（+上传双变体 _api/_e2e 名后缀，INT-129）派生；
- 列表/统计/取 ID 三类查询原先「物化全量候选行（id/name/config）到内存后
  Python 过滤」，万级用例下每请求 ~500ms（隔离栈实测 10k 用例：列表 type
  过滤 490~590ms、统计 type 过滤 460~520ms、fetch_case_ids ~545ms）；
- 本迁移补冗余列，写时物化 derive_case_test_type(config, name) 的结果
  （task_service ORM before_insert/before_update 事件统一刷新），查询侧改
  为 SQL 等值过滤并走索引。

步骤（幂等）：
    ① ADD COLUMN IF NOT EXISTS derived_test_type varchar(10) NOT NULL DEFAULT 'api'
    ② 回填：只对与 derive_case_test_type 结果不一致的行 UPDATE（默认 dry-run
       只统计待回填行数）
    ③ CREATE INDEX IF NOT EXISTS ix_test_cases_derived_test_type

用法：
    python scripts/migrations/202610/add_derived_test_type_int1469.py            # 预览
    python scripts/migrations/202610/add_derived_test_type_int1469.py --apply    # 执行

幂等性：
    列/索引已存在即 SKIP；回填按值比对只写有差异的行，重复执行命中 0 行。
    依赖：无（列自包含，口径函数在 shared/utils/testcase_helpers.py）。
"""
import argparse
import json
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

from shared.utils.testcase_helpers import derive_case_test_type  # noqa: E402

TABLE = 'test_cases'
COLUMN = 'derived_test_type'
INDEX_NAME = 'ix_test_cases_derived_test_type'
BATCH = 2000


def _connect():
    from urllib.parse import urlparse
    parsed = urlparse(os.environ['DATABASE_URL'])
    conn = psycopg2.connect(
        host=parsed.hostname, port=parsed.port or 5432,
        dbname=parsed.path.lstrip('/'), user=parsed.username,
        password=parsed.password)
    return conn


def _column_exists(cur):
    cur.execute(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name = %s AND column_name = %s", (TABLE, COLUMN))
    return cur.fetchone() is not None


def _index_exists(cur):
    cur.execute("SELECT 1 FROM pg_indexes WHERE tablename = %s AND indexname = %s",
                (TABLE, INDEX_NAME))
    return cur.fetchone() is not None


def _backfill(cur, apply):
    """按 derive_case_test_type 回填，只写有差异的行。返回 (扫描数, 待改数, 已改数)。"""
    cur.execute(f"SELECT count(*) FROM {TABLE}")
    scanned = cur.fetchone()[0]
    cur.execute(f"SELECT id, name, config::text, {COLUMN} FROM {TABLE} ORDER BY id")
    pending = []
    while True:
        rows = cur.fetchmany(BATCH)
        if not rows:
            break
        for tc_id, name, config_text, current in rows:
            config = json.loads(config_text) if config_text else {}
            want = derive_case_test_type(config, name)
            if want != current:
                pending.append((want, tc_id))
    changed = 0
    if apply and pending:
        cur.executemany(
            f"UPDATE {TABLE} SET {COLUMN} = %s WHERE id = %s", pending)
        changed = len(pending)
    return scanned, len(pending), changed


def migrate(dry_run=True):
    conn = _connect()
    try:
        cur = conn.cursor()
        # ① 加列
        if _column_exists(cur):
            print(f'[SKIP] 列 {TABLE}.{COLUMN} 已存在')
        else:
            print(f"[{'DRY' if dry_run else 'APPLY'}] ALTER TABLE {TABLE} ADD COLUMN "
                  f"{COLUMN} varchar(10) NOT NULL DEFAULT 'api'")
            if not dry_run:
                cur.execute(
                    f"ALTER TABLE {TABLE} ADD COLUMN IF NOT EXISTS {COLUMN} "
                    "varchar(10) NOT NULL DEFAULT 'api'")
                conn.commit()
        if not _column_exists(cur) and dry_run:
            print('[DRY] 列未创建，跳过回填与索引')
            return
        # ② 回填
        scanned, pending, changed = _backfill(cur, apply=not dry_run)
        print(f"[{'DRY' if dry_run else 'APPLY'}] 回填：扫描 {scanned} 行，"
              f"待改 {pending} 行，已改 {changed} 行")
        if not dry_run:
            conn.commit()
        # ③ 索引
        if _index_exists(cur):
            print(f'[SKIP] 索引 {INDEX_NAME} 已存在')
        else:
            print(f"[{'DRY' if dry_run else 'APPLY'}] CREATE INDEX {INDEX_NAME} "
                  f"ON {TABLE} ({COLUMN})")
            if not dry_run:
                cur.execute(
                    f"CREATE INDEX IF NOT EXISTS {INDEX_NAME} "
                    f"ON {TABLE} ({COLUMN})")
                conn.commit()
    finally:
        conn.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true', help='执行（默认 dry-run 预览）')
    args = ap.parse_args()
    migrate(dry_run=not args.apply)


if __name__ == '__main__':
    main()
