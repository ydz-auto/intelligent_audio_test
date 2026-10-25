# -*- coding: utf-8 -*-
"""INT-1761 D3：增量导出 / 合并导入编排（链路 2）

覆盖（不连真库，仓储与 ACL 用内存替身）：
- 包内 id 翻译：维度行 test_result_id 回 A 原始 id、未映射行整包拒绝（409 +
  unmappedResultIds，A2-2 导出侧硬闸）；
- 报告 7 表翻译：task_id 必须翻译、报告 id 有映射写 A id、无映射剔 id 交给
  A 侧「最新报告 / 新建」定位（A5-2）；
- A 侧维度定义链翻译（name + 父链 + task_type_code，A2-4）、未匹配跳过；
- 增量包结构 / 一致性校验（多任务、id 不一致、缺 sourceTask）；
- manifest 1.2 生成与 1.0/1.1/1.2 三版本接受、非法版本拒绝（A1 + INT-1811）；
- 导入编排：段序（维度 → 报告）、指纹校验（409）、反向 id 校验（409）、
  逆序补偿（报告 → 维度）与补偿失败显式上报（A8）。
"""
import io
import os
import zipfile

import pytest

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')

from shared.constants.data_transfer import (  # noqa: E402
    INCREMENTAL_FINGERPRINT_CODE,
    INCREMENTAL_ID_MISSING_CODE,
    INCREMENTAL_UNMAPPED_CODE,
    IncrementalInclude,
    ManifestVersion,
    SUPPORTED_MANIFEST_VERSIONS,
    TransferTable,
)
from task_service.domain.services.data_transfer import (  # noqa: E402
    build_dimension_id_mapping,
    build_incremental_manifest,
    case_set_hash,
    translate_dimension_rows,
    translate_report_tables,
    validate_incremental_package,
    validate_manifest,
)
from task_service.domain.services.data_transfer.incremental import (  # noqa: E402
    package_report_ids,
)


# ---------- 纯函数：id 翻译 ----------

def test_translate_dimension_rows_maps_result_ids_and_reports_unmapped():
    rows = [
        {'id': 1, 'test_result_id': 205, 'dimension_id': 7, 'round_number': 0},
        {'id': 2, 'test_result_id': 206, 'dimension_id': 7, 'round_number': 1},
        {'id': 3, 'test_result_id': 999, 'dimension_id': 8},  # B 侧新执行产生
    ]
    translated, unmapped = translate_dimension_rows(rows, {205: 101, 206: 101})
    assert [row['test_result_id'] for row in translated] == [101, 101]
    # 维度 id 保留 B 侧值（A 侧按定义链翻译，不在这里动）
    assert {row['dimension_id'] for row in translated} == {7}
    assert translated[0]['round_number'] == 0
    # 未映射行不进包，且必须被显式报出（导出侧据此拒绝整包）
    assert unmapped == [999]


def test_translate_report_tables_translates_task_and_report_ids():
    tables = {
        'test_reports': [
            {'id': 900, 'task_id': 25, 'name': 'r1'},
            {'id': 901, 'task_id': 25, 'name': 'B 侧重生成的新报告'},
        ],
        'report_summaries': [
            {'id': 1, 'report_id': 900, 'summary': 'a'},
            {'id': 2, 'report_id': 901, 'summary': 'b'},
        ],
    }
    translated, unmapped = translate_report_tables(
        tables,
        task_local_to_source={25: 12},
        report_local_to_source={900: 77},  # 901 无映射 = B 侧重生成的新报告
    )
    assert unmapped == []
    reports = translated[TransferTable.TEST_REPORTS.value]
    by_id = {row.get('id'): row for row in reports}
    assert by_id[77]['task_id'] == 12           # 有映射 → 写成 A 原始报告 id
    assert None in by_id                        # 无映射 → 剔除 id（A 侧重新定位）
    assert by_id[None]['task_id'] == 12
    children = translated[TransferTable.REPORT_SUMMARIES.value]
    assert {row.get('report_id') for row in children} == {77, None}


def test_translate_report_tables_flags_unmapped_task_id():
    tables = {'test_reports': [{'id': 1, 'task_id': 404}]}
    translated, unmapped = translate_report_tables(tables, {}, {})
    assert unmapped == [404]
    assert translated[TransferTable.TEST_REPORTS.value] == []


