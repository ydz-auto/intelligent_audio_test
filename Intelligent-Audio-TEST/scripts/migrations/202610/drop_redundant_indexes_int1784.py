# -*- coding: utf-8 -*-
"""迁移脚本：下线定义级冗余 btree 索引 + 废弃空表 report_detail_data（INT-1784）

背景（INT-1784，负责人 2026-10-24 批准「优化·数据库·档1」）：
- 主库 2026-10-24 实测 387 个索引 / 约 77MB，其中相当一部分是「定义层面可证明
  冗余」：同一张表上存在**完全相同定义**的两个索引（历史改名遗留），或**短索引
  被同表复合索引的前缀覆盖**（如 logs(task_id) 被 logs(task_id, time) 覆盖）。
- 冗余索引只增加写放大与磁盘占用，对任何查询都没有增益 —— 本脚本**只删这类**，
  一个 `idx_scan=0` 的「可能有用」索引都不动（统计被崩溃 reset 过，扫描计数不可信，
  那批留给档0 观测窗口二次评审）。

为什么要单独一个「drop 迁移」而不是改历史脚本：
- 索引有三个重建源，必须同时断掉，否则下次部署又会被建回来：
  ① ORM 的 `Index(...)` / `Column(index=True)`（create_all 建表时创建）；
  ② 引导链里 202608/202610 的采索引脚本（部署时重跑）；
  ③ 本脚本兜底删除（历史顺序不可控，且建库早于本次瘦身的存量库只能靠它）。
  ①②已在本卡里同步移除；③保证即使有遗漏的创建点，引导链末端也会收敛到目标状态。

安全边界（本脚本的全部写操作只有这两类）：
1. `DROP INDEX`：**索引名 + 定义双匹配**才删。先按 (表, 索引名) 从 pg_catalog
   取实际定义，与期望定义逐字比对（归一化后比较 `USING btree (...)` 之后的部分，
   并校验非 UNIQUE）；对不上说明被人改过（加列 / 改 WHERE / 变唯一），**跳过并
   打 WARN**，绝不误删。删除前还要求「覆盖索引存在且列序前缀匹配」，覆盖索引
   缺失时同样跳过 —— 宁可不减负，也不让某条查询失去索引。
2. `DROP TABLE report_detail_data`：执行前确认 `to_regclass` 存在、且表内 0 行；
   有数据就跳过并 WARN，绝不删数据。

幂等：所有 DDL 都用 `IF EXISTS` 形态，且删除前先查存在性；第二次执行全部 SKIP。

用法：
    python scripts/migrations/202610/drop_redundant_indexes_int1784.py            # 预览（默认）
    python scripts/migrations/202610/drop_redundant_indexes_int1784.py --apply    # 执行

引导链：`docker/db_bootstrap_entrypoint.py` 的 BOOTSTRAP_STEPS 以 `--apply` 调用，
位置在 INT-1741 的 ANALYZE 之前（ANALYZE 必须是引导链末步，见该卡的静态守卫）。
"""
import argparse
import os
import re
import sys

import psycopg2

DEFAULT_DATABASE_URL = (
    'postgresql://intelligent_audio_test:intelligent_audio_test666'
    '@localhost:5432/intelligent_audio_test')


class IndexSpec(object):
    """一条待下线索引的期望定义 + 覆盖它的复合索引。

    columns / where 是期望定义中 `USING btree (...)` 之后的部分，
    与 pg_get_indexdef 归一化后的尾部逐字比对（双匹配）。
    """

    __slots__ = ('name', 'table', 'columns', 'where', 'covered_by')

    def __init__(self, name, table, columns, covered_by, where=None):
        self.name = name
        self.table = table
        self.columns = columns
        self.where = where
        self.covered_by = covered_by

    @property
    def expected_tail(self):
        tail = f'using btree ({self.columns})'
        if self.where:
            tail += f' where ({self.where})'
        return _normalize(tail)


