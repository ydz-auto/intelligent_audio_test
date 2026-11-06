# -*- coding: utf-8 -*-
"""INT-145 缺陷包 1/2：报告更新静默丢弃 + 批量删除恒空删。

缺陷1（PUT /reports/{id} 更新静默丢弃·严重）：修复前 servicer UpdateReport
只落 status，name/description/analysis/summary 全部丢弃但仍返回 updated:true
——前端报告编辑（ReportView.vue）与对比报告摘要自动保存（useReportShared.ts）
全部假成功。修复后主表字段 + 4 张快照子表（summaries/summary_meta/raw_data/
metric_stats）一并落库（对齐旧库语义），camelCase summary 键归一。

缺陷2（POST /reports/batch-delete 恒空删·严重）：修复前网关发 ids、服务读
report_ids → 恒删 0 条返回成功；hard_delete 参数被忽略；旧库 100 条上限未
迁移。修复后字段对齐（兼容历史 report_ids 键）+ hard_delete 语义 + 上限
校验 + 「删 0 条不得返回成功」守卫。
"""
import json
import os
import tempfile

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from sqlalchemy import create_engine
from sqlalchemy import BigInteger
from sqlalchemy.ext.compiler import compiles

import pytest

import shared.models.database as database
from report_service.domain.entities import ReportAggregate
from report_service.infrastructure.persistence.report_repository import report_repository
from report_service.interfaces.grpc.servicers import (
    MAX_BATCH_DELETE,
    ReportServicer,
)
from shared.proto import report_service_pb2 as report_pb
from shared.utils.grpc_json import dumps as _dumps, loads as _loads


@compiles(BigInteger, 'sqlite')
def _render_bigint_as_integer_sqlite(type_, compiler, **kw):
    return 'INTEGER'


@pytest.fixture()
def db():
    """SQLite 临时文件库：engine 直装全局 scoped_session，仅建报告 5 张表。"""
    from report_service.infrastructure.persistence.models import (
        Report,
        ReportSummary,
        ReportSummaryMeta,
        ReportRawData,
        ReportMetricStats,
        ReportCase,
        ReportComparisonMatrix,
    )

    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    engine = create_engine(f'sqlite:///{path}',
                           connect_args={'check_same_thread': False})
    database.remove_db_session()
    database._engine = engine
    database._SessionFactory.configure(bind=engine)
    database.Base.metadata.create_all(engine, tables=[
        Report.__table__, ReportSummary.__table__, ReportSummaryMeta.__table__,
        ReportRawData.__table__, ReportMetricStats.__table__,
        ReportCase.__table__, ReportComparisonMatrix.__table__,
    ])
    yield database
    database.remove_db_session()
    engine.dispose()
    # 尽力清理：后台监听线程可能仍持连接（Windows 文件锁），删除失败不算失败
    try:
        os.remove(path)
    except PermissionError:
        pass


def _seed_report() -> int:
    """生成一份带 4 张快照子表的 task 报告，返回报告 ID。"""
    agg = ReportAggregate(
        id=0, task_id=11, report_type='task', status='draft',
        config={'name': '原始名称', 'description': '原始描述'},
    )
    rid = report_repository.add(agg)
    report_repository.add_summary(rid, {
        'total_cases': 10, 'completed_cases': 8, 'failed_cases': 2,
        'pass_rate': 80.0,
    })
    report_repository.add_summary_meta(rid, {
        'case_categories': json.dumps(['g1'], ensure_ascii=False),
        'all_case_tags': json.dumps(['t1'], ensure_ascii=False),
        'resource_headers': json.dumps([{'id': 1}], ensure_ascii=False),
        'all_metrics': json.dumps([{'id': 1, 'name': '准确率'}], ensure_ascii=False),
    })
    report_repository.add_raw_data(rid, {
        'raw_data': json.dumps([{'v': 1}], ensure_ascii=False),
    })
    report_repository.add_metric_stats(rid, {
        'metric_data': json.dumps([{'resource': 'r1'}], ensure_ascii=False),
        'tag_metric_data': json.dumps([], ensure_ascii=False),
        'case_type_stats': json.dumps([], ensure_ascii=False),
    })
    return rid


def _update(servicer, report_id, payload):
    return servicer.UpdateReport(report_pb.UpdateReportRequest(
        report_id=report_id, data=_dumps(payload)))


