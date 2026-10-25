# -*- coding: utf-8 -*-
"""INT-1807：test_result_dimensions 原始报文指针列 + 内容寻址回填 + 切换门禁。

钉死的不变量（不连库，全部用假连接 / 假 uploader 驱动）：
1. 迁移步骤在 BOOTSTRAP_STEPS 里且带 --apply，并排在 ㊽ INT-1741 ANALYZE 之前
   （ANALYZE 必须保持末位）；
2. 迁移脚本的 10 列与 ORM ``TestResultDimension`` 元数据逐列对齐，全部可空、
   无默认值，且 DDL 是一条 ALTER TABLE（只拿一次 AccessExclusiveLock）；
3. 对象 key 是内容寻址（``raw/{resp|req}/{sha[:2]}/{sha}.json.gz``），sha256 对
   **规范化**字节计算（键序无关）；
4. 回填只经 ``allow_fallback=False`` 写入：拿到 ``local://`` 即抛
   StorageUnavailableError，该组不写任何 uri（失败方向不落本地盘）；
5. 组内 / 跨组同值只上传一次（值缓存）；
6. 门禁是两项 FILTER 计数，回填口径与门禁口径一致（漏一列就会永远切不过去）。
"""
import importlib.util
import json
import os
import sys
import types

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))

_MIGRATION_REL = ('scripts/migrations/202610/'
                  'add_raw_payload_pointers_int1807.py')
_BACKFILL_REL = ('scripts/migrations/202610/'
                 'backfill_raw_payload_pointers_int1807.py')
_ANALYZE_REL = 'scripts/migrations/202610/analyze_stale_statistics_int1741.py'
_BOOTSTRAP_PATH = os.path.join(PROJECT_ROOT, 'docker',
                               'db_bootstrap_entrypoint.py')

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')
os.environ.setdefault('DATABASE_URL', 'postgresql://u:p@localhost:1/unused')


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


migration = _load(os.path.join(PROJECT_ROOT, *_MIGRATION_REL.split('/')),
                  'int1807_migration')
backfill = _load(os.path.join(PROJECT_ROOT, *_BACKFILL_REL.split('/')),
                 'int1807_backfill')
bootstrap = _load(_BOOTSTRAP_PATH, 'int1807_db_bootstrap')


# ------------------------------------------------------------------ 引导链

def test_bootstrap_step_registered_with_apply():
    steps = [step for step in bootstrap.BOOTSTRAP_STEPS
             if step[1] == _MIGRATION_REL]
    assert steps, f'BOOTSTRAP_STEPS 未包含 {_MIGRATION_REL}：存量库永远补不上指针列'
    assert steps[0][-1] == '--apply', '脚本默认 dry-run，引导链必须带 --apply'


def test_bootstrap_step_runs_before_analyze():
    order = [step[1] for step in bootstrap.BOOTSTRAP_STEPS]
    assert order.index(_MIGRATION_REL) < order.index(_ANALYZE_REL)


def test_backfill_script_stays_out_of_bootstrap_chain():
    """回填要解压约 695MB TOAST，必须人工限流执行，不能进部署引导链。"""
    rels = [step[1] for step in bootstrap.BOOTSTRAP_STEPS]
    assert _BACKFILL_REL not in rels


# ------------------------------------------------------------------ 迁移 DDL

def test_migration_columns_match_orm():
    from evaluation_service.infrastructure.persistence.models.result_models \
        import TestResultDimension

    table = TestResultDimension.__table__
    assert [name for name, _t, _e, _c in migration.COLUMNS] == [
        'api_raw_response_uri', 'api_raw_response_sha256',
        'api_raw_response_bytes', 'api_raw_response_content_type',
        'api_raw_response_created_at',
        'api_request_body_uri', 'api_request_body_sha256',
        'api_request_body_bytes', 'api_request_body_content_type',
        'api_request_body_created_at',
    ]
    for name, _ddl, _expected, comment in migration.COLUMNS:
        assert name in table.columns, f'ORM 缺列 {name}'
        col = table.columns[name]
        assert col.nullable is True, f'{name} 必须可空（存量行兼容）'
        assert col.server_default is None and col.default is None
        assert col.comment == comment, f'{name} 的 ORM 注释与迁移注释不一致'


def test_ddl_is_one_alter_table_without_defaults():
    missing = [(name, ddl) for name, ddl, _e, _c in migration.COLUMNS]
    ddl = migration.build_add_column_ddl(missing)
    assert ddl.count('ALTER TABLE') == 1, '10 列应合成一条 ALTER TABLE（只拿一次锁）'
    assert ddl.count('ADD COLUMN IF NOT EXISTS') == 10
    assert 'NOT NULL' not in ddl
    assert 'DEFAULT' not in ddl
    assert 'test_result_dimensions' in ddl