# 待删清单（22 个，定义级可证明冗余；分 A/B 两类见 INT-1784 卡面）。
#
# A. 同名同定义的重复索引（历史改名残留）
# B. 被同表复合索引前缀覆盖的短索引
INDEX_SPECS = (
    # ── A. 完全相同的两组名字 ──
    # audio_algorithm_relations 上 algorithm_type / audio_id 各有两个同定义索引
    IndexSpec('idx_audio_algo_rel_algorithm_type', 'audio_algorithm_relations',
              'algorithm_type', covered_by='idx_audio_algorithm_type'),
    IndexSpec('idx_audio_algo_rel_audio_id', 'audio_algorithm_relations',
              'audio_id', covered_by='idx_audio_algorithm_audio'),
    # logs 上 task_id 有三个索引（idx_task_time / idx_logs_task_id / idx_task_id）
    IndexSpec('idx_logs_task_id', 'logs', 'task_id', covered_by='idx_task_time'),
    IndexSpec('idx_task_id', 'logs', 'task_id', covered_by='idx_task_time'),
    # test_reports.task_id 两个同定义索引
    IndexSpec('idx_report_task_id', 'test_reports', 'task_id',
              covered_by='idx_test_reports_task_id'),

    # ── B. 前缀冗余 ──
    IndexSpec('idx_audio_annotations_audio_id', 'audio_annotations', 'audio_id',
              covered_by='idx_audio_annotations_audio_deleted'),
    IndexSpec('idx_audio_tags_audio_id', 'audio_tags', 'audio_id',
              covered_by='idx_audio_tags_audio_tag'),
    IndexSpec('ix_audios_created_by_user_id', 'audios', 'created_by_user_id',
              covered_by='idx_audios_created_visibility'),
    IndexSpec('idx_audios_deleted', 'audios', 'deleted',
              covered_by='idx_audios_deleted_created'),
    IndexSpec('idx_cherry_cart_user', 'cherry_pick_cart_items', 'user_id',
              covered_by='idx_cherry_cart_user_source'),
    IndexSpec('ix_device_alarms_status', 'device_alarms', 'status',
              covered_by='ix_alarm_status_time'),
    IndexSpec('ix_device_status_events_device_id', 'device_status_events',
              'device_id', covered_by='ix_status_event_device_time'),
    IndexSpec('ix_dimensions_created_by_user_id', 'dimensions',
              'created_by_user_id', covered_by='idx_dimensions_created_visibility'),
    IndexSpec('idx_favorite_user_id', 'favorites', 'user_id',
              covered_by='idx_favorite_user_type'),
    IndexSpec('idx_category', 'logs', 'category', covered_by='idx_category_time'),
    IndexSpec('idx_level', 'logs', 'level', covered_by='idx_level_time'),
    IndexSpec('idx_report_favorite_user_id', 'report_favorites', 'user_id',
              covered_by='idx_report_favorite_user'),
    IndexSpec('ix_test_cases_created_by_user_id', 'test_cases',
              'created_by_user_id', covered_by='idx_test_cases_created_visibility'),
    IndexSpec('idx_report_type', 'test_reports', 'type',
              covered_by='idx_report_type_status'),
    IndexSpec('ix_test_reports_created_by_user_id', 'test_reports',
              'created_by_user_id', covered_by='idx_test_reports_created_visibility'),
    IndexSpec('idx_test_result_dimensions_test_result_id', 'test_result_dimensions',
              'test_result_id', covered_by='idx_trd_round'),
    IndexSpec('ix_test_tasks_created_by_user_id', 'test_tasks',
              'created_by_user_id', covered_by='idx_test_tasks_created_visibility'),
)

# 废弃空表（代码里 `_create_report_detail_data` 是遗留函数名，实际写的是
# report_raw_data / report_metric_stats，与本表无关；无 ORM 模型 / 外键 / 视图引用）
LEGACY_TABLE = 'report_detail_data'

_INDEXES_SQL = """
SELECT t.relname AS table_name,
       c.relname AS index_name,
       pg_get_indexdef(c.oid) AS index_def
  FROM pg_index i
  JOIN pg_class c ON c.oid = i.indexrelid
  JOIN pg_class t ON t.oid = i.indrelid
  JOIN pg_namespace n ON n.oid = c.relnamespace
 WHERE n.nspname = 'public'
   AND t.relname = ANY(%s)
"""


