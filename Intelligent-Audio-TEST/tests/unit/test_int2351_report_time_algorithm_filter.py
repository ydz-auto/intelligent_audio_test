# -*- coding: utf-8 -*-
"""INT-2351 专项：报告列表时间范围 / 算法类型筛选全链贯通。

背景（INT-2339 方案一致性审计）：报告中心可传 ``start_time`` / ``end_time`` /
``algorithm_type``，网关也已映射进 proto ``ListReportsRequest``（start_date=8 /
end_date=9 / algorithm_type=4），但 report_service servicer 构造
``ListReportsQuery`` 时整组丢弃——页面上筛了不生效（空契约）。

本文件锁定修复口径（契约见 doc/功能设计文档/05_报告管理 §3.3.1）：

- 时间窗作用于 ``test_reports.created_at``，闭区间；纯日期 ``YYYY-MM-DD`` 的
  结束边界覆盖当日整天；无时区按东八区，带 Z / 偏移按 ISO 换算东八区。
- 算法类型按 ``report_cases.algorithm_type`` 存在性归属（报告主表无该列，
  与报告统计同口径）。
- 非法日期 / 起止倒置 → 失败（网关转 400），不静默降级为「不过滤」。
- 列表 items 与 total 同口径；Tab 计数不纳入这两维（INT-2339 裁定）。

DB：进程级 SQLite（tests/conftest.py 注入），按需 create_all 涉及表，
用例内自行清理，对齐 test_int2329_report_search.py 口径。
"""
import os
from datetime import datetime

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


def _make_report(name, task_id=None, created_at=None, status='completed',
                 report_type='task'):
    from report_service.infrastructure.persistence.models import Report
    session = get_db_session()
    try:
        po = Report(name=name, type=report_type, status=status,
                    task_id=task_id, created_at=created_at or datetime(2026, 10, 15, 12, 0, 0))
        session.add(po)
        session.commit()
        return po.id
    finally:
        remove_db_session()


def _make_case(report_id, algorithm_type, test_case_id='c1', seq=1):
    from report_service.infrastructure.persistence.models import ReportCase
    session = get_db_session()
    try:
        # SQLite 的 BigInteger 主键不自增（INT-2351 测试夹具）：显式给 id
        po = ReportCase(id=report_id * 100 + seq, report_id=report_id,
                        algorithm_type=algorithm_type, test_case_id=test_case_id)
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


class TestParseReportDate:
    """应用层日期解析：边界 / 格式 / 时区 / 非法值。"""

    def test_date_only_start_is_midnight(self):
        from report_service.application.queries.report_queries import parse_report_date

        assert parse_report_date('2026-11-02') == datetime(2026, 11, 2, 0, 0, 0)

    def test_date_only_end_covers_whole_day(self):
        from report_service.application.queries.report_queries import parse_report_date

        assert parse_report_date('2026-11-02', end_of_day=True) == \
            datetime(2026, 11, 2, 23, 59, 59, 999999)

    def test_datetime_end_is_not_extended(self):
        """带时刻的结束边界按原时刻，不推整天（否则会多 1 天）。"""
        from report_service.application.queries.report_queries import parse_report_date

        assert parse_report_date('2026-11-02 07:26', end_of_day=True) == \
            datetime(2026, 11, 2, 7, 26, 0)

    def test_space_and_iso_t_separator_equal(self):
        from report_service.application.queries.report_queries import parse_report_date

        assert parse_report_date('2026-11-02 07:26') == \
            parse_report_date('2026-11-02T07:26')

    def test_utc_suffix_is_converted_to_cst(self):
        from report_service.application.queries.report_queries import parse_report_date

        assert parse_report_date('2026-11-01T16:00:00Z') == \
            datetime(2026, 11, 2, 0, 0, 0)

    def test_blank_is_no_filter(self):
        from report_service.application.queries.report_queries import parse_report_date

        assert parse_report_date(None) is None
        assert parse_report_date('') is None
        assert parse_report_date('   ') is None

    @pytest.mark.parametrize('bad', ['2026-13-01', '2026-02-30', 'not-a-date',
                                     '2026/11/02', '2026-11'])
    def test_invalid_raises(self, bad):
        from report_service.application.queries.report_queries import parse_report_date

        with pytest.raises(ValueError):
            parse_report_date(bad)