def test_translate_report_tables_drops_orphan_child_rows():
    tables = {
        'test_reports': [{'id': 900, 'task_id': 25}],
        'report_cases': [
            {'id': 1, 'report_id': 900},
            {'id': 2, 'report_id': 555},  # 包内父报告不存在 → 孤儿子行丢弃
        ],
    }
    translated, _ = translate_report_tables(tables, {25: 12}, {900: 77})
    assert [row['id'] for row in translated[TransferTable.REPORT_CASES.value]] == [1]


# ---------- 纯函数：维度定义链翻译 ----------

def _pkg_defs():
    return [
        {'id': 1, 'name': '准确率', 'parent_dimension_id': None, 'task_type_code': 'wer'},
        {'id': 2, 'name': '字准', 'parent_dimension_id': 1, 'task_type_code': 'wer'},
    ]


def _target_defs():
    return [
        {'id': 10, 'name': '准确率', 'parent_dimension_id': None, 'task_type_code': 'wer'},
        {'id': 11, 'name': '字准', 'parent_dimension_id': 10, 'task_type_code': 'wer'},
        {'id': 12, 'name': '准确率', 'parent_dimension_id': None, 'task_type_code': 'cer'},
    ]


def test_build_dimension_id_mapping_matches_name_parent_and_task_type():
    mapping, unmatched, warnings = build_dimension_id_mapping(_pkg_defs(), _target_defs())
    assert mapping == {1: 10, 2: 11}
    assert unmatched == []
    assert warnings == []


def test_build_dimension_id_mapping_skips_unmatched_and_broken_parent_chain():
    package = _pkg_defs() + [
        {'id': 3, 'name': '不存在', 'parent_dimension_id': None, 'task_type_code': 'wer'},
        # 父维度匹配不到（父名称不同）→ 子维度同样不匹配
        {'id': 4, 'name': '孪生', 'parent_dimension_id': 3, 'task_type_code': 'wer'},
    ]
    mapping, unmatched, _ = build_dimension_id_mapping(package, _target_defs())
    assert 3 not in mapping and 4 not in mapping
    assert unmatched == [3, 4]


def test_build_dimension_id_mapping_requires_task_type_code_match():
    package = [{'id': 1, 'name': '准确率', 'parent_dimension_id': None,
                'task_type_code': 'cer'}]
    mapping, unmatched, _ = build_dimension_id_mapping(package, _target_defs())
    assert mapping == {1: 12}
    assert unmatched == []


def test_build_dimension_id_mapping_ambiguous_candidate_warns():
    target = _target_defs() + [
        {'id': 13, 'name': '准确率', 'parent_dimension_id': None, 'task_type_code': 'cer'},
    ]
    package = [{'id': 1, 'name': '准确率', 'parent_dimension_id': None,
                'task_type_code': 'cer'}]
    mapping, _, warnings = build_dimension_id_mapping(package, target)
    assert mapping == {1: 12}  # 同名同码多候选 → 取 id 最小者
    assert warnings and '同名候选' in warnings[0]


# ---------- 纯函数：指纹 / 结构校验 / manifest ----------

def test_case_set_hash_is_order_insensitive_and_stable():
    assert case_set_hash(['c2', 'c1']) == case_set_hash(['c1', 'c2'])
    assert case_set_hash([]) == case_set_hash([])
    assert case_set_hash(['c1']) != case_set_hash(['c2'])


def test_validate_incremental_package_rejects_multi_task_and_id_mismatch():
    manifest = {'sourceTask': {'id': 12}, 'tasks': [{'id': 12}, {'id': 13}]}
    errors = validate_incremental_package(manifest, {
        'test_reports': [{'id': 1, 'task_id': 12}, {'id': 2, 'task_id': 99}],
        'test_result_dimensions': [{'test_result_id': None}],
    })
    joined = '；'.join(errors)
    assert '单任务' in joined
    assert '99' in joined
    assert 'test_result_id' in joined


def test_validate_incremental_package_requires_source_task():
    assert validate_incremental_package({}, {}) == ['增量包缺少 manifest.sourceTask']