# ==================== 缺陷1：更新落库 ====================

class TestUpdateReportPersists:
    def test_name_description_conclusion_persist(self, db):
        """修复前：name/description/conclusion 被丢弃仍返回 updated:true。"""
        rid = _seed_report()
        servicer = ReportServicer()

        resp = _update(servicer, rid, {
            'name': '新名称', 'description': '新描述', 'conclusion': '新结论',
        })

        assert resp.success is True
        assert _loads(resp.data, {})['updated'] is True
        detail = servicer.GetReportDetail(
            report_pb.GetReportDetailRequest(report_id=rid))
        data = _loads(detail.data, {})
        assert data['name'] == '新名称'
        assert data['description'] == '新描述'
        assert data['conclusion'] == '新结论'
        assert data['analysis'] == '新结论'

    def test_title_alias_and_analysis_priority(self, db):
        """title 别名归一为 name；analysis 优先于 conclusion（对齐旧库 pick）。"""
        rid = _seed_report()
        servicer = ReportServicer()

        resp = _update(servicer, rid, {'title': '标题名', 'analysis': '分析A'})

        assert resp.success is True
        detail = _loads(servicer.GetReportDetail(
            report_pb.GetReportDetailRequest(report_id=rid)).data, {})
        assert detail['name'] == '标题名'
        assert detail['analysis'] == '分析A'

    def test_summary_snapshot_updates_four_child_tables(self, db):
        """summary 快照更新覆盖 4 张子表（修复前全部丢弃）。"""
        from report_service.infrastructure.persistence.models import (
            ReportSummary,
            ReportSummaryMeta,
            ReportRawData,
            ReportMetricStats,
        )

        rid = _seed_report()
        servicer = ReportServicer()

        resp = _update(servicer, rid, {
            'summary': {
                'totalCases': 12, 'completedCases': 9, 'failedCases': 3,
                'passRate': 75.0,
                'caseCategories': ['g2'],
                'allCaseTags': ['t2'],
                'resourceHeaders': [{'id': 2}],
                'allMetrics': [{'id': 2, 'name': '时延'}],
                'rawData': [{'v': 2}],
                'metricData': [{'resource': 'r2'}],
                'tagMetricData': [{'resource': 'r2'}],
                'caseTypeStats': [{'type': 'api'}],
            },
        })

        assert resp.success is True
        session = db.get_db_session()
        try:
            summary_po = session.query(ReportSummary).filter_by(report_id=rid).first()
            assert (summary_po.total_cases, summary_po.completed_cases,
                    summary_po.failed_cases, summary_po.pass_rate) == (12, 9, 3, 75.0)
            meta_po = session.query(ReportSummaryMeta).filter_by(report_id=rid).first()
            assert json.loads(meta_po.case_categories) == ['g2']
            assert json.loads(meta_po.all_case_tags) == ['t2']
            assert json.loads(meta_po.resource_headers) == [{'id': 2}]
            assert json.loads(meta_po.all_metrics) == [{'id': 2, 'name': '时延'}]
            raw_po = session.query(ReportRawData).filter_by(report_id=rid).first()
            assert json.loads(raw_po.raw_data) == [{'v': 2}]
            stats_po = session.query(ReportMetricStats).filter_by(report_id=rid).first()
            assert json.loads(stats_po.metric_data) == [{'resource': 'r2'}]
            assert json.loads(stats_po.tag_metric_data) == [{'resource': 'r2'}]
            assert json.loads(stats_po.case_type_stats) == [{'type': 'api'}]
        finally:
            db.remove_db_session()

    def test_snake_case_summary_keys_accepted(self, db):
        """snake_case summary 键（网关 toReportSummaryFieldDto 出口）直接落库。"""
        from report_service.infrastructure.persistence.models import ReportSummaryMeta

        rid = _seed_report()
        servicer = ReportServicer()

        resp = _update(servicer, rid, {
            'summary': {'case_categories': ['g3'], 'all_tags': ['t3']},
        })

        assert resp.success is True
        session = db.get_db_session()
        try:
            meta_po = session.query(ReportSummaryMeta).filter_by(report_id=rid).first()
            assert json.loads(meta_po.case_categories) == ['g3']
            # all_tags 为历史别名，归一落 all_case_tags
            assert json.loads(meta_po.all_case_tags) == ['t3']
        finally:
            db.remove_db_session()

    def test_partial_update_keeps_other_fields(self, db):
        """部分更新：未携带字段不回退（summary 只更新携带键）。"""
        rid = _seed_report()
        servicer = ReportServicer()

        resp = _update(servicer, rid, {'summary': {'total_cases': 20}})

        assert resp.success is True
        from report_service.infrastructure.persistence.models import ReportSummary
        session = db.get_db_session()
        try:
            summary_po = session.query(ReportSummary).filter_by(report_id=rid).first()
            assert summary_po.total_cases == 20
            assert summary_po.completed_cases == 8  # 未携带键保持原值
        finally:
            db.remove_db_session()
        detail = _loads(servicer.GetReportDetail(
            report_pb.GetReportDetailRequest(report_id=rid)).data, {})
        assert detail['name'] == '原始名称'  # name 未携带保持原值

    def test_missing_report_returns_updated_false(self, db):
        """报告不存在/已删除：不得假成功（修复前恒 updated:true）。"""
        rid = _seed_report()
        servicer = ReportServicer()

        resp = _update(servicer, 9999, {'name': 'x'})
        assert resp.success is False

        report_repository.soft_delete(rid)
        resp = _update(servicer, rid, {'name': 'x'})
        assert resp.success is False


