# -*- coding: utf-8 -*-
"""INT-1741：统计重置后自动重建表统计（引导链 ㊸）+ 只读/幂等守卫。

背景（2026-10-24 真实库实测）：
- postgres 容器 2026-10-23 一天 7 次非正常关闭，PGDATA 的 pg_stat/ 没有
  pgstat.stat 快照 → 每次崩溃重启统计计数器全部归零；
- autoanalyze 阈值 = 50 + 0.1×reltuples，logs 304k 行要约 3 万次变更才触发，
  于是 83/95 张表 last_analyze 恒为 NULL、n_live_tup 与真实行数差 2~3 个数量级。

本文件把修复钉死（不连库，用假连接驱动）：
1. 引导链 BOOTSTRAP_STEPS 必须包含该步且带 --apply（否则部署时只预览不执行）；
2. 脚本对数据库只发两类语句：只读的筛表 SELECT 与 `ANALYZE <schema>.<table>`——
   绝不出现 VACUUM FULL / TRUNCATE / DROP / DELETE / UPDATE / 结构变更；
3. 默认 dry-run：不加 --apply 一条 ANALYZE 都不发；
4. --apply 只分析「本统计周期从未分析过且行数 ≥ 门槛」的表，且逐表容错
   （单表失败 WARN 跳过，不阻断引导）；
5. track_counts=off 时跳过（统计视图恒 NULL，无法判定）；
6. 幂等：无待分析表时什么都不发。
"""
import importlib.util
import os
import sys

from psycopg2 import sql as _pg_sql

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
_MIGRATION_REL = ('scripts/migrations/202610/'
                  'analyze_stale_statistics_int1741.py')
_MIGRATION = os.path.join(PROJECT_ROOT, *_MIGRATION_REL.split('/'))
_BOOTSTRAP_PATH = os.path.join(PROJECT_ROOT, 'docker',
                               'db_bootstrap_entrypoint.py')

# 模块 import 期只校验配置非空，不连库
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')
os.environ.setdefault('DATABASE_URL', 'postgresql://u:p@localhost:1/unused')


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_script = _load(_MIGRATION, 'int1741_analyze_stats')
_bootstrap = _load(_BOOTSTRAP_PATH, 'int1741_db_bootstrap')


def _sql_text(query):
    """把 psycopg2.sql.Composed 渲染成可断言的文本（假连接没有真连接上下文）。"""
    if isinstance(query, str):
        return query
    seq = getattr(query, 'seq', None)
    if seq is None:
        return repr(query)
    parts = []
    for item in seq:
        if isinstance(item, _pg_sql.Identifier):
            parts.append('"%s"' % item.string.replace('"', '""'))
        elif isinstance(item, _pg_sql.SQL):
            parts.append(item.string)
        else:
            parts.append(str(item))
    return ''.join(parts)


class _FakeCursor:
    """记录发出的每一条 SQL；按预设结果回答 fetchone/fetchall。"""

    def __init__(self, conn):
        self._conn = conn
        self._rows = []

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def execute(self, query, params=None):
        text = _sql_text(query)
        self._conn.executed.append((text, params))
        if self._conn.fail_on and self._conn.fail_on in text:
            raise RuntimeError('模拟锁超时')
        if 'track_counts' in text:
            self._rows = [('on' if self._conn.track_counts else 'off',)]
        elif 'FROM pg_class c' in text:
            min_rows = params[0] if params else 0
            self._rows = [row for row in self._conn.stale_rows
                          if row[2] >= min_rows]
        else:
            self._rows = []

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)


class _FakeConn:
    def __init__(self, stale_rows=(), track_counts=True, fail_on=None):
        self.stale_rows = list(stale_rows)
        self.track_counts = track_counts
        self.fail_on = fail_on
        self.executed = []
        self.autocommit = True

    def cursor(self):
        return _FakeCursor(self)

    def rollback(self):
        pass

    def close(self):
        pass

    @property
    def analyze_statements(self):
        return [text for text, _params in self.executed if text.startswith('ANALYZE')]


def _collect():
    out = []
    return out, out.append


# ---------------------------------------------------------------- 引导链登记

def test_migration_file_exists():
    assert os.path.isfile(_MIGRATION), f'迁移脚本不存在: {_MIGRATION_REL}'


