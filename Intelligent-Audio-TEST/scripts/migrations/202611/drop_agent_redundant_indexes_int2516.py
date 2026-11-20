# -*- coding: utf-8 -*-
"""迁移脚本：下线 agent_step / agent_context_snapshot 上与唯一约束完全重复的索引（INT-2516）

背景（INT-2516，2026-11-13 SQL 抽检）：
- `agent_step` 上 `ix_agent_step_run (run_id, "index")` 与唯一约束
  `uq_agent_step_run_index UNIQUE (run_id, "index")` 同列同序；
- `agent_context_snapshot` 上 `ix_agent_context_snapshot_run (run_id, version)` 与
  `uq_agent_context_snapshot_version UNIQUE (run_id, version)` 同列同序。
- 唯一约束自带的 btree 索引已能服务 `run_id` 前缀查询与唯一性校验，普通索引纯写
  放大，没有任何查询收益。

为什么要单独一个「drop 迁移」而不是只改模型 / 建表脚本：
- 索引有两个重建源，必须同时断掉，否则下次部署又被建回来：
  ① ORM 的 `Index(...)`（create_all 建表时创建，已在 INT-2516 移除）；
  ② `scripts/migrations/202611/add_agent_runtime_tables.py` 的 INDEXES 清单
     （部署时重跑，已在 INT-2516 移除）。
- 第三条重建源是「建库早于本卡的存量库」——它只保留这次本脚本兜底删除，
  保证新库与既有库口径一致。

安全边界：
- **索引名 + 定义双匹配**才删：先从 pg_get_indexdef 取实际定义，归一化后与期望
  的 `USING btree (...)` 尾部逐字比对，且校验非 UNIQUE；对不上说明被人改过
  （加列 / 改 WHERE / 变唯一），**跳过并 WARN**，绝不误删。
- 删除前要求「覆盖索引（唯一约束索引）存在且列序完全一致」；覆盖索引缺失时同样
  跳过 —— 宁可不减负，也不让某条查询失去索引。

幂等：所有 DDL 都是 `DROP INDEX IF EXISTS`，删除前先查存在性；第二次执行全部
[SKIP]。

用法：
    python scripts/migrations/202611/drop_agent_redundant_indexes_int2516.py          # 预览（默认）
    python scripts/migrations/202611/drop_agent_redundant_indexes_int2516.py --apply  # 执行

引导链：`docker/db_bootstrap_entrypoint.py` 的 BOOTSTRAP_STEPS 以 `--apply` 调用，
位置在 ㊾-8 agent 七表之后、INT-1741 的 ANALYZE 之前（ANALYZE 必须是引导链末步）。
"""
import argparse
import os
import re
import sys

import psycopg2
from psycopg2 import sql

DEFAULT_DATABASE_URL = (
    'postgresql://intelligent_audio_test:intelligent_audio_test666'
    '@localhost:5432/intelligent_audio_test')


class IndexSpec(object):
    """一条待下线索引的期望定义 + 覆盖它的唯一约束索引。

    columns 是期望定义中 `USING btree (...)` 括号内的列清单，
    与 pg_get_indexdef 归一化后的同段逐字比对（双匹配）。
    """

    __slots__ = ('name', 'table', 'columns', 'covered_by')

    def __init__(self, name, table, columns, covered_by):
        self.name = name
        self.table = table
        self.columns = columns
        self.covered_by = covered_by

    @property
    def expected_tail(self):
        return _normalize(f'using btree ({self.columns})')


# 待删清单（2 个，与唯一约束完全重复；见 INT-2516 卡面证据）
INDEX_SPECS = (
    IndexSpec('ix_agent_step_run', 'agent_step', 'run_id, "index"',
              covered_by='uq_agent_step_run_index'),
    IndexSpec('ix_agent_context_snapshot_run', 'agent_context_snapshot',
              'run_id, version', covered_by='uq_agent_context_snapshot_version'),
)

