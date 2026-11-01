# -*- coding: utf-8 -*-
"""INT-2303：引导链软删维度树未级联 param_profile_mappings / 映射复制未过滤软删维度。

两个根因各钉一组单测（不连库，用假 conn 记录 SQL）：

1. ``202609/seed_interruption_dimensions.py::_soft_delete_dimension_tree`` 的级联
   不含 ``param_profile_mappings``：软删维度树后，指向它的参数策略映射原样存活，
   留下「生效映射指向已软删维度」的悬空行。
2. ``202611/migrate_device_params_to_profiles.py::_COPY_MAPPINGS_SQL`` 不看维度
   ``deleted``：源映射自身没软删、但维度已软删时，每轮引导都会把它复制成一条新的
   生效策略映射。复制口径只认未软删维度，``dimension_id IS NULL``（设备侧允许不挂
   维度）照抄；另外复制前对新旧孤儿做一次幂等回收。
"""
import importlib.util
import os
import sys

import pytest

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

pytest.importorskip('psycopg2')

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

SEED_PATH = os.path.join(
    PROJECT_ROOT, 'scripts', 'migrations', '202609',
    'seed_interruption_dimensions.py')
MIGRATION_PATH = os.path.join(
    PROJECT_ROOT, 'scripts', 'migrations', '202611',
    'migrate_device_params_to_profiles.py')


def _load(module_name, path):
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


seed = _load('int2303_seed_interruption_dimensions', SEED_PATH)
migration = _load('int2303_migrate_device_params_to_profiles', MIGRATION_PATH)


def _norm(sql):
    return ' '.join(sql.split())


# ============================================================
# 1. 软删维度树 → param_profile_mappings 级联软删
# ============================================================

class _FakeResult:
    def __init__(self, rows=None):
        self._rows = list(rows or [])
        self.rowcount = len(self._rows)

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._rows[0] if self._rows else None


class _SeedFakeConn:
    """按 parent_dimension_id 返回子树；记录全部 (sql, params)。"""

    def __init__(self, children=None):
        self.children = dict(children or {})
        self.calls = []

    def execute(self, stmt, params=None):
        sql = str(stmt)
        bound = dict(params or {})
        self.calls.append((sql, bound))
        if 'parent_dimension_id = :pid' in sql:
            return _FakeResult(self.children.get(bound.get('pid'), []))
        return _FakeResult()

    def updates(self, table):
        marker = f'update {table.lower()} set'
        return [c for c in self.calls
                if c[0].lower().lstrip().startswith('update')
                and marker in _norm(c[0]).lower()]


def test_soft_delete_tree_cascades_to_param_profile_mappings():
    """软删维度树后，指向它的 param_profile_mappings 必须全部置 deleted=TRUE。"""
    conn = _SeedFakeConn()
    seed._soft_delete_dimension_tree(conn, 412, '单测')

    rows = conn.updates('param_profile_mappings')
    assert rows, '软删维度树必须级联 param_profile_mappings'
    assert 'deleted = true' in _norm(rows[0][0]).lower()
    assert "where dimension_id = :did" in _norm(rows[0][0]).lower()
    assert rows[0][1]['did'] == 412


def test_soft_delete_tree_cascades_children_profile_mappings():
    """子维度递归软删时同样级联（子维度也能被映射引用）。"""
    conn = _SeedFakeConn(children={412: [(413, '子维度')]})
    seed._soft_delete_dimension_tree(conn, 412, '单测')

    dids = {c[1]['did'] for c in conn.updates('param_profile_mappings')}
    assert dids == {412, 413}


def test_soft_delete_tree_keeps_existing_cascades():
    """原有级联一个都不能少（新增的 param_profile_mappings 只是多一张表）。"""
    conn = _SeedFakeConn()
    seed._soft_delete_dimension_tree(conn, 412, '单测')

    for table in ('dimensions', 'evaluation_dimension_params', 'param_mappings',
                  'algorithm_dimension_relations', 'param_profile_mappings'):
        rows = conn.updates(table)
        assert rows, f'{table} 未被级联软删'
        assert 'deleted = true' in _norm(rows[0][0]).lower(), table


