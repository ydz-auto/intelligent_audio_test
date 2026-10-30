# -*- coding: utf-8 -*-
"""迁移脚本：新增参数策略三表 + API 绑定表，并把算法级 API 参数/映射收敛为策略

背景（本轮重构）：
- API 参数与映射不再挂在「算法类型级默认（api_id IS NULL）」，也不再由算法编辑
  弹窗维护；
- 改为显式命名策略 ``param_profiles``（``scope='api'``），API 实例经
  ``api_param_bindings`` 引用（绑定归 algorithm_service，运行时不必跨服务读 apis）；
  实例差异仍写在 ``algorithm_api_params`` / ``param_mappings`` 的 api_id 行（实例覆盖）。
- 物理侧（scope='device'）本轮不接线，表结构预留。

执行步骤（单事务，``--apply`` 时）：
    1) CREATE TABLE IF NOT EXISTS param_profiles / param_profile_params /
       param_profile_mappings / api_param_bindings（含唯一索引）；
    2) 按 algorithm_type 生成/复用默认策略（scope='api', name='default'）；
    3) 复制 algorithm_api_params(api_id IS NULL) → param_profile_params；
       复制 param_mappings(api_id IS NULL AND source='api') → param_profile_mappings；
    4) 为同 algorithm_type 的 API 实例回填 api_param_bindings；
    5) 软删算法级默认行（api_id IS NULL），实例级行（api_id 非空）保持为覆盖。

幂等：建表/建索引均有 IF NOT EXISTS；复制按唯一键 ON CONFLICT 跳过；
默认行软删后重复执行不会再复制出重复行。本脚本不新增任何列（绑定只落
``api_param_bindings``，不在 ``apis`` 上冗余 ``param_profile_id``）。

部署顺序（重要）：本脚本把默认层数据搬走后，读侧必须已经按「策略 + 实例覆盖」
解析，否则该算法类型下没有实例引用时会读成空。因此本步必须与读侧改造同版本上线，
且排在各服务代码更新之后（引导链里放在 migrate 步之后）。

用法：
    python scripts/migrations/202610/add_param_profiles_scope.py            # 预览
    python scripts/migrations/202610/add_param_profiles_scope.py --apply    # 执行
    python scripts/migrations/202610/add_param_profiles_scope.py --rollback # 回滚

回滚：按依赖倒序删除 ``api_param_bindings`` / ``param_profile_mappings`` /
``param_profile_params`` / ``param_profiles`` 四张表。**不恢复**被本脚本软删的
算法级默认行（``algorithm_api_params`` / ``param_mappings`` 的 ``api_id IS NULL``
行仅置 ``deleted=true``，数据仍在库中），也不回退 ``apis`` 的任何列（本脚本从未
新增列）。如需恢复默认层，须先放行读侧旧版本，再手工执行::

    UPDATE algorithm_api_params SET deleted = false
     WHERE algorithm_type = %s AND api_id IS NULL;
    UPDATE param_mappings SET deleted = false
     WHERE algorithm_type = %s AND api_id IS NULL AND source = 'api';

无法区分「本脚本软删」与「历史软删」，故该恢复需 DBA 按 ``updated_at >= 执行时间``
复核后逐类型执行。
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
    CREATE TABLE IF NOT EXISTS param_profiles (
        id SERIAL PRIMARY KEY,
        scope VARCHAR(10) NOT NULL DEFAULT 'api',
        algorithm_type VARCHAR(50) NOT NULL,
        name VARCHAR(100) NOT NULL,
        description TEXT,
        status VARCHAR(20) NOT NULL DEFAULT 'online',
        cloned_from INTEGER,
        deleted BOOLEAN DEFAULT false,
        created_at TIMESTAMP DEFAULT now(),
        updated_at TIMESTAMP DEFAULT now()
    )
    """,
    """
    CREATE UNIQUE INDEX IF NOT EXISTS uq_param_profile_scope_type_name
        ON param_profiles (scope, algorithm_type, name) WHERE deleted = false
    """,
    """
    CREATE TABLE IF NOT EXISTS param_profile_params (
        id SERIAL PRIMARY KEY,
        profile_id INTEGER NOT NULL,
        param_code VARCHAR(50) NOT NULL,
        param_name VARCHAR(100),
        label VARCHAR(100),
        param_type VARCHAR(30) NOT NULL,
        direction VARCHAR(10) DEFAULT 'input',
        required BOOLEAN DEFAULT false,
        default_value TEXT,
        validation_rules TEXT,
        help_text TEXT,
        ui_order INTEGER DEFAULT 0,
        hidden BOOLEAN DEFAULT false,
        field_path VARCHAR(255),
        deleted BOOLEAN DEFAULT false,
        created_at TIMESTAMP DEFAULT now(),
        updated_at TIMESTAMP DEFAULT now()
    )
    """,
    """
    CREATE UNIQUE INDEX IF NOT EXISTS uq_param_profile_param_key
        ON param_profile_params (profile_id, param_code, direction) WHERE deleted = false
    """,
    """
    CREATE TABLE IF NOT EXISTS param_profile_mappings (
        id SERIAL PRIMARY KEY,
        profile_id INTEGER NOT NULL,
        source VARCHAR(20) NOT NULL DEFAULT 'api',
        source_param VARCHAR(50) NOT NULL,
        source_direction VARCHAR(10) DEFAULT 'output',
        dimension_id INTEGER,
        target_param VARCHAR(50) NOT NULL,
        transform_type VARCHAR(20) DEFAULT 'none',
        deleted BOOLEAN DEFAULT false,
        created_at TIMESTAMP DEFAULT now(),
        updated_at TIMESTAMP DEFAULT now()
    )
    """,
    """
    CREATE UNIQUE INDEX IF NOT EXISTS uq_param_profile_mapping_key
        ON param_profile_mappings (profile_id, source, source_param, dimension_id)
        WHERE deleted = false
    """,
    # 绑定点归 algorithm_service：运行时按 api_id 解析策略不再跨服务读 apis
    """
    CREATE TABLE IF NOT EXISTS api_param_bindings (
        id SERIAL PRIMARY KEY,
        api_id INTEGER NOT NULL,
        profile_id INTEGER NOT NULL,
        deleted BOOLEAN DEFAULT false,
        created_at TIMESTAMP DEFAULT now(),
        updated_at TIMESTAMP DEFAULT now()
    )
    """,
    """
    CREATE UNIQUE INDEX IF NOT EXISTS uq_api_param_binding_api
        ON api_param_bindings (api_id) WHERE deleted = false
    """,
)

