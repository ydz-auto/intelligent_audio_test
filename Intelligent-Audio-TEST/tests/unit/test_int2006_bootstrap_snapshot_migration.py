# -*- coding: utf-8 -*-
"""INT-2006：档4 R1 部署会打断 db_bootstrap 的修复守卫。

背景（INT-1994 的部署前核对）：引导链 ① ``create_all_tables.py`` 先按模型建出
``report_case_snapshots``，到 ㊽-7 迁移步时 ``need_table=False``、``missing=4`` →
走 apply 分支；旧模型是裸 ``DateTime`` → PG ``timestamp without time zone``，而
迁移 ``_verify`` 期望 ``timestamptz`` → FAIL → ``SystemExit(3)`` → 整条引导链失败
（部署打不出去）。同一次部署重试又是 ``missing=0`` 的 ``[SKIP]`` 早退，早退既跳过
``SET STORAGE EXTERNAL`` 又让 ``_verify`` 的 FAIL 不影响退出码 → 假通过。

本文件把修复钉死（不连库，用内存假库驱动 —— 与 test_int1741 / test_int1784 同法）：
1. 模型两侧都声明 ``timezone=True``（全新库 create_all 才与迁移的期望一致），
   但 ``report_cases`` 既有的 ``created_at`` 不许跟着改；
2. 部署形态（表在、4 列缺）→ apply 后 4 列到位、``payload_gz`` 存储 EXTERNAL、
   退出码 0；
3. ``[SKIP]`` 早退仍执行 ``STORAGE_SQL`` 并按 ``_verify`` 决定退出码（FAIL → 3）；
4. 表已存在但 ``created_at`` 为 no-tz 的历史库 → 幂等自愈成 timestamptz；
5. 引导链里该步仍在 ANALYZE 之前且带 ``--apply``（编号不变）。
"""
import importlib.util
import os
import sys

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')
os.environ.setdefault('DATABASE_URL', 'postgresql://u:p@localhost:1/unused')

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
_MIGRATION = os.path.join(PROJECT_ROOT, 'scripts', 'migrations', '202610',
                          'add_report_case_snapshots_int1994.py')
_BOOTSTRAP_PATH = os.path.join(PROJECT_ROOT, 'docker', 'db_bootstrap_entrypoint.py')


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_script = _load(_MIGRATION, 'int2006_add_report_case_snapshots')

#: information_schema.columns 的期望列形态（类型, 长度, 可空）
_TSTZ = ('timestamp with time zone', None, 'NO', None)
_NO_TZ = ('timestamp without time zone', None, 'NO', None)


# ------------------------------------------------------------------ 内存假库

class _FakeState:
    """最小 schema 状态：{表: {列: (data_type, max_len, is_nullable, default)}}。"""

    def __init__(self, tables, storage='x'):
        self.tables = {name: dict(cols) for name, cols in tables.items()}
        self.storage = storage
        self.executed = []
        self.commits = 0


class _FakeCursor:
    def __init__(self, state):
        self._state = state
        self._rows = []
        self.closed = False

    # -------------------------------------------------- psycopg2 接口
    def execute(self, sql, params=None):
        self._state.executed.append(sql if not params else (sql, params))
        text = ' '.join(sql.split())
        self._rows = []

        if text.startswith('SET '):
            return
        if text.startswith('SELECT 1 FROM information_schema.tables'):
            if params[0] in self._state.tables:
                self._rows = [(1,)]
            return
        if text.startswith('SELECT column_name, data_type'):
            table = params[0]
            for name, info in self._state.tables.get(table, {}).items():
                data_type, max_len, nullable, default = info
                self._rows.append((name, data_type, max_len, nullable, default))
            return
        if text.startswith('SELECT DISTINCT l.pid') or text.startswith('SELECT pid FROM pg_locks'):
            return
        if text.startswith('SELECT attname, attstorage FROM pg_attribute'):
            if params[0] in self._state.tables:
                self._rows = [('payload_gz', self._state.storage)]
            return
        if text.startswith('COMMENT ON'):
            return

        snapshot = _script.SNAPSHOT_TABLE
        if text.startswith(f'CREATE TABLE IF NOT EXISTS {snapshot}'):
            # CREATE_TABLE_SQL 原文即 timestamptz（INT-2006 后与模型一致）
            self._state.tables[snapshot] = {
                'sha256': ('character', 64, 'NO', None),
                'payload_gz': ('bytea', None, 'NO', None),
                'payload_bytes': ('integer', None, 'YES', None),
                'created_at': ('timestamp with time zone', None, 'NO', 'now()'),
            }
            return
        if text.startswith(f'ALTER TABLE {snapshot} ALTER COLUMN payload_gz SET STORAGE'):
            self._state.storage = 'e'
            return
        if text.startswith(f'ALTER TABLE {snapshot} ALTER COLUMN created_at TYPE timestamptz'):
            cols = self._state.tables.get(snapshot)
            assert cols is not None, '类型自愈前表必须已存在'
            old = cols['created_at']
            cols['created_at'] = ('timestamp with time zone',) + old[1:]
            return
        if text.startswith(f'ALTER TABLE {_script.CASES_TABLE} ADD COLUMN'):
            self._apply_add_columns(text)
            return
        raise AssertionError(f'未预期的 SQL：{text}')

    def _apply_add_columns(self, text):
        cols = self._state.tables.setdefault(_script.CASES_TABLE, {})
        for part in text.split('ADD COLUMN IF NOT EXISTS ')[1:]:
            name, _, ddl_type = part.partition(' ')
            ddl_type = ddl_type.split(',')[0].strip()
            if ddl_type == 'timestamptz':
                cols[name] = ('timestamp with time zone', None, 'YES', None)
            elif ddl_type.startswith('varchar('):
                cols[name] = ('character varying', int(ddl_type[8:-1]), 'YES', None)
            elif ddl_type.startswith('char('):
                cols[name] = ('character', int(ddl_type[5:-1]), 'YES', None)
            elif ddl_type == 'bigint':
                cols[name] = ('bigint', None, 'YES', None)
            else:
                raise AssertionError(f'未预期的列类型：{ddl_type}')

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)

    def close(self):
        self.closed = True


