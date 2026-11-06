# -*- coding: utf-8 -*-
"""test_tasks 历史时间回填脚本（INT-2209，默认只读 dry-run）。

背景：执行引擎曾把 `datetime.now(utc_plus_8)`（aware CST）写进
`timestamp without time zone` 列，读回 naive 值后又 `.replace(tzinfo=utc_plus_8)`
写回 ORM 属性——每往返一次 PostgreSQL 按会话时区（UTC）再转一次，`started_at`
每次偏移 -8h。修复（task_service.core.time_utils：写库统一 UTC naive）只保证
新任务不再产生偏移，历史行需回填。

本脚本对 `test_tasks` 做两件事：

1. **可修正行**：`started_at < created_at` 且偏移是 8h 的整数倍（容差内），
   按 `-8h × k` 平移回真实开始时刻，并用修正后的起止时间重算
   `actual_duration`（completed_at 未写则置 NULL）。当前主库上就是 -16h
   (107 条) / -8h (13 条) 两类。
2. **历史脏值**：偏移不是 8h 整数倍（-240h / -789h / -1360h 等，多为旧版本
   多次往返叠加或人工改数），**只报告不动**，交负责人判断。

安全性：
- 默认 dry-run：只 SELECT + 打印统计与样例，任何写操作都不执行；
- `--apply` 必须同时给 `--expect <N>`，N == 本次 dry-run 命中行数，否则中止
  （防止误对另一份库执行）；
- 每个 8h 倍数分组一条 UPDATE，单事务内执行，回滚可控；
- 不碰 `updated_at`（避免影响列表排序与其他读侧口径）；
- TaskCase 的 `started_at` 受另一条写侧缺陷影响（写成本地墙钟，+8h 方向），
  但其真实开始时刻与创建时刻的间隔不确定，无法按恒定偏移可靠判定，本脚本
  只输出分布供参考，不做修改。

用法：
    # 只读统计（默认）
    python scripts/maintenance/backfill_task_time_utc_int2209.py
    # 负责人拍板后执行（N 取 dry-run 输出的「可修正」条数）
    python scripts/maintenance/backfill_task_time_utc_int2209.py --apply --expect 120
"""
import argparse
import os
import sys
from collections import Counter, defaultdict
from datetime import timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from sqlalchemy import text  # noqa: E402

HOUR = 3600
SHIFT_STEP = 8 * HOUR          # 每次往返造成的偏移
DEFAULT_TOLERANCE_MIN = 30     # 偏移余量（真实开始时刻延后创建时刻）容忍分钟数
# 只自动修正「当前缺陷」产生的 -8h / -16h 两类（step = -1 / -2 次往返）。
# 更早的 -240h / -789h 之类是旧版本多次叠加或人工改数，形态不可归因，只报告。
AUTO_FIX_STEPS = (-1, -2)


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description='INT-2209：test_tasks.started_at 历史偏移回填（默认 dry-run）')
    parser.add_argument('--apply', action='store_true',
                        help='实际执行 UPDATE（不加则只读统计）')
    parser.add_argument('--expect', type=int, default=None,
                        help='--apply 时必须给：与 dry-run 命中的「可修正」条数一致才执行')
    parser.add_argument('--tolerance-min', type=float, default=DEFAULT_TOLERANCE_MIN,
                        help='偏移余量容忍（分钟），默认 %(default)s')
    parser.add_argument('--samples', type=int, default=10,
                        help='每类打印的样例条数，默认 %(default)s')
    return parser.parse_args(argv)


def _classify(offset_seconds: float, tolerance_seconds: float):
    """返回 (可修正步数 k, 余量秒)；k=0 表示不可自动修正。

    只有 k ∈ AUTO_FIX_STEPS（-8h / -16h）且余量在容忍内才算可修正；
    其余一律归入「历史脏值」。
    """
    k = int(round(offset_seconds / SHIFT_STEP))
    residual = offset_seconds - k * SHIFT_STEP
    if k not in AUTO_FIX_STEPS or abs(residual) > tolerance_seconds:
        return 0, residual
    return k, residual


def _fixed_start(row, k):
    """按 k 平移回真实开始时刻，并校验落在 [created_at, completed_at] 之间。"""
    fixed = row['started_at'] - timedelta(seconds=k * SHIFT_STEP)
    if fixed < row['created_at']:
        return None
    if row['completed_at'] is not None and fixed > row['completed_at']:
        return None
    return fixed


def _load_candidates(engine):
    """读取所有 started_at < created_at 的任务行（只读）。"""
    sql = text("""
        SELECT id, name, status, created_at, started_at, completed_at, actual_duration
        FROM test_tasks
        WHERE started_at IS NOT NULL AND started_at < created_at
        ORDER BY id DESC
    """)
    with engine.connect() as conn:
        return [dict(r._mapping) for r in conn.execute(sql)]


