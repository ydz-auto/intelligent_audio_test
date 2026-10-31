# -*- coding: utf-8 -*-
"""迁移脚本：算法级设备参数下沉为 scope=device 参数策略（设备侧）

背景：
    ``202610/add_param_profiles_scope.py`` 只完成了 API 侧下沉（scope=api：
    ``algorithm_api_params`` / ``param_mappings(source='api')`` → 策略），其首行
    明确写着「物理侧（scope='device'）本轮不接线，表结构预留」。
    ``202611/add_device_param_bindings.py`` 补上 ``device_param_bindings`` 后，
    设备侧三层解析（设备覆盖 > 设备绑定策略 > 算法级默认）已接线，但库里仍
    没有 scope=device 的策略，导致：

      - 设备参数页按 ``scope=device`` 拉策略恒为 0 条；
      - 设备参数映射（``param_profile_mappings``）恒为 0 条；
      - 设备无法绑定策略，只能吃算法类型级默认行。

本脚本按 ``algorithm_definitions``（未删除）里的算法类型，逐个完成设备侧下沉：

    1. 建 ``param_profiles(scope='device', algorithm_type, name='default')``；
    2. 复制算法级设备参数 ``algorithm_device_params``（device_id IS NULL）→
       ``param_profile_params``；
    3. 复制设备参数映射 ``param_mappings(source='device')``（api_id/device_id
       均为 NULL）→ ``param_profile_mappings``；
    4. 把 ``supported_algorithms`` 含该算法类型的设备绑定到该策略
       （``device_param_bindings``）。

为什么不软删算法级行：
    与 API 侧不同，设备参数解析链路的**兜底层就是算法级行**（未绑定策略的
    设备仍需它）；下沉后保留原行，解析结果不变（策略内容 = 原行副本）。
    API 侧当年软删是因为不传 api_id 的读路径已废弃，设备侧没有这条前提。

幂等性：
    策略按 ``(scope, algorithm_type, name)`` 复用；参数/映射按唯一键
    ``ON CONFLICT DO NOTHING``；设备绑定按 ``device_id`` 唯一索引去重。
    重复执行命中 0 行。

用法：
    python scripts/migrations/202611/migrate_device_params_to_profiles.py            # 预览
    python scripts/migrations/202611/migrate_device_params_to_profiles.py --apply    # 执行

退出码：0 完成/无需变更；1 前置缺失或执行失败。
"""
import argparse
import os
import sys

import psycopg2

if not os.environ.get('DATABASE_URL'):
    os.environ['DATABASE_URL'] = os.environ.get(
        'DATABASE_URI',
        'postgresql://intelligent_audio_test:intelligent_audio_test666'
        '@localhost:5432/intelligent_audio_test')

LOCK_TIMEOUT = '10s'

PROFILE_SCOPE_DEVICE = 'device'
PROFILE_NAME_DEFAULT = 'default'
PROFILE_STATUS_ONLINE = 'online'
PROFILE_DESCRIPTION = '由算法级设备参数迁移生成'

REQUIRED_COLUMNS = (
    'algorithm_definitions.type',
    'algorithm_device_params.device_id',
    'param_profiles.scope',
    'param_profile_params.profile_id',
    'param_profile_mappings.profile_id',
    'device_param_bindings.device_id',
    'devices.supported_algorithms',
)

# 只处理正式登记的算法类型（排除 int2213_perf_* 这类用例残留）
_TYPES_SQL = """
    SELECT DISTINCT d.type
      FROM algorithm_definitions d
     WHERE d.deleted = false
       AND (
            EXISTS (SELECT 1 FROM algorithm_device_params p
                     WHERE p.algorithm_type = d.type
                       AND p.deleted IS NOT TRUE AND p.device_id IS NULL)
         OR EXISTS (SELECT 1 FROM param_mappings m
                     WHERE m.algorithm_type = d.type
                       AND m.deleted IS NOT TRUE AND m.source = 'device'
                       AND m.api_id IS NULL AND m.device_id IS NULL))
     ORDER BY d.type
"""

_UPSERT_PROFILE_SQL = """
    INSERT INTO param_profiles
        (scope, algorithm_type, name, description, status, deleted)
    VALUES (%s, %s, %s, %s, %s, false)
    ON CONFLICT (scope, algorithm_type, name) WHERE deleted = false DO NOTHING
"""

_GET_PROFILE_SQL = """
    SELECT id FROM param_profiles
     WHERE scope = %s AND algorithm_type = %s AND name = %s AND deleted = false
"""

_COPY_PARAMS_SQL = """
    INSERT INTO param_profile_params (
        profile_id, param_code, param_name, label, param_type, direction,
        required, default_value, validation_rules, help_text, ui_order, hidden,
        deleted)
    SELECT %s, param_code, param_name, label, param_type, direction,
           required, default_value, validation_rules, help_text, ui_order, hidden,
           false
      FROM algorithm_device_params
     WHERE algorithm_type = %s AND device_id IS NULL AND deleted IS NOT TRUE
    ON CONFLICT (profile_id, param_code, direction) WHERE deleted = false DO NOTHING
"""

_COPY_MAPPINGS_SQL = """
    INSERT INTO param_profile_mappings (
        profile_id, source, source_param, source_direction, dimension_id,
        target_param, transform_type, deleted)
    SELECT %s, source, source_param, source_direction, dimension_id,
           target_param, transform_type, false
      FROM param_mappings
     WHERE algorithm_type = %s AND source = 'device'
       AND api_id IS NULL AND device_id IS NULL AND deleted IS NOT TRUE
    ON CONFLICT (profile_id, source, source_param, dimension_id)
        WHERE deleted = false DO NOTHING
"""