DDL_ROLLBACK = (
    "DROP TABLE IF EXISTS api_param_bindings",
    "DROP TABLE IF EXISTS param_profile_mappings",
    "DROP TABLE IF EXISTS param_profile_params",
    "DROP TABLE IF EXISTS param_profiles",
)

# 参与迁移的算法类型：有算法级默认行或有 API 实例
_COLLECT_TYPES_SQL = """
    SELECT DISTINCT t FROM (
        SELECT algorithm_type AS t FROM algorithm_api_params
         WHERE deleted = false AND api_id IS NULL
        UNION
        SELECT algorithm_type AS t FROM param_mappings
         WHERE deleted = false AND api_id IS NULL AND source = 'api'
        UNION
        SELECT algorithm_type AS t FROM apis
         WHERE algorithm_type IS NOT NULL AND algorithm_type <> ''
    ) s ORDER BY t
"""

_UPSERT_PROFILE_SQL = """
    INSERT INTO param_profiles (scope, algorithm_type, name, description, status)
    VALUES ('api', %s, 'default', '由算法级默认参数迁移生成', 'online')
    ON CONFLICT (scope, algorithm_type, name) WHERE deleted = false DO NOTHING
    RETURNING id
"""

_GET_PROFILE_ID_SQL = """
    SELECT id FROM param_profiles
     WHERE scope = 'api' AND algorithm_type = %s AND name = 'default' AND deleted = false
"""

_COPY_PARAMS_SQL = """
    INSERT INTO param_profile_params (
        profile_id, param_code, param_name, label, param_type, direction,
        required, default_value, validation_rules, help_text, ui_order, hidden, field_path)
    SELECT %s, param_code, param_name, label, param_type, direction,
           required, default_value, validation_rules, help_text, ui_order, hidden, field_path
      FROM algorithm_api_params
     WHERE algorithm_type = %s AND api_id IS NULL AND deleted = false
    ON CONFLICT (profile_id, param_code, direction) WHERE deleted = false DO NOTHING
"""

_COPY_MAPPINGS_SQL = """
    INSERT INTO param_profile_mappings (
        profile_id, source, source_param, source_direction, dimension_id,
        target_param, transform_type)
    SELECT %s, source, source_param, source_direction, dimension_id,
           target_param, transform_type
      FROM param_mappings
     WHERE algorithm_type = %s AND api_id IS NULL AND deleted = false AND source = 'api'
    ON CONFLICT (profile_id, source, source_param, dimension_id) WHERE deleted = false DO NOTHING
"""

_BACKFILL_APIS_SQL = """
    INSERT INTO api_param_bindings (api_id, profile_id)
    SELECT a.id, %s FROM apis a
     WHERE a.algorithm_type = %s
       AND NOT EXISTS (
           SELECT 1 FROM api_param_bindings b
            WHERE b.api_id = a.id AND b.deleted = false)
    ON CONFLICT (api_id) WHERE deleted = false DO NOTHING
"""

