# -*- coding: utf-8 -*-
"""INT-219 专项：报告回收站列表 deleted_at / deleted_by_user_id 字段贯通。

背景：报告软删除链（INT-141）已落库与序列化，但 ListReports 全链（repo →
_report_po_to_entity → _aggregate_to_dict → gRPC servicer）对删除人/删除时间
字段无 pytest 锁定，且 api_gateway ReportListItem/ReportDetailData schema 缺
字段声明。本文件按验收口径锁定：

- 软删除后 ListReports(deleted=True) 全链条目含 deleted_at /
  deleted_by_user_id / deleted 真实数据
- 未删除报告与恢复后的报告两字段为 null（显式 null 不缺省，避免前端
  None 处理差异）
- api_gateway ReportListItem 字段口径与 TaskListItem 一致（同命名、同
  类型、同 null 语义），ReportDetailData 与详情序列化输出对齐

DB：进程级 SQLite（tests/conftest.py 注入），按需 create_all 涉及表，
用例内自行清理，对齐 test_int141_favorites_trash_operator.py 口径。
"""
import os

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

from shared.models.database import (
    Base, init_db, get_engine, get_db_session, remove_db_session,
)
from shared.infrastructure.user_context import set_current_user_id
from shared.utils.grpc_json import loads as grpc_loads

_REPORT_TABLES = None


def _ensure_db():
    init_db(pool_size=2)


def _ensure_report_tables():
    _ensure_db()
    global _REPORT_TABLES
    if _REPORT_TABLES is None:
        from report_service.infrastructure.persistence.models import (
            Report, ReportSummary, ReportSummaryMeta, ReportRawData,
            ReportCase, ReportMetricStats, ReportComparisonMatrix, ReportFavorite,
        )
        _REPORT_TABLES = [t.__table__ for t in (
            Report, ReportSummary, ReportSummaryMeta, ReportRawData,
            ReportCase, ReportMetricStats, ReportComparisonMatrix, ReportFavorite,
        )]
        Base.metadata.create_all(bind=get_engine(), tables=_REPORT_TABLES)
    return _REPORT_TABLES


def _cleanup_tables(tables):
    session = get_db_session()
    try:
        for table in tables:
            session.execute(table.delete())
        session.commit()
    finally:
        remove_db_session()


def _make_report(name='INT219_回收站报告'):
    from report_service.infrastructure.persistence.models import Report
    session = get_db_session()
    try:
        po = Report(name=name, type='task', status='completed',
                    created_by_user_id=444)
        session.add(po)
        session.commit()
        return po.id
    finally:
        remove_db_session()


def _soft_delete_report(rid, user_id):
    from report_service.infrastructure.persistence.report_repository import (
        report_repository,
    )
    set_current_user_id(user_id)
    try:
        assert report_repository.soft_delete(rid) is True
    finally:
        set_current_user_id(None)


