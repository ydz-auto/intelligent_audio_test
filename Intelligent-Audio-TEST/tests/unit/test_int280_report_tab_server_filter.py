# -*- coding: utf-8 -*-
"""INT-280 专项：HistoryReports Tab 过滤服务端化全链贯通。

背景（INT-261 全站 UX 审计）：前端 Tab 切换退化为纯客户端过滤——分页 total
是全量总数、Tab 计数只统计当前页。且后端 report_service ListReports 链
（servicer → ListReportsQuery → 仓储）从未消费 proto 已有的 report_type
字段：即使前端下发 type 也无法服务端过滤（INT-262 task_id 同款断链）。
本文件按验收口径锁定：

- report_service 仓储：list_reports/count_reports 支持 report_types IN 过滤，
  空集合/None 不过滤（既有用例零回归）
- gRPC servicer：ListReports 透传 report_type（单值）+ CountReports 新 RPC
  （多类型逗号分隔拆分；分页字段忽略）
- report_service HTTP 路由 /api/reports/count（report_type 多类型逗号分隔）
- api_gateway：/api/v1/reports/tab-counts 四 Tab 聚合（all/draft/published/
  comparison），单 Tab 失败降级 0 不阻塞
- 仓储 count 与 list 过滤口径一致（INT-297 口径扩展到 report_types）

DB：进程级 SQLite（tests/conftest.py 注入），按需 create_all 涉及表，
用例内自行清理，对齐 test_int262_report_task_filter.py 口径。
"""
import os

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from shared.models.database import (
    Base, init_db, get_engine, get_db_session, remove_db_session,
)
from shared.utils.grpc_json import loads as grpc_loads, dumps as grpc_dumps

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


def _make_report(name, type_='task', status='draft'):
    from report_service.infrastructure.persistence.models import Report
    session = get_db_session()
    try:
        po = Report(name=name, type=type_, status=status)
        session.add(po)
        session.commit()
        return po.id
    finally:
        remove_db_session()


class _FakeStub:
    """report_config_service.stub 桩：记录请求并返回预设响应。"""

    def __init__(self, resp=None):
        self.resp = resp
        self.calls = []

    def ListReports(self, req):
        self.calls.append(req)
        return self.resp

    def CountReports(self, req):
        self.calls.append(req)
        return self.resp


def _install_fake_stub(monkeypatch, resp):
    from api_gateway.infrastructure.grpc_proxies import report_proxies
    fake = _FakeStub(resp)
    monkeypatch.setattr(report_proxies, 'get_report_config_service_stub',
                        lambda: fake)
    return fake


@pytest.fixture()
def gw_client():
    """挂载真实 report_bp 路由的迷你网关（注入 admin 权限 + 请求适配中间件）。"""
    from api_gateway.routes.report_bp import router as report_router
    from api_gateway.middleware import RequestAdapterMiddleware

    app = FastAPI()
    app.add_middleware(RequestAdapterMiddleware)

    @app.middleware('http')
    async def _inject_permissions(request, call_next):
        request.state.permissions = ['*']
        return await call_next(request)

    app.include_router(report_router, prefix='/api/v1/reports')
    return TestClient(app, raise_server_exceptions=False)


class TestReportTypesRepoFilter:
    """report_service 仓储层：report_types IN 过滤（list/count 同口径）。"""

    def setup_method(self):
        _ensure_report_tables()

    def teardown_method(self):
        _cleanup_tables(_REPORT_TABLES)

    def test_repo_list_reports_filters_by_types(self):
        """仓储层：report_types=['comparison','secondary_comparison'] 只返回这两类。"""
        from report_service.infrastructure.persistence.report_repository import (
            report_repository,
        )

        rid_task = _make_report('INT280_task报告', type_='task', status='published')
        rid_cmp = _make_report('INT280_对比报告', type_='comparison', status='published')
        rid_sec = _make_report('INT280_二次对比', type_='secondary_comparison', status='published')

        got = report_repository.list_reports(
            report_types=['comparison', 'secondary_comparison'],
            page=1, page_size=20)
        assert {a.id for a in got} == {rid_cmp, rid_sec}
        assert rid_task not in {a.id for a in got}

    def test_repo_count_matches_list_with_types(self):
        """count_reports 与 list_reports 在 report_types 下口径一致（INT-297 口径扩展）。"""
        from report_service.infrastructure.persistence.report_repository import (
            report_repository,
        )

        _make_report('INT280_CNT_task', type_='task', status='draft')
        _make_report('INT280_CNT_cmp', type_='comparison', status='draft')
        _make_report('INT280_CNT_sec', type_='secondary_comparison', status='published')

        types = ['comparison', 'secondary_comparison']
        total = report_repository.count_reports(report_types=types)
        listed = report_repository.list_reports(report_types=types, page=1, page_size=10)
        assert total == len(listed) == 2

    def test_repo_empty_types_no_filter(self):
        """None/空集合不过滤（既有调用方零回归）。"""
        from report_service.infrastructure.persistence.report_repository import (
            report_repository,
        )

        rid_a = _make_report('INT280_A', type_='task')
        rid_b = _make_report('INT280_B', type_='comparison')

        got = report_repository.list_reports(report_types=None, page=1, page_size=20)
        assert {a.id for a in got} >= {rid_a, rid_b}
        got_empty = report_repository.list_reports(report_types=[], page=1, page_size=20)
        assert {a.id for a in got_empty} >= {rid_a, rid_b}

    def test_repo_types_and_status_combined(self):
        """report_types 与 status 组合过滤（对比 Tab + 状态筛选并存）。"""
        from report_service.infrastructure.persistence.report_repository import (
            report_repository,
        )

        _make_report('INT280_pub_cmp', type_='comparison', status='published')
        rid_draft_cmp = _make_report('INT280_draft_cmp', type_='comparison', status='draft')
        _make_report('INT280_draft_task', type_='task', status='draft')

        got = report_repository.list_reports(
            status='draft', report_types=['comparison'],
            page=1, page_size=20)
        assert [a.id for a in got] == [rid_draft_cmp]


