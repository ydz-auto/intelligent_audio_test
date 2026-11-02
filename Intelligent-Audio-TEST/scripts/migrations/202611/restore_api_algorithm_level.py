# -*- coding: utf-8 -*-
"""迁移脚本：恢复 API 参数的算法级默认层（三层解析的兜底层）

背景：``add_param_profiles_scope.py``（202610）把 ``api_id IS NULL`` 的算法级
默认参数/映射复制进 ``default`` 策略后**软删**了原行。2026-11-02 口径回退：
算法级默认层作为「实例覆盖 > 策略 > 算法级默认」的兜底层保留，需要把被软删的
原行恢复为可见。

本脚本做三件事（全部幂等）：

1. ``algorithm_api_params``：``api_id IS NULL AND deleted=true`` 恢复为 ``deleted=false``，
   同键已有活跃行时跳过（避免撞部分唯一索引）；
2. ``param_mappings``：``api_id IS NULL AND source='api' AND deleted=true`` 同上恢复；
   其它来源（case / case_config / device / evaluation / reference）的历史软删行**不动**；
3. ``api_param_bindings``：解绑迁移期生成的 ``scope='api' AND name='default'`` 策略，
   让实例真正回落到算法级默认层（策略本身保留，可手工重新绑定）。

用法：
    python scripts/migrations/202611/restore_api_algorithm_level.py            # 预览
    python scripts/migrations/202611/restore_api_algorithm_level.py --apply    # 执行
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

# 恢复算法级 API 参数行：每个自然键只恢复一行（优先 id 最大者），
# 同键已有活跃行则跳过。必须用 DISTINCT ON——同键可能有多条历史软删行，
# 直接 UPDATE 会同时恢复多行，撞 `uq_algorithm_api_param_algo_level`。
RESTORE_API_PARAMS = """
WITH pick AS (
  SELECT DISTINCT ON (algorithm_type, param_code, direction) id
  FROM algorithm_api_params p
  WHERE p.api_id IS NULL AND p.deleted = true
    AND NOT EXISTS (
      SELECT 1 FROM algorithm_api_params o
      WHERE o.algorithm_type = p.algorithm_type
        AND o.param_code = p.param_code
        AND o.direction = p.direction
        AND o.api_id IS NULL AND o.deleted = false
    )
  ORDER BY algorithm_type, param_code, direction, id DESC
)
UPDATE algorithm_api_params p SET deleted = false
FROM pick WHERE p.id = pick.id
"""

# 恢复算法级 api 来源映射：每个自然键只恢复一行（优先 id 最大者），同键已有活跃行则跳过
RESTORE_API_MAPPINGS = """
WITH pick AS (
  SELECT DISTINCT ON (algorithm_type, source, source_param, dimension_id) id
  FROM param_mappings m
  WHERE m.api_id IS NULL AND m.deleted = true AND m.source = 'api'
    AND NOT EXISTS (
      SELECT 1 FROM param_mappings o
      WHERE o.algorithm_type = m.algorithm_type
        AND o.source = m.source
        AND o.source_param = m.source_param
        AND o.dimension_id IS NOT DISTINCT FROM m.dimension_id
        AND o.api_id IS NULL AND o.deleted = false
    )
  ORDER BY algorithm_type, source, source_param, dimension_id, id DESC
)
UPDATE param_mappings m SET deleted = false
FROM pick WHERE m.id = pick.id
"""

# 解绑迁移生成的 default API 策略（实例回落算法级默认）
UNBIND_DEFAULT_PROFILE = """
UPDATE api_param_bindings b SET deleted = true
FROM param_profiles p
WHERE b.profile_id = p.id
  AND p.scope = 'api' AND p.name = 'default'
  AND COALESCE(b.deleted, false) = false
"""

_COUNT_SQL = {
    'algorithm_api_params(算法级可用)': """
        SELECT count(*) FROM algorithm_api_params
        WHERE api_id IS NULL AND deleted = false""",
    'algorithm_api_params(算法级已软删)': """
        SELECT count(*) FROM algorithm_api_params
        WHERE api_id IS NULL AND deleted = true""",
    "param_mappings(算法级 api 可用)": """
        SELECT count(*) FROM param_mappings
        WHERE api_id IS NULL AND source = 'api' AND deleted = false""",
    "param_mappings(算法级 api 已软删)": """
        SELECT count(*) FROM param_mappings
        WHERE api_id IS NULL AND source = 'api' AND deleted = true""",
    'api_param_bindings(default 策略活跃绑定)': """
        SELECT count(*) FROM api_param_bindings b
        JOIN param_profiles p ON p.id = b.profile_id
        WHERE p.scope = 'api' AND p.name = 'default'
          AND COALESCE(b.deleted, false) = false""",
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
        cur.execute(RESTORE_API_PARAMS)
        params = cur.rowcount
        cur.execute(RESTORE_API_MAPPINGS)
        mappings = cur.rowcount
        cur.execute(UNBIND_DEFAULT_PROFILE)
        bindings = cur.rowcount
        print(f'[ok] 恢复算法级参数 {params} 行 / 映射 {mappings} 行；'
              f'解绑 default 策略 {bindings} 条')
    conn.commit()


def main():
    parser = argparse.ArgumentParser(description='恢复 API 算法级默认层（dry-run 默认）')
    parser.add_argument('--apply', action='store_true', help='执行数据恢复')
    args = parser.parse_args()

    conn = _connect()
    try:
        print('--- 执行前 ---')
        _print_counts(conn)
        if args.apply:
            apply(conn)
            print('--- 执行后 ---')
            _print_counts(conn)
        else:
            print('[dry-run] 未执行；加 --apply 落库')
    finally:
        conn.close()


if __name__ == '__main__':
    main()
