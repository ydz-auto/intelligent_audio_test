# -*- coding: utf-8 -*-
"""INT-1811 / A1：离线搬运携带原始报文对象（导出打包 + 导入回写 + 1.0 旧包物化）

覆盖（不连真库 / 真 OSS：存储用内存替身）：
- 口径唯一：与 C1 回填脚本（scripts/migrations/202610/…_int1807.py）同一套
  规范化 / sha256 / key / gzip，杜绝两个算法各算一个 sha；
- 导出：维度行 uri 引用的对象按内容寻址**只打一次**，manifest.rawObjects 与
  包内 files/raw/ 条目一一对应；对象读不到整包失败（不留悬空包）；
- 导入：包内对象回写本端存储、行指针改写到本端路径（免 id 重映射）、
  内联 JSON 列置空（uri-only）；
- 1.0 旧包：内联 JSON 现场物化；无对象可物化的历史行清空指针并给警告；
- 1.2 包：行引用的对象缺失 → 坏包拒绝；
- 往返幂等：A→B→A 两轮对象数不膨胀（内容寻址 key 稳定）。
"""
import importlib.util
import json
import os
import zipfile

import pytest

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from shared.constants.data_transfer import (  # noqa: E402
    FILES_DIR,
    ManifestVersion,
    TransferTable,
    manifest_requires_raw_objects,
)
from shared.infrastructure.storage import StorageUnavailableError  # noqa: E402
from shared.utils.raw_payload import (  # noqa: E402
    RAW_CATEGORY,
    RAW_KEY_ROOT,
    RAW_CONTENT_TYPE,
    RAW_PAYLOAD_SPECS,
    canonical_bytes,
    compress,
    object_key,
    sha256_hex,
)
from task_service.domain.services.data_transfer import (  # noqa: E402
    build_manifest,
    collect_raw_object_refs,
    validate_manifest,
)
from task_service.infrastructure.transfer import raw_payload_store  # noqa: E402
from task_service.infrastructure.transfer.raw_payload_store import (  # noqa: E402
    RawObjectCollector,
    RawObjectPackageError,
    iter_raw_object_entries,
    import_raw_objects,
)

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_BACKFILL_SCRIPT = os.path.join(
    _REPO_ROOT, 'scripts', 'migrations', '202610',
    'backfill_raw_payload_pointers_int1807.py')


# ---------- 内存存储替身 ----------

class FakeStorage:
    """按「端」隔离的内存对象存储（A / B 各一份，模拟离线搬运两端）"""

    def __init__(self):
        self.objects = {}          # key -> bytes
        self.saves = []            # 上传发生顺序（断言去重 / 次数）
        self.unavailable = False

    def load_bytes(self, path, allow_fallback=True):
        if self.unavailable:
            raise RuntimeError('OSS 不可达')
        key = _key_of(path)
        if key not in self.objects:
            raise FileNotFoundError(f'对象不存在: {path}')
        return self.objects[key]

    def save_bytes(self, data, category, key, content_type=None, allow_fallback=True):
        if self.unavailable:
            if not allow_fallback:
                raise StorageUnavailableError(f'OSS 不可用: {key}')
            raise RuntimeError('OSS 不可用（调用方不应允许降级）')
        assert category == RAW_CATEGORY, category
        assert content_type == RAW_CONTENT_TYPE, content_type
        self.objects[key] = data
        self.saves.append(key)
        return f'oss://{category}/{key}'

    def put(self, value, kind='resp'):
        """按口径写入一个对象，返回 (uri, sha, 压缩字节)"""
        sha = sha256_hex(value)
        key = object_key(kind, sha)
        data = compress(canonical_bytes(value))
        self.objects[key] = data
        return f'oss://{RAW_CATEGORY}/{key}', sha, data