def test_manifest_versions_accept_10_and_11():
    # INT-1811：包结构变更（携带原始报文对象）→ 产出升 1.2；
    # 1.0 / 1.1 历史包仍在接受集内（不因版本号误拒）
    assert SUPPORTED_MANIFEST_VERSIONS == {ManifestVersion.V1_0.value,
                                           ManifestVersion.V1_1.value,
                                           ManifestVersion.V1_2.value}
    manifest = build_incremental_manifest(
        source_task={'id': 12, 'name': 't', 'caseCount': 2, 'caseSetHash': 'h'},
        task_rows=[{'id': 12, 'name': 't', 'status': 'completed', 'resultCount': 3}],
        dimension_count=4, report_count=1,
        entities=[IncrementalInclude.DIMENSIONS.value, IncrementalInclude.REPORTS.value],
        source='B-server')
    assert manifest['version'] == ManifestVersion.V1_2.value
    assert manifest['sourceTask']['id'] == 12
    assert manifest['stats']['resultCount'] == 0  # 增量包不搬结果本体
    assert validate_manifest(manifest)['version'] == '1.2'
    # 1.0 整包 / 1.1 历史增量包仍可导入（不因版本号误拒）
    assert validate_manifest({'version': '1.0', 'tasks': []})['version'] == '1.0'
    assert validate_manifest({'version': '1.1', 'tasks': []})['version'] == '1.1'
    with pytest.raises(Exception):
        validate_manifest({'version': '9.9', 'tasks': []})


def test_package_report_ids_only_returns_translated_ids():
    tables = {'test_reports': [{'id': 77}, {'name': 'no-id'}]}
    assert package_report_ids(tables) == [77]


# ---------- 编排：共享替身 ----------

class _FakeTaskRepository:
    def __init__(self, visible_ids):
        self._visible = set(visible_ids)

    def filter_visible_task_ids(self, task_ids, user_id=None, is_admin=None):
        return [tid for tid in task_ids if tid in self._visible]


class _FakeTransferRepository:
    """导出/导入共用的 task_service 仓储替身（内存数据）"""

    def __init__(self, **kw):
        self.task_row = kw.get('task_row', {'id': 25, 'name': 'B 任务', 'status': 'completed'})
        self.case_ids = kw.get('case_ids', ['c1', 'c2'])
        self.result_ids = kw.get('result_ids', [205, 206])
        self.source_refs = kw.get('source_refs', [{
            'source_server': 'A-server', 'source_task_id': 12,
            'entity_type': 'tasks', 'source_id': 12, 'local_id': 25}])
        self.source_ids = kw.get('source_ids', {
            'test_results': {205: 101, 206: 102}, 'test_reports': {900: 77}})
        self.identity = kw.get('identity', {'id': 12, 'name': 'A 任务',
                                            'status': 'completed', 'deleted': False})
        self.a_case_ids = kw.get('a_case_ids', ['c1', 'c2'])
        self.existing_results = kw.get('existing_results', {101, 102})

    # 导出侧
    def fetch_source_task_refs(self, local_task_ids):
        return [dict(ref) for ref in self.source_refs
                if ref['local_id'] in set(local_task_ids)]

    def fetch_export_rows(self, task_ids):
        return {
            'test_tasks': [dict(self.task_row)],
            'test_results': [{'id': rid, 'task_id': self.task_row['id']}
                             for rid in self.result_ids],
            'task_case_relations': [{'task_id': self.task_row['id'], 'test_case_id': cid}
                                    for cid in self.case_ids],
        }

    def fetch_source_ids_by_local_ids(self, source_server, entity_type, local_ids):
        return {int(k): int(v) for k, v in self.source_ids.get(entity_type, {}).items()
                if k in set(local_ids)}

    # 导入侧
    def fetch_task_identity(self, task_id):
        return self.identity

    def fetch_task_case_ids(self, task_id):
        return list(self.a_case_ids)

    def fetch_existing_result_ids(self, result_ids):
        return {rid for rid in result_ids if rid in self.existing_results}


class _FakeEvaluationAcl:
    def __init__(self, dimension_rows=None, dim_defs=None, merge_error=None):
        self.dimension_rows = dimension_rows or []
        # 注意不能用 `dim_defs or _target_defs()`：显式传空列表（目标库无维度）
        # 会被当成缺省，测试就测不到「全部未匹配」分支
        self.dim_defs = _target_defs() if dim_defs is None else dim_defs
        self.merge_error = merge_error
        self.calls = []
        self.merge_args = None

    def export_dimensions_for_tasks(self, result_ids):
        return {'dimensions': list(self.dimension_rows), 'dimension_defs': _pkg_defs()}

    def list_dimension_defs(self):
        return list(self.dim_defs)

    def merge_dimensions(self, rows, dimension_id_mapping, batch_id):
        self.calls.append('merge_dimensions')
        self.merge_args = (rows, dimension_id_mapping, batch_id)
        if self.merge_error:
            raise self.merge_error
        return {'imported': len(rows), 'deleted': 2, 'skipped_dimensions': [],
                'batch_id': batch_id, 'rollback_available': True}

    def rollback_dimension_merge(self, batch_id):
        self.calls.append('rollback_dimension_merge')
        return {'batch_id': batch_id, 'deleted': 0, 'restored': 0}


