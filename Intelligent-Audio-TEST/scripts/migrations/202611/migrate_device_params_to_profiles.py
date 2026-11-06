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

幂等性（INT-2275，语义级：只补「从未有过」的数据）：
    本脚本留在引导链里、每次部署都会执行，所以不能只看 ``deleted = false`` 的
    有效行——管理员在 UI 解绑设备（``device_param_bindings.deleted = true``）、
    删除策略参数/映射、软删整个 default 策略，都是需要跨部署保持的用户状态。
    口径统一为「有任何历史行（含 deleted=true）即视为已补过」：

      - 策略：``(scope, algorithm_type, name)`` 有有效行 → 复用；只有软删行 →
        整个算法类型跳过（不重建策略、不回填参数/映射/绑定）；从未有过 → 新建。
      - 参数/映射：按唯一键 ``NOT EXISTS``（不筛 deleted）判断是否已存在，
        ``ON CONFLICT DO NOTHING`` 仅作并发兜底。
      - 设备绑定：``NOT EXISTS`` 不筛 deleted（有历史绑定行即不再补）。

    重复执行命中 0 行。

INT-2303（悬空映射）：
    复制口径只认「维度未软删」的源行（``dimension_id IS NULL`` 的行照抄——设备侧
    允许不挂维度），并在处理任何算法类型之前先回收旧部署遗留的「生效映射 → 已
    软删维度」行（幂等 UPDATE，重复执行命中 0 行）。维度树被软删时，
    ``202609/seed_interruption_dimensions.py`` 的级联也同步软删
    ``param_profile_mappings``；两处合起来不再产生悬空引用。硬删仍走数据清理卡
    （INT-2294），不进引导链。

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
    # INT-2303：映射复制/回收都按维度软删状态过滤
    'dimensions.deleted',
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

# INT-2275：按 (scope, algorithm_type, name) 取**任意**历史行（含软删），
# 有效行优先。软删行存在而有效行不存在 = 管理员删掉了 default 策略，
# 本脚本不得重建（否则每次部署都会复活整条策略链）。
_GET_ANY_PROFILE_SQL = """
    SELECT id, COALESCE(deleted, false) FROM param_profiles
     WHERE scope = %s AND algorithm_type = %s AND name = %s
     ORDER BY COALESCE(deleted, false) ASC, id ASC
     LIMIT 1
"""

_GET_PROFILE_SQL = """
    SELECT id FROM param_profiles
     WHERE scope = %s AND algorithm_type = %s AND name = %s AND deleted = false
"""

# INT-2275：NOT EXISTS 不带 deleted 条件——同键行（哪怕已软删）存在即不补，
# 用户删掉的策略参数保持删除状态。direction 可能为 NULL，用 IS NOT DISTINCT
# FROM 比较（普通 = 遇 NULL 恒 UNKNOWN，会让 NULL 行每次部署重复插入）。
_COPY_PARAMS_SQL = """
    INSERT INTO param_profile_params (
        profile_id, param_code, param_name, label, param_type, direction,
        required, default_value, validation_rules, help_text, ui_order, hidden,
        deleted)
    SELECT %s, a.param_code, a.param_name, a.label, a.param_type, a.direction,
           a.required, a.default_value, a.validation_rules, a.help_text,
           a.ui_order, a.hidden, false
      FROM algorithm_device_params a
     WHERE a.algorithm_type = %s AND a.device_id IS NULL AND a.deleted IS NOT TRUE
       AND NOT EXISTS (
           SELECT 1 FROM param_profile_params pp
            WHERE pp.profile_id = %s
              AND pp.param_code = a.param_code
              AND pp.direction IS NOT DISTINCT FROM a.direction)
    ON CONFLICT (profile_id, param_code, direction) WHERE deleted = false DO NOTHING
"""

# INT-2275：同上，dimension_id 可为 NULL，用 IS NOT DISTINCT FROM。
# INT-2303：跳过「指向已软删维度」的映射行——这类源头行往往自身没软删（维度树
# 被级联软删的旧路径留下的），照抄就会每轮把悬空引用复制成一条新的生效策略映射。
# dimension_id 为 NULL 表示不挂维度（设备侧合法形态），不能因为 exists 判定被误伤。
_COPY_MAPPINGS_SQL = """
    INSERT INTO param_profile_mappings (
        profile_id, source, source_param, source_direction, dimension_id,
        target_param, transform_type, deleted)
    SELECT %s, a.source, a.source_param, a.source_direction, a.dimension_id,
           a.target_param, a.transform_type, false
      FROM param_mappings a
     WHERE a.algorithm_type = %s AND a.source = 'device'
       AND a.api_id IS NULL AND a.device_id IS NULL AND a.deleted IS NOT TRUE
       AND (
            a.dimension_id IS NULL
            OR EXISTS (SELECT 1 FROM dimensions d
                        WHERE d.id = a.dimension_id AND d.deleted IS NOT TRUE))
       AND NOT EXISTS (
           SELECT 1 FROM param_profile_mappings pm
            WHERE pm.profile_id = %s
              AND pm.source = a.source
              AND pm.source_param = a.source_param
              AND pm.dimension_id IS NOT DISTINCT FROM a.dimension_id)
    ON CONFLICT (profile_id, source, source_param, dimension_id)
        WHERE deleted = false DO NOTHING
"""

