# -*- coding: utf-8 -*-
"""迁移/维护脚本：统计信息重置后自动重建表统计（INT-1741）

背景（INT-1741 缺陷·基础设施·数据库）：
- 2026-10-24 巡检发现主库 83/95 张用户表 `last_analyze` 与 `last_autoanalyze`
  全为 NULL，`pg_stat_user_tables.n_live_tup` 与真实行数差 2~3 个数量级
  （logs 真实 304,709 行，计数器只有 334）。
- 只读定位结论：autovacuum 配置、权限、worker 槽位、`track_counts`、长事务
  全部正常，真因是 **PostgreSQL 统计子系统在重启后从零开始计数**：
  postgres 容器 2026-10-23 当天发生 7 次非正常关闭（日志 "database system was
  interrupted … not properly shut down; automatic recovery in progress"），
  而 PGDATA 的 `pg_stat/` 目录里没有 `pgstat.stat` 持久化快照，于是每次崩溃重启
  所有计数器归零（`pg_stat_bgwriter.stats_reset` = 本次 postmaster 启动时间）。
  数据、`pg_class.reltuples`、`pg_statistic` 是目录级/落盘对象，不受影响。
- 归零后 autoanalyze 的触发阈值按「计数器增量」算：
  `autovacuum_analyze_threshold + autovacuum_analyze_scale_factor × reltuples`
  —— logs 需要 50 + 0.1×300,095 ≈ 30,060 次变更，而本统计周期只累计到 350 次，
  于是大表永远不会被 autoanalyze 扫描，统计停留在一个崩溃前的旧快照上。
  `n_live_tup` 同理只是「本周期插入-删除」的计数器，不是表扫描结果。

设计（为什么放在 db_bootstrap 引导链末端）：
- 引导链每次 `docker compose up` 都会跑一遍（compose 以
  service_completed_successfully 门控业务服务），崩溃/重建容器后能在业务服务
  连上库之前把统计补回来，是这套部署里唯一稳定的「启动后」钩子。
- **只做统计、不碰数据**：本脚本唯一执行的语句是 `ANALYZE <表名>`，
  绝不 VACUUM FULL / TRUNCATE / DROP / 改结构（负责人 2026-10-22 铁律）。
- 只挑「本统计周期内一次都没分析过」且行数 ≥ `--min-rows`（默认 1000）的表：
  小表 autoanalyze 很快会自己覆盖，大表才需要兜底；已分析过的表交给
  autovacuum 自己记账，避免每次部署全库重扫。
- 幂等：ANALYZE 会同时写入 `last_analyze`，重复执行命中 0 张表。
- **best-effort，不阻断部署**：统计缺失只影响查询计划质量，不影响正确性；
  某张表被锁挡住（lock_timeout）时打 WARN 跳过，脚本仍以 0 退出，不让一次
  统计刷新把整套服务挡在门外。
- `track_counts=off` 时统计视图恒为 NULL、无法判定谁缺统计，直接跳过并说明
  原因（此时 autovacuum 本身也工作不正常，属另一类部署问题）。

用法：
    python scripts/migrations/202610/analyze_stale_statistics_int1741.py            # 预览
    python scripts/migrations/202610/analyze_stale_statistics_int1741.py --apply    # 执行
    python scripts/migrations/202610/analyze_stale_statistics_int1741.py --apply --min-rows 10000
"""
import argparse
import os
import sys

import psycopg2
from psycopg2 import sql

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

if not os.environ.get('DATABASE_URL'):
    os.environ['DATABASE_URL'] = os.environ.get(
        'DATABASE_URI',
        'postgresql://intelligent_audio_test:intelligent_audio_test666'
        '@localhost:5432/intelligent_audio_test')

# 行数门槛：低于此值的表 autoanalyze 几十次写就能覆盖，不值得每次部署重扫
DEFAULT_MIN_ROWS = 1000

# 统计周期内从未分析过的用户表（reltuples 为 pg_class 里的估算行数，
# 统计计数器归零不影响它；用它筛规模而不是用已被归零的 n_live_tup）
_STALE_TABLES_SQL = """
SELECT n.nspname AS schema_name,
       c.relname AS table_name,
       c.reltuples::bigint AS reltuples,
       s.n_live_tup
  FROM pg_class c
  JOIN pg_namespace n ON n.oid = c.relnamespace
  LEFT JOIN pg_stat_user_tables s ON s.relid = c.oid
 WHERE c.relkind = 'r'
   AND n.nspname NOT LIKE 'pg\\_%%'
   AND n.nspname <> 'information_schema'
   AND s.last_analyze IS NULL
   AND s.last_autoanalyze IS NULL
   AND c.reltuples >= %s
 ORDER BY c.reltuples DESC, n.nspname, c.relname
"""