class TestGrpcListAndCountReports:
    """gRPC servicer：ListReports 透传 report_type + CountReports 新 RPC。"""

    def setup_method(self):
        _ensure_report_tables()

    def teardown_method(self):
        _cleanup_tables(_REPORT_TABLES)

    def test_grpc_list_reports_forwards_report_type(self):
        """ListReports：report_type 单值透传（此前被静默忽略——回归主缺陷）。"""
        from shared.proto import report_service_pb2 as report_pb
        from report_service.interfaces.grpc.servicers import ReportServicer

        rid_task = _make_report('INT280_gRPC_task', type_='task', status='draft')
        rid_cmp = _make_report('INT280_gRPC_cmp', type_='comparison', status='draft')
        rid_sec = _make_report('INT280_gRPC_sec', type_='secondary_comparison', status='draft')

        resp = ReportServicer().ListReports(
            report_pb.ListReportsRequest(page=1, per_page=20, report_type='comparison'),
            context=None)
        assert resp.success is True
        data = grpc_loads(resp.data, {}) or {}
        ids = {i['id'] for i in data['items']}
        assert ids == {rid_cmp}
        assert data['total'] == 1

        # 多类型逗号分隔（对比 Tab 口径）
        resp_multi = ReportServicer().ListReports(
            report_pb.ListReportsRequest(
                page=1, per_page=20,
                report_type='comparison,secondary_comparison'),
            context=None)
        data_multi = grpc_loads(resp_multi.data, {}) or {}
        assert {i['id'] for i in data_multi['items']} == {rid_cmp, rid_sec}
        assert rid_task not in {i['id'] for i in data_multi['items']}

    def test_grpc_count_reports_rpc(self):
        """CountReports：同一套过滤计数，分页字段忽略，响应 {'total': N}。"""
        from shared.proto import report_service_pb2 as report_pb
        from report_service.interfaces.grpc.servicers import ReportServicer

        rid_cmp = _make_report('INT280_CNT_gRPC_cmp', type_='comparison', status='draft')
        _make_report('INT280_CNT_gRPC_task', type_='task', status='draft')

        resp = ReportServicer().CountReports(
            report_pb.ListReportsRequest(report_type='comparison', page=1, per_page=3),
            context=None)
        assert resp.success is True
        assert (grpc_loads(resp.data, {}) or {})['total'] == 1
        assert rid_cmp

        # 无过滤总数 = 全部
        resp_all = ReportServicer().CountReports(
            report_pb.ListReportsRequest(), context=None)
        assert (grpc_loads(resp_all.data, {}) or {})['total'] == 2

    def test_grpc_count_reports_status_filter(self):
        """CountReports：status 过滤（草稿/已发布 Tab 计数口径）。"""
        from shared.proto import report_service_pb2 as report_pb
        from report_service.interfaces.grpc.servicers import ReportServicer

        _make_report('INT280_CNT_st_cmp', type_='comparison', status='draft')
        _make_report('INT280_CNT_st_cmp_pub', type_='comparison', status='published')

        resp_draft = ReportServicer().CountReports(
            report_pb.ListReportsRequest(status='draft'), context=None)
        total_draft = (grpc_loads(resp_draft.data, {}) or {})['total']
        resp_pub = ReportServicer().CountReports(
            report_pb.ListReportsRequest(status='published'), context=None)
        total_pub = (grpc_loads(resp_pub.data, {}) or {})['total']
        assert total_draft >= 1
        assert total_pub >= 1

    def test_grpc_list_reports_types_empty_segments_ignored(self):
        """report_type 纯逗号/空段归一为不过滤（防脏参数静默清空列表）。"""
        from shared.proto import report_service_pb2 as report_pb
        from report_service.interfaces.grpc.servicers import ReportServicer

        rid_a = _make_report('INT280_dirty_a', type_='task')
        rid_b = _make_report('INT280_dirty_b', type_='comparison')

        resp = ReportServicer().ListReports(
            report_pb.ListReportsRequest(page=1, per_page=20, report_type=',,'),
            context=None)
        data = grpc_loads(resp.data, {}) or {}
        assert {a for a in (rid_a, rid_b)} <= {i['id'] for i in data['items']}