def test_missing_columns_only_reports_absent():
    existing = {name: ('', None, 'YES', None)
                for name, _t, _e, _c in migration.COLUMNS[:7]}
    missing = [name for name, _ddl in migration._missing_columns(existing)]
    assert missing == [name for name, _t, _e, _c in migration.COLUMNS[7:]]


def test_migration_dry_run_emits_no_ddl(monkeypatch):
    class _Cursor:
        def __init__(self):
            self.statements = []

        def execute(self, sql, params=None):
            self.statements.append(sql)

        def fetchone(self):
            return (1,)  # 表存在

        def fetchall(self):
            return []  # 列全部缺失

        def close(self):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    class _Conn:
        autocommit = False
        committed = 0

        def __init__(self):
            self.cur = _Cursor()

        def cursor(self):
            return self.cur

        def commit(self):
            self.committed += 1

        def close(self):
            pass

    conn = _Conn()
    monkeypatch.setattr(migration, '_connect', lambda: conn)
    migration.migrate(dry_run=True)
    assert conn.committed == 0
    assert not any('ADD COLUMN' in s for s in conn.cur.statements)


# ------------------------------------------------------------------ 内容寻址

def test_canonical_bytes_is_key_order_independent():
    a = {'b': 1, 'a': [1, 2, {'z': None, 'y': '中文'}]}
    b = {'a': [1, 2, {'y': '中文', 'z': None}], 'b': 1}
    assert backfill.canonical_bytes(a) == backfill.canonical_bytes(b)
    assert backfill.sha256_hex(a) == backfill.sha256_hex(b)
    # ensure_ascii=False：中文按 UTF-8 原样编码
    assert '中文'.encode('utf-8') in backfill.canonical_bytes(a)


def test_object_key_is_content_addressed():
    value = {'x': 1}
    sha = backfill.sha256_hex(value)
    assert len(sha) == 64
    assert backfill.object_key('resp', sha) == f'raw/resp/{sha[:2]}/{sha}.json.gz'
    assert backfill.object_key('req', sha) == f'raw/req/{sha[:2]}/{sha}.json.gz'


def test_gzip_roundtrip_is_deep_equal():
    value = {'rounds': [{'text': '你好', 'n': 0.5}], 'ok': True}
    gz = backfill.compress(backfill.canonical_bytes(value))
    assert backfill.compress(backfill.canonical_bytes(value)) == gz  # mtime 固定
    assert json.loads(__import__('gzip').decompress(gz)) == value


# ------------------------------------------------------------------ 写入口径

def test_default_uploader_forbids_local_fallback(monkeypatch):
    class _Unavailable(RuntimeError):
        pass

    calls = {}

    class _Storage:
        def save_bytes(self, data, category, key, content_type=None,
                       allow_fallback=True):
            calls.update(category=category, key=key,
                         content_type=content_type,
                         allow_fallback=allow_fallback)
            return f'oss://{category}/{key}'

    module = types.ModuleType('shared.infrastructure.storage')
    module.storage = _Storage()
    module.StorageUnavailableError = _Unavailable
    monkeypatch.setitem(sys.modules, 'shared.infrastructure.storage', module)

    uri = backfill._default_uploader(b'x', 'raw/resp/ab/x.json.gz')
    assert uri == 'oss://case_result/raw/resp/ab/x.json.gz'
    assert calls['allow_fallback'] is False
    assert calls['content_type'] == 'application/json+gzip'
    assert calls['category'] == 'case_result'


def test_default_uploader_rejects_local_uri(monkeypatch):
    class _Unavailable(RuntimeError):
        pass

    class _Storage:
        def save_bytes(self, *a, **kw):
            return 'local://case_result/raw/resp/ab/x.json.gz'

    module = types.ModuleType('shared.infrastructure.storage')
    module.storage = _Storage()
    module.StorageUnavailableError = _Unavailable
    monkeypatch.setitem(sys.modules, 'shared.infrastructure.storage', module)

    with pytest.raises(_Unavailable):
        backfill._default_uploader(b'x', 'raw/resp/ab/x.json.gz')


