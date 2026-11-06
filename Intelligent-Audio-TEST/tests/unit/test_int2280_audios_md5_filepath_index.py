# -*- coding: utf-8 -*-
"""INT-2280：audios md5 / file_path 局部索引（模型 + 迁移 + 引导链）守卫。

背景：INT-2278 SQL 抽检发现 ``audios`` 每次 ``seq_scan`` 都把整表读满 ——
``audio_repository`` 里按 md5 / file_path 等值过滤的三条查询（上传 md5 去重、
ZIP 回导逐文件去重、stream/download 的 file_path 可见性校验）此前无索引可命中，
文件数 × 表行数的增长曲线。

本文件把下列契约钉死（不连库，内存假游标驱动）：
1. ORM ``Audio.__table_args__`` 声明 ``idx_audios_md5`` / ``idx_audios_file_path``
   两条**局部索引**（``WHERE deleted = false``，与三条读路径的谓词一致）；
2. 迁移脚本的索引名 / 列 / 谓词与模型逐字对齐（本仓库有 create_all 先建表、
   两侧漂移的前例），且用 ``CREATE INDEX CONCURRENTLY``（不长期阻塞写）；
3. 迁移脚本挂在 ``BOOTSTRAP_STEPS`` 里且带 ``--apply``，位置在 INT-1741 的
   ANALYZE 之前（ANALYZE 固定为引导链末步）；
4. 默认 dry-run 不执行任何 DDL；索引已存在即 SKIP（幂等）；
5. CONCURRENTLY 中途失败留下的 invalid 索引被检出、以非零码退出并给出
   ``DROP INDEX CONCURRENTLY`` 命令（``IF NOT EXISTS`` 不会自愈它）；
6. ``--rollback`` 用 ``DROP INDEX CONCURRENTLY IF EXISTS`` 删两条索引。
"""
import importlib.util
import os
import sys

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'unit-test')
os.environ.setdefault('OSS_SECRET_KEY', 'unit-test')

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
_MIGRATION_REL = ('scripts/migrations/202611/'
                  'add_audios_md5_filepath_index.py')
_MIGRATION = os.path.join(PROJECT_ROOT, *_MIGRATION_REL.split('/'))
_BOOTSTRAP_PATH = os.path.join(PROJECT_ROOT, 'docker',
                               'db_bootstrap_entrypoint.py')
_ANALYZE_REL = ('scripts/migrations/202610/'
                'analyze_stale_statistics_int1741.py')
_TABLE = 'audios'


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_migration = _load(_MIGRATION, 'int2280_audios_md5_filepath_index')
_bootstrap = _load(_BOOTSTRAP_PATH, 'int2280_db_bootstrap')

#: 索引名 → 列（迁移与模型两侧都必须一致）
EXPECTED = {'idx_audios_md5': 'md5', 'idx_audios_file_path': 'file_path'}


def _norm(sql):
    return ' '.join(str(sql).split())


class _FakeCursor:
    """足够驱动 _table_exists / _index_state / _plan / _verify 的内存假游标。"""

    def __init__(self, state):
        # state: {索引名: None | {'valid': bool, 'def': str}}
        self.state = state
        self.executed = []
        self._rows = []

    def _name_in(self, sql):
        for name in EXPECTED:
            if name in sql:
                return name
        return None

    def execute(self, sql, params=None):
        self.executed.append((_norm(sql), params))
        self._rows = []
        if 'to_regclass' in sql:
            self._rows = [(_TABLE,)]
        elif 'indisvalid' in sql:
            # _index_state：索引名是绑定参数（WHERE c.relname = %s）
            name = params[0] if params else self._name_in(sql)
            st = self.state.get(name)
            self._rows = [] if st is None else [
                (st['valid'], True, st['def'])]
        elif 'count(*)' in sql.lower():
            self._rows = [(0, 0)]
        elif _norm(sql).upper().startswith('EXPLAIN'):
            name = self._name_in(sql)
            self._rows = [(f'Index Scan using {name} on {_TABLE}',)]
        elif 'pg_indexes' in sql:
            name = params[1] if params else None
            st = self.state.get(name)
            self._rows = [] if st is None else [(name, st['def'])]

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)

    def mogrify(self, sql, params=None):
        return str(sql).encode('utf-8')


class _FakeConn:
    def __init__(self, cursor):
        self._cursor = cursor
        self.autocommit = None
        self.closed = False

    def cursor(self):
        return self._cursor

    def close(self):
        self.closed = True


def _executed_ddl(cursor):
    return [sql for sql, _p in cursor.executed
            if sql.upper().startswith(('CREATE INDEX', 'DROP INDEX'))]


def _valid_def(name):
    col = EXPECTED[name]
    return (f'CREATE INDEX {name} ON public.{_TABLE} USING btree ({col}) '
            'WHERE (deleted = false)')


# ── 1. 模型声明 ──────────────────────────────────────────────────────────

def test_model_declares_partial_indexes():
    from audio_service.infrastructure.persistence.models.audio_models import Audio

    indexes = {idx.name: idx for idx in Audio.__table__.indexes}
    for name, col in EXPECTED.items():
        assert name in indexes, f'模型 __table_args__ 缺少 {name}'
        idx = indexes[name]
        assert [expr.name for expr in idx.expressions] == [col], \
            f'{name} 的列应为 {col}'
        where = idx.dialect_options['postgresql'].get('where')
        assert where is not None, f'{name} 应为局部索引（缺 postgresql_where）'
        assert _norm(where) == 'deleted = false', \
            f'{name} 的谓词应与仓储层三条读路径一致（deleted = false）'