_INDEXES_SQL = """
SELECT t.relname AS table_name,
       c.relname AS index_name,
       i.indisunique AS is_unique,
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


def fetch_indexes(conn, tables):
    """返回 {(table, index): (is_unique, index_def)}（只取 public 下这些表）。"""
    with conn.cursor() as cur:
        cur.execute(_INDEXES_SQL, (list(tables),))
        return {(row[0], row[1]): (row[2], row[3]) for row in cur.fetchall()}


def plan(indexes, specs=INDEX_SPECS):
    """按「存在 + 非唯一 + 定义匹配 + 覆盖唯一索引在位」筛出待删项。

    返回 (to_drop, skipped)，skipped 是 [(spec, 原因), ...]。
    """
    to_drop, skipped = [], []
    for spec in specs:
        actual = indexes.get((spec.table, spec.name))
        if actual is None:
            skipped.append((spec, 'missing'))
            continue
        is_unique, index_def = actual
        if is_unique:
            skipped.append((spec, 'unique'))
            continue
        if _definition_tail(index_def) != spec.expected_tail:
            skipped.append((spec, 'definition-mismatch'))
            continue
        covering = indexes.get((spec.table, spec.covered_by))
        if covering is None:
            skipped.append((spec, 'covering-missing'))
            continue
        covering_unique, covering_def = covering
        if not covering_unique:
            skipped.append((spec, 'covering-not-unique'))
            continue
        if _definition_tail(covering_def) != spec.expected_tail:
            skipped.append((spec, 'covering-mismatch'))
            continue
        to_drop.append((spec, index_def))
    return to_drop, skipped


_SKIP_DETAIL = {
    'unique': '实际是 UNIQUE 索引，不动',
    'definition-mismatch': '定义与期望不符，疑似被人工改过，跳过',
    'covering-missing': '覆盖的唯一约束索引不存在，删了会失去索引支撑',
    'covering-not-unique': '覆盖索引不是 UNIQUE，删了会失去唯一性索引',
    'covering-mismatch': '覆盖索引列序与期望不一致',
}


def _index_size(cur, name):
    try:
        cur.execute('SELECT pg_size_pretty(pg_relation_size(%s::regclass))', (name,))
        row = cur.fetchone()
        return row[0] if row else '?'
    except Exception:  # noqa: BLE001 - 仅用于日志展示
        return '?'


def run(conn, apply_changes=False, out=print, specs=INDEX_SPECS):
    """核心流程；返回已删除（或预览可删）的索引数。

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
        out(f'[WARN] {spec.table}.{spec.name} 跳过：{_SKIP_DETAIL.get(reason, reason)}')

    if not to_drop:
        out(f'[SKIP] 无可删除的冗余索引（清单 {len(specs)} 个）')
        return 0

    if not apply_changes:
        with conn.cursor() as cur:
            sized = [(spec, _index_size(cur, spec.name)) for spec, _ in to_drop]
        for spec, size in sized:
            out(f'[DRY-RUN] DROP INDEX {spec.name}  ({spec.table}, {size})')
        out(f'[DRY-RUN] 预览模式：以上 {len(sized)} 个索引未删除（加 --apply 执行）')
        return len(sized)

    dropped = 0
    with conn.cursor() as cur:
        for spec, _index_def in to_drop:
            size = _index_size(cur, spec.name)
            cur.execute(sql.SQL('DROP INDEX IF EXISTS {}').format(
                sql.Identifier(spec.name)))
            dropped += 1
            out(f'[DONE] DROP INDEX {spec.name}  ({spec.table}, 释放 {size})')
    out(f'[DONE] 已删除冗余索引 {dropped} 个')
    return dropped


def main(argv=None):
    parser = argparse.ArgumentParser(
        description='INT-2516：下线 agent_step / agent_context_snapshot 冗余索引')
    parser.add_argument('--apply', action='store_true',
                        help='真正执行 DROP（缺省仅预览）')
    parser.add_argument('--database-url', default=None,
                        help='覆盖 DATABASE_URL（默认读环境变量）')
    args = parser.parse_args(argv)

    dsn = args.database_url or os.environ.get('DATABASE_URL') \
        or os.environ.get('DATABASE_URI') or DEFAULT_DATABASE_URL
    print(f'[INT-2516] agent 冗余索引下线：目标 {len(INDEX_SPECS)} 个索引')
    print(f'[INT-2516] 模式：{"EXEC（真删）" if args.apply else "DRY-RUN（仅预览）"}')

    try:
        conn = psycopg2.connect(dsn, connect_timeout=10,
                                application_name='int2516_drop_agent_redundant_indexes')
        conn.autocommit = True
    except Exception as exc:  # noqa: BLE001 - 引导链里必须让失败可见
        print(f'[INT-2516] [FAIL] 连接数据库失败：{exc}', flush=True)
        return 1
    try:
        run(conn, apply_changes=args.apply)
    except Exception as exc:  # noqa: BLE001
        print(f'[INT-2516] [FAIL] 执行异常：{exc}', flush=True)
        return 1
    finally:
        try:
            conn.close()
        except Exception:  # noqa: BLE001
            pass
    return 0


if __name__ == '__main__':
    sys.exit(main())
