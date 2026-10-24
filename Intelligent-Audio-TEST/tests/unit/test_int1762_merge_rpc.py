# -*- coding: utf-8 -*-
"""INT-1762 D4：离线搬运跨服务合并 RPC（维度合并 + 报告原地替换）单测

覆盖 D0 裁定（INT-1758）要求的口径：
- 维度合并按 `(test_result_id, dimension_id)` 覆盖集（含各 round），同任务其它
  result 的维度行一字不改；包内 result id 在 A 无维度行 → 409 + 明细、零写入；
  维度 id 未命中映射的行跳过并计入回执；旧值快照可取回并逐字段恢复。
- 报告替换原地保留 A 报告 id / visibility / created_by_user_id / type / created_at，
  6 子表重建；历史多报告只替换目标那一份；中途失败整事务回滚、旧报告完好；
  批次快照回滚逐字段恢复。
- proto 新增 RPC 的方法属性与 servicer JSON 信封。

DB：sqlite 临时库（复用 tests/integration/test_data_transfer_roundtrip.py 的 db
夹具：全模型建表 + 本地存储降级）。
"""
import json
import os

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

from tests.integration.test_data_transfer_roundtrip import db, storage_env  # noqa: F401

from report_service.infrastructure.persistence.models import (  # noqa: E402
    BenchmarkReport, Report, ReportCase, ReportComparisonMatrix, ReportFavorite,
    ReportMergeSnapshot, ReportMetricStats, ReportRawData, ReportShare,
    ReportStudioDocument, ReportSummary, ReportSummaryMeta,
)
from evaluation_service.infrastructure.persistence.models import (  # noqa: E402
    EvaluationMergeSnapshot,
    TestResultDimension as _ResultDimension,   # 别名：避免 pytest 误收集同名 PO
)

_CHILD_PO = {
    'report_summaries': ReportSummary,
    'report_summary_meta': ReportSummaryMeta,
    'report_raw_data': ReportRawData,
    'report_cases': ReportCase,
    'report_metric_stats': ReportMetricStats,
    'report_comparison_matrix': ReportComparisonMatrix,
}


def _session():
    from shared.models.database import get_db_session
    return get_db_session()


def _rows(po_cls, **filters):
    session = _session()
    try:
        query = session.query(po_cls)
        for key, value in filters.items():
            query = query.filter(getattr(po_cls, key) == value)
        return query.order_by(po_cls.__mapper__.primary_key[0].asc()).all()
    finally:
        session.close()


def _row_dicts(po_cls, **filters):
    out = []
    for po in _rows(po_cls, **filters):
        row = {}
        for col in po.__table__.columns:
            value = getattr(po, col.name)
            row[col.name] = value.isoformat(sep=' ') if hasattr(value, 'isoformat') else value
        out.append(row)
    return out


# ==================================================================
# 维度合并（evaluation_service）
# ==================================================================

def _seed_dimensions():
    """result 101：dim1 两轮 + dim2 一轮；result 102：dim1/dim2 各一轮"""
    session = _session()
    try:
        session.add_all([
            _ResultDimension(id=1, test_result_id=101, dimension_id=1,
                                round_number=0, score=10.0, status='failed',
                                evaluation_status='completed'),
            _ResultDimension(id=2, test_result_id=101, dimension_id=1,
                                round_number=1, score=11.0, status='failed',
                                evaluation_status='completed'),
            _ResultDimension(id=3, test_result_id=101, dimension_id=2,
                                round_number=None, score=20.0, status='passed',
                                evaluation_status='completed'),
            _ResultDimension(id=4, test_result_id=102, dimension_id=1,
                                round_number=None, score=30.0, status='passed',
                                evaluation_status='completed'),
        ])
        session.commit()
    finally:
        session.close()