class TestReportTrashFieldsChain:
    """删除 → 列表含删除人/时间；未删除/恢复后 → 字段为 null。"""

    def setup_method(self):
        _ensure_report_tables()

    def teardown_method(self):
        _cleanup_tables(_REPORT_TABLES)

    def test_deleted_list_carries_operator_and_time(self):
        """软删除后 list_reports(deleted=True) 聚合根与序列化均含真实数据。"""
        from report_service.infrastructure.persistence.report_repository import (
            report_repository,
        )
        from report_service.interfaces.grpc.servicers import _aggregate_to_dict

        rid = _make_report()
        _soft_delete_report(rid, user_id=555)

        aggregates = report_repository.list_reports(
            deleted=True, page=1, page_size=20)
        agg = next(a for a in aggregates if a.id == rid)
        assert agg.deleted is True
        assert agg.deleted_at is not None
        assert agg.deleted_by_user_id == 555

        item = _aggregate_to_dict(agg)
        assert item['deleted'] is True
        assert item['deleted_at']  # ISO 字符串非空
        assert item['deleted_by_user_id'] == 555

    def test_grpc_servicer_deleted_list_full_chain(self):
        """gRPC servicer ListReports(deleted=True) 响应条目含字段与 is_favorite。"""
        from shared.proto import report_service_pb2 as report_pb
        from report_service.interfaces.grpc.servicers import ReportServicer

        rid = _make_report(name='INT219_gRPC链路报告')
        _soft_delete_report(rid, user_id=777)

        resp = ReportServicer().ListReports(
            report_pb.ListReportsRequest(page=1, per_page=20, deleted=True),
            context=None)
        assert resp.success is True
        data = grpc_loads(resp.data, {}) or {}
        item = next(i for i in data['items'] if i['id'] == rid)
        assert item['deleted'] is True
        assert item['deleted_at']
        assert item['deleted_by_user_id'] == 777
        # 无用户上下文时收藏标记显式 False（不缺省）
        assert item['is_favorite'] is False

    def test_active_report_fields_null_by_default(self):
        """未删除报告两字段为显式 null 不缺省（验收1 后半）。"""
        from report_service.infrastructure.persistence.report_repository import (
            report_repository,
        )
        from report_service.interfaces.grpc.servicers import _aggregate_to_dict

        rid = _make_report(name='INT219_未删报告')
        aggregates = report_repository.list_reports(
            deleted=False, page=1, page_size=20)
        agg = next(a for a in aggregates if a.id == rid)
        item = _aggregate_to_dict(agg)
        assert item['deleted'] is False
        assert item['deleted_at'] is None
        assert item['deleted_by_user_id'] is None

    def test_restore_clears_fields_in_active_list(self):
        """恢复后 deleted 列表不含该报告；活跃列表条目字段回 null（验收3）。"""
        from report_service.infrastructure.persistence.report_repository import (
            report_repository,
        )
        from report_service.infrastructure.persistence.report_favorite_trash_repository import (
            report_favorite_trash_repository,
        )
        from report_service.interfaces.grpc.servicers import _aggregate_to_dict

        rid = _make_report()
        _soft_delete_report(rid, user_id=555)
        assert report_favorite_trash_repository.restore_reports([rid]) == 1

        deleted_ids = {a.id for a in report_repository.list_reports(
            deleted=True, page=1, page_size=20)}
        assert rid not in deleted_ids

        aggregates = report_repository.list_reports(
            deleted=False, page=1, page_size=20)
        agg = next(a for a in aggregates if a.id == rid)
        item = _aggregate_to_dict(agg)
        assert item['deleted'] is False
        assert item['deleted_at'] is None
        assert item['deleted_by_user_id'] is None


class TestReportTrashFieldsSchemaContract:
    """api_gateway schema 口径与 task 一致（验收2/4）。"""

    def test_report_list_item_schema_carries_trash_fields(self):
        """ReportListItem 接收并保留四字段，序列化输出 snake_case。"""
        from api_gateway.schemas.report import ReportListItem
        item = ReportListItem.model_validate({
            'id': 1, 'name': 'r', 'type': 'task', 'task_name': 't',
            'status': 'completed', 'created_at': '2026-10-12T00:00:00',
            'is_favorite': False, 'deleted': True,
            'deleted_at': '2026-10-12T10:00:00', 'deleted_by_user_id': 555,
        })
        assert item.is_favorite is False
        assert item.deleted is True
        assert item.deleted_at == '2026-10-12T10:00:00'
        assert item.deleted_by_user_id == 555
        dumped = item.model_dump()
        assert dumped['deleted_by_user_id'] == 555
        assert dumped['deleted_at'] == '2026-10-12T10:00:00'

    def test_report_list_item_fields_match_task_calibration(self):
        """与 TaskListItem 同命名、同类型、同 null 语义（验收2）。"""
        from api_gateway.schemas.report import ReportListItem
        from api_gateway.schemas.task import TaskListItem
        report_fields = ReportListItem.model_fields
        task_fields = TaskListItem.model_fields
        for name in ('is_favorite', 'deleted', 'deleted_at', 'deleted_by_user_id'):
            assert name in report_fields, f'ReportListItem 缺字段 {name}'
            assert report_fields[name].annotation == task_fields[name].annotation, (
                f'{name} 类型口径与 TaskListItem 不一致: '
                f'{report_fields[name].annotation} != {task_fields[name].annotation}')

    def test_report_detail_data_schema_carries_trash_fields(self):
        """ReportDetailData 与详情序列化输出对齐（目标：详情响应补字段）。"""
        from api_gateway.schemas.report import ReportDetailData
        detail = ReportDetailData.model_validate({
            'id': 1, 'name': 'r', 'type': 'task', 'task_name': 't',
            'status': 'completed', 'created_at': '2026-10-12T00:00:00',
            'summary': {}, 'deleted': True,
            'deleted_at': '2026-10-12T10:00:00', 'deleted_by_user_id': 555,
        })
        assert detail.deleted is True
        assert detail.deleted_at == '2026-10-12T10:00:00'
        assert detail.deleted_by_user_id == 555
        # 未删除语义：显式 null
        plain = ReportDetailData.model_validate({
            'id': 2, 'name': 'r2', 'type': 'task', 'task_name': 't',
            'status': 'completed', 'created_at': '2026-10-12T00:00:00',
            'summary': {},
        })
        assert plain.deleted is None
        assert plain.deleted_at is None
        assert plain.deleted_by_user_id is None
