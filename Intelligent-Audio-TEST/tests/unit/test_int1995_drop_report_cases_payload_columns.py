# -*- coding: utf-8 -*-
"""INT-1995 / 档4 M1：DROP report_cases 九字段 payload 列 + sweep 脚本的纯函数单测

只测脚本自己的判定逻辑（不连真库）：九字段词表、DDL 合成（一条 ALTER）、门禁在
「列存在 / 列已删」两种形态下的行为、幂等判据、以及 sweep 的 anti-join SQL 必须
显式滤 NULL。脚本实测（隔离库上的 DROP → VACUUM FULL → ANALYZE 与 sweep 孤儿
回收）见交付评论里的取证，不在这里起栈。
"""
import importlib.util
import os
import sys

import pytest

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_DROP_SCRIPT = os.path.join(_REPO_ROOT, 'scripts', 'migrations', '202610',
                            'drop_report_cases_payload_columns_int1995.py')
_SWEEP_SCRIPT = os.path.join(_REPO_ROOT, 'scripts', 'migrations', '202610',
                             'sweep_report_case_snapshots_int1995.py')


def _load_script(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class _FakeCursor:
    """按预置响应队列返回结果；记录执行过的语句。"""

    def __init__(self, responses=None):
        self.responses = list(responses or [])
        self.statements = []
        self._last = None

    def execute(self, sql, params=None):
        self.statements.append((sql, params))
        self._last = self.responses.pop(0) if self.responses else None

    def fetchone(self):
        return self._last

    def fetchall(self):
        return self._last or []

    def close(self):
        pass


class _FakeConn:
    def __init__(self, cursor):
        self.autocommit = False
        self._cursor = cursor
        self.closed = False

    def cursor(self):
        return self._cursor

    def close(self):
        self.closed = True


# 列已删后的 report_cases 形态（保留五列 + 4 指针列）
_POST_DROP_COLUMNS = [
    ('id', 'bigint'), ('report_id', 'bigint'), ('test_case_id', 'character varying'),
    ('algorithm_type', 'character varying'), ('logs', 'text'),
    ('snapshot_uri', 'character varying'), ('snapshot_sha256', 'character'),
    ('snapshot_bytes', 'bigint'), ('snapshot_created_at', 'timestamp with time zone'),
    ('created_by_user_id', 'bigint'), ('created_at', 'timestamp with time zone'),
]
_TOAST_PENDING = {'pg_total_relation_size': 258000000, 'pg_relation_size': 64000000,
                  'pg_table_size': 70000000, 'toast_size': 190000000}
_TOAST_RECLAIMED = {'pg_total_relation_size': 46000000, 'pg_relation_size': 44000000,
                    'pg_table_size': 45000000, 'toast_size': 8192}


def test_payload_columns_are_the_nine_snapshot_fields():
    """列词表唯一来源：与 report_case_snapshot_store.PAYLOAD_FIELDS 一致。"""
    m = _load_script(_DROP_SCRIPT, 'int1995_m1')
    from report_service.infrastructure.persistence import report_case_snapshot_store
    assert tuple(m.PAYLOAD_COLUMNS) == tuple(report_case_snapshot_store.PAYLOAD_FIELDS)
    assert len(m.PAYLOAD_COLUMNS) == 9
    assert m.CATEGORY_INDEX == 'idx_report_cases_category'


def test_drop_ddl_is_single_alter_with_if_exists():
    """9 列合成一条 ALTER（只拿一次 ACCESS EXCLUSIVE 锁），且带 IF EXISTS 幂等。"""
    m = _load_script(_DROP_SCRIPT, 'int1995_m1')
    ddl = m.build_drop_ddl(m.PAYLOAD_COLUMNS)
    assert ddl.startswith('ALTER TABLE report_cases ')
    assert ddl.count('ALTER TABLE') == 1
    assert ddl.count('DROP COLUMN IF EXISTS') == 9
    assert 'category' in ddl and 'algorithm_results' in ddl


def test_pending_columns_drives_idempotency():
    m = _load_script(_DROP_SCRIPT, 'int1995_m1')
    both = {name: 'json' for name in m.PAYLOAD_COLUMNS}
    both.update({'snapshot_sha256': 'character', 'id': 'bigint'})
    assert m._pending_columns(both) == list(m.PAYLOAD_COLUMNS)
    # 列已删 → 没有待删项 → 脚本走 [SKIP]
    assert m._pending_columns(dict(_POST_DROP_COLUMNS)) == []


def test_gate_counts_skips_when_pointer_column_gone():
    m = _load_script(_DROP_SCRIPT, 'int1995_m1')
    cur = _FakeCursor()
    assert m.gate_counts(cur, {'id': 'bigint'}) == {'no_pointer': None,
                                                    'dangling': None}
    assert cur.statements == []  # 一条 SQL 都不发


def test_gate_counts_reports_dangling_and_no_pointer():
    m = _load_script(_DROP_SCRIPT, 'int1995_m1')
    columns = {'snapshot_sha256': 'character', 'id': 'bigint'}
    # 快照表存在：no_pointer=1，dangling=0
    cur = _FakeCursor(responses=[(1,), (0,), (0,)])
    result = m.gate_counts(cur, columns)
    assert result == {'no_pointer': 1, 'dangling': 0}
    sqls = [sql for sql, _ in cur.statements]
    assert 'snapshot_sha256 IS NULL' in sqls[0]
    assert 'NOT EXISTS' in sqls[2]  # sqls[1] 是快照表存在性检查


def test_recent_write_violations_uses_per_column_is_not_null():
    """COALESCE 跨 varchar/jsonb 类型无法匹配（实测 DatatypeMismatch），必须逐列 IS NOT NULL。"""
    m = _load_script(_DROP_SCRIPT, 'int1995_m1')
    columns = {name: 'json' for name in m.PAYLOAD_COLUMNS}
    cur = _FakeCursor(responses=[(120,), (0,)])
    recent = m.recent_write_violations(cur, columns, hours=24)
    assert recent == {'rows': 120, 'violations': 0, 'window': 24}
    sql = cur.statements[1][0]
    assert 'COALESCE' not in sql
    assert 'name IS NOT NULL' in sql and 'algorithm_results IS NOT NULL' in sql


def test_run_gates_blocks_when_backfill_gate_not_zero():
    m = _load_script(_DROP_SCRIPT, 'int1995_m1')
    columns = {name: 'json' for name in m.PAYLOAD_COLUMNS}
    columns.update({'snapshot_sha256': 'character', 'snapshot_uri': 'character',
                    'id': 'bigint', 'created_at': 'timestamp with time zone'})
    # gate_counts: no_pointer=(0), table-exists=(0), dangling=(1) → recent rows=100,
    # violations=0 → pointer_stats
    cur = _FakeCursor(responses=[(0,), (0,), (1,), (100,), (0,), (2, 0, 0)])
    args = type('A', (), {'confirm_read_path': True, 'confirm_backup': True,
                          'strict_24h': False, 'ack_no_recent_traffic': False})()
    failures = m.run_gates(cur, columns, args)
    assert any('回填门禁未归零' in item for item in failures)


def test_run_gates_requires_confirm_read_path_and_backup():
    """读路径 / 备份两条 DB 查不出来，必须操作人显式确认。"""
    m = _load_script(_DROP_SCRIPT, 'int1995_m1')
    columns = {name: 'json' for name in m.PAYLOAD_COLUMNS}
    columns.update({'snapshot_sha256': 'character', 'snapshot_uri': 'character',
                    'id': 'bigint', 'created_at': 'timestamp with time zone'})
    cur = _FakeCursor(responses=[(0,), (0,), (0,), (100,), (0,), (2, 0, 0)])
    args = type('A', (), {'confirm_read_path': False, 'confirm_backup': False,
                          'strict_24h': False, 'ack_no_recent_traffic': False})()
    failures = m.run_gates(cur, columns, args)
    assert any('--confirm-read-path' in item for item in failures)
    assert any('--confirm-backup' in item for item in failures)


def test_apply_requires_confirm_read_path(monkeypatch):
    """走真实 parser + migrate()：缺 --confirm-read-path 时返回 4（不动库）。"""
    m = _load_script(_DROP_SCRIPT, 'int1995_m1')
    cur = _FakeCursor(responses=[
        (1,),                                              # _table_exists
        [(name, 'json') for name in m.PAYLOAD_COLUMNS] + _POST_DROP_COLUMNS,
        (258000000, 64000000, 70000000, 190000000),        # _sizes BEFORE
        [('idx_report_cases_report_id',), ('idx_report_cases_test_case_id',),
         ('idx_report_cases_category',)],                 # _existing_indexes
        [],                                                # lock_risks
    ])
    conn = _FakeConn(cur)
    monkeypatch.setattr(m, '_connect', lambda: conn)
    monkeypatch.setattr(m, 'run_gates', lambda *a, **k: [])
    args = m.build_parser().parse_args(['--apply', '--confirm-backup'])
    assert m.migrate(args) == 4
    assert conn.closed is True
    assert not any('DROP' in sql for sql, _ in cur.statements)


def test_parser_flags_do_not_drift():
    m = _load_script(_DROP_SCRIPT, 'int1995_m1')
    args = m.build_parser().parse_args(
        ['--apply', '--confirm-read-path', '--confirm-backup', '--strict-24h'])
    assert args.apply and args.confirm_read_path and args.confirm_backup
    assert args.strict_24h
    assert m.build_parser().parse_args(['--apply']).confirm_read_path is False
    assert m.build_parser().parse_args(['--apply']).confirm_backup is False


def test_vacuum_still_pending_uses_toast_size():
    m = _load_script(_DROP_SCRIPT, 'int1995_m1')
    assert m.vacuum_still_pending(_TOAST_PENDING) is True
    assert m.vacuum_still_pending(_TOAST_RECLAIMED) is False
    assert m.vacuum_still_pending({'toast_size': 0}) is False


def test_apply_after_drop_fails_when_toast_not_reclaimed(monkeypatch, capsys):
    m = _load_script(_DROP_SCRIPT, 'int1995_m1')
    cur = _FakeCursor(responses=[(0,), (0,), (0,), (0,), (2, 0, 0)])
    monkeypatch.setattr(m, 'vacuum_full', lambda *a, **k: pytest.fail('不该重跑 VACUUM FULL'))
    args = m.build_parser().parse_args(
        ['--apply', '--confirm-read-path', '--confirm-backup', '--strict-24h'])
    code = m._after_drop(_FakeConn(cur), cur, dict(_POST_DROP_COLUMNS),
                         args, dict(_TOAST_PENDING), 900000)
    out = capsys.readouterr().out
    assert code == 3
    assert 'TOAST 未回收' in out and '--force-vacuum' in out


def test_apply_after_drop_force_vacuum_reclaims(monkeypatch):
    m = _load_script(_DROP_SCRIPT, 'int1995_m1')
    cur = _FakeCursor(responses=[
        (0,), (0,), (0,), (0,), (2, 0, 0),     # 门禁
        [],                                    # lock_risks
        (46000000, 44000000, 45000000, 8192),  # _sizes(after) 已回收
    ])
    calls = []
    monkeypatch.setattr(m, 'vacuum_full', lambda conn, timeout: calls.append(('vacuum', timeout)))
    monkeypatch.setattr(m, 'analyze', lambda conn: calls.append(('analyze', None)))
    args = m.build_parser().parse_args(
        ['--apply', '--confirm-read-path', '--confirm-backup', '--strict-24h',
         '--force-vacuum'])
    code = m._after_drop(_FakeConn(cur), cur, dict(_POST_DROP_COLUMNS),
                         args, dict(_TOAST_PENDING), 900000)
    assert code == 0
    assert calls == [('vacuum', 900000), ('analyze', None)]


# ------------------------------------------------------------------ sweep

def test_sweep_sql_explicitly_filters_null_pointers():
    """孤儿判定的子查询必须显式 IS NOT NULL——PG 的 NOT IN 遇 NULL 返回空集。"""
    m = _load_script(_SWEEP_SCRIPT, 'int1995_sweep')
    assert 'WHERE snapshot_sha256 IS NOT NULL' in m.SWEEP_SQL
    assert m.SWEEP_SQL.startswith('DELETE FROM report_case_snapshots')
    assert 'NOT IN' in m.SWEEP_SQL


def test_sweep_parser_flags():
    m = _load_script(_SWEEP_SCRIPT, 'int1995_sweep')
    assert m.build_parser().parse_args([]).apply is False
    assert m.build_parser().parse_args(['--apply']).apply is True
