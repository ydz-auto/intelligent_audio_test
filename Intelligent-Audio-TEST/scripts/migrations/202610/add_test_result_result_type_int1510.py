# -*- coding: utf-8 -*-
"""迁移脚本：test_results 补结果类型列 result_type（INT-1510 / §8.2.3）

背景（设计文档 §8.2.1 第 3/4 条、§8.2.3 第 1 条）：
- 候选行 result_type 原先不是列：取值走 `extract_result_type` →
  `load_full_result_data`，在 `result_data_path` 非空时先读对象存储
  （`storage.exists` + `storage.load_bytes`，每行 2 次 OSS 往返，
  read_timeout=60），是阶段 2 候选接口长尾的主因；
- 可挑范围内 2805/3614 行有 `result_data_path`，其中 2598 行 DB 轻量 JSON
  已含 `result_type`，1016 行缺键。

本迁移把 result_type 落成列并回填存量行，读侧改 DB-first（请求路径零 OSS 往返）：
- 值域沿用现有口径（asr / api / voice / real-time / final 等），
- 缺值语义 = UX「结果类型待补充」桶：落库为 NULL，对外统一输出 default，
  查询侧 `result_type=default` 命中 `IS NULL OR = ''`。

步骤（幂等）：
    ① ADD COLUMN IF NOT EXISTS result_type varchar(50) NULL
    ② 回填：只对当前为 NULL 且 `materialize_result_type(None, result_data)`
       能算出非空值的行 UPDATE（默认 dry-run 只统计待回填行数）；
       **只读 DB 轻量 JSON，不回源对象存储**（缺键行保持 NULL = 待补充桶）。

用法：
    python scripts/migrations/202610/add_test_result_result_type_int1510.py            # 预览
    python scripts/migrations/202610/add_test_result_result_type_int1510.py --apply    # 执行

幂等性：列已存在即 SKIP；回填按值比对只写有差异的行，重复执行命中 0 行
（db_bootstrap 每次部署都会执行该步）。不建索引：读侧缺值桶是
`IS NULL OR = ''` 的 OR 条件走不了等值索引，且写入路径（结果逐条落库）不宜加索引成本。
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

from shared.utils.result_data_store import materialize_result_type  # noqa: E402

TABLE = 'test_results'
COLUMN = 'result_type'
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


def _parse_result_data(raw):
    """result_data::text → dict / 原样字符串（脏数据不阻断引导链）。

    写成 JSON 字符串的存量行（双重编码）交由 `materialize_result_type` 内部
    的字符串解析分支处理；无法解析的行返回 None（按缺值桶处理）。
    """
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return None


def _backfill(cur, apply):
    """按 materialize_result_type 回填，只写值为 NULL 且解析出类型的结果行。"""
    cur.execute(f"SELECT count(*) FROM {TABLE}")
    scanned = cur.fetchone()[0]
    cur.execute(
        f"SELECT id, {COLUMN}, result_data::text FROM {TABLE} "
        f"WHERE {COLUMN} IS NULL ORDER BY id")
    pending = []
    while True:
        rows = cur.fetchmany(BATCH)
        if not rows:
            break
        for result_id, current, result_data_text in rows:
            want = materialize_result_type(None, _parse_result_data(result_data_text))
            if current is None and want:
                pending.append((want, result_id))
    changed = 0
    if apply and pending:
        cur.executemany(
            f"UPDATE {TABLE} SET {COLUMN} = %s WHERE id = %s", pending)
        changed = len(pending)
    return scanned, len(pending), changed


def _count_pending_bucket(cur):
    """缺值桶（落库 NULL/空串）行数——交付评论需要的检出计数。"""
    cur.execute(
        f"SELECT count(*) FROM {TABLE} WHERE {COLUMN} IS NULL OR {COLUMN} = ''")
    return cur.fetchone()[0]


def migrate(dry_run=True):
    conn = _connect()
    try:
        cur = conn.cursor()
        # ① 加列
        if _column_exists(cur):
            print(f'[SKIP] 列 {TABLE}.{COLUMN} 已存在')
        else:
            print(f"[{'DRY' if dry_run else 'APPLY'}] ALTER TABLE {TABLE} ADD COLUMN "
                  f"{COLUMN} varchar(50) NULL")
            if not dry_run:
                cur.execute(
                    f"ALTER TABLE {TABLE} ADD COLUMN IF NOT EXISTS {COLUMN} "
                    "varchar(50) NULL")
                conn.commit()
        if not _column_exists(cur) and dry_run:
            print('[DRY] 列未创建，跳过回填')
            return
        # ② 回填
        scanned, pending, changed = _backfill(cur, apply=not dry_run)
        print(f"[{'DRY' if dry_run else 'APPLY'}] 回填：扫描 {scanned} 行，"
              f"待改 {pending} 行，已改 {changed} 行")
        if not dry_run:
            conn.commit()
        # ③ 缺值桶计数（读侧统一输出 default）
        print(f"[{'DRY' if dry_run else 'APPLY'}] 缺值桶（NULL/空串）"
              f"{_count_pending_bucket(cur)} 行")
    finally:
        conn.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true', help='执行（默认 dry-run 预览）')
    args = ap.parse_args()
    migrate(dry_run=not args.apply)


if __name__ == '__main__':
    main()