def test_store_payload_uploads_once_and_reuses_cache(monkeypatch):
    class _Unavailable(RuntimeError):
        pass

    module = types.ModuleType('shared.infrastructure.storage')
    module.StorageUnavailableError = _Unavailable
    monkeypatch.setitem(sys.modules, 'shared.infrastructure.storage', module)

    uploaded = []

    def _uploader(data, key):
        uploaded.append(key)
        return f'oss://case_result/{key}'

    cache = {}
    stats = backfill._Stats()
    value = {'a': 1}
    first = backfill._store_payload(value, 'resp', cache, stats, _uploader)
    second = backfill._store_payload(value, 'resp', cache, stats, _uploader)
    assert first == second
    assert len(uploaded) == 1
    assert stats.uploaded == 1 and stats.reused == 1
    assert first[2] > 0


def test_process_group_writes_no_uri_when_upload_fails(monkeypatch):
    """失败方向：第二个对象上传失败 → 整组一条 uri 都不写（重跑幂等）。"""
    class _Unavailable(RuntimeError):
        pass

    module = types.ModuleType('shared.infrastructure.storage')
    module.StorageUnavailableError = _Unavailable
    monkeypatch.setitem(sys.modules, 'shared.infrastructure.storage', module)

    monkeypatch.setattr(
        backfill, 'fetch_group_rows',
        lambda conn, tid, rn: [(1, {'resp': 1}, {'req': 1}),
                               (2, {'resp': 2}, None)])

    updates = []
    monkeypatch.setattr(
        backfill, '_update_row',
        lambda conn, row_id, prefix, record: updates.append(row_id) or 1)

    calls = {'n': 0}

    def _uploader(data, key):
        calls['n'] += 1
        if calls['n'] == 2:
            raise _Unavailable('OSS 不可用')
        return f'oss://case_result/{key}'

    stats = backfill._Stats()
    with pytest.raises(_Unavailable):
        backfill.process_group(None, 1, None, {}, stats, _uploader)
    assert updates == [], '上传失败后不允许写 uri'


def test_process_group_updates_each_row_and_skips_empty(monkeypatch):
    monkeypatch.setattr(
        backfill, 'fetch_group_rows',
        lambda conn, tid, rn: [(1, {'v': 1}, None), (2, None, {'q': 1})])
    monkeypatch.setattr(backfill, '_store_payload',
                        lambda value, kind, cache, stats, uploader:
                        (f'oss://case_result/raw/{kind}/k', 'a' * 64, 10))
    written = []
    monkeypatch.setattr(
        backfill, '_update_row',
        lambda conn, row_id, prefix, record: written.append((row_id, prefix)) or 1)

    stats = backfill._Stats()
    backfill.process_group(None, 1, 0, {}, stats,
                           lambda data, key: 'oss://x')
    assert written == [(1, 'api_raw_response'), (2, 'api_request_body')]
    assert stats.groups == 1 and stats.rows == 2


# ------------------------------------------------------------------ 门禁

def test_gate_counts_both_payload_kinds():
    sql = backfill.GATE_SQL
    assert 'resp_missing' in sql and 'req_missing' in sql
    assert sql.count('FILTER') == 2
    assert 'api_raw_response_uri IS NULL' in sql
    assert 'api_request_body_uri IS NULL' in sql
    assert 'test_result_dimensions' in sql


def test_pending_predicate_matches_gate_semantics():
    """回填的待处理口径必须与门禁同义，否则门禁永远归不了零。"""
    normalized = ' '.join(backfill.PENDING_PREDICATE.split())
    assert ('api_raw_response IS NOT NULL AND api_raw_response_uri IS NULL'
            in normalized)
    assert ('api_request_body IS NOT NULL AND api_request_body_uri IS NULL'
            in normalized)


def test_gate_mode_exit_code(monkeypatch, capsys):
    class _Cur:
        def __init__(self, row):
            self.row = row

        def execute(self, sql, params=None):
            pass

        def fetchone(self):
            return self.row

        def close(self):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    class _Conn:
        def __init__(self, row):
            self.row = row

        def cursor(self):
            return _Cur(self.row)

        def close(self):
            pass

    cases = [((0, 0), 0), ((3, 0), 1), ((0, 7), 1)]
    for row, code in cases:
        monkeypatch.setattr(backfill, '_connect', lambda row=row: _Conn(row))
        monkeypatch.setattr(sys, 'argv',
                            ['backfill', '--gate'])
        with pytest.raises(SystemExit) as exc:
            backfill.main()
        assert exc.value.code == code
        capsys.readouterr()


def test_backfill_uses_no_storage_exists_and_no_local_fallback():
    """卡面红线：不得用 storage.exists（会把本地降级副本算进去）、不得留降级口子。"""
    with open(os.path.join(PROJECT_ROOT, *_BACKFILL_REL.split('/')),
              encoding='utf-8') as f:
        source = f.read()
    assert 'storage.exists' not in source
    assert 'allow_fallback=False' in source
    assert 'allow_fallback=True' not in source
