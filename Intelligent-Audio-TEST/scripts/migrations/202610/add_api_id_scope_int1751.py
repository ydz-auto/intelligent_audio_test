# -*- coding: utf-8 -*-
"""迁移脚本：algorithm_api_params / param_mappings 加 api_id 作用域 + 唯一索引拆分（INT-1751 / INT-1756）

背景（父卡 INT-1751 第二、八节定稿，执行卡 INT-1756）：
- 同一 ``algorithm_type`` 下所有厂商共享一套参数与映射，第二家接入必然覆盖第一家。
  ``AlgorithmApiParam`` / ``ParamMapping`` 补 ``api_id``（NULL = 算法类型级默认，
  指向 api_test_service 的 ``apis.id``；**不建外键** —— 跨服务 DB 约束违反架构红线，
  存在性与算法类型一致性由网关写路径校验）；
- 唯一索引必须按「算法级 / API 级」拆成两条并统一 ``NULLS NOT DISTINCT``：
  并进一条时算法级行（api_id NULL）因 PG 默认 NULLS DISTINCT 不参与唯一约束；
  ``param_mappings.dimension_id`` 本身可空，不加 NULLS NOT DISTINCT 时
  同一 ``(algorithm_type, source, source_param, NULL)`` 的重复插入不会被拒。

DDL（与父卡第八节草案一致，模型见
``algorithm_service/infrastructure/persistence/models/algorithm_models.py``）：
    SET lock_timeout = '10s'
    ALTER TABLE algorithm_api_params ADD COLUMN IF NOT EXISTS api_id INTEGER NULL
    ALTER TABLE param_mappings      ADD COLUMN IF NOT EXISTS api_id INTEGER NULL
    CREATE INDEX idx_algorithm_api_params_api_id ON algorithm_api_params (api_id) WHERE deleted = false
    CREATE INDEX idx_param_mappings_api_id      ON param_mappings (api_id)      WHERE deleted = false
    DROP INDEX uq_algorithm_api_param_direction / uq_algorithm_source_to_dimension
    CREATE UNIQUE INDEX uq_algorithm_api_param_algo_level ... NULLS NOT DISTINCT WHERE deleted = false AND api_id IS NULL
    CREATE UNIQUE INDEX uq_algorithm_api_param_api_level  ... NULLS NOT DISTINCT WHERE deleted = false AND api_id IS NOT NULL
    CREATE UNIQUE INDEX uq_param_mapping_algo_level       ... NULLS NOT DISTINCT WHERE deleted = false AND api_id IS NULL
    CREATE UNIQUE INDEX uq_param_mapping_api_level        ... NULLS NOT DISTINCT WHERE deleted = false AND api_id IS NOT NULL

执行语义：
- 默认 dry-run：只打印待执行 DDL 与前置检查（存量行数、重复组、索引现状），不改库；
- ``--apply``：单事务执行（DDL 在 PostgreSQL 可事务化，失败整体回滚）；
- ``--rollback``：回滚到迁移前结构（DROP 四条新索引 → 按旧定义重建两条 ``uq_*``
  （无 NULLS NOT DISTINCT）→ DROP COLUMN api_id）；
- 幂等：列/索引存在即 SKIP，重复执行不报错；
- ``lock_timeout`` 固定 10s，等不到 ACCESS EXCLUSIVE 抛 ``55P03``（lock_not_available）
  并原样上抛，**不吞**——引导链要让部署失败而不是留下半截结构。

用法：
    python scripts/migrations/202610/add_api_id_scope_int1751.py            # 预览
    python scripts/migrations/202610/add_api_id_scope_int1751.py --apply    # 执行
    python scripts/migrations/202610/add_api_id_scope_int1751.py --rollback # 回滚

回滚步骤（与本脚本 --rollback 等价，供 DBA 手工复核）：
    1) DROP INDEX IF EXISTS uq_algorithm_api_param_api_level, uq_algorithm_api_param_algo_level,
                                uq_param_mapping_api_level,  uq_param_mapping_algo_level;
    2) CREATE UNIQUE INDEX uq_algorithm_api_param_direction
         ON algorithm_api_params (algorithm_type, param_code, direction) WHERE deleted = false;
       CREATE UNIQUE INDEX uq_algorithm_source_to_dimension
         ON param_mappings (algorithm_type, source, source_param, dimension_id) WHERE deleted = false;
    3) DROP INDEX IF EXISTS idx_algorithm_api_params_api_id, idx_param_mappings_api_id;
    4) ALTER TABLE algorithm_api_params DROP COLUMN IF EXISTS api_id;
       ALTER TABLE param_mappings      DROP COLUMN IF EXISTS api_id;
    注意：回滚后 API 级行（api_id 非 NULL）信息会随列丢失，执行前须确认没有
    API 实例级配置，或先导出备份。

与其它脚本的关系：
    ``scripts/migrations/202608/fix_partial_unique_indexes.py`` 已排除在
    docker/db_bootstrap_entrypoint.py 的引导链外；但若被手工执行，它会按旧口径
    （无 api_id）重建这两条唯一索引，在有 API 级行时必然冲突失败。手工执行前
    请先跑本脚本、或跳过上述两张表。
"""
import argparse
import os
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