class TestMergeDimensions:
    def test_overwrites_pairs_and_keeps_other_results_untouched(self, db):
        _seed_dimensions()
        other_before = _row_dicts(_ResultDimension, test_result_id=102)
        dim2_before = _row_dicts(_ResultDimension, test_result_id=101,
                                 dimension_id=2)
        from evaluation_service.application.dimension_merge_service import (
            dimension_merge_service,
        )
        result = dimension_merge_service.merge_dimensions(
            rows=[
                {'id': 901, 'test_result_id': 101, 'dimension_id': 1,
                 'round_number': 0, 'score': 88.0, 'status': 'passed',
                 'evaluation_status': 'completed'},
                {'id': 902, 'test_result_id': 101, 'dimension_id': 1,
                 'round_number': 1, 'score': 89.0, 'status': 'passed',
                 'evaluation_status': 'completed'},
            ],
            dimension_id_mapping={}, batch_id='batch-dim-1')

        assert result['success'] is True, result
        data = result['data']
        assert data['imported'] == 2
        assert data['deleted'] == 2          # dim1 的两轮旧行被覆盖
        assert data['rollback_available'] is True

        merged = _rows(_ResultDimension, test_result_id=101, dimension_id=1)
        assert sorted(r.round_number for r in merged) == [0, 1]
        assert [r.score for r in sorted(merged, key=lambda x: x.round_number)] == [88.0, 89.0]
        # 逐行比对：其它 result 与未覆盖维度一字不改
        assert _row_dicts(_ResultDimension, test_result_id=102) == other_before
        assert _row_dicts(_ResultDimension, test_result_id=101,
                          dimension_id=2) == dim2_before

    def test_missing_result_id_rejects_without_writes(self, db):
        _seed_dimensions()
        before = _row_dicts(_ResultDimension)
        from evaluation_service.application.dimension_merge_service import (
            dimension_merge_service,
        )
        result = dimension_merge_service.merge_dimensions(
            rows=[{'test_result_id': 101, 'dimension_id': 1, 'round_number': 0,
                   'score': 1.0, 'evaluation_status': 'completed'},
                  {'test_result_id': 999, 'dimension_id': 1, 'round_number': 0,
                   'score': 1.0, 'evaluation_status': 'completed'}],
            batch_id='batch-dim-miss')

        assert result['success'] is False
        assert result['data']['code'] == 409
        assert result['data']['missing_result_ids'] == [999]
        assert _row_dicts(_ResultDimension) == before
        assert _rows(EvaluationMergeSnapshot) == []

    def test_unmapped_dimension_is_skipped_not_written(self, db):
        _seed_dimensions()
        dim1_before = _row_dicts(_ResultDimension, test_result_id=101,
                                 dimension_id=1)
        from evaluation_service.application.dimension_merge_service import (
            dimension_merge_service,
        )
        result = dimension_merge_service.merge_dimensions(
            rows=[{'test_result_id': 101, 'dimension_id': 7, 'round_number': 0,
                   'score': 50.0, 'evaluation_status': 'completed'},
                  {'test_result_id': 101, 'dimension_id': 9, 'round_number': 0,
                   'score': 60.0, 'evaluation_status': 'completed'}],
            dimension_id_mapping={7: 1}, batch_id='batch-dim-skip')

        assert result['success'] is True, result
        assert result['data']['skipped_dimensions'] == [9]
        assert result['data']['imported'] == 1
        # 7 → 1 覆盖集生效：dim1 的两轮旧行被一条包内行取代，dim2 未在包内 → 不动
        assert sorted(r.dimension_id for r in
                      _rows(_ResultDimension, test_result_id=101)) == [1, 2]
        assert _row_dicts(_ResultDimension, test_result_id=101,
                          dimension_id=1) != dim1_before  # 7 → 1 生效
        assert not _rows(_ResultDimension, dimension_id=9)

    def test_rollback_restores_old_rows_field_by_field(self, db):
        _seed_dimensions()
        before = _row_dicts(_ResultDimension, test_result_id=101)
        from evaluation_service.application.dimension_merge_service import (
            dimension_merge_service,
        )
        merge = dimension_merge_service.merge_dimensions(
            rows=[{'test_result_id': 101, 'dimension_id': 1, 'round_number': 0,
                   'score': 1.0, 'evaluation_status': 'completed'}],
            batch_id='batch-dim-rollback')
        assert merge['success'] is True

        rollback = dimension_merge_service.rollback_merge('batch-dim-rollback')
        assert rollback['success'] is True, rollback
        assert rollback['data']['restored'] == 2
        assert rollback['data']['deleted'] == 1
        assert _row_dicts(_ResultDimension, test_result_id=101) == before
        assert _rows(EvaluationMergeSnapshot) == []

    def test_rollback_unknown_batch_is_noop(self, db):
        from evaluation_service.application.dimension_merge_service import (
            dimension_merge_service,
        )
        result = dimension_merge_service.rollback_merge('no-such-batch')
        assert result['success'] is True
        assert result['data']['nothing_to_rollback'] is True

    def test_servicer_json_envelope(self, db):
        _seed_dimensions()
        from evaluation_service.interfaces.grpc.evaluation_data_servicer import (
            EvaluationDataServiceServicer,
        )
        from shared.proto import evaluation_service_pb2 as eval_pb

        request = eval_pb.MergeDimensionsRequest(data=json.dumps({
            'rows': [{'test_result_id': 101, 'dimension_id': 2, 'score': 77.0,
                      'evaluation_status': 'completed'}],
            'dimension_id_mapping': {},
            'batch_id': 'batch-dim-rpc',
        }))
        resp = EvaluationDataServiceServicer().MergeDimensions(request)
        assert resp.success is True
        payload = json.loads(resp.data)
        assert payload['batch_id'] == 'batch-dim-rpc'
        assert payload['rollback_available'] is True

        bad = eval_pb.MergeDimensionsRequest(data=json.dumps({
            'rows': [{'test_result_id': 424242, 'dimension_id': 1}],
            'batch_id': 'batch-dim-rpc-bad',
        }))
        bad_resp = EvaluationDataServiceServicer().MergeDimensions(bad)
        assert bad_resp.success is False
        assert json.loads(bad_resp.data)['code'] == 409