class _FakeConn:
    def __init__(self, state):
        self._state = state
        self.autocommit = True
        self.committed = 0
        self.rolled_back = 0

    def cursor(self):
        return _FakeCursor(self._state)

    def commit(self):
        self.committed += 1
        self._state.commits += 1

    def rollback(self):
        self.rolled_back += 1

    def close(self):
        pass


def _state(tables, storage='x'):
    """默认给一张「有 report_cases、没有新表新列」的部署形态库。"""
    base = {_script.CASES_TABLE: {
        'id': ('bigint', None, 'NO', None),
        'created_at': _NO_TZ,
    }}
    base.update(tables)
    return _FakeState(base, storage=storage)


def _snapshot_table(created_at=_TSTZ):
    return {
        'sha256': ('character', 64, 'NO', None),
        'payload_gz': ('bytea', None, 'NO', None),
        'payload_bytes': ('integer', None, 'YES', None),
        'created_at': created_at,
    }


def _cases_with_pointers():
    return {
        'id': ('bigint', None, 'NO', None),
        'created_at': _NO_TZ,
        'snapshot_uri': ('character varying', 128, 'YES', None),
        'snapshot_sha256': ('character', 64, 'YES', None),
        'snapshot_bytes': ('bigint', None, 'YES', None),
        'snapshot_created_at': ('timestamp with time zone', None, 'YES', None),
    }


def _run(monkeypatch, state, dry_run=False):
    """用假连接跑一次 migrate()，返回假连接（SystemExit 由调用方接）。"""
    monkeypatch.setattr(_script, '_connect', lambda: _FakeConn(state))
    _script.migrate(dry_run=dry_run)
    return state


# ------------------------------------------------------------ 1. 模型对齐文档

class TestModelTypes:
    def test_snapshot_created_at_is_timezone_aware(self):
        from report_service.infrastructure.persistence.models import ReportCaseSnapshot
        col = ReportCaseSnapshot.__table__.c.created_at
        assert col.type.timezone is True
        assert col.nullable is False

    def test_pointer_snapshot_created_at_is_timezone_aware(self):
        from report_service.infrastructure.persistence.models import ReportCase
        col = ReportCase.__table__.c.snapshot_created_at
        assert col.type.timezone is True
        assert col.nullable is True

    def test_report_cases_own_timestamps_stay_naive(self):
        """全库 created_at/updated_at 是 no-tz；本卡只改快照相关列。"""
        from report_service.infrastructure.persistence.models import ReportCase
        assert ReportCase.__table__.c.created_at.type.timezone is False
        assert ReportCase.__table__.c.updated_at.type.timezone is False

    def test_create_table_ddl_matches_model(self):
        """迁移里的 CREATE TABLE 与模型都写 timestamptz，create_all 后不会再对不上。"""
        assert 'created_at    timestamptz NOT NULL DEFAULT now()' in _script.CREATE_TABLE_SQL


# ------------------------------------------------- 2. 部署形态：表在、4 列缺