def _key_of(uri: str) -> str:
    for scheme in ('oss://', 'local://'):
        if uri.startswith(scheme):
            rest = uri[len(scheme):]
            return rest.split('/', 1)[1] if '/' in rest else ''
    return uri.split('/', 1)[1] if '/' in uri else uri


@pytest.fixture()
def storage(monkeypatch):
    fake = FakeStorage()
    monkeypatch.setattr(raw_payload_store, 'storage', fake)
    return fake


# ---------- 口径唯一：与 C1 回填脚本一致 ----------

def _load_backfill_module():
    spec = importlib.util.spec_from_file_location('int1807_backfill_int1811', _BACKFILL_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_raw_payload_algorithms_match_backfill_script():
    backfill = _load_backfill_module()
    samples = [
        {'z': 1, 'a': [1, 2, {'k': '中文'}]},
        {'b': None, 'a': {'nested': [True, False]}},
        [1, 2, 3],
    ]
    for value in samples:
        assert canonical_bytes(value) == backfill.canonical_bytes(value)
        assert sha256_hex(value) == backfill.sha256_hex(value)
        assert compress(canonical_bytes(value)) == backfill.compress(
            backfill.canonical_bytes(value))
        assert object_key('resp', sha256_hex(value)) == backfill.object_key(
            'resp', backfill.sha256_hex(value))


def test_manifest_requires_raw_objects_by_version():
    assert manifest_requires_raw_objects('1.2') is True
    assert manifest_requires_raw_objects('1.1') is False
    assert manifest_requires_raw_objects('1.0') is False
    assert manifest_requires_raw_objects('9.9') is True


# ---------- 导出侧：收集引用 ----------

def test_collect_raw_object_refs_dedupes_same_content_across_rows():
    resp = {'answer': 'x', 'score': 1}
    req = {'question': 'q'}
    resp_sha = sha256_hex(resp)
    req_sha = sha256_hex(req)
    rows = [
        {'id': 1, 'api_raw_response_uri': f'oss://{RAW_CATEGORY}/raw/resp/{resp_sha[:2]}/{resp_sha}.json.gz',
         'api_raw_response_sha256': resp_sha},
        # 同一个响应在另一维度行上重复出现 → 内容寻址只保留一个对象
        {'id': 2, 'api_raw_response_uri': f'oss://{RAW_CATEGORY}/raw/resp/{resp_sha[:2]}/{resp_sha}.json.gz',
         'api_raw_response_sha256': resp_sha},
        {'id': 3, 'api_request_body_uri': f'oss://{RAW_CATEGORY}/raw/req/{req_sha[:2]}/{req_sha}.json.gz',
         'api_request_body_sha256': req_sha},
        {'id': 4},  # 无报文
    ]
    refs, errors = collect_raw_object_refs(rows)
    assert errors == []
    assert sorted(ref.key for ref in refs) == sorted([
        object_key('resp', resp_sha), object_key('req', req_sha)])


def test_collect_raw_object_refs_derives_sha_from_uri_when_column_missing():
    value = {'answer': 'y'}
    sha = sha256_hex(value)
    rows = [{'id': 1,
             'api_raw_response_uri': f'oss://{RAW_CATEGORY}/raw/resp/{sha[:2]}/{sha}.json.gz'}]
    refs, errors = collect_raw_object_refs(rows)
    assert errors == []
    assert [ref.sha256 for ref in refs] == [sha]


def test_collect_raw_object_refs_reports_unresolvable_uri():
    rows = [{'id': 7, 'api_raw_response_uri': 'oss://case_result/1/2/3/result_data.json'}]
    refs, errors = collect_raw_object_refs(rows)
    assert refs == []
    assert errors and 'id=7' in errors[0]


def test_collector_summary_lists_every_packaged_object(storage):
    uri_resp, sha_resp, resp_data = storage.put({'a': 1}, 'resp')
    uri_req, sha_req, req_data = storage.put({'b': 2}, 'req')
    entries = [(_key_of(uri_resp), resp_data), (_key_of(uri_req), req_data)]
    collector = RawObjectCollector(iter(entries))
    written = dict(collector)
    summary = collector.summary()
    assert summary['count'] == len(written) == 2
    assert {item['key'] for item in summary['files']} == set(written)
    assert {item['sha256'] for item in summary['files']} == {sha_resp, sha_req}
    assert summary['totalBytes'] == len(resp_data) + len(req_data)
    assert summary['contentType'] == RAW_CONTENT_TYPE


# ---------- 全量导出：包内对象只出现一次 + manifest 一一对应 ----------

class _FakeTaskRepository:
    def filter_visible_task_ids(self, task_ids, user_id=None, is_admin=None):
        return list(task_ids)


class _FakeTransferRepository:
    def __init__(self, rows):
        self.rows = rows

    def fetch_export_rows(self, task_ids):
        return {key: [dict(row) for row in value] for key, value in self.rows.items()}

    def fetch_case_configs(self, case_ids):
        return {}


class _FakeEvaluationAcl:
    def __init__(self, dimension_rows, dim_defs=None):
        self.dimension_rows = dimension_rows
        self.dim_defs = dim_defs or []

    def export_dimensions_for_tasks(self, result_ids):
        return {'dimensions': [dict(row) for row in self.dimension_rows],
                'dimension_defs': list(self.dim_defs)}


class _FakeIncrementalTransferRepository:
    """增量导出编排的最小替身（D3 的完整替身在 test_int1761，本卡只关心对象）"""

    def fetch_source_task_refs(self, local_task_ids):
        return [{'source_server': 'A-server', 'source_task_id': 12,
                 'entity_type': 'tasks', 'source_id': 12, 'local_id': 25}]

    def fetch_export_rows(self, task_ids):
        return {'test_tasks': [{'id': 25, 'name': 'B 任务', 'status': 'completed'}],
                'test_results': [{'id': 205, 'task_id': 25}],
                'task_case_relations': [{'task_id': 25, 'test_case_id': 'c1'}]}

    def fetch_source_ids_by_local_ids(self, source_server, entity_type, local_ids):
        return {205: 101} if entity_type == 'test_results' else {}


class _FakeReportAcl:
    def export_reports_for_tasks(self, task_ids):
        return {}


@pytest.fixture()
def export_module(tmp_path, monkeypatch, storage):
    from task_service.application.task import data_transfer_export_service as module
    monkeypatch.setattr(module, '_export_tmp_dir', lambda: str(tmp_path))
    monkeypatch.setattr(module, 'resolve_transfer_server_id', lambda: 'A-server')
    import task_service.infrastructure.persistence.task_repository as task_repo_module
    monkeypatch.setattr(task_repo_module, 'task_repository', _FakeTaskRepository())
    return module


def _wire_full_export(module, monkeypatch, dimension_rows, storage):
    rows = {
        'test_tasks': [{'id': 5, 'name': '任务', 'status': 'completed'}],
        'test_results': [{'id': 9, 'task_id': 5}],
    }
    monkeypatch.setattr(module, 'transfer_repository', _FakeTransferRepository(rows))
    monkeypatch.setattr(module, 'evaluation_transfer_acl_repository',
                        _FakeEvaluationAcl(dimension_rows))
    monkeypatch.setattr(module, 'report_transfer_acl_repository', _FakeReportAcl())


def _dimension_rows_with_objects(storage):
    resp = {'answer': 'resp-1', 'round': 0}
    req = {'question': 'q-1'}
    resp_uri, resp_sha, resp_bytes = storage.put(resp, 'resp')
    req_uri, req_sha, req_bytes = storage.put(req, 'req')
    rows = [
        {'id': 101, 'test_result_id': 9, 'dimension_id': 1,
         'api_raw_response_uri': resp_uri, 'api_raw_response_sha256': resp_sha},
        # 同一响应重复引用（多维度 / 多轮）→ 包内仍只出现一次
        {'id': 102, 'test_result_id': 9, 'dimension_id': 2,
         'api_raw_response_uri': resp_uri, 'api_raw_response_sha256': resp_sha},
        {'id': 103, 'test_result_id': 9, 'dimension_id': 3,
         'api_request_body_uri': req_uri, 'api_request_body_sha256': req_sha},
    ]
    return rows, {object_key('resp', resp_sha), object_key('req', req_sha)}, resp_bytes, req_bytes


def test_full_export_packages_each_raw_object_once(export_module, monkeypatch, storage):
    dims, expected_keys, resp_bytes, req_bytes = _dimension_rows_with_objects(storage)
    _wire_full_export(export_module, monkeypatch, dims, storage)

    result = export_module.data_transfer_export_service.export_tasks([5])
    assert result['success'] is True, result
    assert result['data']['raw_object_count'] == 2
    assert result['data']['file_count'] == 0  # 原始报文不计入附件 fileCount

    with zipfile.ZipFile(result['data']['zip_path']) as zf:
        names = set(zf.namelist())
        manifest = json.loads(zf.read('manifest.json').decode('utf-8'))
        raw_entries = sorted(name for name in names if name.startswith(f'{FILES_DIR}/{RAW_KEY_ROOT}/'))
        blobs = {name: zf.read(name) for name in raw_entries}
        db_rows = json.loads(zf.read('db/test_result_dimensions.json').decode('utf-8'))

    assert manifest['version'] == ManifestVersion.V1_2.value
    assert validate_manifest(manifest)['version'] == '1.2'
    raw_section = manifest['rawObjects']
    assert raw_section['count'] == 2
    # manifest 清单与包内文件一一对应
    assert {item['key'] for item in raw_section['files']} == expected_keys
    assert {f'files/{key}' for key in expected_keys} == set(raw_entries)
    assert blobs[f'files/{object_key("resp", sha256_hex({"answer": "resp-1", "round": 0}))}'] == resp_bytes
    assert sum(item['bytes'] for item in raw_section['files']) == len(resp_bytes) + len(req_bytes)
    # 维度行仍带 uri（导入侧按 uri 找对象）
    assert all(row.get('api_raw_response_uri') or row.get('api_request_body_uri')
               for row in db_rows)


def test_full_export_fails_loudly_when_object_is_unreachable(export_module, monkeypatch, storage):
    dims, _keys, _resp_bytes, _req_bytes = _dimension_rows_with_objects(storage)
    _wire_full_export(export_module, monkeypatch, dims, storage)
    # 模拟对象被删：行里还有 uri，存储里取不到
    for key in list(storage.objects):
        if key.startswith('raw/req/'):
            del storage.objects[key]

    result = export_module.data_transfer_export_service.export_tasks([5])
    assert result['success'] is False
    assert result['code'] == 500
    # 不留半成品 ZIP
    assert not [name for name in os.listdir(str(export_module._export_tmp_dir()))
                if name.endswith('.zip')]


def test_incremental_export_packages_raw_objects_and_bumps_version(
        export_module, monkeypatch, storage, tmp_path):
    resp_uri, resp_sha, _ = storage.put({'answer': 'inc'}, 'resp')
    dims = [{'id': 1, 'test_result_id': 205, 'dimension_id': 2, 'round_number': 0,
             'api_raw_response_uri': resp_uri, 'api_raw_response_sha256': resp_sha}]
    monkeypatch.setattr(export_module, 'transfer_repository',
                        _FakeIncrementalTransferRepository())
    monkeypatch.setattr(export_module, 'evaluation_transfer_acl_repository',
                        _FakeEvaluationAcl(dims))
    monkeypatch.setattr(export_module, 'report_transfer_acl_repository', _FakeReportAcl())

    result = export_module.data_transfer_export_service.export_incremental([25])
    assert result['success'] is True, result
    assert result['data']['rawObjectCount'] == 1
    with zipfile.ZipFile(result['data']['zip_path']) as zf:
        names = set(zf.namelist())
        manifest = json.loads(zf.read('manifest.json').decode('utf-8'))
    assert manifest['version'] == '1.2'
    assert manifest['rawObjects']['count'] == 1
    assert f'files/{object_key("resp", resp_sha)}' in names
    # 增量包仍不搬结果 / 音频文件
    assert not [name for name in names
                if name.startswith(f'{FILES_DIR}/')
                and not name.startswith(f'{FILES_DIR}/{RAW_KEY_ROOT}/')]


# ---------- 导入侧 ----------

def _pointer_row(row_id, spec, uri, sha):
    return {'id': row_id, spec.uri_column: uri, spec.sha256_column: sha}


def test_import_writes_object_once_and_rewrites_pointers(storage):
    value = {'answer': 'imported'}
    sha = sha256_hex(value)
    key = object_key('resp', sha)
    data = compress(canonical_bytes(value))
    spec = RAW_PAYLOAD_SPECS[0]
    rows = [_pointer_row(1, spec, f'oss://case_result/{key}', sha),
            _pointer_row(2, spec, f'oss://case_result/{key}', sha)]

    stats = import_raw_objects([(key, data)], rows)

    assert stats['written'] == 1          # 同对象只写一次
    assert stats['packageObjects'] == 1
    assert storage.saves == [key]
    for row in rows:
        assert row['api_raw_response_uri'] == f'oss://{RAW_CATEGORY}/{key}'
        assert row['api_raw_response_sha256'] == sha
        assert row['api_raw_response_bytes'] == len(data)
        assert row['api_raw_response_content_type'] == RAW_CONTENT_TYPE
        assert row['api_raw_response_created_at']
        assert row.get('api_raw_response') is None


def test_import_materializes_inline_json_from_legacy_10_package(storage):
    resp = {'answer': 'legacy', 'meta': {'中文': 1}}
    req = {'question': 'legacy-q'}
    rows = [{'id': 11, 'api_raw_response': resp, 'api_request_body': req}]

    stats = import_raw_objects([], rows, require_objects=False)

    assert stats['materialized'] == 2
    assert stats['packageObjects'] == 0
    resp_sha = sha256_hex(resp)
    req_sha = sha256_hex(req)
    assert rows[0]['api_raw_response_sha256'] == resp_sha
    assert rows[0]['api_raw_response_uri'] == (
        f'oss://{RAW_CATEGORY}/{object_key("resp", resp_sha)}')
    assert rows[0]['api_request_body_sha256'] == req_sha
    # 物化后 uri-only：内联 JSON 列不再下发
    assert rows[0]['api_raw_response'] is None
    assert rows[0]['api_request_body'] is None
    # 对象内容 = 规范化 + gzip，解压后与原 JSON deep-equal
    stored = storage.objects[object_key('resp', resp_sha)]
    import gzip
    assert json.loads(gzip.decompress(stored)) == resp


def test_import_rejects_12_package_missing_object(storage):
    sha = sha256_hex({'answer': 'missing'})
    spec = RAW_PAYLOAD_SPECS[0]
    rows = [_pointer_row(1, spec, f'oss://case_result/{object_key("resp", sha)}', sha)]
    with pytest.raises(RawObjectPackageError) as exc:
        import_raw_objects([], rows, require_objects=True)
    assert '包内缺少原始报文对象' in str(exc.value)


def test_import_rejects_object_with_wrong_content(storage):
    sha = sha256_hex({'answer': 'expected'})
    key = object_key('resp', sha)
    tampered = compress(canonical_bytes({'answer': 'tampered'}))
    spec = RAW_PAYLOAD_SPECS[0]
    rows = [_pointer_row(1, spec, f'oss://case_result/{key}', sha)]
    with pytest.raises(RawObjectPackageError) as exc:
        import_raw_objects([(key, tampered)], rows)
    assert 'sha256' in str(exc.value)


def test_import_legacy_package_with_unreachable_uri_strips_pointer(storage):
    sha = sha256_hex({'answer': 'gone'})
    spec = RAW_PAYLOAD_SPECS[0]
    rows = [_pointer_row(1, spec, f'oss://case_result/{object_key("resp", sha)}', sha)]

    stats = import_raw_objects([], rows, require_objects=False)

    assert stats['stripped'] == 1
    assert stats['warnings']
    for column in (spec.uri_column, spec.sha256_column, spec.bytes_column,
                   spec.content_type_column, spec.created_at_column):
        assert rows[0][column] is None
    # 门禁口径：内联 JSON 与 uri 都为空，不留悬空指针
    assert rows[0][spec.json_column] is None


def test_import_keeps_pointer_when_object_already_in_storage(storage):
    value = {'answer': 'same-deployment'}
    uri, sha, _data = storage.put(value, 'resp')
    spec = RAW_PAYLOAD_SPECS[0]
    rows = [_pointer_row(1, spec, uri, sha)]

    stats = import_raw_objects([], rows, require_objects=False)

    assert stats['kept'] == 1
    assert stats['written'] == 0
    assert rows[0][spec.uri_column] == uri


def test_import_prefers_package_object_over_inline_json(storage):
    resp = {'answer': 'both'}
    sha = sha256_hex(resp)
    key = object_key('resp', sha)
    data = compress(canonical_bytes(resp))
    spec = RAW_PAYLOAD_SPECS[0]
    rows = [{**{'id': 1}, spec.json_column: resp,
             spec.uri_column: f'oss://case_result/{key}', spec.sha256_column: sha}]

    stats = import_raw_objects([(key, data)], rows)

    assert stats['written'] == 1
    assert rows[0][spec.json_column] is None
    assert rows[0][spec.uri_column] == f'oss://{RAW_CATEGORY}/{key}'


def test_import_round_trip_a_b_a_does_not_inflate_objects(monkeypatch):
    """A→B→A 两轮：对象数不膨胀、指针稳定（内容寻址 key 与 id 无关）"""
    server_a = FakeStorage()
    server_b = FakeStorage()
    monkeypatch.setattr(raw_payload_store, 'storage', server_a)

    values = [{'answer': 'r1', 'round': 0}, {'answer': 'r2', 'round': 1}]
    # A 侧：1.0 旧包（内联 JSON）现场物化
    rows_a = [{'id': idx, RAW_PAYLOAD_SPECS[0].json_column: value}
              for idx, value in enumerate(values, start=1)]
    import_raw_objects([], rows_a, require_objects=False)
    assert len(server_a.objects) == 2

    # A → 包 → B
    refs, errors = collect_raw_object_refs(rows_a)
    assert errors == []
    package = list(iter_raw_object_entries(refs))
    monkeypatch.setattr(raw_payload_store, 'storage', server_b)
    rows_b = [dict(row) for row in rows_a]
    import_raw_objects(package, rows_b, require_objects=True)
    assert set(server_b.objects) == set(server_a.objects)

    # B → 包 → A（第二轮）
    refs_b, errors_b = collect_raw_object_refs(rows_b)
    assert errors_b == []
    package_b = list(iter_raw_object_entries(refs_b))
    monkeypatch.setattr(raw_payload_store, 'storage', server_a)
    rows_a2 = [dict(row) for row in rows_b]
    import_raw_objects(package_b, rows_a2, require_objects=True)

    assert set(server_a.objects) == set(server_b.objects)
    assert len(server_a.objects) == len(values)
    assert [row[RAW_PAYLOAD_SPECS[0].uri_column] for row in rows_a2] == \
        [row[RAW_PAYLOAD_SPECS[0].uri_column] for row in rows_b]


def test_import_surfaces_storage_unavailable_without_local_fallback(storage):
    resp = {'answer': 'oss-down'}
    rows = [{'id': 1, 'api_raw_response': resp}]
    storage.unavailable = True
    with pytest.raises(raw_payload_store.RawObjectUnavailableError):
        import_raw_objects([], rows, require_objects=False)
    assert storage.saves == []  # 不落本地、不留假 uri


def test_manifest_carries_raw_objects_section():
    manifest = build_manifest(
        task_rows=[], result_rows=[], dimension_count=0, report_count=0,
        file_count=0, total_file_size=0, source='A-server',
        raw_objects={'count': 1, 'totalBytes': 10,
                     'files': [{'key': 'raw/resp/aa/x.json.gz', 'sha256': 'x', 'bytes': 10}]})
    assert manifest['version'] == '1.2'
    assert manifest['rawObjects']['count'] == 1
    assert manifest['rawObjects']['contentType'] == RAW_CONTENT_TYPE
    # 缺省（无对象）也给出结构化的空段，便于对端一一对应校验
    empty = build_manifest(task_rows=[], result_rows=[], dimension_count=0,
                           report_count=0, file_count=0, total_file_size=0)
    assert empty['rawObjects']['count'] == 0
    assert empty['rawObjects']['files'] == []
    assert empty['rawObjects']['category'] == RAW_CATEGORY
    assert TransferTable.TEST_RESULT_DIMENSIONS.value == 'test_result_dimensions'


# ---------- 编排接线：整包导入（1.0 旧包 / 1.2 缺对象） ----------

class _ExecTransferRepository:
    """execute_import 的 task_service 仓储替身（不连库）"""

    def fetch_existing_ids(self):
        return {}

    def import_task_segment(self, tables, conflicts, rewrite_fk_fn, progress_fn=None):
        return ({'tasks': {5: 105}, 'test_results': {9: 209}}, {})

    def update_result_data_paths(self, changes):
        return None

    def upsert_source_maps(self, entries):
        return {'insertedCount': len(entries), 'updatedCount': 0,
                'inserted': list(entries)}


class _ExecEvaluationAcl:
    def __init__(self):
        self.imported_rows = None
        self.merged_rows = None

    def import_dimensions(self, rows, result_id_mapping, batch_id):
        self.imported_rows = [dict(row) for row in rows]
        return {'imported': len(rows), 'id_mapping': {}, 'batch_id': batch_id}

    def merge_dimensions(self, rows, dimension_id_mapping=None, batch_id=''):
        self.merged_rows = [dict(row) for row in rows]
        return {'imported': len(rows), 'deleted': 0, 'skipped_dimensions': [],
                'batch_id': batch_id, 'rollback_available': True}

    def rollback_dimension_import(self, batch_id):
        return {'batch_id': batch_id}

    def rollback_dimension_merge(self, batch_id):
        return {'batch_id': batch_id}


class _ExecReportAcl:
    def import_reports(self, tables, task_id_mapping, batch_id):
        return {'imported': 0, 'id_mapping': {}, 'batch_id': batch_id}

    def rollback_report_import(self, batch_id):
        return {'batch_id': batch_id}


class _ExecBatchRegistry:
    def record(self, batch_id, service, tables):
        return None

    def record_source_map(self, batch_id, service, entries):
        return None

    def delete(self, batch_id):
        return None


@pytest.fixture()
def import_module(monkeypatch, storage):
    from task_service.application.task import data_transfer_import_service as module
    monkeypatch.setattr(module, 'transfer_batch_registry', _ExecBatchRegistry())
    acl = _ExecEvaluationAcl()
    monkeypatch.setattr(module, 'evaluation_transfer_acl_repository', acl)
    monkeypatch.setattr(module, 'report_transfer_acl_repository', _ExecReportAcl())
    monkeypatch.setattr(module, 'transfer_repository', _ExecTransferRepository())
    import task_service.infrastructure.persistence.task_repository as task_repo_module
    monkeypatch.setattr(task_repo_module, 'task_repository', _FakeTaskRepository())
    return module, acl


def _write_package(path, manifest, db_tables, raw_entries=()):
    with zipfile.ZipFile(path, 'w') as zf:
        zf.writestr('manifest.json', json.dumps(manifest, ensure_ascii=False))
        for table, rows in db_tables.items():
            zf.writestr(f'db/{table}.json', json.dumps(rows, ensure_ascii=False, default=str))
        for key, data in raw_entries:
            zf.writestr(f'files/{key}', data)
    return str(path)


def _legacy_manifest():
    return {'version': '1.0', 'exportedAt': '2026-10-01T00:00:00+08:00',
            'serverInfo': {'source': 'A-server'},
            'tasks': [{'id': 5, 'name': '任务', 'status': 'completed', 'resultCount': 1}],
            'stats': {}, 'options': {}}


def test_execute_import_materializes_legacy_inline_payloads(import_module, tmp_path, storage):
    module, acl = import_module
    resp = {'answer': 'legacy-1.0'}
    req = {'question': 'legacy-q'}
    dims = [{'id': 1, 'test_result_id': 9, 'dimension_id': 1, 'round_number': 0,
             'api_raw_response': resp, 'api_request_body': req}]
    zip_path = _write_package(
        tmp_path / 'legacy.zip', _legacy_manifest(),
        {'test_tasks': [{'id': 5, 'name': '任务', 'status': 'completed'}],
         'test_results': [{'id': 9, 'task_id': 5}],
         'test_result_dimensions': dims})

    result = module.data_transfer_import_service.execute_import(
        zip_path, {'intent': 'restore'})

    assert result['success'] is True, result
    stats = result['data']
    assert stats['materializedRawObjects'] == 2
    assert stats['importedRawObjects'] == 2
    # 交给 evaluation_service 的行已是 uri-only（内联 JSON 不再下发）
    assert acl.imported_rows, '维度段未执行'
    row = acl.imported_rows[0]
    assert row['api_raw_response'] is None and row['api_request_body'] is None
    assert row['api_raw_response_sha256'] == sha256_hex(resp)
    assert row['api_raw_response_uri'] == (
        f'oss://{RAW_CATEGORY}/{object_key("resp", sha256_hex(resp))}')
    assert row['api_request_body_sha256'] == sha256_hex(req)
    # 门禁口径：内联 JSON 非空而 uri 为空的行数 = 0
    gate = [r for r in acl.imported_rows
            if (r.get('api_raw_response') is not None and r.get('api_raw_response_uri') is None)
            or (r.get('api_request_body') is not None and r.get('api_request_body_uri') is None)]
    assert gate == []


def test_execute_import_rejects_12_package_missing_raw_object(import_module, tmp_path, storage):
    module, acl = import_module
    sha = sha256_hex({'answer': 'gone'})
    key = object_key('resp', sha)
    dims = [{'id': 1, 'test_result_id': 9, 'dimension_id': 1,
             'api_raw_response_uri': f'oss://{RAW_CATEGORY}/{key}',
             'api_raw_response_sha256': sha}]
    manifest = {**_legacy_manifest(), 'version': '1.2',
                'rawObjects': {'count': 1, 'totalBytes': 1, 'files': []}}
    zip_path = _write_package(
        tmp_path / 'missing.zip', manifest,
        {'test_tasks': [{'id': 5, 'name': '任务', 'status': 'completed'}],
         'test_results': [{'id': 9, 'task_id': 5}],
         'test_result_dimensions': dims})

    result = module.data_transfer_import_service.execute_import(
        zip_path, {'intent': 'restore'})

    assert result['success'] is False
    assert result['code'] == 400
    assert acl.imported_rows is None  # 未进入维度段