_BIND_DEVICES_SQL = """
    INSERT INTO device_param_bindings (device_id, profile_id, deleted)
    SELECT dv.id, %s, false
      FROM devices dv
     WHERE dv.deleted = false
       AND dv.supported_algorithms::jsonb @> to_jsonb(ARRAY[%s]::text[])
       AND NOT EXISTS (SELECT 1 FROM device_param_bindings b
                        WHERE b.device_id = dv.id AND b.deleted = false)
    ON CONFLICT (device_id) WHERE deleted = false DO NOTHING
"""

_COUNT_SQL = {
    'param_profiles(scope=device)': """
        SELECT count(*) FROM param_profiles WHERE scope = 'device' AND deleted = false""",
    'param_profile_params(device 策略下)': """
        SELECT count(*) FROM param_profile_params pp
          JOIN param_profiles p ON p.id = pp.profile_id
         WHERE p.scope = 'device' AND p.deleted = false AND pp.deleted = false""",
    'param_profile_mappings(device 策略下)': """
        SELECT count(*) FROM param_profile_mappings pm
          JOIN param_profiles p ON p.id = pm.profile_id
         WHERE p.scope = 'device' AND p.deleted = false AND pm.deleted = false""",
    'device_param_bindings(有效)': """
        SELECT count(*) FROM device_param_bindings WHERE deleted = false""",
}


def _connect():
    return psycopg2.connect(os.environ['DATABASE_URL'])


def _missing_columns(cur):
    cur.execute(
        """
        SELECT table_name || '.' || column_name
          FROM information_schema.columns
         WHERE table_schema = 'public'
           AND (table_name || '.' || column_name) = ANY(%s)
        """,
        (list(REQUIRED_COLUMNS),))
    present = {row[0] for row in cur.fetchall()}
    return [c for c in REQUIRED_COLUMNS if c not in present]


def _print_counts(conn):
    with conn.cursor() as cur:
        for label, sql in _COUNT_SQL.items():
            cur.execute(sql)
            print(f"[state] {label}: {cur.fetchone()[0]}")


def _ensure_profile(cur, algorithm_type):
    cur.execute(_UPSERT_PROFILE_SQL, (
        PROFILE_SCOPE_DEVICE, algorithm_type, PROFILE_NAME_DEFAULT,
        PROFILE_DESCRIPTION, PROFILE_STATUS_ONLINE))
    created = cur.rowcount
    cur.execute(_GET_PROFILE_SQL, (
        PROFILE_SCOPE_DEVICE, algorithm_type, PROFILE_NAME_DEFAULT))
    row = cur.fetchone()
    if not row:
        raise RuntimeError(f'{algorithm_type}: scope=device 策略创建后仍查不到')
    return row[0], created


def apply(conn):
    stats = {'types': 0, 'profiles_created': 0, 'params': 0,
             'mappings': 0, 'devices': 0}
    with conn.cursor() as cur:
        cur.execute(f"SET lock_timeout = '{LOCK_TIMEOUT}'")
        cur.execute(_TYPES_SQL)
        types = [row[0] for row in cur.fetchall()]

        for algorithm_type in types:
            stats['types'] += 1
            profile_id, created = _ensure_profile(cur, algorithm_type)
            stats['profiles_created'] += created

            cur.execute(_COPY_PARAMS_SQL, (profile_id, algorithm_type))
            stats['params'] += cur.rowcount

            cur.execute(_COPY_MAPPINGS_SQL, (profile_id, algorithm_type))
            stats['mappings'] += cur.rowcount

            cur.execute(_BIND_DEVICES_SQL, (profile_id, algorithm_type))
            stats['devices'] += cur.rowcount

            print(f"[ok] {algorithm_type}: profile_id={profile_id}"
                  f"（{'新建' if created else '已存在'}）")

    conn.commit()
    print(f"[ok] 算法类型 {stats['types']} 个；新建策略 {stats['profiles_created']} 个；"
          f"复制参数 {stats['params']} 条、映射 {stats['mappings']} 条、"
          f"绑定设备 {stats['devices']} 台")


def main():
    parser = argparse.ArgumentParser(
        description='设备参数下沉为 scope=device 参数策略（默认 dry-run）')
    parser.add_argument('--apply', action='store_true', help='执行迁移')
    args = parser.parse_args()

    conn = _connect()
    try:
        with conn.cursor() as cur:
            missing = _missing_columns(cur)
        if missing:
            print(f"[ABORT] 缺少结构对象：{', '.join(missing)}；"
                  "请先执行 202610/add_param_profiles_scope.py 与 "
                  "202611/add_device_param_bindings.py")
            return 1

        print(f"目标库：{os.environ['DATABASE_URL'].rsplit('@', 1)[-1]}")
        _print_counts(conn)

        if not args.apply:
            with conn.cursor() as cur:
                cur.execute(_TYPES_SQL)
                types = [row[0] for row in cur.fetchall()]
            print(f"[dry-run] 待下沉算法类型：{types or '无'}；未修改数据库，"
                  "加 --apply 执行")
            return 0

        apply(conn)
        print('--- 执行后 ---')
        _print_counts(conn)
        return 0
    finally:
        conn.close()


if __name__ == '__main__':
    sys.exit(main())