# ==================================================================
# 报告原地替换（report_service）
# ==================================================================

def _seed_report(report_id, task_id, name, visibility='shared',
                 created_by=7, report_type='task', case_count=2):
    session = _session()
    try:
        session.add(Report(id=report_id, name=name, type=report_type, task_id=task_id,
                           status='published', description=f'{name}-desc',
                           analysis='old-analysis', visibility=visibility,
                           created_by_user_id=created_by))
        session.add(ReportSummary(id=report_id * 10 + 1, report_id=report_id,
                                  total_cases=case_count, pass_rate=0.5))
        session.add(ReportSummaryMeta(id=report_id * 10 + 2, report_id=report_id,
                                      all_metrics=[{'name': 'old'}]))
        session.add(ReportRawData(id=report_id * 10 + 3, report_id=report_id,
                                  raw_data={'old': True}))
        for index in range(case_count):
            session.add(ReportCase(id=report_id * 100 + index, report_id=report_id,
                                   test_case_id=f'case-{report_id}-{index}',
                                   name=f'用例{index}'))
        session.add(ReportMetricStats(id=report_id * 10 + 4, report_id=report_id,
                                      metric_data={'old': 1}))
        session.add(ReportComparisonMatrix(id=report_id * 10 + 5, report_id=report_id,
                                           comparison_matrix={'old': 1}))
        session.commit()
    finally:
        session.close()