class TestDeploymentShape:
    def test_missing_columns_apply_then_exit_zero(self, monkeypatch):
        state = _state({_script.SNAPSHOT_TABLE: _snapshot_table()})
        _run(monkeypatch, state)   # 不抛 SystemExit 即退出码 0

        cases = state.tables[_script.CASES_TABLE]
        for name in ('snapshot_uri', 'snapshot_sha256', 'snapshot_bytes',
                     'snapshot_created_at'):
            assert name in cases
        assert cases['snapshot_created_at'][0] == 'timestamp with time zone'
        assert state.storage == 'e'
        assert state.commits >= 1

    def test_second_run_is_noop_but_still_verifies(self, monkeypatch):
        state = _state({_script.SNAPSHOT_TABLE: _snapshot_table()})
        _run(monkeypatch, state)
        executed_before = len(state.executed)
        _run(monkeypatch, state)   # 第二次仍必须能过（幂等）

        replay = [s for s in state.executed[executed_before:]
                  if isinstance(s, str) and s.startswith('ALTER TABLE')]
        # 只有幂等的 STORAGE 会重发，ADD COLUMN / 类型自愈都不再出现
        assert all('SET STORAGE EXTERNAL' in s for s in replay)


# ------------------------------------- 3. SKIP 早退仍校验、并按校验决定退出码

class TestSkipBranchStillVerifies:
    def test_skip_branch_repairs_storage_and_exits_zero(self, monkeypatch):
        """全新库形态（表与列都由 create_all 建好）：早退也必须执行 STORAGE。"""
        state = _state({
            _script.SNAPSHOT_TABLE: _snapshot_table(),
            _script.CASES_TABLE: _cases_with_pointers(),
        }, storage='x')
        _run(monkeypatch, state)
        assert state.storage == 'e'

    def test_skip_branch_fails_nonzero_when_verify_fails(self, monkeypatch):
        """列形状偏离（= 静默漂移）时不再假通过：退出码必须非 0。"""
        cases = _cases_with_pointers()
        cases['snapshot_uri'] = ('text', None, 'YES', None)   # 期望 varchar(128)
        state = _state({
            _script.SNAPSHOT_TABLE: _snapshot_table(),
            _script.CASES_TABLE: cases,
        })
        with pytest.raises(SystemExit) as excinfo:
            _run(monkeypatch, state)
        assert excinfo.value.code == 3

    def test_dry_run_never_executes_storage(self, monkeypatch):
        state = _state({
            _script.SNAPSHOT_TABLE: _snapshot_table(),
            _script.CASES_TABLE: _cases_with_pointers(),
        })
        _run(monkeypatch, state, dry_run=True)
        assert state.storage == 'x'
        assert not any('SET STORAGE' in s for s in state.executed
                       if isinstance(s, str))


# ------------------------------------------------------- 4. no-tz 类型幂等自愈

class TestTypeDriftSelfHeal:
    def test_no_tz_created_at_is_healed(self, monkeypatch):
        """上一次失败部署已经把表建出来（no-tz），不自愈就永久偏离文档 §3.2。"""
        state = _state({
            _script.SNAPSHOT_TABLE: _snapshot_table(created_at=_NO_TZ),
            _script.CASES_TABLE: _cases_with_pointers(),
        }, storage='e')
        _run(monkeypatch, state)

        assert state.tables[_script.SNAPSHOT_TABLE]['created_at'][0] == (
            'timestamp with time zone')
        assert any('ALTER COLUMN created_at TYPE timestamptz' in s
                   for s in state.executed if isinstance(s, str))

    def test_heal_is_idempotent(self, monkeypatch):
        state = _state({
            _script.SNAPSHOT_TABLE: _snapshot_table(created_at=_NO_TZ),
            _script.CASES_TABLE: _cases_with_pointers(),
        }, storage='e')
        _run(monkeypatch, state)
        before = len(state.executed)
        _run(monkeypatch, state)
        assert not any('ALTER COLUMN created_at TYPE timestamptz' in s
                       for s in state.executed[before:] if isinstance(s, str))

    def test_correct_type_never_rewrites_table(self, monkeypatch):
        state = _state({
            _script.SNAPSHOT_TABLE: _snapshot_table(),
            _script.CASES_TABLE: _cases_with_pointers(),
        }, storage='e')
        _run(monkeypatch, state)
        assert not any('ALTER COLUMN created_at' in s
                       for s in state.executed if isinstance(s, str))


# ------------------------------------------------- 5. 引导链位置与 --apply 不变

class TestBootstrapWiring:
    def test_step_stays_before_analyze_with_apply(self):
        bootstrap = _load(_BOOTSTRAP_PATH, 'int2006_db_bootstrap')
        steps = [list(step) for step in bootstrap.BOOTSTRAP_STEPS]
        rel = 'scripts/migrations/202610/add_report_case_snapshots_int1994.py'
        names = [step[1] for step in steps]
        assert rel in names
        assert '--apply' in steps[names.index(rel)]
        assert names.index(rel) < names.index(
            'scripts/migrations/202610/analyze_stale_statistics_int1741.py')