def _task_case_distribution(engine, limit=12):
    sql = text("""
        SELECT round(extract(epoch FROM (started_at - created_at)) / 3600) AS off_h,
               count(*) AS n
        FROM task_case_relations
        WHERE started_at IS NOT NULL
        GROUP BY 1 ORDER BY 2 DESC LIMIT :lim
    """)
    with engine.connect() as conn:
        return [(int(r[0]), int(r[1])) for r in conn.execute(sql, {'lim': limit})]


def _apply_shifts(engine, groups, dry_run):
    """按 k 分组执行 UPDATE；返回每个分组影响行数。"""
    results = {}
    update_sql = text("""
        UPDATE test_tasks
        SET started_at = started_at + (CAST(:k AS integer) * interval '8 hours'),
            actual_duration = CASE
                WHEN completed_at IS NULL THEN NULL
                ELSE GREATEST(0, round(extract(epoch FROM (
                    completed_at - (started_at + CAST(:k AS integer) * interval '8 hours'))))::int)
            END
        WHERE id = ANY(:ids)
    """)
    with engine.begin() as conn:
        for k, ids in groups.items():
            if dry_run:
                results[k] = len(ids)
                continue
            res = conn.execute(update_sql, {'k': -k, 'ids': ids})
            results[k] = res.rowcount
    return results


def main(argv=None):
    args = _parse_args(argv)
    tolerance = args.tolerance_min * 60

    from shared.models.database import init_db, get_engine
    init_db(pool_size=2)
    engine = get_engine()

    rows = _load_candidates(engine)
    print(f'库: {engine.url.render_as_string(hide_password=True)}')
    print(f'started_at < created_at 的行: {len(rows)}')

    fixable = defaultdict(list)
    dirty = []
    for row in rows:
        offset = (row['started_at'] - row['created_at']).total_seconds()
        k, residual = _classify(offset, tolerance)
        if k and _fixed_start(row, k) is not None:
            fixable[k].append((row, offset, residual))
        else:
            dirty.append((row, offset, residual))

    print('\n== 可自动修正（8h 整数倍偏移）==')
    total_fixable = 0
    for k in sorted(fixable):
        items = fixable[k]
        total_fixable += len(items)
        print(f'  偏移 {k * 8:+d}h: {len(items)} 条（余量最大 '
              f'{max(abs(i[2]) for i in items) / 60:.1f} 分钟）')
        for row, offset, residual in items[:args.samples]:
            fixed = _fixed_start(row, k)
            new_dur = (None if row['completed_at'] is None
                       else max(0, int((row['completed_at'] - fixed).total_seconds())))
            print(f"    id={row['id']} {row['name'][:28]!r} "
                  f"created={row['created_at']} started={row['started_at']} -> {fixed} "
                  f"actual_duration {row['actual_duration']} -> {new_dur}")
    print(f'  合计: {total_fixable} 条')

    print('\n== 历史脏值（非 8h 整数倍，需人工判断，不自动处理）==')
    if not dirty:
        print('  无')
    else:
        buckets = Counter(int(round(o / HOUR)) for _r, o, _res in dirty)
        print(f'  共 {len(dirty)} 条，偏移小时分布: '
              + ', '.join(f'{h:+d}h×{n}' for h, n in buckets.most_common(12)))
        for row, offset, _res in dirty[:args.samples]:
            print(f"    id={row['id']} {row['name'][:28]!r} "
                  f"created={row['created_at']} started={row['started_at']} "
                  f'偏移={offset / HOUR:+.2f}h')

    print('\n== TaskCase 参考（不处理）==')
    print('  task_case_relations.started_at - created_at 小时分布（前若干）: '
          + ', '.join(f'{h:+d}h×{n}' for h, n in _task_case_distribution(engine)))

    if not args.apply:
        print('\n[dry-run] 未执行任何写操作。'
              f' 如需执行: --apply --expect {total_fixable}')
        return 0

    if args.expect is None or args.expect != total_fixable:
        print(f'\n[中止] --apply 需要 --expect {total_fixable}（本次可修正条数），'
              f'实际给的是 {args.expect}。未写入。', file=sys.stderr)
        return 2

    groups = {k: [row['id'] for row, _o, _r in items] for k, items in fixable.items()}
    changed = _apply_shifts(engine, groups, dry_run=False)
    print('\n[apply] 更新条数: '
          + ', '.join(f'{k * 8:+d}h→{n}' for k, n in sorted(changed.items())))

    with engine.connect() as conn:
        remain = conn.execute(text(
            'SELECT count(*) FROM test_tasks '
            'WHERE started_at IS NOT NULL AND started_at < created_at')).scalar()
    print(f'[apply] 剩余 started_at < created_at: {remain} 条（历史脏值仍保留）')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
