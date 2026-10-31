# -*- coding: utf-8 -*-
"""迁移脚本：algorithm_device_params / param_mappings 加 device_id 作用域 + 唯一索引拆分

背景（「设备参数及映射移到设备里配置」/ 真·设备级独立覆盖）：
- 设备参数此前只有算法类型级作用域，同一算法下所有设备共享一套声明；
- 本迁移补 ``device_id``（NULL = 算法类型级默认，指向 device_service 的 devices.id；
  **不建跨服务外键**，存在性由网关写路径校验），合并读取时设备级行覆盖算法级行，
  与 ``api_id``（INT-1751 / INT-1756）同一套口径。

DDL（与 algorithm_service/infrastructure/persistence/models/algorithm_models.py 对齐）：
    SET lock_timeout = '10s'
    ALTER TABLE algorithm_device_params ADD COLUMN IF NOT EXISTS device_id INTEGER NULL
    ALTER TABLE param_mappings         ADD COLUMN IF NOT EXISTS device_id INTEGER NULL
    CREATE INDEX idx_algorithm_device_params_device_id ... WHERE deleted = false
    CREATE INDEX idx_param_mappings_device_id          ... WHERE deleted = false

    -- 设备参数：旧「算法级唯一」拆成「算法级 / 设备级」两条
    DROP INDEX uq_algorithm_device_param_direction
    CREATE UNIQUE INDEX uq_algorithm_device_param_algo_level
        ON algorithm_device_params (algorithm_type, param_code, direction)
        NULLS NOT DISTINCT WHERE deleted = false AND device_id IS NULL
    CREATE UNIQUE INDEX uq_algorithm_device_param_device_level
        ON algorithm_device_params (algorithm_type, device_id, param_code, direction)
        NULLS NOT DISTINCT WHERE deleted = false AND device_id IS NOT NULL

    -- 参数映射：api_id 迁移已拆成 algo/api 两级，这里再收敛为「算法级 / API 级 / 设备级」三条
    -- 两条旧索引与新索引同名，只有定义不同（旧定义无 device_id 条件），
    -- 故按「名称 + 定义」双匹配判断：定义已一致就不动，不一致才 DROP 后重建。
    CREATE UNIQUE INDEX uq_param_mapping_algo_level   ... WHERE deleted = false
        AND api_id IS NULL AND device_id IS NULL
    CREATE UNIQUE INDEX uq_param_mapping_api_level    ... WHERE deleted = false
        AND api_id IS NOT NULL AND device_id IS NULL
    CREATE UNIQUE INDEX uq_param_mapping_device_level
        ON param_mappings (algorithm_type, device_id, source, source_param, dimension_id)
        NULLS NOT DISTINCT WHERE deleted = false AND device_id IS NOT NULL

执行语义：
- 默认 dry-run：打印待执行 DDL 与前置检查（存量行数、重复组、索引现状），不改库；
- ``--apply``：单事务执行（DDL 在 PostgreSQL 可事务化，失败整体回滚）；
- ``--rollback``：DROP 新索引 → 按迁移前定义重建旧索引 → DROP COLUMN device_id；
- 幂等：列 / 简单索引存在即 SKIP；唯一索引按「名称 + 定义」比对——唯一性、
  NULLS NOT DISTINCT、列序、WHERE 谓词全部一致才 SKIP，因此迁移完成后的
  每次部署都不会再对 param_mappings / algorithm_device_params 做 DROP + CREATE；
- ``lock_timeout`` 固定 10s，等不到 ACCESS EXCLUSIVE 抛 55P03 且原样上抛（引导链失败）。

用法：
    python scripts/migrations/202611/add_device_id_scope.py            # 预览
    python scripts/migrations/202611/add_device_id_scope.py --apply    # 执行
    python scripts/migrations/202611/add_device_id_scope.py --rollback --apply  # 回滚
"""
import argparse
import os
import re
import sys
import time
from urllib.parse import urlparse

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

DEVICE_PARAM_TABLE = 'algorithm_device_params'
MAPPING_TABLE = 'param_mappings'
PROFILE_TABLE = 'param_profiles'

# 设备参数：旧唯一索引 vs 新两级索引（列定义见 UNIQUE_INDEX_SPECS）
DEVICE_PARAM_SPEC = {
    'table': DEVICE_PARAM_TABLE,
    'device_index': 'idx_algorithm_device_params_device_id',
    'old_unique': 'uq_algorithm_device_param_direction',
    'old_unique_cols': 'algorithm_type, param_code, direction',
    'algo_level': 'uq_algorithm_device_param_algo_level',
    'device_level': 'uq_algorithm_device_param_device_level',
}

