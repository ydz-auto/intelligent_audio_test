# -*- coding: utf-8 -*-
"""INT-2275：设备参数下沉迁移的语义级幂等单测（fake cursor，不连库）。

引导链每次部署都会带 ``--apply`` 重跑
``scripts/migrations/202611/migrate_device_params_to_profiles.py``。管理员在
UI 上解绑设备 / 删除策略参数 / 软删 default 策略后，重跑不得复活这些状态：

  - 设备绑定：``NOT EXISTS`` 不筛 ``deleted``（有历史绑定行就不再补）；
  - 参数/映射：按唯一键（含已软删行）判重，NULL 维度/方向用 IS NOT DISTINCT FROM；
  - 策略：只有软删行时整个算法类型跳过，不重建策略也不回填。
"""
import importlib.util
import os
import sys

import pytest

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

pytest.importorskip('psycopg2')

_MODULE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    'scripts', 'migrations', '202611', 'migrate_device_params_to_profiles.py')


def _load_migration():
    spec = importlib.util.spec_from_file_location(
        'migrate_device_params_to_profiles_202611', _MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


migration = _load_migration()


def _norm(sql):
    return ' '.join(sql.split())


class FakeCursor:
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
            f'意外的 fetchone；已执行 SQL: {[_norm(s) for s, _ in self.executed]}')
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

    @property
    def params(self):
        return [p for _, p in self.executed]


class FakeConn:
    def __init__(self, cursor):
        self._cursor = cursor
        self.commits = 0

    def cursor(self):
        return self._cursor

    def commit(self):
        self.commits += 1


# ---- SQL 口径 ----

def test_binding_not_exists_ignores_soft_deleted_history():
    """解绑 = 绑定行软删；NOT EXISTS 若只看 deleted=false，每次部署都会补回。"""
    sql = _norm(migration._BIND_DEVICES_SQL)
    assert 'NOT EXISTS (SELECT 1 FROM device_param_bindings b WHERE b.device_id = dv.id)' in sql
    assert 'b.deleted' not in sql
    # 唯一索引仍作并发兜底
    assert 'ON CONFLICT (device_id) WHERE deleted = false DO NOTHING' in sql


@pytest.mark.parametrize('copy_sql', [
    migration._COPY_PARAMS_SQL, migration._COPY_MAPPINGS_SQL])
def test_copy_sql_dedupes_against_history_including_deleted(copy_sql):
    sql = _norm(copy_sql)
    assert 'NOT EXISTS' in sql
    # 判重子查询里不得再出现按 deleted 过滤（已软删行也算「补过」）
    assert 'ppm.deleted' not in sql and 'pp.deleted' not in sql and 'pm.deleted' not in sql


def test_copy_sql_null_key_uses_is_not_distinct_from():
    """direction / dimension_id 可为 NULL，普通 = 会让 NULL 行每次部署重复插入。"""
    assert ('pp.direction IS NOT DISTINCT FROM a.direction'
            in _norm(migration._COPY_PARAMS_SQL))
    assert ('pm.dimension_id IS NOT DISTINCT FROM a.dimension_id'
            in _norm(migration._COPY_MAPPINGS_SQL))


def test_profile_lookup_considers_soft_deleted_rows():
    sql = _norm(migration._GET_ANY_PROFILE_SQL)
    assert 'deleted = false' not in sql
    assert 'COALESCE(deleted, false) ASC' in sql  # 有效行优先


# ---- apply 行为 ----

def _run_apply(fetchone_results, fetchall_results, rowcount_plan=None):
    cursor = FakeCursor(fetchone_results, fetchall_results, rowcount_plan)
    migration.apply(FakeConn(cursor))
    return cursor


def test_apply_skips_type_when_default_profile_soft_deleted(capsys):
    """策略被软删 → 不重建、不回填参数/映射/绑定（整类型跳过）。"""
    cursor = _run_apply(
        fetchone_results=[(77, True)],
        fetchall_results=[[('asr',)]],
    )

    sqls = cursor.sqls
    assert not any(s.startswith('INSERT INTO param_profiles') for s in sqls)
    assert not any(s.startswith('INSERT INTO param_profile_params') for s in sqls)
    assert not any(s.startswith('INSERT INTO param_profile_mappings') for s in sqls)
    assert not any(s.startswith('INSERT INTO device_param_bindings') for s in sqls)
    assert '[skip] asr' in capsys.readouterr().out


def test_apply_reuses_live_profile_without_reinserting(capsys):
    cursor = _run_apply(
        fetchone_results=[(77, False)],
        fetchall_results=[[('asr',)]],
        rowcount_plan={
            'INSERT INTO param_profile_params': 0,
            'INSERT INTO param_profile_mappings': 0,
            'INSERT INTO device_param_bindings': 0,
        },
    )

    sqls = cursor.sqls
    assert not any(s.startswith('INSERT INTO param_profiles') for s in sqls)
    # 参数/映射每条都带同一 profile_id 两次（插入 + 判重）
    copy_params = [p for s, p in cursor.executed
                   if _norm(s).startswith('INSERT INTO param_profile_params')]
    assert copy_params == [(77, 'asr', 77)]
    copy_mappings = [p for s, p in cursor.executed
                     if _norm(s).startswith('INSERT INTO param_profile_mappings')]
    assert copy_mappings == [(77, 'asr', 77)]


def test_apply_creates_profile_only_when_never_existed(capsys):
    cursor = _run_apply(
        fetchone_results=[None, (78,)],
        fetchall_results=[[('asr',)]],
        rowcount_plan={'INSERT INTO param_profiles': 1,
                       'INSERT INTO device_param_bindings': 2},
    )

    sqls = cursor.sqls
    assert sum(1 for s in sqls if s.startswith('INSERT INTO param_profiles')) == 1
    out = capsys.readouterr().out
    assert '新建策略 1 个' in out
    assert '绑定设备 2 台' in out


def test_second_run_inserts_nothing_after_first_apply(monkeypatch):
    """连跑两遍：第二遍（策略已存在、参数/映射/绑定都已补过）插入 0 行。"""
    # 第一遍：策略不存在 → 新建，复制各 1 条、绑定 1 台
    first = FakeCursor(
        fetchone_results=[None, (79,)],
        fetchall_results=[[('asr',)]],
        rowcount_plan={'INSERT INTO param_profiles': 1,
                       'INSERT INTO param_profile_params': 1,
                       'INSERT INTO param_profile_mappings': 1,
                       'INSERT INTO device_param_bindings': 1})
    migration.apply(FakeConn(first))

    # 第二遍：策略已存在（有效），三个 INSERT 的 rowcount 均为 0
    second = FakeCursor(
        fetchone_results=[(79, False)],
        fetchall_results=[[('asr',)]],
        rowcount_plan={'INSERT INTO param_profile_params': 0,
                       'INSERT INTO param_profile_mappings': 0,
                       'INSERT INTO device_param_bindings': 0})
    migration.apply(FakeConn(second))
    assert sum(1 for s in second.sqls if s.startswith('INSERT INTO param_profiles')) == 0