# 两张表的结构描述：表名 → 旧唯一索引 / 新索引名与定义
SPECS = (
    {
        'table': 'algorithm_api_params',
        'api_id_index': 'idx_algorithm_api_params_api_id',
        'old_unique': 'uq_algorithm_api_param_direction',
        'old_unique_cols': 'algorithm_type, param_code, direction',
        'algo_level': 'uq_algorithm_api_param_algo_level',
        'api_level': 'uq_algorithm_api_param_api_level',
        'algo_level_cols': 'algorithm_type, param_code, direction',
        'api_level_cols': 'algorithm_type, api_id, param_code, direction',
    },
    {
        'table': 'param_mappings',
        'api_id_index': 'idx_param_mappings_api_id',
        'old_unique': 'uq_algorithm_source_to_dimension',
        'old_unique_cols': 'algorithm_type, source, source_param, dimension_id',
        'algo_level': 'uq_param_mapping_algo_level',
        'api_level': 'uq_param_mapping_api_level',
        'algo_level_cols': 'algorithm_type, source, source_param, dimension_id',
        'api_level_cols': 'algorithm_type, api_id, source, source_param, dimension_id',
    },
)


def _connect():
    parsed = urlparse(os.environ['DATABASE_URL'])
    return psycopg2.connect(
        host=parsed.hostname, port=parsed.port or 5432,
        dbname=parsed.path.lstrip('/'), user=parsed.username,
        password=parsed.password)


def add_column_sql(spec):
    return (f"ALTER TABLE {spec['table']} ADD COLUMN IF NOT EXISTS "
            f"api_id INTEGER NULL")


def api_id_index_sql(spec):
    return (f"CREATE INDEX IF NOT EXISTS {spec['api_id_index']} "
            f"ON {spec['table']} (api_id) WHERE deleted = false")


def drop_old_unique_sql(spec):
    return f"DROP INDEX IF EXISTS {spec['old_unique']}"


def create_level_index_sql(spec, level):
    if level == 'algo':
        name, cols = spec['algo_level'], spec['algo_level_cols']
        cond = 'AND api_id IS NULL'
    else:
        name, cols = spec['api_level'], spec['api_level_cols']
        cond = 'AND api_id IS NOT NULL'
    return (f'CREATE UNIQUE INDEX IF NOT EXISTS {name} ON {spec["table"]} '
            f'({cols}) NULLS NOT DISTINCT WHERE deleted = false {cond}')


def rollback_drop_index_sqls(spec):
    return [f'DROP INDEX IF EXISTS {spec["api_level"]}',
            f'DROP INDEX IF EXISTS {spec["algo_level"]}',
            f'DROP INDEX IF EXISTS {spec["api_id_index"]}']


def rollback_old_unique_sql(spec):
    return (f'CREATE UNIQUE INDEX IF NOT EXISTS {spec["old_unique"]} '
            f'ON {spec["table"]} ({spec["old_unique_cols"]}) '
            f'WHERE deleted = false')


def rollback_drop_column_sql(spec):
    return (f"ALTER TABLE {spec['table']} DROP COLUMN IF EXISTS api_id")


# ---- 前置检查（只读） ----

def _table_exists(cur, table):
    cur.execute(
        'SELECT 1 FROM information_schema.tables WHERE table_name = %s',
        (table,))
    return cur.fetchone() is not None