def _normalize(text):
    """归一化 indexdef：去双引号、折叠空白、转小写（标识符全小写，安全）。"""
    return re.sub(r'\s+', ' ', (text or '').replace('"', '')).strip().lower()


def _definition_tail(index_def):
    """取 `USING btree` 起的尾部；不是 btree 索引返回 None。"""
    norm = _normalize(index_def)
    marker = 'using btree '
    pos = norm.find(marker)
    return norm[pos:] if pos >= 0 else None


def _covers(drop_spec, covering_def):
    """覆盖索引的列序必须是待删索引列的前缀（`(a, b)` 覆盖 `(a)`）。"""
    tail = _definition_tail(covering_def)
    if not tail:
        return False
    pattern = r'using btree \(%s(?:,|\))' % re.escape(_normalize(drop_spec.columns))
    return re.search(pattern, tail) is not None


def fetch_indexes(conn, tables):
    """返回 {(table, index): index_def}（只取 public 下这些表的索引）。"""
    with conn.cursor() as cur:
        cur.execute(_INDEXES_SQL, (list(tables),))
        return {(row[0], row[1]): row[2] for row in cur.fetchall()}


def plan(indexes, specs=INDEX_SPECS):
    """按「存在 + 定义匹配 + 覆盖索引在位」三条件筛出待删项。

    返回 (to_drop, skipped)，skipped 是 [(spec, 原因), ...]。
    """
    to_drop, skipped = [], []
    for spec in specs:
        actual = indexes.get((spec.table, spec.name))
        if actual is None:
            skipped.append((spec, 'missing'))
            continue
        if _normalize(actual).startswith('create unique index '):
            skipped.append((spec, 'unique'))
            continue
        if _definition_tail(actual) != spec.expected_tail:
            skipped.append((spec, 'definition-mismatch'))
            continue
        covering_def = indexes.get((spec.table, spec.covered_by))
        if covering_def is None:
            skipped.append((spec, 'covering-missing'))
            continue
        if not _covers(spec, covering_def):
            skipped.append((spec, 'covering-mismatch'))
            continue
        to_drop.append((spec, actual))
    return to_drop, skipped


def _index_size(cur, name):
    try:
        cur.execute('SELECT pg_size_pretty(pg_relation_size(%s::regclass))', (name,))
        row = cur.fetchone()
        return row[0] if row else '?'
    except Exception:  # noqa: BLE001 - 仅用于日志展示
        return '?'


def _drop_index(cur, spec):
    """DROP INDEX（标识符走 libpq 转义，不拼裸字符串）。"""
    from psycopg2 import sql
    cur.execute(sql.SQL('DROP INDEX IF EXISTS {}').format(sql.Identifier(spec.name)))


def _plan_legacy_table(conn):
    """返回 (状态, 行数)：absent / empty / non-empty。"""
    with conn.cursor() as cur:
        cur.execute('SELECT to_regclass(%s)', (f'public.{LEGACY_TABLE}',))
        row = cur.fetchone()
        if not row or row[0] is None:
            return 'absent', 0
        from psycopg2 import sql
        cur.execute(sql.SQL('SELECT count(*) FROM {}').format(
            sql.Identifier(LEGACY_TABLE)))
        return 'present', cur.fetchone()[0]