# 参数映射：api_id 迁移留下的同名两级索引 → 收敛为三级（旧定义无 device_id 条件）
MAPPING_SPEC = {
    'table': MAPPING_TABLE,
    'device_index': 'idx_param_mappings_device_id',
    'base_cols': 'algorithm_type, source, source_param, dimension_id',
    'algo_level': 'uq_param_mapping_algo_level',
    'api_level': 'uq_param_mapping_api_level',
    'device_level': 'uq_param_mapping_device_level',
}

LEGACY_MAPPING_INDEX = {
    'old_unique': 'uq_algorithm_source_to_dimension',
    'old_unique_cols': 'algorithm_type, source, source_param, dimension_id',
}

# 唯一索引目标定义：幂等判定按「唯一 / NULLS NOT DISTINCT / 列序 / WHERE 谓词」逐项比对，
# 与 ORM（algorithm_service/.../models/algorithm_models.py）保持同一口径。
# 注意 param_mappings 的两条旧索引与新索引**同名**，不能只看索引名存在就 SKIP。
UNIQUE_INDEX_SPECS = (
    {
        'name': DEVICE_PARAM_SPEC['algo_level'],
        'table': DEVICE_PARAM_TABLE,
        'columns': ('algorithm_type', 'param_code', 'direction'),
        'where': 'deleted = false AND device_id IS NULL',
    },
    {
        'name': DEVICE_PARAM_SPEC['device_level'],
        'table': DEVICE_PARAM_TABLE,
        'columns': ('algorithm_type', 'device_id', 'param_code', 'direction'),
        'where': 'deleted = false AND device_id IS NOT NULL',
    },
    {
        'name': MAPPING_SPEC['algo_level'],
        'table': MAPPING_TABLE,
        'columns': ('algorithm_type', 'source', 'source_param', 'dimension_id'),
        'where': 'deleted = false AND api_id IS NULL AND device_id IS NULL',
    },
    {
        'name': MAPPING_SPEC['api_level'],
        'table': MAPPING_TABLE,
        'columns': ('algorithm_type', 'api_id', 'source', 'source_param',
                    'dimension_id'),
        'where': 'deleted = false AND api_id IS NOT NULL AND device_id IS NULL',
    },
    {
        'name': MAPPING_SPEC['device_level'],
        'table': MAPPING_TABLE,
        'columns': ('algorithm_type', 'device_id', 'source', 'source_param',
                    'dimension_id'),
        'where': 'deleted = false AND device_id IS NOT NULL',
    },
)


def _connect():
    parsed = urlparse(os.environ['DATABASE_URL'])
    return psycopg2.connect(
        host=parsed.hostname, port=parsed.port or 5432,
        dbname=parsed.path.lstrip('/'), user=parsed.username,
        password=parsed.password, application_name='migration_device_scope')


def _table_exists(cur, table):
    cur.execute(
        'SELECT 1 FROM information_schema.tables WHERE table_name = %s', (table,))
    return cur.fetchone() is not None


def _column_exists(cur, table, column='device_id'):
    cur.execute(
        'SELECT 1 FROM information_schema.columns '
        'WHERE table_name = %s AND column_name = %s', (table, column))
    return cur.fetchone() is not None


def _index_exists(cur, name):
    cur.execute('SELECT 1 FROM pg_indexes WHERE indexname = %s', (name,))
    return cur.fetchone() is not None


def _index_state(cur, name):
    """唯一索引现状：None（不存在）或 dict(unique/nulls_not_distinct/columns/predicate/definition)。"""
    cur.execute(
        "SELECT i.indisunique, i.indnullsnotdistinct, "
        "       pg_get_expr(i.indpred, i.indrelid), "
        "       pg_get_indexdef(i.indexrelid), "
        "       ARRAY(SELECT a.attname "
        "               FROM unnest(i.indkey) WITH ORDINALITY AS k(attnum, ord) "
        "               JOIN pg_attribute a "
        "                 ON a.attrelid = i.indrelid AND a.attnum = k.attnum "
        "              ORDER BY k.ord) "
        "  FROM pg_index i "
        "  JOIN pg_class c ON c.oid = i.indexrelid "
        "  JOIN pg_namespace n ON n.oid = c.relnamespace "
        " WHERE c.relname = %s AND n.nspname = current_schema()", (name,))
    row = cur.fetchone()
    if row is None:
        return None
    return {
        'unique': bool(row[0]),
        'nulls_not_distinct': bool(row[1]),
        'predicate': row[2],
        'definition': row[3],
        'columns': [str(col) for col in (row[4] or [])],
    }


def _normalize_sql(fragment):
    """归一化 WHERE 谓词：去括号 / 空白并转小写（PG 回显会把三元 AND 加括号）。"""
    return re.sub(r'[\s()]+', '', fragment or '').lower()