def _column_exists(cur, table):
    cur.execute(
        'SELECT 1 FROM information_schema.columns '
        'WHERE table_name = %s AND column_name = %s', (table, 'api_id'))
    return cur.fetchone() is not None


def _index_exists(cur, index_name):
    cur.execute(
        'SELECT 1 FROM pg_indexes WHERE indexname = %s', (index_name,))
    return cur.fetchone() is not None


def _count_rows(cur, spec):
    """存量对照：总行数 / 未删除行数 / api_id NULL 与 NOT NULL 行数。"""
    if _column_exists(cur, spec['table']):
        cur.execute(
            f"SELECT COUNT(*), "
            f"COUNT(*) FILTER (WHERE deleted = false), "
            f"COUNT(*) FILTER (WHERE deleted = false AND api_id IS NULL), "
            f"COUNT(*) FILTER (WHERE deleted = false AND api_id IS NOT NULL) "
            f"FROM {spec['table']}")
        return cur.fetchone()
    cur.execute(
        f"SELECT COUNT(*), COUNT(*) FILTER (WHERE deleted = false), NULL, NULL "
        f"FROM {spec['table']}")
    return cur.fetchone()


def _duplicate_groups(cur, spec, level):
    """按新唯一索引口径统计重复组（NULLS NOT DISTINCT 语义下 GROUP BY 即等价）。"""
    if level == 'algo':
        cols = spec['algo_level_cols']
        cond = 'AND api_id IS NULL'
    else:
        cols = spec['api_level_cols']
        cond = 'AND api_id IS NOT NULL'
    if not _column_exists(cur, spec['table']):
        return 0
    cur.execute(
        f'SELECT COUNT(*) FROM (SELECT 1 FROM {spec["table"]} '
        f'WHERE deleted = false {cond} GROUP BY {cols} HAVING COUNT(*) > 1) dup')
    return int(cur.fetchone()[0] or 0)


def _verify(cur):
    for spec in SPECS:
        cur.execute(
            'SELECT data_type, is_nullable FROM information_schema.columns '
            'WHERE table_name = %s AND column_name = %s',
            (spec['table'], 'api_id'))
        row = cur.fetchone()
        print(f"[VERIFY] {spec['table']}.api_id: "
              f"{row[0] if row else 'MISSING'} "
              f"{'NULL' if row and row[1] == 'YES' else ''}".rstrip())
        for name in (spec['api_id_index'], spec['algo_level'],
                     spec['api_level'], spec['old_unique']):
            cur.execute('SELECT indexdef FROM pg_indexes WHERE indexname = %s',
                        (name,))
            r = cur.fetchone()
            print(f'[VERIFY] {name}: '
                  f'{r[0] if r else "不存在（回滚后为预期）"}')