class TestReportServiceHttpCount:
    """report_service HTTP 直连路由 /api/reports/count。"""

    def setup_method(self):
        _ensure_report_tables()

    def teardown_method(self):
        _cleanup_tables(_REPORT_TABLES)

    def test_http_count_reports(self):
        from report_service.interfaces.api.routes import count_reports

        _make_report('INT280_HTTP_cmp', type_='comparison', status='draft')
        _make_report('INT280_HTTP_task', type_='task', status='draft')

        resp = count_reports(status=None, report_type='comparison,secondary_comparison')
        assert resp['success'] is True
        assert resp['data']['total'] == 1

        resp_all = count_reports(status=None, report_type=None)
        assert resp_all['success'] is True
        assert resp_all['data']['total'] >= 2


class TestGatewayTabCounts:
    """api_gateway：/api/v1/reports/tab-counts 四 Tab 聚合。"""

    def test_tab_counts_assembles_four_tabs(self, gw_client, monkeypatch):
        """逐 Tab CountReports：all 无过滤 / draft|published 按状态 / comparison 多类型。"""
        from shared.proto import report_service_pb2 as report_pb

        captured = {}

        def _fake_count(req):
            captured[req.status or (req.report_type or 'all')] = True
            total_by_filter = {'all': 20, 'draft': 5, 'published': 12,
                               'comparison,secondary_comparison': 3}
            total = total_by_filter.get(req.status or req.report_type or 'all', 0)
            return report_pb.ReportConfigResponse(
                success=True, message='ok', data=grpc_dumps({'total': total}))

        fake = _FakeStub()
        fake.CountReports = _fake_count
        monkeypatch.setattr(report_proxies_module(), 'get_report_config_service_stub',
                            lambda: fake)

        r = gw_client.get('/api/v1/reports/tab-counts')
        assert r.status_code == 200
        body = r.json()
        assert body['success'] is True
        assert body['data'] == {'all': 20, 'draft': 5, 'published': 12, 'comparison': 3}
        # 四次 RPC：无过滤 + draft + published + 多类型
        assert captured.get('all') and captured.get('draft') and captured.get('published')
        assert captured.get('comparison,secondary_comparison')

    def test_tab_counts_single_tab_failure_degrades_to_zero(self, gw_client, monkeypatch):
        """单 Tab CountReports 失败：该 Tab 计数 0 降级继续，其余 Tab 正常。"""
        from shared.proto import report_service_pb2 as report_pb

        def _fake_count(req):
            if req.status == 'draft':
                raise RuntimeError('rpc down')
            if req.report_type:
                return report_pb.ReportConfigResponse(
                    success=True, message='ok', data=grpc_dumps({'total': 3}))
            total = {'all': 7, 'published': 2}.get(req.status or 'all')
            return report_pb.ReportConfigResponse(
                success=True, message='ok', data=grpc_dumps({'total': total}))

        fake = _FakeStub()
        fake.CountReports = _fake_count
        monkeypatch.setattr(report_proxies_module(), 'get_report_config_service_stub',
                            lambda: fake)

        r = gw_client.get('/api/v1/reports/tab-counts')
        assert r.status_code == 200
        body = r.json()
        assert body['data'] == {'all': 7, 'draft': 0, 'published': 2, 'comparison': 3}

    def test_tab_counts_grpc_failure_response_counts_zero(self, gw_client, monkeypatch):
        """CountReports 返回 success=False：该 Tab 计数 0（不假成功）。"""
        from shared.proto import report_service_pb2 as report_pb

        def _fake_count(req):
            if req.status == 'published':
                return report_pb.ReportConfigResponse(
                    success=False, message='boom', data=grpc_dumps({'total': 99}))
            return report_pb.ReportConfigResponse(
                success=True, message='ok', data=grpc_dumps({'total': 4}))

        fake = _FakeStub()
        fake.CountReports = _fake_count
        monkeypatch.setattr(report_proxies_module(), 'get_report_config_service_stub',
                            lambda: fake)

        r = gw_client.get('/api/v1/reports/tab-counts')
        assert r.status_code == 200
        body = r.json()
        assert body['data']['published'] == 0
        assert body['data']['all'] == 4


def report_proxies_module():
    from api_gateway.infrastructure.grpc_proxies import report_proxies
    return report_proxies