# ==================== 缺陷2：批量删除 ====================

def _batch(servicer, payload):
    return servicer.BatchActionReports(report_pb.BatchActionReportsRequest(
        data=_dumps(payload)))


class TestBatchDeleteReports:
    def test_gateway_ids_field_alignment(self, db):
        """网关发 ids（修复前服务读 report_ids 恒删 0 条仍返回成功）。"""
        rid = _seed_report()
        servicer = ReportServicer()

        resp = _batch(servicer, {'ids': [rid], 'action': 'delete'})

        assert resp.success is True
        data = _loads(resp.data, {})
        assert data['deleted_count'] == 1
        assert data['items'] == [{'report_id': rid, 'deleted': True}]

    def test_delete_zero_must_not_succeed(self, db):
        """守卫：请求的 ID 全部不存在 → 不得返回成功（恒空删假成功缺陷回归位）。"""
        _seed_report()
        servicer = ReportServicer()

        resp = _batch(servicer, {'ids': [987654], 'action': 'delete'})

        assert resp.success is False
        assert _loads(resp.data, {})['deleted_count'] == 0

    def test_legacy_report_ids_key_still_accepted(self, db):
        """历史 report_ids 键兼容读取（对齐旧库契约）。"""
        rid = _seed_report()
        servicer = ReportServicer()

        resp = _batch(servicer, {'report_ids': [rid], 'action': 'delete'})

        assert resp.success is True
        assert _loads(resp.data, {})['deleted_count'] == 1

    def test_soft_delete_marks_deleted(self, db):
        """默认软删除：主行 deleted=True，GetReportDetail 查不到。"""
        rid = _seed_report()
        servicer = ReportServicer()

        resp = _batch(servicer, {'ids': [rid]})

        assert resp.success is True
        detail = servicer.GetReportDetail(
            report_pb.GetReportDetailRequest(report_id=rid))
        assert detail.success is False
        from report_service.infrastructure.persistence.models import Report
        session = db.get_db_session()
        try:
            po = session.get(Report, rid)
            assert po is not None and po.deleted is True
        finally:
            db.remove_db_session()

    def test_hard_delete_removes_row(self, db):
        """hard_delete=True：主行物理删除（修复前参数被忽略）。"""
        rid = _seed_report()
        servicer = ReportServicer()

        resp = _batch(servicer, {'ids': [rid], 'hard_delete': True})

        assert resp.success is True
        from report_service.infrastructure.persistence.models import Report
        session = db.get_db_session()
        try:
            assert session.get(Report, rid) is None
        finally:
            db.remove_db_session()

    def test_over_limit_rejected(self, db):
        """旧库 100 条上限校验迁移。"""
        servicer = ReportServicer()
        ids = list(range(1, MAX_BATCH_DELETE + 2))

        resp = _batch(servicer, {'ids': ids})

        assert resp.success is False
        assert '100' in resp.message

    def test_empty_ids_rejected(self, db):
        servicer = ReportServicer()

        resp = _batch(servicer, {'ids': [], 'action': 'delete'})

        assert resp.success is False