def _index_matches(state, spec):
    """索引定义与目标一致（唯一 + NULLS NOT DISTINCT + 列序 + WHERE 谓词）。"""
    return (state['unique']
            and state['nulls_not_distinct']
            and state['columns'] == list(spec['columns'])
            and _normalize_sql(state['predicate'])
            == _normalize_sql(spec['where']))


def _create_index_sql(spec):
    return (f"CREATE UNIQUE INDEX IF NOT EXISTS {spec['name']} "
            f"ON {spec['table']} ({', '.join(spec['columns'])}) "
            f"NULLS NOT DISTINCT WHERE {spec['where']}")


def _count_rows(cur, table):
    cur.execute(
        f'SELECT COUNT(*), COUNT(*) FILTER (WHERE deleted = false) FROM {table}')
    return cur.fetchone()


def _duplicates(cur, table, cols, cond):
    cur.execute(
        f'SELECT COUNT(*) FROM (SELECT 1 FROM {table} '
        f'WHERE deleted = false {cond} GROUP BY {cols} HAVING COUNT(*) > 1) dup')
    return int(cur.fetchone()[0] or 0)


def _forward_statements(cur):
    """按当前结构生成待执行 DDL（已存在的跳过）。"""
    stmts = []
    # 策略配置快照（同一批上线）：param_profiles.config_snapshot TEXT
    if not _column_exists(cur, PROFILE_TABLE, 'config_snapshot'):
        stmts.append(f'ALTER TABLE {PROFILE_TABLE} ADD COLUMN IF NOT EXISTS '
                     'config_snapshot TEXT')
    for table, idx in ((DEVICE_PARAM_TABLE, DEVICE_PARAM_SPEC['device_index']),
                       (MAPPING_TABLE, MAPPING_SPEC['device_index'])):
        if not _column_exists(cur, table):
            stmts.append(f'ALTER TABLE {table} ADD COLUMN IF NOT EXISTS '
                         'device_id INTEGER NULL')
        if not _index_exists(cur, idx):
            stmts.append(f'CREATE INDEX IF NOT EXISTS {idx} '
                         f'ON {table} (device_id) WHERE deleted = false')

    spec = DEVICE_PARAM_SPEC
    if _index_exists(cur, spec['old_unique']):
        stmts.append(f"DROP INDEX IF EXISTS {spec['old_unique']}")

    # 唯一索引按「名称 + 定义」判：已一致就 SKIP（迁移完成后再部署不再 DROP/CREATE）；
    # 存在但定义不符（旧两级的 / 缺 NULLS NOT DISTINCT 的）才重建。
    for item in UNIQUE_INDEX_SPECS:
        state = _index_state(cur, item['name'])
        if state is None:
            stmts.append(_create_index_sql(item))
        elif not _index_matches(state, item):
            print(f"[INFO] {item['name']} 定义与目标不符，重建："
                  f"{state['definition']}")
            stmts.append(f"DROP INDEX IF EXISTS {item['name']}")
            stmts.append(_create_index_sql(item))
    return stmts


def _rollback_statements(cur):
    stmts = []
    if _column_exists(cur, PROFILE_TABLE, 'config_snapshot'):
        stmts.append(f'ALTER TABLE {PROFILE_TABLE} DROP COLUMN IF EXISTS config_snapshot')
    spec = MAPPING_SPEC
    for name in (spec['device_level'], spec['algo_level'], spec['api_level']):
        if _index_exists(cur, name):
            stmts.append(f'DROP INDEX IF EXISTS {name}')
    # 恢复到 api_id 迁移后的两级定义
    stmts.append(
        f"CREATE UNIQUE INDEX IF NOT EXISTS {spec['algo_level']} "
        f"ON {spec['table']} ({spec['base_cols']}) NULLS NOT DISTINCT "
        'WHERE deleted = false AND api_id IS NULL')
    stmts.append(
        f"CREATE UNIQUE INDEX IF NOT EXISTS {spec['api_level']} "
        f"ON {spec['table']} (algorithm_type, api_id, source, source_param, dimension_id) "
        'NULLS NOT DISTINCT WHERE deleted = false AND api_id IS NOT NULL')

    spec = DEVICE_PARAM_SPEC
    for name in (spec['device_level'], spec['algo_level']):
        if _index_exists(cur, name):
            stmts.append(f'DROP INDEX IF EXISTS {name}')
    stmts.append(
        f"CREATE UNIQUE INDEX IF NOT EXISTS {spec['old_unique']} "
        f"ON {spec['table']} ({spec['old_unique_cols']}) WHERE deleted = false")

    for table, idx in ((DEVICE_PARAM_TABLE, DEVICE_PARAM_SPEC['device_index']),
                       (MAPPING_TABLE, MAPPING_SPEC['device_index'])):
        if _index_exists(cur, idx):
            stmts.append(f'DROP INDEX IF EXISTS {idx}')
        if _column_exists(cur, table):
            cur.execute(f'SELECT COUNT(*) FROM {table} WHERE device_id IS NOT NULL')
            device_rows = int(cur.fetchone()[0] or 0)
            if device_rows:
                print(f'[WARN] {table} 仍有 {device_rows} 行设备级配置，'
                      '回滚会随 DROP COLUMN 丢失 device_id（行保留为算法级）')
            stmts.append(f'ALTER TABLE {table} DROP COLUMN IF EXISTS device_id')
    return stmts