# ============================================================
# 2. 映射复制只看未软删维度；复制前幂等回收孤儿
# ============================================================

def test_copy_mappings_sql_excludes_soft_deleted_dimension():
    sql = _norm(migration._COPY_MAPPINGS_SQL)
    assert ('EXISTS (SELECT 1 FROM dimensions d '
            'WHERE d.id = a.dimension_id AND d.deleted IS NOT TRUE)') in sql


def test_copy_mappings_sql_keeps_null_dimension_rows():
    """dimension_id 为 NULL 是设备侧合法形态，不能因 exists 判定被误伤。"""
    sql = _norm(migration._COPY_MAPPINGS_SQL)
    assert 'a.dimension_id IS NULL OR EXISTS' in sql


def test_copy_mappings_dedupe_still_counts_soft_deleted_profile_rows():
    """判重仍不筛 deleted（INT-2275 口径）：删掉的策略映射不得被补回。"""
    assert 'pm.deleted' not in _norm(migration._COPY_MAPPINGS_SQL)


def test_purge_sql_only_touches_rows_whose_dimension_is_soft_deleted():
    sql = _norm(migration._PURGE_DANGLING_MAPPINGS_SQL)
    low = sql.lower()
    assert low.startswith('update param_profile_mappings ppm set deleted = true')
    assert 'd.deleted is true' in low          # 维度确实已软删
    assert 'ppm.deleted is not true' in low    # 只碰生效行（含历史 NULL）
    assert 'd.id = ppm.dimension_id' in low    # NULL dimension_id 不参与 join


def test_required_columns_include_dimensions_deleted():
    assert 'dimensions.deleted' in migration.REQUIRED_COLUMNS


# ---- apply 行为 ----

class _FakeCursor:
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
        assert self._fetchone_results, '意外的 fetchone'
        return self._fetchone_results.pop(0)

    def fetchall(self):
        assert self._fetchall_results, '意外的 fetchall'
        return self._fetchall_results.pop(0)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    @property
    def sqls(self):
        return [_norm(sql) for sql, _ in self.executed]


class _FakeConn:
    def __init__(self, cursor):
        self._cursor = cursor
        self.commits = 0

    def cursor(self):
        return self._cursor

    def commit(self):
        self.commits += 1


def _run_apply(capsys, rowcount_plan):
    cursor = _FakeCursor(fetchone_results=[(77, False)],
                         fetchall_results=[[('asr',)]],
                         rowcount_plan=rowcount_plan)
    migration.apply(_FakeConn(cursor))
    return cursor, capsys.readouterr().out


def test_apply_purges_before_copying(capsys):
    """先回收再复制：复制结束前库里已无悬空行，NOT EXISTS 判重看到的是干净状态。"""
    cursor, out = _run_apply(capsys, {
        'UPDATE param_profile_mappings': 3,
        'INSERT INTO param_profile_mappings': 0,
    })

    sqls = cursor.sqls
    purge = next(i for i, s in enumerate(sqls)
                 if s.startswith('UPDATE param_profile_mappings'))
    copy = next(i for i, s in enumerate(sqls)
                if s.startswith('INSERT INTO param_profile_mappings'))
    assert purge < copy
    assert '回收悬空映射 3 条' in out


def test_apply_second_run_purges_and_copies_nothing(capsys):
    """幂等：第二遍回收 0 条、复制 0 条，且不再新建策略/绑定。"""
    cursor, out = _run_apply(capsys, {
        'UPDATE param_profile_mappings': 0,
        'INSERT INTO param_profile_mappings': 0,
        'INSERT INTO param_profile_params': 0,
        'INSERT INTO device_param_bindings': 0,
    })

    assert sum(1 for s in cursor.sqls if s.startswith('UPDATE param_profile_mappings')) == 1
    assert '回收悬空映射 0 条' in out
    assert '复制参数 0 条、映射 0 条' in out
    assert '绑定设备 0 台' in out