def test_bootstrap_chain_includes_step_with_apply():
    """部署链路必须真的执行（带 --apply），否则只会打一行预览。"""
    steps = [step for step in _bootstrap.BOOTSTRAP_STEPS
             if step[1] == _MIGRATION_REL]
    assert steps, f'BOOTSTRAP_STEPS 未包含 {_MIGRATION_REL}：崩溃重启后无人重建统计'
    assert '--apply' in steps[0], f'{_MIGRATION_REL} 在引导链中缺少 --apply（只预览不执行）'


def test_bootstrap_step_is_last():
    """统计兜底必须在所有 DDL/种子之后（否则分析完又被后续 DDL 作废）。"""
    assert _bootstrap.BOOTSTRAP_STEPS[-1][1] == _MIGRATION_REL


# ---------------------------------------------------------------- 只读/不破坏

def test_only_analyze_and_readonly_select_are_issued():
    conn = _FakeConn(stale_rows=[('public', 'logs', 304710, 334)])
    out, sink = _collect()
    _script.run(conn, apply_changes=True, out=sink)

    assert conn.analyze_statements == ['ANALYZE "public"."logs"']
    for text, _params in conn.executed:
        head = text.strip().upper()
        assert head.startswith('ANALYZE') or head.startswith('SELECT'), \
            f'出现了非只读/非 ANALYZE 语句: {text}'
        for forbidden in ('VACUUM', 'TRUNCATE', 'DROP', 'DELETE ', 'UPDATE ',
                          'INSERT', 'ALTER', 'CREATE'):
            assert forbidden not in head, f'禁止的破坏性语句: {text}'


def test_dry_run_issues_no_analyze():
    conn = _FakeConn(stale_rows=[('public', 'logs', 304710, 334),
                                 ('public', 'report_cases', 33919, 5)])
    out, sink = _collect()
    handled = _script.run(conn, apply_changes=False, out=sink)

    assert handled == 2
    assert conn.analyze_statements == []
    assert any('预览模式' in line for line in out)


# ---------------------------------------------------------------- 行为

def test_apply_analyzes_each_stale_table():
    rows = [('public', 'logs', 304710, 334),
            ('public', 'report_cases', 33919, 5),
            ('public', 'test_result_dimensions', 51857, 26)]
    conn = _FakeConn(stale_rows=rows)
    out, sink = _collect()
    done = _script.run(conn, apply_changes=True, out=sink)

    assert done == 3
    assert conn.analyze_statements == [
        'ANALYZE "public"."logs"',
        'ANALYZE "public"."report_cases"',
        'ANALYZE "public"."test_result_dimensions"',
    ]
    assert any('已分析 3/3' in line for line in out)


def test_min_rows_filters_small_tables():
    """行数门槛以下的表交给 autoanalyze，不占部署时间。"""
    conn = _FakeConn(stale_rows=[('public', 'logs', 304710, 334),
                                 ('public', 'tiny_table', 12, 12)])
    out, sink = _collect()
    _script.run(conn, min_rows=1000, apply_changes=True, out=sink)
    assert conn.analyze_statements == ['ANALYZE "public"."logs"']


def test_single_table_failure_is_skipped_not_fatal():
    """单表被锁挡住只 WARN，其余表照做，且不向引导链抛异常。"""
    conn = _FakeConn(stale_rows=[('public', 'logs', 304710, 334),
                                 ('public', 'report_cases', 33919, 5)],
                     fail_on='report_cases')
    out, sink = _collect()
    done = _script.run(conn, apply_changes=True, out=sink)

    assert done == 1
    assert any('[WARN]' in line and 'report_cases' in line for line in out)
    assert 'ANALYZE "public"."logs"' in conn.analyze_statements


def test_no_stale_tables_is_noop():
    conn = _FakeConn(stale_rows=[])
    out, sink = _collect()
    assert _script.run(conn, apply_changes=True, out=sink) == 0
    assert conn.analyze_statements == []
    assert any('无需处理' in line for line in out)


def test_track_counts_off_skips():
    conn = _FakeConn(stale_rows=[('public', 'logs', 304710, 334)],
                     track_counts=False)
    out, sink = _collect()
    assert _script.run(conn, apply_changes=True, out=sink) == 0
    assert conn.analyze_statements == []
    assert any('track_counts=off' in line for line in out)


# ---------------------------------------------------------------- 入口不阻断

def test_main_returns_zero_when_db_unreachable(monkeypatch):
    """统计刷新是 best-effort：连不上库也不能把整套部署挡在门外。"""
    def _boom(*a, **kw):
        raise RuntimeError('connection refused')
    monkeypatch.setattr(_script.psycopg2, 'connect', _boom)
    assert _script.main(['--apply']) == 0
