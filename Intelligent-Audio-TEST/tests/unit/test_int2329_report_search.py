# -*- coding: utf-8 -*-
"""INT-2329 专项：报告中心搜索（keyword → ListReports.search）全链贯通。

背景（INT-2328 前端回归日巡）：报告中心搜索框输入关键字后，网关已把
``keyword`` 映射到 proto ``ListReportsRequest.search``，但 report_service
从未消费该字段——servicer 构造 ListReportsQuery 时丢弃、查询对象无字段、
仓储 list/count 无参数，导致列表、total、Tab 计数全部不生效。

本文件锁定修复口径：

- 仓储层 list_reports/count_reports(search=...) 按「名称或描述」模糊匹配，
  忽略大小写；空白关键字不过滤；LIKE 元字符按字面量匹配（不放大命中）。
- gRPC servicer ListReports 透传 search（主缺陷回归），items 与 total 同口径。
- report_service HTTP 路由支持 ?search=。

DB：进程级 SQLite（tests/conftest.py 注入），按需 create_all 涉及表，
用例内自行清理，对齐 test_int262_report_task_filter.py 口径。
"""
import os

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

from shared.models.database import (
    Base, init_db, get_engine, get_db_session, remove_db_session,
)
from shared.utils.grpc_json import loads as grpc_loads

_REPORT_TABLES = None


def _ensure_report_tables():
    init_db(pool_size=2)
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


def _make_report(name, task_id=None, description=None):
    from report_service.infrastructure.persistence.models import Report
    session = get_db_session()
    try:
        po = Report(name=name, type='task', status='completed',
                    task_id=task_id, description=description)
        session.add(po)
        session.commit()
        return po.id
    finally:
        remove_db_session()


@pytest.fixture()
def report_tables():
    tables = _ensure_report_tables()
    _cleanup_tables(tables)
    yield tables
    _cleanup_tables(tables)


class TestReportSearchRepository:
    """仓储层：list_reports / count_reports 的关键字过滤口径。"""

    def test_list_filters_by_name_keyword(self, report_tables):
        from report_service.infrastructure.persistence.report_repository import (
            report_repository,
        )

        hit = _make_report('接线测试_搜索命中报告', task_id=1)
        _make_report('无关报告', task_id=2)

        got = report_repository.list_reports(
            search='搜索命中', page=1, page_size=20)
        assert [a.id for a in got] == [hit]

    def test_list_search_is_case_insensitive(self, report_tables):
        from report_service.infrastructure.persistence.report_repository import (
            report_repository,
        )

        hit = _make_report('INT2329_AlphaReport')

        got = report_repository.list_reports(
            search='alphareport', page=1, page_size=20)
        assert [a.id for a in got] == [hit]

    def test_list_filters_by_description_keyword(self, report_tables):
        from report_service.infrastructure.persistence.report_repository import (
            report_repository,
        )

        hit = _make_report('INT2329_描述命中', description='包含关键字：夜间回归')
        _make_report('INT2329_描述无关', description='普通描述')

        got = report_repository.list_reports(
            search='夜间回归', page=1, page_size=20)
        assert [a.id for a in got] == [hit]

    def test_no_match_returns_empty(self, report_tables):
        from report_service.infrastructure.persistence.report_repository import (
            report_repository,
        )

        _make_report('INT2329_存在报告')

        assert report_repository.list_reports(
            search='zzzz_no_such', page=1, page_size=20) == []
        assert report_repository.count_reports(search='zzzz_no_such') == 0

    def test_blank_search_does_not_filter(self, report_tables):
        from report_service.infrastructure.persistence.report_repository import (
            report_repository,
        )

        _make_report('INT2329_空白A')
        _make_report('INT2329_空白B')

        assert report_repository.count_reports() == 2
        assert report_repository.count_reports(search='') == 2
        assert report_repository.count_reports(search='   ') == 2

    def test_count_matches_list_for_same_keyword(self, report_tables):
        from report_service.infrastructure.persistence.report_repository import (
            report_repository,
        )

        _make_report('INT2329_同口径_甲')
        _make_report('INT2329_同口径_乙')
        _make_report('其他报告')

        items = report_repository.list_reports(
            search='同口径', page=1, page_size=20)
        total = report_repository.count_reports(search='同口径')
        assert len(items) == total == 2

    def test_like_metacharacters_are_literal(self, report_tables):
        """关键字里的 % / _ 按字面量匹配，不放大成全表命中。"""
        from report_service.infrastructure.persistence.report_repository import (
            report_repository,
        )

        with_us = _make_report('INT2329_含下划线')
        _make_report('INT2329普通报告')

        # '%' 只命中名字里真的有百分号的报告（本数据没有 → 0，而非全表 2）
        assert report_repository.count_reports(search='%') == 0
        # '_' 只命中名字里真的有下划线的报告（1），不是任意单字符通配（2）
        assert report_repository.count_reports(search='_') == 1
        assert report_repository.list_reports(
            search='_', page=1, page_size=20)[0].id == with_us


class TestReportSearchGrpcServicer:
    """gRPC servicer：ListReportsRequest.search 不再被丢弃（主缺陷回归）。"""

    def test_servicer_forwards_search_to_items_and_total(self, report_tables):
        from shared.proto import report_service_pb2 as report_pb
        from report_service.interfaces.grpc.servicers import ReportServicer

        hit = _make_report('INT2329_gRPC_命中')
        _make_report('INT2329_gRPC_无关')

        resp = ReportServicer().ListReports(
            report_pb.ListReportsRequest(page=1, per_page=20, search='gRPC_命中'),
            context=None)
        assert resp.success is True
        data = grpc_loads(resp.data, {}) or {}
        assert {i['id'] for i in data['items']} == {hit}
        assert data['total'] == 1

    def test_servicer_no_match_returns_empty_page(self, report_tables):
        from shared.proto import report_service_pb2 as report_pb
        from report_service.interfaces.grpc.servicers import ReportServicer

        _make_report('INT2329_gRPC_存在')

        resp = ReportServicer().ListReports(
            report_pb.ListReportsRequest(page=1, per_page=20,
                                         search='zzzz_no_such'),
            context=None)
        assert resp.success is True
        data = grpc_loads(resp.data, {}) or {}
        assert data['items'] == []
        assert data['total'] == 0

    def test_servicer_without_search_keeps_full_list(self, report_tables):
        from shared.proto import report_service_pb2 as report_pb
        from report_service.interfaces.grpc.servicers import ReportServicer

        _make_report('INT2329_gRPC_无关键字A')
        _make_report('INT2329_gRPC_无关键字B')

        resp = ReportServicer().ListReports(
            report_pb.ListReportsRequest(page=1, per_page=20), context=None)
        data = grpc_loads(resp.data, {}) or {}
        assert data['total'] == 2


class TestReportSearchHttpRoute:
    """report_service HTTP 路由：?search= 生效且不回归缺省行为。"""

    def test_http_route_filters_by_search(self, report_tables):
        from report_service.interfaces.api.routes import list_reports

        hit = _make_report('INT2329_HTTP_命中')
        _make_report('INT2329_HTTP_无关')

        resp = list_reports(status=None, task_id=None, search='HTTP_命中',
                            page=1, page_size=20)
        assert resp['success'] is True
        assert {i['id'] for i in resp['data']['items']} == {hit}
        assert resp['data']['total'] == 1

        resp_all = list_reports(status=None, task_id=None, search=None,
                                page=1, page_size=20)
        assert resp_all['data']['total'] == 2