def _tables_are_tracked(cur):
    """track_counts 关闭时统计视图恒 NULL，无法判定谁缺统计。"""
    cur.execute("SELECT setting FROM pg_settings WHERE name = 'track_counts'")
    row = cur.fetchone()
    return bool(row) and str(row[0]).lower() in ('on', 'true', '1')


def select_stale_tables(cur, min_rows=DEFAULT_MIN_ROWS):
    """返回 [(schema, table, reltuples, n_live_tup), ...]。"""
    cur.execute(_STALE_TABLES_SQL, (int(min_rows),))
    return [tuple(row) for row in cur.fetchall()]


def analyze_table(cur, schema_name, table_name):
    """对单表执行 ANALYZE（唯一允许的语句）。标识符走 psycopg2.sql 转义。"""
    cur.execute(sql.SQL('ANALYZE {}.{}').format(
        sql.Identifier(schema_name), sql.Identifier(table_name)))


def run(conn, min_rows=DEFAULT_MIN_ROWS, apply_changes=False, out=print):
    """核心流程；返回本次处理（或待处理）的表数。

    连接需为 autocommit（ANALYZE 不属于事务语义，逐表提交才不会一条失败拖垮全部）。
    """
    with conn.cursor() as cur:
        if not _tables_are_tracked(cur):
            out('[ANALYZE] [SKIP] track_counts=off：统计视图恒为空，'
                '无法判定哪些表缺统计（该部署的 autovacuum 本身也需排查）')
            return 0
        stale = select_stale_tables(cur, min_rows=min_rows)

    if not stale:
        out(f'[ANALYZE] 无需处理：行数 ≥ {min_rows} 的表在本次统计周期内都已有分析记录')
        return 0

    out(f'[ANALYZE] 待分析表 {len(stale)} 张（本统计周期从未 analyze，行数 ≥ {min_rows}）：')
    for schema_name, table_name, reltuples, n_live_tup in stale:
        out(f'[ANALYZE]   {schema_name}.{table_name}  reltuples={reltuples}  '
            f'n_live_tup={n_live_tup}')

    if not apply_changes:
        out('[ANALYZE] 预览模式：以上仅列出，未执行 ANALYZE（加 --apply 执行）')
        return len(stale)

    done = 0
    for schema_name, table_name, reltuples, _n_live in stale:
        try:
            with conn.cursor() as cur:
                analyze_table(cur, schema_name, table_name)
            done += 1
            out(f'[ANALYZE]   OK {schema_name}.{table_name}（reltuples={reltuples}）')
        except Exception as exc:  # noqa: BLE001 - 单表失败不阻断部署
            conn.rollback()
            out(f'[ANALYZE]   [WARN] {schema_name}.{table_name} 分析失败，已跳过：{exc}')

    with conn.cursor() as cur:
        remaining = select_stale_tables(cur, min_rows=min_rows)
    out(f'[ANALYZE] 完成：已分析 {done}/{len(stale)} 张，仍缺统计 {len(remaining)} 张')
    return done


def main(argv=None):
    parser = argparse.ArgumentParser(
        description='INT-1741：统计周期重置后，对从未 analyze 的大表重建统计')
    parser.add_argument('--apply', action='store_true',
                        help='真正执行 ANALYZE（缺省仅预览）')
    parser.add_argument('--min-rows', type=int, default=DEFAULT_MIN_ROWS,
                        help=f'行数门槛，低于此值的表交给 autoanalyze（默认 {DEFAULT_MIN_ROWS}）')
    args = parser.parse_args(argv)

    dsn = os.environ.get('DATABASE_URL')
    if not dsn:
        print('[ANALYZE] [WARN] DATABASE_URL 未设置，跳过（不阻断引导）', flush=True)
        return 0
    try:
        conn = psycopg2.connect(dsn, connect_timeout=10,
                                application_name='db_bootstrap_analyze')
        conn.autocommit = True
    except Exception as exc:  # noqa: BLE001 - 统计刷新不阻断引导
        print(f'[ANALYZE] [WARN] 连接数据库失败，跳过：{exc}', flush=True)
        return 0
    try:
        run(conn, min_rows=args.min_rows, apply_changes=args.apply)
    except Exception as exc:  # noqa: BLE001
        print(f'[ANALYZE] [WARN] 统计刷新异常，跳过（不阻断引导）：{exc}', flush=True)
        return 0
    finally:
        try:
            conn.close()
        except Exception:  # noqa: BLE001
            pass
    return 0


if __name__ == '__main__':
    sys.exit(main())