def _package(new_report_id, task_id, name='新报告'):
    rows = {
        'test_reports': [{
            'id': new_report_id, 'name': name, 'type': 'task', 'task_id': task_id,
            'status': 'published', 'description': 'new-desc',
            'analysis': 'new-analysis', 'visibility': 'private',
            'created_by_user_id': 999,
            'created_at': '2026-10-01T10:00:00',
        }],
        'report_summaries': [{'id': new_report_id * 10 + 1,
                              'report_id': new_report_id, 'total_cases': 5,
                              'pass_rate': 0.9}],
        'report_summary_meta': [{'id': new_report_id * 10 + 2,
                                 'report_id': new_report_id,
                                 'all_metrics': [{'name': 'new'}]}],
        'report_raw_data': [{'id': new_report_id * 10 + 3,
                             'report_id': new_report_id, 'raw_data': {'new': True}}],
        'report_cases': [
            {'id': new_report_id * 100 + i, 'report_id': new_report_id,
             'test_case_id': f'new-case-{i}', 'name': f'新用例{i}'} for i in range(5)],
        'report_metric_stats': [{'id': new_report_id * 10 + 4,
                                 'report_id': new_report_id,
                                 'metric_data': {'new': 2}}],
        'report_comparison_matrix': [{'id': new_report_id * 10 + 5,
                                      'report_id': new_report_id,
                                      'comparison_matrix': {'new': 2}}],
    }
    return rows


def _table_counts(report_id):
    return {table: len(_rows(po_cls, report_id=report_id))
            for table, po_cls in _CHILD_PO.items()}