class TestRepositoryTimeWindow:
    """仓储层：created_at 闭区间 + 纯日期整天 + 开区间。"""

    def test_window_is_inclusive_on_both_ends(self, report_tables):
        from report_service.application.queries.report_queries import parse_report_date
        from report_service.infrastructure.persistence.report_repository import (
            report_repository,
        )

        at_start = _make_report('INT2351_起点', created_at=datetime(2026, 10, 1, 0, 0, 0))
        inside = _make_report('INT2351_窗内', created_at=datetime(2026, 10, 5, 12, 0, 0))
        at_end = _make_report('INT2351_终点', created_at=datetime(2026, 10, 9, 23, 59, 59))
        _make_report('INT2351_窗外前', created_at=datetime(2026, 9, 30, 23, 59, 59))
        _make_report('INT2351_窗外后', created_at=datetime(2026, 10, 10, 0, 0, 0))

        got = report_repository.list_reports(
            start_time=parse_report_date('2026-10-01'),
            end_time=parse_report_date('2026-10-09', end_of_day=True),
            page=1, page_size=20)
        assert {a.id for a in got} == {at_start, inside, at_end}

    def test_open_interval_start_only(self, report_tables):
        from report_service.application.queries.report_queries import parse_report_date
        from report_service.infrastructure.persistence.report_repository import (
            report_repository,
        )

        hit = _make_report('INT2351_开区间后', created_at=datetime(2026, 10, 20, 8, 0, 0))
        _make_report('INT2351_开区间前', created_at=datetime(2026, 10, 1, 8, 0, 0))

        got = report_repository.list_reports(
            start_time=parse_report_date('2026-10-10'), page=1, page_size=20)
        assert [a.id for a in got] == [hit]

    def test_open_interval_end_only(self, report_tables):
        from report_service.application.queries.report_queries import parse_report_date
        from report_service.infrastructure.persistence.report_repository import (
            report_repository,
        )

        hit = _make_report('INT2351_开区间早', created_at=datetime(2026, 10, 2, 8, 0, 0))
        _make_report('INT2351_开区间晚', created_at=datetime(2026, 10, 20, 8, 0, 0))

        got = report_repository.list_reports(
            end_time=parse_report_date('2026-10-10'), page=1, page_size=20)
        assert [a.id for a in got] == [hit]

    def test_date_only_end_includes_whole_day_row(self, report_tables):
        """结束日 23:59:59 的报告在「选到该日」时必须命中（整天含边界）。"""
        from report_service.application.queries.report_queries import parse_report_date
        from report_service.infrastructure.persistence.report_repository import (
            report_repository,
        )

        late = _make_report('INT2351_当日深夜', created_at=datetime(2026, 10, 9, 23, 59, 59))
        _make_report('INT2351_次日零点', created_at=datetime(2026, 10, 10, 0, 0, 0))

        got = report_repository.list_reports(
            end_time=parse_report_date('2026-10-09', end_of_day=True),
            page=1, page_size=20)
        assert [a.id for a in got] == [late]

    def test_no_window_keeps_full_list(self, report_tables):
        from report_service.infrastructure.persistence.report_repository import (
            report_repository,
        )

        _make_report('INT2351_无筛选A', created_at=datetime(2026, 1, 1, 0, 0, 0))
        _make_report('INT2351_无筛选B', created_at=datetime(2026, 12, 31, 23, 0, 0))
        assert report_repository.count_reports() == 2

    def test_count_matches_list_for_window(self, report_tables):
        from report_service.application.queries.report_queries import parse_report_date
        from report_service.infrastructure.persistence.report_repository import (
            report_repository,
        )

        _make_report('INT2351_同口径窗内A', created_at=datetime(2026, 10, 5, 1, 0, 0))
        _make_report('INT2351_同口径窗内B', created_at=datetime(2026, 10, 6, 1, 0, 0))
        _make_report('INT2351_同口径窗外', created_at=datetime(2026, 11, 6, 1, 0, 0))

        kwargs = {'start_time': parse_report_date('2026-10-01'),
                  'end_time': parse_report_date('2026-10-31', end_of_day=True)}
        items = report_repository.list_reports(page=1, page_size=20, **kwargs)
        assert len(items) == report_repository.count_reports(**kwargs) == 2