def _verify(cur):
    for table in (DEVICE_PARAM_TABLE, MAPPING_TABLE):
        cur.execute(
            'SELECT data_type, is_nullable FROM information_schema.columns '
            'WHERE table_name = %s AND column_name = %s', (table, 'device_id'))
        row = cur.fetchone()
        print(f'[VERIFY] {table}.device_id: '
              f'{row[0] if row else "MISSING"} '
              f'{"NULL" if row and row[1] == "YES" else ""}'.rstrip())
    for item in UNIQUE_INDEX_SPECS:
        state = _index_state(cur, item['name'])
        if state is None:
            print(f"[VERIFY] {item['name']}: 不存在")
        else:
            mark = '一致' if _index_matches(state, item) else '与目标不符'
            print(f"[VERIFY] {item['name']}: {mark} :: {state['definition']}")


def _run(dry_run, statements, label):
    conn = _connect()
    try:
        conn.autocommit = False
        cur = conn.cursor()
        cur.execute(f"SET lock_timeout = '{LOCK_TIMEOUT}'")
        missing = [t for t in (DEVICE_PARAM_TABLE, MAPPING_TABLE)
                   if not _table_exists(cur, t)]
        if missing:
            print(f'[SKIP] 表不存在：{", ".join(missing)}'
                  '（空库请先 create_all_tables.py）')
            conn.rollback()
            return

        statements = statements(cur)
        if not statements:
            print(f'[SKIP] 结构已是{label}形态，无需执行')
            _verify(cur)
            conn.rollback()
            return
        for sql in statements:
            print(f"[{'DRY' if dry_run else 'APPLY'}] {sql}")
        if dry_run:
            print('[DRY] 未执行；加 --apply 生效')
            conn.rollback()
            return

        started = time.time()
        try:
            for sql in statements:
                cur.execute(sql)
            conn.commit()
        except psycopg2.Error as exc:
            conn.rollback()
            print(f'[FAIL] {"回滚" if label == "回滚" else "迁移"}失败'
                  f'（pgcode={getattr(exc, "pgcode", None)}）：{exc}', flush=True)
            raise
        _verify(cur)
        print(f'[APPLY] {label}完成，耗时 {time.time() - started:.2f}s')
    finally:
        conn.close()


def _precheck():
    """只读前置检查：存量行 + 新索引口径下的重复组。"""
    conn = _connect()
    try:
        cur = conn.cursor()
        for table in (DEVICE_PARAM_TABLE, MAPPING_TABLE):
            if not _table_exists(cur, table):
                continue
            total, alive = _count_rows(cur, table)
            print(f'[INFO] {table}: 总 {total} 行 / 未删除 {alive} 行')
        checks = (
            (DEVICE_PARAM_TABLE, 'algorithm_type, param_code, direction',
             'AND device_id IS NULL'),
            (MAPPING_TABLE, 'algorithm_type, source, source_param, dimension_id',
             'AND api_id IS NULL AND device_id IS NULL'),
        )
        failed = False
        for table, cols, cond in checks:
            if not _column_exists(cur, table):
                continue
            dup = _duplicates(cur, table, cols, cond)
            print(f'[INFO] {table} 算法级重复组：{dup}')
            if dup:
                print(f'[FAIL] {table} 存在 {dup} 组算法级重复行，'
                      '建唯一索引会失败；请先人工清理')
                failed = True
        if failed:
            sys.exit(2)
    finally:
        conn.close()


def main():
    ap = argparse.ArgumentParser(
        description='algorithm_device_params / param_mappings 加 device_id 作用域')
    ap.add_argument('--apply', action='store_true', help='执行（默认 dry-run 预览）')
    ap.add_argument('--rollback', action='store_true',
                    help='回滚到迁移前结构（默认 dry-run，配 --apply 执行）')
    args = ap.parse_args()
    _precheck()
    if args.rollback:
        _run(not args.apply, _rollback_statements, '回滚')
    else:
        _run(not args.apply, _forward_statements, '迁移')


if __name__ == '__main__':
    main()