class _FakeReportAcl:
    def __init__(self, report_tables=None, replace_error=None, rollback_error=None):
        self.report_tables = report_tables or {}
        self.replace_error = replace_error
        self.rollback_error = rollback_error
        self.calls = []
        self.replace_args = None

    def export_reports_for_tasks(self, task_ids):
        return {table: [dict(row) for row in rows]
                for table, rows in self.report_tables.items()}

    def replace_reports(self, tables_rows, task_id, target_report_id, batch_id):
        self.calls.append('replace_reports')
        self.replace_args = (tables_rows, task_id, target_report_id, batch_id)
        if self.replace_error:
            raise self.replace_error
        return {'report_id': 77, 'target_resolved_by': 'target_report_id',
                'inserted_report_ids': [77], 'warnings': [],
                'batch_id': batch_id, 'rollback_available': True}

    def rollback_report_replacement(self, batch_id):
        self.calls.append('rollback_report_replacement')
        if self.rollback_error:
            raise self.rollback_error
        return {'batch_id': batch_id}


class _FakeBatchRegistry:
    def __init__(self):
        self.records = []
        self.removed = []
        self.deleted = []

    def record(self, batch_id, service, tables):
        self.records.append((service, tables))

    def remove_service(self, batch_id, service):
        self.removed.append(service)

    def delete(self, batch_id):
        self.deleted.append(batch_id)


@pytest.fixture()
def export_module(tmp_path, monkeypatch):
    from task_service.application.task import data_transfer_export_service as module
    return module


@pytest.fixture()
def import_module(monkeypatch):
    from task_service.application.task import data_transfer_import_service as module
    fake_registry = _FakeBatchRegistry()
    monkeypatch.setattr(module, 'transfer_batch_registry', fake_registry)
    # 任务可见性经 task_repository（真库仓储）判断，单测用内存替身
    import task_service.infrastructure.persistence.task_repository as task_repo_module
    monkeypatch.setattr(task_repo_module, 'task_repository',
                        _FakeTaskRepository({12}))
    return module, fake_registry


def _wire_export(export_module, monkeypatch, transfer_repo, eval_acl, report_acl, tmp_path,
                 visible=(25,)):
    monkeypatch.setattr(export_module, 'transfer_repository', transfer_repo)
    monkeypatch.setattr(export_module, 'evaluation_transfer_acl_repository', eval_acl)
    monkeypatch.setattr(export_module, 'report_transfer_acl_repository', report_acl)
    monkeypatch.setattr(export_module, '_export_tmp_dir', lambda: str(tmp_path))
    monkeypatch.setattr(export_module, 'resolve_transfer_server_id', lambda: 'B-server')
    import task_service.infrastructure.persistence.task_repository as task_repo_module
    monkeypatch.setattr(task_repo_module, 'task_repository',
                        _FakeTaskRepository(visible))


# ---------- 编排：增量导出 ----------