# ── 2. 迁移脚本与模型对齐 ────────────────────────────────────────────────

def test_migration_indexes_match_model():
    names = [name for name, _col, _ddl, _rb in _migration.INDEXES]
    assert names == list(EXPECTED), f'迁移索引集合不符：{names}'
    for name, col, ddl, rollback_ddl in _migration.INDEXES:
        assert col == EXPECTED[name]
        normalized = _norm(ddl)
        # 必须 CONCURRENTLY（不长时间阻塞写）+ 幂等 + 与模型同一局部谓词
        assert normalized.startswith(
            f'CREATE INDEX CONCURRENTLY IF NOT EXISTS {name}'), normalized
        assert f'ON {_TABLE} ({col})' in normalized, normalized
        assert normalized.endswith('WHERE deleted = false'), normalized
        assert 'CREATE INDEX' not in rollback_ddl.upper().replace(
            'DROP INDEX', ''), rollback_ddl
        assert _norm(rollback_ddl) == (
            f'DROP INDEX CONCURRENTLY IF EXISTS {name}')


def test_migration_uses_autocommit_connection():
    """CREATE INDEX CONCURRENTLY 不能在事务块内执行 —— 连接必须 autocommit
    （源码断言，避免连库）。"""
    with open(_MIGRATION, encoding='utf-8') as fh:
        source = fh.read()
    assert 'conn.autocommit = True' in source


# ── 3. 引导链接线 ────────────────────────────────────────────────────────

def test_bootstrap_step_wired_before_analyze():
    rels = [step[1] for step in _bootstrap.BOOTSTRAP_STEPS]
    matches = [step for step in _bootstrap.BOOTSTRAP_STEPS
               if step[1] == _MIGRATION_REL]
    assert matches, (f'BOOTSTRAP_STEPS 未包含 {_MIGRATION_REL}：'
                     '建库早于本卡的存量库不会补索引')
    assert '--apply' in matches[0], '引导链必须带 --apply（脚本默认 dry-run）'
    assert rels.index(_MIGRATION_REL) < rels.index(_ANALYZE_REL), \
        '建索引 DDL 必须排在 INT-1741 的 ANALYZE 之前'
    assert _bootstrap.BOOTSTRAP_STEPS[-1][1] == _ANALYZE_REL, \
        'ANALYZE 必须保持引导链末位'


# ── 4. dry-run / 幂等 / invalid 索引 / 回滚 ──────────────────────────────

def test_dry_run_executes_no_ddl(monkeypatch):
    cursor = _FakeCursor({})
    conn = _FakeConn(cursor)
    monkeypatch.setattr(_migration, '_connect', lambda: conn)

    rc = _migration._run(False, _migration._plan, '迁移')
    assert rc == 0
    assert _executed_ddl(cursor) == [], 'dry-run 不得执行任何 DDL'
    assert conn.closed, '连接必须关闭'


def test_apply_creates_missing_indexes(monkeypatch):
    cursor = _FakeCursor({})
    conn = _FakeConn(cursor)
    monkeypatch.setattr(_migration, '_connect', lambda: conn)

    rc = _migration._run(True, _migration._plan, '迁移')
    assert rc == 0
    ddl = _executed_ddl(cursor)
    assert len(ddl) == 2, ddl
    assert all(sql.startswith('CREATE INDEX CONCURRENTLY') for sql in ddl)


def test_plan_skips_existing_indexes():
    state = {name: {'valid': True, 'def': _valid_def(name)} for name in EXPECTED}
    cursor = _FakeCursor(state)
    assert _migration._plan(cursor) == [], '索引已存在时应全 SKIP（幂等）'


def test_invalid_index_exits_nonzero_without_ddl(monkeypatch):
    """CONCURRENTLY 中途失败留下的 invalid 索引：IF NOT EXISTS 会一直跳过，
    必须检出并以非零码退出 + 打印 DROP 命令，否则部署静默通过、索引永不生效。"""
    state = {
        'idx_audios_md5': {'valid': False, 'def': 'CREATE INDEX idx_audios_md5 ...'},
        'idx_audios_file_path': None,
    }
    cursor = _FakeCursor(state)
    conn = _FakeConn(cursor)
    monkeypatch.setattr(_migration, '_connect', lambda: conn)

    assert _migration._invalid_indexes(cursor) == ['idx_audios_md5']
    rc = _migration._run(True, _migration._plan, '迁移')
    assert rc == 2, 'invalid 索引存在时必须非零退出'
    assert _executed_ddl(cursor) == [], '不得在 invalid 状态下继续建索引'


def test_rollback_drops_both_indexes(monkeypatch):
    state = {name: {'valid': True, 'def': _valid_def(name)} for name in EXPECTED}
    cursor = _FakeCursor(state)
    conn = _FakeConn(cursor)
    monkeypatch.setattr(_migration, '_connect', lambda: conn)

    rc = _migration._run(True, _migration._rollback_statements, '回滚')
    assert rc == 0
    ddl = _executed_ddl(cursor)
    assert sorted(ddl) == sorted(
        f'DROP INDEX CONCURRENTLY IF EXISTS {name}' for name in EXPECTED)