class TestReplaceReports:
    def test_in_place_keeps_identity_and_rebuilds_children(self, db):
        _seed_report(30, 12, '旧报告-最新', visibility='private', created_by=7)
        _seed_report(25, 12, '旧报告-历史', visibility='shared', created_by=8)
        created_at_30 = _rows(Report, id=30)[0].created_at
        history_before = _row_dicts(ReportCase, report_id=25)

        from report_service.application.report_replacement_service import (
            report_replacement_service,
        )
        result = report_replacement_service.replace_reports(
            _package(999, 12), task_id=12, batch_id='batch-rep-1')

        assert result['success'] is True, result
        data = result['data']
        assert data['replaced_tasks'] == [12]
        assert data['inserted_report_ids'] == [30]
        assert data['target_resolved_by'] == 'latest_report'
        assert data['deleted_counts']['report_cases'] == 2

        report = _rows(Report, id=30)[0]
        assert report.id == 30                       # 保留 A 报告 id
        assert report.name == '新报告'
        assert report.analysis == 'new-analysis'
        assert report.visibility == 'private'        # 保留 A 可见性
        assert report.created_by_user_id == 7        # 保留 A owner
        assert report.type == 'task'
        assert report.created_at == created_at_30    # 保留 A 创建时间
        # 旧子表行全部不存在、新子表挂在旧 id 上
        assert _table_counts(30) == {
            'report_summaries': 1, 'report_summary_meta': 1, 'report_raw_data': 1,
            'report_cases': 5, 'report_metric_stats': 1,
            'report_comparison_matrix': 1}
        assert not [po for po in _rows(ReportCase, report_id=30)
                    if po.id in (3000, 3001)]
        # 历史多报告（25）原样保留
        assert _row_dicts(ReportCase, report_id=25) == history_before
        assert _rows(Report, id=25)[0].name == '旧报告-历史'

    def test_creates_report_when_task_has_none(self, db):
        from report_service.application.report_replacement_service import (
            report_replacement_service,
        )
        result = report_replacement_service.replace_reports(
            _package(1001, 13), task_id=13, batch_id='batch-rep-new')

        assert result['success'] is True, result
        data = result['data']
        assert data['target_resolved_by'] == 'created'
        new_id = data['inserted_report_ids'][0]
        report = _rows(Report, id=new_id)[0]
        assert report.task_id == 13
        assert report.visibility == 'shared'     # B 的私有可见性不带入
        assert report.created_by_user_id is None
        assert _table_counts(new_id)['report_cases'] == 5

    def test_explicit_target_report_id_wins(self, db):
        _seed_report(30, 12, '旧报告-最新')
        _seed_report(25, 12, '旧报告-历史')
        from report_service.application.report_replacement_service import (
            report_replacement_service,
        )
        package = _package(999, 12, name='指定替换历史报告')
        package['test_reports'][0]['id'] = 25
        for table, rows in package.items():
            if table == 'test_reports':
                continue
            for row in rows:
                row['report_id'] = 25

        result = report_replacement_service.replace_reports(
            package, task_id=12, target_report_id=25, batch_id='batch-rep-target')

        assert result['success'] is True, result
        assert result['data']['target_resolved_by'] == 'target_report_id'
        assert _rows(Report, id=25)[0].name == '指定替换历史报告'
        assert _rows(Report, id=30)[0].name == '旧报告-最新'   # 未被波及

    def test_rollback_restores_seven_tables_field_by_field(self, db):
        _seed_report(30, 12, '旧报告-最新', visibility='private', created_by=7)
        before = {table: _row_dicts(po_cls, report_id=30)
                  for table, po_cls in _CHILD_PO.items()}
        before['test_reports'] = _row_dicts(Report, id=30)

        from report_service.application.report_replacement_service import (
            report_replacement_service,
        )
        assert report_replacement_service.replace_reports(
            _package(999, 12), task_id=12, batch_id='batch-rep-rb')['success'] is True

        rollback = report_replacement_service.rollback_replacement('batch-rep-rb')
        assert rollback['success'] is True, rollback
        after = {table: _row_dicts(po_cls, report_id=30)
                 for table, po_cls in _CHILD_PO.items()}
        after['test_reports'] = _row_dicts(Report, id=30)
        assert after == before
        assert _rows(ReportMergeSnapshot) == []

    def test_midway_failure_leaves_old_report_intact(self, db, monkeypatch):
        _seed_report(30, 12, '旧报告-最新', visibility='private', created_by=7)
        before = {table: _row_dicts(po_cls, report_id=30)
                  for table, po_cls in _CHILD_PO.items()}

        from report_service.application.report_replacement_service import (
            report_replacement_service,
        )
        from report_service.infrastructure.persistence import (
            report_replacement_repository as repo_module,
        )

        original = repo_module.ReportReplacementRepository._package_child_rows
        calls = {'n': 0}

        def _boom(tables, table, package_report_id, report_id):
            calls['n'] += 1
            if calls['n'] == 3:
                raise RuntimeError('injected failure')
            return original(tables, table, package_report_id, report_id)

        monkeypatch.setattr(
            repo_module.ReportReplacementRepository, '_package_child_rows',
            staticmethod(_boom))

        result = report_replacement_service.replace_reports(
            _package(999, 12), task_id=12, batch_id='batch-rep-fail')

        assert result['success'] is False
        assert result['data']['code'] == 500
        assert _rows(Report, id=30)[0].name == '旧报告-最新'
        after = {table: _row_dicts(po_cls, report_id=30)
                 for table, po_cls in _CHILD_PO.items()}
        assert after == before
        assert _rows(ReportMergeSnapshot) == []

    def test_multi_report_package_replaces_latest_and_warns(self, db):
        _seed_report(30, 12, '旧报告-最新')
        package = _package(999, 12, name='包内-最新')
        package['test_reports'][0]['created_at'] = '2026-10-02T10:00:00'
        older = dict(package['test_reports'][0])
        older.update({'id': 888, 'name': '包内-历史',
                      'created_at': '2026-10-01T10:00:00'})
        package['test_reports'].append(older)

        from report_service.application.report_replacement_service import (
            report_replacement_service,
        )
        result = report_replacement_service.replace_reports(
            package, task_id=12, batch_id='batch-rep-multi')

        assert result['success'] is True, result
        assert _rows(Report, id=30)[0].name == '包内-最新'
        assert result['data']['warnings'], result['data']
        assert '888' in result['data']['warnings'][0]

    def test_referrers_survive_in_place_replacement(self, db):
        """A5 引用方清单：share / studio / benchmark / 收藏 原地替换后仍有效、无孤儿"""
        _seed_report(30, 12, '旧报告-最新')
        session = _session()
        try:
            session.add(ReportShare(id=1, report_id=30, token='token-30', access='login'))
            session.add(ReportStudioDocument(doc_id='doc-000000000001', report_id=30,
                                             title='报告文档'))
            session.add(BenchmarkReport(id=1, report_id=30, suite='s1'))
            session.add(ReportFavorite(id=1, user_id=3, entity_type='report',
                                       entity_id='30'))
            session.commit()
        finally:
            session.close()

        from report_service.application.report_replacement_service import (
            report_replacement_service,
        )
        result = report_replacement_service.replace_reports(
            _package(999, 12), task_id=12, batch_id='batch-rep-refs')

        assert result['success'] is True, result
        assert result['data']['warnings'] == [], result['data']['warnings']
        assert len(_rows(ReportShare, report_id=30)) == 1
        assert len(_rows(ReportStudioDocument, report_id=30)) == 1
        assert len(_rows(BenchmarkReport, report_id=30)) == 1
        assert len(_rows(ReportFavorite, entity_id='30')) == 1
        # 报告本体仍是同一个 id（引用方无需改）
        assert _rows(Report, id=30)[0].name == '新报告'

    def test_servicer_json_envelope(self, db):
        _seed_report(30, 12, '旧报告-最新')
        from report_service.interfaces.grpc.servicers import ReportServicer
        from shared.proto import report_service_pb2 as report_pb

        request = report_pb.ReplaceReportsRequest(data=json.dumps({
            'rows_by_table': _package(999, 12),
            'task_id': 12,
            'batch_id': 'batch-rep-rpc',
        }))
        resp = ReportServicer().ReplaceReports(request)
        assert resp.success is True, resp.message
        payload = json.loads(resp.data)
        assert payload['replaced_tasks'] == [12]
        assert payload['rollback_available'] is True

        rollback = ReportServicer().RollbackReportReplacement(
            report_pb.RollbackReportReplacementRequest(batch_id='batch-rep-rpc'))
        assert rollback.success is True
        assert json.loads(rollback.data)['restored']['test_reports'] == 1