def test_export_incremental_builds_v12_package_with_translated_ids(
        export_module, monkeypatch, tmp_path):
    dims = [{'id': 1, 'test_result_id': 205, 'dimension_id': 2, 'round_number': 0},
            {'id': 2, 'test_result_id': 206, 'dimension_id': 2, 'round_number': 0}]
    reports = {'test_reports': [{'id': 900, 'task_id': 25, 'name': 'B 报告'}],
               'report_summaries': [{'id': 1, 'report_id': 900, 'summary': 's'}]}
    transfer_repo = _FakeTransferRepository()
    eval_acl = _FakeEvaluationAcl(dimension_rows=dims)
    report_acl = _FakeReportAcl(report_tables=reports)
    _wire_export(export_module, monkeypatch, transfer_repo, eval_acl, report_acl, tmp_path)

    result = export_module.data_transfer_export_service.export_incremental([25])
    assert result['success'] is True, result
    zip_path = result['data']['zip_path']
    assert os.path.isfile(zip_path)

    with zipfile.ZipFile(zip_path) as zf:
        names = set(zf.namelist())
        assert 'manifest.json' in names
        assert 'db/test_result_dimensions.json' in names
        assert 'db/test_reports.json' in names
        assert 'meta/dimensions.json' in names
        # 增量包不搬任务 / 结果 / 文件
        assert 'db/test_tasks.json' not in names
        assert 'db/test_results.json' not in names
        assert not any(name.startswith('files/') for name in names)
        import json
        manifest = json.loads(zf.read('manifest.json').decode('utf-8'))
        dim_rows = json.loads(zf.read('db/test_result_dimensions.json').decode('utf-8'))
        report_rows = json.loads(zf.read('db/test_reports.json').decode('utf-8'))

    assert manifest['version'] == '1.2'
    assert manifest['sourceTask']['id'] == 12
    assert manifest['sourceTask']['caseSetHash'] == case_set_hash(['c1', 'c2'])
    assert manifest['tasks'] == [{'id': 12, 'name': 'B 任务', 'status': 'completed',
                                  'resultCount': 2}]
    assert [row['test_result_id'] for row in dim_rows] == [101, 102]
    assert report_rows[0]['task_id'] == 12 and report_rows[0]['id'] == 77


def test_export_incremental_rejects_unmapped_result_rows(
        export_module, monkeypatch, tmp_path):
    dims = [{'id': 1, 'test_result_id': 205, 'dimension_id': 2},
            {'id': 2, 'test_result_id': 999, 'dimension_id': 2}]  # B 侧重执行新结果
    transfer_repo = _FakeTransferRepository()
    _wire_export(export_module, monkeypatch, transfer_repo,
                 _FakeEvaluationAcl(dimension_rows=dims), _FakeReportAcl(), tmp_path)

    result = export_module.data_transfer_export_service.export_incremental([25])
    assert result['success'] is False
    assert result['code'] == INCREMENTAL_UNMAPPED_CODE
    assert result['data']['unmappedResultIds'] == [999]
    assert not any(tmp_path.iterdir())  # 不产出包


def test_export_incremental_requires_single_task_and_source_map(
        export_module, monkeypatch, tmp_path):
    _wire_export(export_module, monkeypatch,
                 _FakeTransferRepository(source_refs=[]),
                 _FakeEvaluationAcl(), _FakeReportAcl(), tmp_path, visible=(25, 26))
    svc = export_module.data_transfer_export_service
    multi = svc.export_incremental([25, 26])
    assert multi['success'] is False and multi['code'] == 400
    missing = svc.export_incremental([25])
    assert missing['success'] is False and missing['code'] == 400
    assert '链路 1' in missing['message']


# ---------- 编排：增量导入 ----------

def _incremental_zip(tmp_path, *, task_id=12, case_hash=None, dims=None,
                     reports=None, extra_tasks=None):
    from task_service.domain.services.data_transfer import build_incremental_manifest

    dims = dims if dims is not None else [
        {'id': 1, 'test_result_id': 101, 'dimension_id': 2, 'round_number': 0}]
    reports = reports if reports is not None else {
        'test_reports': [{'id': 77, 'task_id': task_id, 'name': 'A 原报告'}],
        'report_summaries': [{'id': 5, 'report_id': 77, 'summary': 'new'}],
    }
    manifest = build_incremental_manifest(
        source_task={'id': task_id, 'name': 'A 任务', 'caseCount': 2,
                     'caseSetHash': case_hash or case_set_hash(['c1', 'c2'])},
        task_rows=[{'id': task_id, 'name': 'A 任务', 'status': 'completed',
                    'resultCount': 2}] + list(extra_tasks or []),
        dimension_count=len(dims), report_count=1,
        entities=['dimensions', 'reports'], source='B-server')
    path = tmp_path / 'incremental.zip'
    with zipfile.ZipFile(path, 'w') as zf:
        import json
        zf.writestr('manifest.json', json.dumps(manifest, ensure_ascii=False))
        zf.writestr('db/test_result_dimensions.json', json.dumps(dims, ensure_ascii=False))
        for table, rows in reports.items():
            zf.writestr(f'db/{table}.json', json.dumps(rows, ensure_ascii=False))
        zf.writestr('meta/dimensions.json', json.dumps(_pkg_defs(), ensure_ascii=False))
    return str(path)


