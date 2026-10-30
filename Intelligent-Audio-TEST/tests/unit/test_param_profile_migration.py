# -*- coding: utf-8 -*-
"""参数策略迁移脚本（scripts/migrations/202610/add_param_profiles_scope.py）
行为契约单测：不连真 PG，用 fake connection/cursor 验证 dry-run / apply /
rollback 与幂等结构。
"""
import importlib.util
import os
import sys

import pytest

# tests/unit/conftest.py 的 teardown 会导入 shared.infrastructure.config，
# 该模块要求 OSS 凭据（不触达真实 OSS 时也用假值兜底，与既有单测一致）。
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

pytest.importorskip('psycopg2')

_MODULE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    'scripts', 'migrations', '202610', 'add_param_profiles_scope.py',
)


def _load_migration():
    spec = importlib.util.spec_from_file_location(
        'add_param_profiles_scope_202610', _MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


migration = _load_migration()


def _norm(sql):
    return ' '.join(sql.split())


class FakeCursor:
    """记录 SQL 与参数；fetchone 按预置队列出值。"""

    def __init__(self, fetchone_results=None, fetchall_results=None,
                 rowcount_plan=None):
        self.executed = []
        self._fetchone_results = list(fetchone_results or [])
        self._fetchall_results = list(fetchall_results or [])
        self._rowcount_plan = dict(rowcount_plan or {})
        self.rowcount = 0

    def execute(self, sql, params=None):
        self.executed.append((sql, params))
        self.rowcount = 0
        for marker, value in self._rowcount_plan.items():
            if marker in sql:
                self.rowcount = value
                break

    def fetchone(self):
        assert self._fetchone_results, (
            f'意外的 fetchone 调用；已执行 SQL: '
            f'{[_norm(s) for s, _ in self.executed]}')
        return self._fetchone_results.pop(0)

    def fetchall(self):
        assert self._fetchall_results, '意外的 fetchall 调用'
        return self._fetchall_results.pop(0)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    @property
    def sqls(self):
        return [_norm(sql) for sql, _ in self.executed]


class FakeConn:
    def __init__(self, cursor):
        self._cursor = cursor
        self.commits = 0
        self.rollbacks = 0
        self.closed = False

    def cursor(self):
        return self._cursor

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.closed = True


def _make(fetchone_results=None, fetchall_results=None, rowcount_plan=None):
    cursor = FakeCursor(fetchone_results, fetchall_results, rowcount_plan)
    return cursor, FakeConn(cursor)


def _run_main(monkeypatch, conn, argv):
    monkeypatch.setattr(migration, '_connect', lambda: conn)
    monkeypatch.setattr(sys, 'argv', argv)
    migration.main()


def test_dry_run_never_writes(monkeypatch, capsys):
    cursor, conn = _make(fetchone_results=[(True,), (0,), (0,), (0,)])
    _run_main(monkeypatch, conn, ['prog'])

    out = capsys.readouterr().out
    assert '[dry-run]' in out
    sqls = cursor.sqls
    for ddl in migration.DDL_FORWARD:
        assert _norm(ddl) not in sqls
    assert not any('INSERT INTO param_profile_params' in s for s in sqls)
    assert not any('INSERT INTO param_profile_mappings' in s for s in sqls)
    assert not any(s.startswith('UPDATE algorithm_api_params') for s in sqls)
    assert conn.commits == 0
    assert conn.closed is True


def test_apply_cross_db_executes_ddl_and_copy_without_backfill(
        monkeypatch, capsys):
    cursor, conn = _make(
        fetchone_results=[(True,), (0,), (0,), (0,),
                          (False,), (101,), (102,)],
        fetchall_results=[[('asr',), ('tts',)]],
        rowcount_plan={
            'INSERT INTO param_profile_params': 2,
            'INSERT INTO param_profile_mappings': 1,
            'UPDATE algorithm_api_params': 2,
            'UPDATE param_mappings': 1,
        },
    )
    _run_main(monkeypatch, conn, ['prog', '--apply'])

    sqls = cursor.sqls
    for ddl in migration.DDL_FORWARD:
        assert _norm(ddl) in sqls

    assert sum(1 for s in sqls if s.startswith('INSERT INTO param_profiles')) == 2
    assert sum(1 for s in sqls if s.startswith(
        'INSERT INTO param_profile_params')) == 2
    assert sum(1 for s in sqls if s.startswith(
        'INSERT INTO param_profile_mappings')) == 2
    assert sum(1 for s in sqls if s.startswith(
        'UPDATE algorithm_api_params SET deleted = true')) == 2
    assert sum(1 for s in sqls if s.startswith(
        'UPDATE param_mappings SET deleted = true')) == 2

    # 跨库（apis 不在本库）→ 不回填绑定
    assert not any('INSERT INTO api_param_bindings' in s for s in sqls)
    assert conn.commits == 1

    out = capsys.readouterr().out
    assert '不同库，跳过回填' in out


def test_apply_same_db_backfills_bindings(monkeypatch, capsys):
    cursor, conn = _make(
        fetchone_results=[(True,), (0,), (0,), (0,), (True,), (201,)],
        fetchall_results=[[('asr',)]],
        rowcount_plan={
            'INSERT INTO param_profile_params': 2,
            'INSERT INTO param_profile_mappings': 1,
            'INSERT INTO api_param_bindings': 3,
            'UPDATE algorithm_api_params': 2,
            'UPDATE param_mappings': 1,
        },
    )
    _run_main(monkeypatch, conn, ['prog', '--apply'])

    sqls = cursor.sqls
    backfill = [s for s in sqls if s.startswith('INSERT INTO api_param_bindings')]
    assert len(backfill) == 1
    assert conn.commits == 1

    out = capsys.readouterr().out
    assert '同库，可回填绑定' in out
    assert 'apis绑定=3' in out


def test_idempotent_sql_structure_and_double_apply(monkeypatch):
    for ddl in migration.DDL_FORWARD:
        assert 'IF NOT EXISTS' in ddl

    for copy_sql in (migration._COPY_PARAMS_SQL, migration._COPY_MAPPINGS_SQL):
        assert 'ON CONFLICT' in copy_sql
        assert 'DO NOTHING' in copy_sql
    assert 'ON CONFLICT' in migration._UPSERT_PROFILE_SQL

    cursor, conn = _make(
        fetchone_results=[(False,), (1,), (False,), (1,)],
        fetchall_results=[[('asr',)], [('asr',)]],
        rowcount_plan={
            'INSERT INTO param_profile_params': 1,
            'INSERT INTO param_profile_mappings': 0,
            'UPDATE algorithm_api_params': 0,
            'UPDATE param_mappings': 0,
        },
    )
    migration.apply(conn)
    migration.apply(conn)

    sqls = cursor.sqls
    assert sum(1 for s in sqls if s.startswith('INSERT INTO param_profiles')) == 2
    assert sum(1 for s in sqls if s.startswith(
        'INSERT INTO param_profile_params')) == 2
    assert conn.commits == 2


def test_rollback_drops_tables_in_order(monkeypatch, capsys):
    cursor, conn = _make()
    _run_main(monkeypatch, conn, ['prog', '--rollback'])

    sqls = cursor.sqls
    drops = [s for s in sqls if s.startswith('DROP TABLE IF EXISTS')]
    assert drops == [
        'DROP TABLE IF EXISTS api_param_bindings',
        'DROP TABLE IF EXISTS param_profile_mappings',
        'DROP TABLE IF EXISTS param_profile_params',
        'DROP TABLE IF EXISTS param_profiles',
    ]
    assert conn.commits == 1

    out = capsys.readouterr().out
    assert '回滚' in out
    assert '[warn]' in out


def test_apply_raises_when_profile_id_unresolvable(monkeypatch):
    cursor, conn = _make(
        fetchone_results=[(False,), None, None],
        fetchall_results=[[('asr',)]],
    )
    with pytest.raises(RuntimeError):
        migration.apply(conn)

    assert conn.commits == 0