# ==================================================================
# proto 兼容性
# ==================================================================

class TestProtoCompatibility:
    def test_new_rpcs_registered_and_existing_untouched(self):
        from shared.proto import evaluation_service_pb2_grpc as eval_grpc
        from shared.proto import report_service_pb2_grpc as report_grpc

        assert hasattr(eval_grpc.EvaluationDataServiceStub, '__init__')
        servicer = eval_grpc.EvaluationDataServiceServicer()
        for name in ('MergeDimensions', 'RollbackDimensionMerge',
                     'ImportDimensions', 'RollbackDimensionImport',
                     'ExportDimensionsForTasks'):
            assert callable(getattr(servicer, name)), name

        report_servicer = report_grpc.ReportConfigServiceServicer()
        for name in ('ReplaceReports', 'RollbackReportReplacement',
                     'ImportReports', 'RollbackReportImport',
                     'ExportReportsForTasks'):
            assert callable(getattr(report_servicer, name)), name

    def test_response_envelopes_unchanged(self):
        from shared.proto import evaluation_service_pb2 as eval_pb
        from shared.proto import report_service_pb2 as report_pb

        assert set(eval_pb.EvaluationDataResponse.DESCRIPTOR.fields_by_name) == {
            'success', 'message', 'data'}
        assert set(report_pb.ReportConfigResponse.DESCRIPTOR.fields_by_name) == {
            'success', 'message', 'data', 'code'}