class TestRepositoryAlgorithmType:
    """仓储层：算法类型按 report_cases.algorithm_type 存在性归属。"""

    def test_matches_report_with_case_of_that_algorithm(self, report_tables):
        from report_service.infrastructure.persistence.report_repository import (
            report_repository,
        )

        voice = _make_report('INT2351_算法voice')
        _make_case(voice, 'voice_llm')
        asr = _make_report('INT2351_算法asr')
        _make_case(asr, 'asr')
        _make_report('INT2351_无用例报告')

        got = report_repository.list_reports(
            algorithm_type='voice_llm', page=1, page_size=20)
        assert [a.id for a in got] == [voice]
        assert report_repository.count_reports(algorithm_type='voice_llm') == 1

    def test_report_with_mixed_algorithms_matches_either(self, report_tables):
        """一份报告含多算法用例时，按任一算法筛选都应命中（存在性，不是唯一归属）。"""
        from report_service.infrastructure.persistence.report_repository import (
            report_repository,
        )

        mixed = _make_report('INT2351_混合算法')
        _make_case(mixed, 'voice_llm', 'c1', seq=1)
        _make_case(mixed, 'asr', 'c2', seq=2)

        assert [a.id for a in report_repository.list_reports(
            algorithm_type='voice_llm', page=1, page_size=20)] == [mixed]
        assert [a.id for a in report_repository.list_reports(
            algorithm_type='asr', page=1, page_size=20)] == [mixed]

    def test_unknown_algorithm_returns_empty(self, report_tables):
        from report_service.infrastructure.persistence.report_repository import (
            report_repository,
        )

        report = _make_report('INT2351_未知算法')
        _make_case(report, 'voice_llm')

        assert report_repository.list_reports(
            algorithm_type='no_such_algo', page=1, page_size=20) == []
        assert report_repository.count_reports(algorithm_type='no_such_algo') == 0

    def test_blank_algorithm_does_not_filter(self, report_tables):
        from report_service.infrastructure.persistence.report_repository import (
            report_repository,
        )

        _make_report('INT2351_空算法无用例')
        _make_report('INT2351_空算法有用例')

        assert report_repository.count_reports(algorithm_type='') == 2
        assert report_repository.count_reports(algorithm_type=None) == 2

    def test_combines_with_keyword_and_status(self, report_tables):
        from report_service.infrastructure.persistence.report_repository import (
            report_repository,
        )

        hit = _make_report('INT2351_组合命中', status='published')
        _make_case(hit, 'voice_llm')
        draft = _make_report('INT2351_组合草稿', status='draft')
        _make_case(draft, 'voice_llm')
        other = _make_report('INT2351_组合无关', status='published')
        _make_case(other, 'asr')

        got = report_repository.list_reports(
            search='组合命中', status='published', algorithm_type='voice_llm',
            page=1, page_size=20)
        assert [a.id for a in got] == [hit]