_SOFT_DELETE_DEFAULTS_PARAMS_SQL = """
    UPDATE algorithm_api_params SET deleted = true
     WHERE algorithm_type = %s AND api_id IS NULL AND deleted = false
"""

_SOFT_DELETE_DEFAULTS_MAPPINGS_SQL = """
    UPDATE param_mappings SET deleted = true
     WHERE algorithm_type = %s AND api_id IS NULL AND deleted = false AND source = 'api'
"""

_COUNT_SQL = {
    'algorithm_api_params(NULL)': """
        SELECT count(*) FROM algorithm_api_params WHERE deleted = false AND api_id IS NULL""",
    'param_mappings(NULL, api)': """
        SELECT count(*) FROM param_mappings
         WHERE deleted = false AND api_id IS NULL AND source = 'api'""",
    'api_param_bindings': """
        SELECT count(*) FROM api_param_bindings WHERE deleted = false""",
}


def _connect():
    return psycopg2.connect(os.environ['DATABASE_URL'])


def _apis_exists(cur) -> bool:
    """``apis`` 归 api_test_service；同库部署时才做列与回填，否则跳过。"""
    cur.execute("SELECT to_regclass('public.apis') IS NOT NULL")
    return bool(cur.fetchone()[0])


def _print_counts(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass('public.param_profiles') IS NOT NULL")
        has_table = cur.fetchone()[0]
        print(f"[state] param_profiles={'存在' if has_table else '缺失'}")
        for label, sql in _COUNT_SQL.items():
            try:
                cur.execute(sql)
                print(f"[state] {label}: {cur.fetchone()[0]}")
            except Exception as exc:  # 列/表缺失时只提示，不阻断预览
                conn.rollback()
                print(f"[state] {label}: 跳过（{exc.__class__.__name__}）")


def apply(conn):
    with conn.cursor() as cur:
        cur.execute(f"SET lock_timeout = '{LOCK_TIMEOUT}'")
        apis_exists = _apis_exists(cur)
        for ddl in DDL_FORWARD:
            cur.execute(ddl)
        print(f"[ok] 策略三表 + api_param_bindings 就绪（{len(DDL_FORWARD)} 条 DDL；"
              f"apis={'同库，可回填绑定' if apis_exists else '不同库，跳过回填'}）")

        cur.execute(_COLLECT_TYPES_SQL)
        types = [row[0] for row in cur.fetchall()]
        print(f"[info] 待迁移算法类型 {len(types)} 个: {types}")

        for algorithm_type in types:
            cur.execute(_UPSERT_PROFILE_SQL, (algorithm_type,))
            row = cur.fetchone()
            if row is None:
                cur.execute(_GET_PROFILE_ID_SQL, (algorithm_type,))
                row = cur.fetchone()
            profile_id = row[0] if row else None
            if profile_id is None:
                raise RuntimeError(f'策略创建失败: {algorithm_type}')

            cur.execute(_COPY_PARAMS_SQL, (profile_id, algorithm_type))
            copied_params = cur.rowcount
            cur.execute(_COPY_MAPPINGS_SQL, (profile_id, algorithm_type))
            copied_mappings = cur.rowcount
            bound_apis = 0
            if apis_exists:
                cur.execute(_BACKFILL_APIS_SQL, (profile_id, algorithm_type))
                bound_apis = cur.rowcount

            cur.execute(_SOFT_DELETE_DEFAULTS_PARAMS_SQL, (algorithm_type,))
            dropped_params = cur.rowcount
            cur.execute(_SOFT_DELETE_DEFAULTS_MAPPINGS_SQL, (algorithm_type,))
            dropped_mappings = cur.rowcount

            print(f"[ok] {algorithm_type}: profile={profile_id} "
                  f"params+{copied_params} mappings+{copied_mappings} "
                  f"apis绑定={bound_apis} 默认行软删 params={dropped_params} "
                  f"mappings={dropped_mappings}")
    conn.commit()


def rollback(conn):
    with conn.cursor() as cur:
        cur.execute(f"SET lock_timeout = '{LOCK_TIMEOUT}'")
        for ddl in DDL_ROLLBACK:
            cur.execute(ddl)
        print(f"[ok] 已回滚（{len(DDL_ROLLBACK)} 条 DDL）")
        print("[warn] 算法级默认行已被软删，回滚不会自动复活；"
              "如需恢复请从 param_profile_params / param_profile_mappings 反向导出")
    conn.commit()


def main():
    parser = argparse.ArgumentParser(description='参数策略迁移（dry-run 默认）')
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