def test_import_incremental_merges_dimensions_then_replaces_report(
        import_module, monkeypatch, tmp_path):
    module, registry = import_module
    transfer_repo = _FakeTransferRepository()
    eval_acl = _FakeEvaluationAcl()
    report_acl = _FakeReportAcl(report_tables={
        'test_reports': [{'id': 77, 'task_id': 12}]})
    monkeypatch.setattr(module, 'transfer_repository', transfer_repo)
    monkeypatch.setattr(module, 'evaluation_transfer_acl_repository', eval_acl)
    monkeypatch.setattr(module, 'report_transfer_acl_repository', report_acl)

    zip_path = _incremental_zip(tmp_path)
    result = module.data_transfer_import_service.import_incremental(zip_path)

    assert result['success'] is True, result
    data = result['data']
    assert data['taskId'] == 12
    assert data['mergedDimensions'] == 1
    assert data['replacedReportId'] == 77
    assert data['rollbackAvailable'] is True
    assert data['warnings'] == []
    # 段序：维度合并先于报告替换
    assert eval_acl.calls == ['merge_dimensions']
    assert report_acl.calls == ['replace_reports']
    # 维度 id 翻译按定义链（B 2 → A 11）
    _, dim_map, _ = eval_acl.merge_args
    assert dim_map == {1: 10, 2: 11}
    # 批次登记保留（7 天可回滚），成功后不销毁
    assert registry.records == [('evaluation_service', {}), ('report_service', {})]
    assert registry.deleted == []


def test_import_incremental_rejects_fingerprint_mismatch(
        import_module, monkeypatch, tmp_path):
    module, _ = import_module
    eval_acl = _FakeEvaluationAcl()
    report_acl = _FakeReportAcl()
    monkeypatch.setattr(module, 'transfer_repository', _FakeTransferRepository())
    monkeypatch.setattr(module, 'evaluation_transfer_acl_repository', eval_acl)
    monkeypatch.setattr(module, 'report_transfer_acl_repository', report_acl)

    zip_path = _incremental_zip(tmp_path, case_hash='deadbeef')
    result = module.data_transfer_import_service.import_incremental(zip_path)

    assert result['success'] is False
    assert result['code'] == INCREMENTAL_FINGERPRINT_CODE
    assert result['data']['expected'] == 'deadbeef'
    assert result['data']['actual'] == case_set_hash(['c1', 'c2'])
    # 未写任何数据
    assert eval_acl.calls == [] and report_acl.calls == []


def test_import_incremental_rejects_missing_result_ids(
        import_module, monkeypatch, tmp_path):
    module, _ = import_module
    eval_acl = _FakeEvaluationAcl()
    report_acl = _FakeReportAcl()
    monkeypatch.setattr(module, 'transfer_repository',
                        _FakeTransferRepository(existing_results=set()))
    monkeypatch.setattr(module, 'evaluation_transfer_acl_repository', eval_acl)
    monkeypatch.setattr(module, 'report_transfer_acl_repository', report_acl)

    zip_path = _incremental_zip(tmp_path)
    result = module.data_transfer_import_service.import_incremental(zip_path)

    assert result['success'] is False
    assert result['code'] == INCREMENTAL_ID_MISSING_CODE
    assert result['data']['missingIds'] == [101]
    assert eval_acl.calls == [] and report_acl.calls == []


def test_import_incremental_compensates_in_reverse_order_on_report_failure(
        import_module, monkeypatch, tmp_path):
    """段 2 失败 → 逆序补偿（报告段 → 维度段），旧值由 D4 快照恢复。"""
    from task_service.infrastructure.acl.report_transfer_acl import TransferReplaceError

    module, registry = import_module
    eval_acl = _FakeEvaluationAcl()
    report_acl = _FakeReportAcl(replace_error=TransferReplaceError(
        '报告替换失败: 子表写入失败', code=500, data={'detail': 'boom'}))
    monkeypatch.setattr(module, 'transfer_repository', _FakeTransferRepository())
    monkeypatch.setattr(module, 'evaluation_transfer_acl_repository', eval_acl)
    monkeypatch.setattr(module, 'report_transfer_acl_repository', report_acl)

    result = module.data_transfer_import_service.import_incremental(
        _incremental_zip(tmp_path))

    assert result['success'] is False and result['code'] == 500
    assert report_acl.calls == ['replace_reports', 'rollback_report_replacement']
    assert eval_acl.calls == ['merge_dimensions', 'rollback_dimension_merge']
    assert result['data']['compensationErrors'] == []
    assert registry.removed == ['report_service', 'evaluation_service']
    assert registry.deleted  # 补偿全部成功 → 销毁批次登记