# INT-2303：回收历史孤儿——生效策略映射指向已软删维度。上面的复制过滤只能拦住
# 「新复制」，旧部署已经复制出来的行仍在库里；本脚本每轮引导都跑且排在全部维度
# 种子之后，这里做一次幂等软删，让悬空行在一次引导后就归零（重复执行命中 0 行）。
# 只碰「维度确实已软删」的行：dimension_id 为 NULL 不参与 join；硬删走数据清理卡
# （INT-2294），不进引导链。
_PURGE_DANGLING_MAPPINGS_SQL = """
    UPDATE param_profile_mappings ppm
       SET deleted = true, updated_at = NOW()
      FROM dimensions d
     WHERE d.id = ppm.dimension_id
       AND d.deleted IS TRUE
       AND ppm.deleted IS NOT TRUE
"""

# INT-2275：NOT EXISTS 不筛 deleted——设备曾在 UI 解绑（绑定行软删）就不再自动
# 绑回；部分唯一索引 WHERE deleted = false 允许「软删行 + 新行」共存，只看有效行
# 会让每次部署都补一条绑定。
_BIND_DEVICES_SQL = """
    INSERT INTO device_param_bindings (device_id, profile_id, deleted)
    SELECT dv.id, %s, false
      FROM devices dv
     WHERE dv.deleted = false
       AND dv.supported_algorithms::jsonb @> to_jsonb(ARRAY[%s]::text[])
       AND NOT EXISTS (SELECT 1 FROM device_param_bindings b
                        WHERE b.device_id = dv.id)
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
    # INT-2303：应为 0；非 0 说明有生效映射指向已软删维度（apply 会幂等回收）
    'param_profile_mappings(悬空·指向软删维度)': """
        SELECT count(*) FROM param_profile_mappings ppm
          JOIN dimensions d ON d.id = ppm.dimension_id
         WHERE d.deleted IS TRUE AND ppm.deleted IS NOT TRUE""",
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
    """取/建 default 策略。

    返回 ``(profile_id, created)``；策略曾被软删时返回 ``(None, 0)``，调用方应
    跳过该算法类型的后续步骤（INT-2275：不复活管理员删掉的策略）。
    """
    cur.execute(_GET_ANY_PROFILE_SQL, (
        PROFILE_SCOPE_DEVICE, algorithm_type, PROFILE_NAME_DEFAULT))
    row = cur.fetchone()
    if row:
        profile_id, deleted = row[0], row[1]
        if deleted:
            return None, 0
        return profile_id, 0

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
    stats = {'types': 0, 'profiles_created': 0, 'profiles_skipped': 0,
             'params': 0, 'mappings': 0, 'devices': 0, 'purged': 0}
    with conn.cursor() as cur:
        cur.execute(f"SET lock_timeout = '{LOCK_TIMEOUT}'")
        # INT-2303：先回收旧部署遗留的「生效映射 → 已软删维度」，再按过滤后的口径
        # 复制；两者合起来保证单轮引导后悬空行为 0（重复执行命中 0 行）。
        cur.execute(_PURGE_DANGLING_MAPPINGS_SQL)
        stats['purged'] = cur.rowcount
        if stats['purged']:
            print(f"[purge] 回收指向已软删维度的生效映射 {stats['purged']} 条")
        cur.execute(_TYPES_SQL)
        types = [row[0] for row in cur.fetchall()]

        for algorithm_type in types:
            stats['types'] += 1
            profile_id, created = _ensure_profile(cur, algorithm_type)
            if profile_id is None:
                stats['profiles_skipped'] += 1
                print(f"[skip] {algorithm_type}: default 策略已软删，"
                      "保持删除状态（不重建、不回填）")
                continue
            stats['profiles_created'] += created

            cur.execute(_COPY_PARAMS_SQL, (profile_id, algorithm_type, profile_id))
            stats['params'] += cur.rowcount

            cur.execute(_COPY_MAPPINGS_SQL, (profile_id, algorithm_type, profile_id))
            stats['mappings'] += cur.rowcount

            cur.execute(_BIND_DEVICES_SQL, (profile_id, algorithm_type))
            stats['devices'] += cur.rowcount

            print(f"[ok] {algorithm_type}: profile_id={profile_id}"
                  f"（{'新建' if created else '已存在'}）")

    conn.commit()
    print(f"[ok] 算法类型 {stats['types']} 个；新建策略 {stats['profiles_created']} 个；"
          f"跳过已软删策略 {stats['profiles_skipped']} 个；"
          f"复制参数 {stats['params']} 条、映射 {stats['mappings']} 条、"
          f"绑定设备 {stats['devices']} 台；"
          f"回收悬空映射 {stats['purged']} 条")


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