def migrate(dry_run=True):
    started = time.time()
    conn = _connect()
    try:
        conn.autocommit = False
        cur = conn.cursor()
        # 锁预算：等不到 ACCESS EXCLUSIVE 抛 55P03，不做吞咽
        cur.execute(f"SET lock_timeout = '{LOCK_TIMEOUT}'")

        missing = [s['table'] for s in SPECS if not _table_exists(cur, s['table'])]
        if missing:
            print(f'[SKIP] 表不存在：{", ".join(missing)}'
                  '（空库请先 create_all_tables.py）')
            conn.rollback()
            return

        print(f'[INFO] lock_timeout={LOCK_TIMEOUT}')
        for spec in SPECS:
            total, alive, algo_rows, api_rows = _count_rows(cur, spec)
            print(f"[INFO] {spec['table']}: 总 {total} 行 / 未删除 {alive} 行 / "
                  f"api_id IS NULL {algo_rows} / api_id IS NOT NULL {api_rows}")
            for level in ('algo', 'api'):
                dup = _duplicate_groups(cur, spec, level)
                print(f"[INFO] {spec['table']} {level}-level 重复组：{dup}")
                if dup:
                    print(f'[FAIL] {spec["table"]} 存在 {dup} 组 {level}-level '
                          '重复行，建唯一索引会失败；请先人工清理')
                    conn.rollback()
                    sys.exit(2)

        statements = []
        for spec in SPECS:
            if not _column_exists(cur, spec['table']):
                statements.append(add_column_sql(spec))
            if not _index_exists(cur, spec['api_id_index']):
                statements.append(api_id_index_sql(spec))
        for spec in SPECS:
            if _index_exists(cur, spec['old_unique']):
                statements.append(drop_old_unique_sql(spec))
            for level in ('algo', 'api'):
                name = spec['algo_level'] if level == 'algo' else spec['api_level']
                if not _index_exists(cur, name):
                    statements.append(create_level_index_sql(spec, level))

        if not statements:
            print('[SKIP] 结构已是迁移后形态（列与索引均存在），无需执行')
            _verify(cur)
            conn.rollback()
            return

        for sql in statements:
            print(f"[{'DRY' if dry_run else 'APPLY'}] {sql}")
        if dry_run:
            print('[DRY] 未执行；加 --apply 生效')
            conn.rollback()
            return

        try:
            for sql in statements:
                cur.execute(sql)
            conn.commit()
        except psycopg2.Error as exc:
            conn.rollback()
            pgcode = getattr(exc, 'pgcode', None)
            if pgcode == '55P03':
                print(f'[FAIL] 等锁超时（55P03, lock_not_available）：{exc}',
                      flush=True)
            else:
                print(f'[FAIL] 迁移失败（pgcode={pgcode}）：{exc}', flush=True)
            # 55P03 等错误必须原样上抛，引导链不能“失败当成功”
            raise

        _verify(cur)
        print(f'[APPLY] 完成，耗时 {time.time() - started:.2f}s')
    finally:
        conn.close()


def rollback(dry_run=True):
    started = time.time()
    conn = _connect()
    try:
        conn.autocommit = False
        cur = conn.cursor()
        cur.execute(f"SET lock_timeout = '{LOCK_TIMEOUT}'")
        missing = [s['table'] for s in SPECS
                   if not _table_exists(cur, s['table'])]
        if missing:
            print(f'[SKIP] 表不存在：{", ".join(missing)}')
            conn.rollback()
            return

        statements = []
        for spec in SPECS:
            if _index_exists(cur, spec['api_level']) or \
                    _index_exists(cur, spec['algo_level']) or \
                    _index_exists(cur, spec['api_id_index']):
                statements.extend(rollback_drop_index_sqls(spec))
            if not _index_exists(cur, spec['old_unique']):
                statements.append(rollback_old_unique_sql(spec))
            if _column_exists(cur, spec['table']):
                cur.execute(
                    f"SELECT COUNT(*) FROM {spec['table']} "
                    f'WHERE api_id IS NOT NULL')
                api_rows = int(cur.fetchone()[0] or 0)
                if api_rows:
                    print(f"[WARN] {spec['table']} 仍有 {api_rows} 行 API 实例级配置，"
                          '回滚会随 DROP COLUMN 丢失其 api_id（行本身保留为算法级）')
                statements.append(rollback_drop_column_sql(spec))

        if not statements:
            print('[SKIP] 结构已是迁移前形态，无需回滚')
            _verify(cur)
            conn.rollback()
            return
        for sql in statements:
            print(f"[{'DRY' if dry_run else 'APPLY'}] {sql}")
        if dry_run:
            print('[DRY] 未执行；加 --rollback --apply 生效')
            conn.rollback()
            return
        try:
            for sql in statements:
                cur.execute(sql)
            conn.commit()
        except psycopg2.Error as exc:
            conn.rollback()
            print(f'[FAIL] 回滚失败（pgcode={getattr(exc, "pgcode", None)}）：{exc}',
                  flush=True)
            raise
        _verify(cur)
        print(f'[APPLY] 回滚完成，耗时 {time.time() - started:.2f}s')
    finally:
        conn.close()


def main():
    ap = argparse.ArgumentParser(
        description='algorithm_api_params / param_mappings 加 api_id 作用域'
                    '（INT-1751 / INT-1756）')
    ap.add_argument('--apply', action='store_true', help='执行（默认 dry-run 预览）')
    ap.add_argument('--rollback', action='store_true',
                    help='回滚到迁移前结构（默认 dry-run，配 --apply 执行）')
    args = ap.parse_args()
    if args.rollback:
        rollback(dry_run=not args.apply)
    else:
        migrate(dry_run=not args.apply)


if __name__ == '__main__':
    main()