def run(conn, apply_changes=False, out=print, specs=INDEX_SPECS):
    """核心流程；返回 (dropped_index_count, dropped_table_bool)。

    连接需为 autocommit：逐条提交，单条失败不拖垮同批其它索引。
    """
    tables = sorted({spec.table for spec in specs})
    indexes = fetch_indexes(conn, tables)
    to_drop, skipped = plan(indexes, specs)

    missing = [spec.name for spec, reason in skipped if reason == 'missing']
    if missing:
        out(f'[SKIP] 已不存在（幂等）：{len(missing)} 个 —— {", ".join(missing)}')
    for spec, reason in skipped:
        if reason == 'missing':
            continue
        detail = {
            'unique': '实际是 UNIQUE 索引，不动',
            'definition-mismatch': f'定义与期望不符（期望 using btree ({spec.columns})），'
                                   '疑似被人工改过，跳过',
            'covering-missing': f'覆盖索引 {spec.covered_by} 不存在，删了会失去索引支撑',
            'covering-mismatch': f'覆盖索引 {spec.covered_by} 列序不以前缀覆盖'
                                 f' ({spec.columns})',
        }.get(reason, reason)
        out(f'[WARN] {spec.table}.{spec.name} 跳过：{detail}')

    if not to_drop:
        out(f'[SKIP] 无可删除的冗余索引（清单 {len(specs)} 个）')
    elif not apply_changes:
        with conn.cursor() as cur:
            sized = [(spec, _index_size(cur, spec.name)) for spec, _ in to_drop]
        for spec, size in sized:
            out(f'[DRY-RUN] DROP INDEX {spec.name}  ({spec.table}, {size})')
        out(f'[DRY-RUN] 预览模式：以上 {len(sized)} 个索引未删除（加 --apply 执行）')
    else:
        dropped = 0
        with conn.cursor() as cur:
            for spec, _actual in to_drop:
                size = _index_size(cur, spec.name)
                _drop_index(cur, spec)
                dropped += 1
                out(f'[DONE] DROP INDEX {spec.name}  ({spec.table}, 释放 {size})')
        out(f'[DONE] 已删除冗余索引 {dropped} 个')

    # 废弃空表
    state, row_count = _plan_legacy_table(conn)
    table_dropped = False
    if state == 'absent':
        out(f'[SKIP] 表 {LEGACY_TABLE} 已不存在')
    elif row_count:
        out(f'[WARN] 表 {LEGACY_TABLE} 有 {row_count} 行数据，不是空表，跳过 DROP TABLE'
            '（需人工确认后再处理）')
    elif not apply_changes:
        out(f'[DRY-RUN] DROP TABLE {LEGACY_TABLE}（0 行，无引用）')
    else:
        with conn.cursor() as cur:
            from psycopg2 import sql
            cur.execute(sql.SQL('DROP TABLE IF EXISTS {}').format(
                sql.Identifier(LEGACY_TABLE)))
        table_dropped = True
        out(f'[DONE] DROP TABLE {LEGACY_TABLE}')

    return len(to_drop) if apply_changes else 0, table_dropped


def main(argv=None):
    parser = argparse.ArgumentParser(
        description='INT-1784：下线定义级冗余索引 + 废弃空表 report_detail_data')
    parser.add_argument('--apply', action='store_true',
                        help='真正执行 DROP（缺省仅预览）')
    parser.add_argument('--database-url', default=None,
                        help='覆盖 DATABASE_URL（默认读环境变量）')
    args = parser.parse_args(argv)

    dsn = args.database_url or os.environ.get('DATABASE_URL') \
        or os.environ.get('DATABASE_URI') or DEFAULT_DATABASE_URL
    print(f'[INT-1784] 冗余索引下线：目标 {len(INDEX_SPECS)} 个索引 + 表 {LEGACY_TABLE}')
    print(f'[INT-1784] 模式：{"EXEC（真删）" if args.apply else "DRY-RUN（仅预览）"}')

    try:
        conn = psycopg2.connect(dsn, connect_timeout=10,
                                application_name='int1784_drop_redundant_indexes')
        conn.autocommit = True
    except Exception as exc:  # noqa: BLE001 - 引导链里必须让失败可见
        print(f'[INT-1784] [FAIL] 连接数据库失败：{exc}', flush=True)
        return 1
    try:
        run(conn, apply_changes=args.apply)
    except Exception as exc:  # noqa: BLE001
        print(f'[INT-1784] [FAIL] 执行异常：{exc}', flush=True)
        return 1
    finally:
        try:
            conn.close()
        except Exception:  # noqa: BLE001
            pass
    return 0


if __name__ == '__main__':
    sys.exit(main())