def test_import_incremental_surfaces_compensation_failure(
        import_module, monkeypatch, tmp_path):
    """补偿自身失败必须显式要求人工介入，不得静默。"""
    from task_service.infrastructure.acl.report_transfer_acl import TransferReplaceError

    module, registry = import_module
    eval_acl = _FakeEvaluationAcl()
    report_acl = _FakeReportAcl(
        replace_error=TransferReplaceError('报告替换失败', code=500, data={}),
        rollback_error=RuntimeError('远端连接断开'))
    monkeypatch.setattr(module, 'transfer_repository', _FakeTransferRepository())
    monkeypatch.setattr(module, 'evaluation_transfer_acl_repository', eval_acl)
    monkeypatch.setattr(module, 'report_transfer_acl_repository', report_acl)

    result = module.data_transfer_import_service.import_incremental(
        _incremental_zip(tmp_path))

    assert result['success'] is False
    assert result['code'] == 500
    errors = result['data']['compensationErrors']
    assert errors and '报告替换段回滚失败' in errors[0]
    assert '人工介入' in result['message']
    assert not registry.deleted  # 补偿失败 → 保留批次登记供人工回滚


def test_import_incremental_rejects_multi_task_package(
        import_module, monkeypatch, tmp_path):
    module, _ = import_module
    eval_acl = _FakeEvaluationAcl()
    monkeypatch.setattr(module, 'transfer_repository', _FakeTransferRepository())
    monkeypatch.setattr(module, 'evaluation_transfer_acl_repository', eval_acl)
    monkeypatch.setattr(module, 'report_transfer_acl_repository', _FakeReportAcl())

    zip_path = _incremental_zip(tmp_path, extra_tasks=[{'id': 13, 'name': 'another'}])
    result = module.data_transfer_import_service.import_incremental(zip_path)
    assert result['success'] is False and result['code'] == 400
    assert eval_acl.calls == []


def test_import_incremental_skips_unmatched_dimensions_with_warning(
        import_module, monkeypatch, tmp_path):
    module, _ = import_module
    eval_acl = _FakeEvaluationAcl(dim_defs=[])  # 目标库没有这些维度
    report_acl = _FakeReportAcl()
    monkeypatch.setattr(module, 'transfer_repository', _FakeTransferRepository())
    monkeypatch.setattr(module, 'evaluation_transfer_acl_repository', eval_acl)
    monkeypatch.setattr(module, 'report_transfer_acl_repository', report_acl)

    result = module.data_transfer_import_service.import_incremental(
        _incremental_zip(tmp_path))
    assert result['success'] is True
    joined = '；'.join(result['data']['warnings'])
    assert '匹配不到' in joined and '跳过' in joined
    # 未命中的行在编排层就被滤掉：绝不把 B 的 dimension_id 交给远端直写
    assert eval_acl.calls == []  # 无可合并行 → 不发合并 RPC
    assert result['data']['mergedDimensions'] == 0


def test_import_incremental_requires_dimensions_snapshot(
        import_module, monkeypatch, tmp_path):
    """缺 meta/dimensions.json → 400（无法翻译维度 id，不得按 B id 直写）。"""
    module, _ = import_module
    eval_acl = _FakeEvaluationAcl()
    monkeypatch.setattr(module, 'transfer_repository', _FakeTransferRepository())
    monkeypatch.setattr(module, 'evaluation_transfer_acl_repository', eval_acl)
    monkeypatch.setattr(module, 'report_transfer_acl_repository', _FakeReportAcl())

    path = _incremental_zip(tmp_path)
    import zipfile
    with zipfile.ZipFile(path) as zf:
        payload = {name: zf.read(name) for name in zf.namelist()
                   if name != 'meta/dimensions.json'}
    with zipfile.ZipFile(path, 'w') as zf:
        for name, data in payload.items():
            zf.writestr(name, data)

    result = module.data_transfer_import_service.import_incremental(path)
    assert result['success'] is False and result['code'] == 400
    assert 'dimensions.json' in result['message']
    assert eval_acl.calls == []