class TestServicerTimeAlgorithmFilter:
    """gRPC servicer：start_date / end_date / algorithm_type 不再被丢弃。"""

    def test_servicer_forwards_window_and_algorithm(self, report_tables):
        from shared.proto import report_service_pb2 as report_pb
        from report_service.interfaces.grpc.servicers import ReportServicer

        hit = _make_report('INT2351_gRPC命中',
                           created_at=datetime(2026, 10, 5, 10, 0, 0))
        _make_case(hit, 'voice_llm')
        old = _make_report('INT2351_gRPC窗内但算法不符',
                           created_at=datetime(2026, 10, 6, 10, 0, 0))
        _make_case(old, 'asr')
        _make_report('INT2351_gRPC窗外', created_at=datetime(2026, 9, 1, 10, 0, 0))

        resp = ReportServicer().ListReports(
            report_pb.ListReportsRequest(
                page=1, per_page=20,
                start_date='2026-10-01', end_date='2026-10-09',
                algorithm_type='voice_llm'),
            context=None)
        assert resp.success is True
        data = grpc_loads(resp.data, {}) or {}
        assert [i['id'] for i in data['items']] == [hit]
        assert data['total'] == 1

    def test_servicer_without_filters_keeps_full_list(self, report_tables):
        from shared.proto import report_service_pb2 as report_pb
        from report_service.interfaces.grpc.servicers import ReportServicer

        _make_report('INT2351_gRPC无筛选A')
        _make_report('INT2351_gRPC无筛选B')

        resp = ReportServicer().ListReports(
            report_pb.ListReportsRequest(page=1, per_page=20), context=None)
        data = grpc_loads(resp.data, {}) or {}
        assert data['total'] == 2

    def test_servicer_invalid_date_fails_loudly(self, report_tables):
        from shared.proto import report_service_pb2 as report_pb
        from report_service.interfaces.grpc.servicers import ReportServicer

        _make_report('INT2351_非法日期')

        resp = ReportServicer().ListReports(
            report_pb.ListReportsRequest(page=1, per_page=20, start_date='2026-13-01'),
            context=None)
        assert resp.success is False
        assert '日期' in resp.message

    def test_servicer_start_after_end_fails_loudly(self, report_tables):
        from shared.proto import report_service_pb2 as report_pb
        from report_service.interfaces.grpc.servicers import ReportServicer

        _make_report('INT2351_起止倒置')

        resp = ReportServicer().ListReports(
            report_pb.ListReportsRequest(page=1, per_page=20,
                                         start_date='2026-10-10',
                                         end_date='2026-10-01'),
            context=None)
        assert resp.success is False
        assert '晚于' in resp.message

    def test_count_reports_same_filters(self, report_tables):
        """CountReports 复用同一套过滤（列表 total 同口径的兜底）。"""
        from shared.proto import report_service_pb2 as report_pb
        from report_service.interfaces.grpc.servicers import ReportServicer

        hit = _make_report('INT2351_计数命中', created_at=datetime(2026, 10, 5, 9, 0, 0))
        _make_case(hit, 'voice_llm')
        _make_report('INT2351_计数窗外', created_at=datetime(2026, 9, 1, 9, 0, 0))

        resp = ReportServicer().CountReports(
            report_pb.ListReportsRequest(
                start_date='2026-10-01', end_date='2026-10-09',
                algorithm_type='voice_llm'),
            context=None)
        assert resp.success is True
        assert (grpc_loads(resp.data, {}) or {}).get('total') == 1


class TestServiceHttpRoute:
    """report_service 内部 HTTP 路由：同一套时间窗 / 算法类型筛选。"""

    def test_http_route_filters_by_window_and_algorithm(self, report_tables):
        from report_service.interfaces.api.routes import list_reports

        hit = _make_report('INT2351_HTTP命中', created_at=datetime(2026, 10, 5, 9, 0, 0))
        _make_case(hit, 'voice_llm')
        _make_report('INT2351_HTTP窗外', created_at=datetime(2026, 9, 1, 9, 0, 0))

        resp = list_reports(status=None, task_id=None, search=None,
                            start_time='2026-10-01', end_time='2026-10-09',
                            algorithm_type='voice_llm', page=1, page_size=20)
        assert resp['success'] is True
        assert [i['id'] for i in resp['data']['items']] == [hit]
        assert resp['data']['total'] == 1

    def test_http_route_blank_filters_keep_full_list(self, report_tables):
        from report_service.interfaces.api.routes import list_reports

        _make_report('INT2351_HTTP无筛选A')
        _make_report('INT2351_HTTP无筛选B')

        resp = list_reports(status=None, task_id=None, search=None,
                            start_time=None, end_time='', algorithm_type='',
                            page=1, page_size=20)
        assert resp['data']['total'] == 2
