# -*- coding: utf-8 -*-
"""INT-262 专项：按任务查报告全链贯通。

背景（INT-95 第 10 轮主链复验）：GET /api/v1/reports?task_id=601 返回
task 534 的报告——网关 ReportListQuery 无 task_id 字段、report_service
ListReports servicer 忽略 proto 已有的 task_id 字段、仓储层无该过滤；
网关也未透出 /reports/by_task/{task_id}（V9.7.10 单体能力，微服务化
后丢失）。本文件按验收口径锁定：

- report_service 仓储/查询链：list_reports(task_id=X) 只返回该任务报告，
  任务无报告返回空列表而非全量
- gRPC servicer ListReports 透传 task_id（task_service ACL 已在发送该
  字段，此前被静默忽略）
- report_service HTTP 路由 list_reports 支持 task_id 查询参数
- api_gateway：ReportListQuery 接受 taskId/task_id、get_all 透传、
  /api/v1/reports/by_task/{task_id} 路由 200 且数据一致、任务无报告 404

DB：进程级 SQLite（tests/conftest.py 注入），按需 create_all 涉及表，
用例内自行清理，对齐 test_int219_report_trash_fields.py 口径。
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


def _make_report(name, task_id):
    from report_service.infrastructure.persistence.models import Report
    session = get_db_session()
    try:
        po = Report(name=name, type='task', status='completed', task_id=task_id)
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

    def GetReportByTask(self, req):
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


class TestReportTaskIdFilterChain:
    """report_service 仓储 → 查询 → gRPC/HTTP 路由：task_id 精确过滤。"""

    def setup_method(self):
        _ensure_report_tables()

    def teardown_method(self):
        _cleanup_tables(_REPORT_TABLES)

    def test_repo_list_reports_filters_by_task(self):
        """仓储层：task_id=601 只返回该任务报告；无报告任务返回空列表。"""
        from report_service.infrastructure.persistence.report_repository import (
            report_repository,
        )

        rid_534 = _make_report('INT262_534报告', task_id=534)
        rid_601 = _make_report('INT262_601报告', task_id=601)

        got = report_repository.list_reports(task_id=601, page=1, page_size=20)
        assert [a.id for a in got] == [rid_601]

        got_all = report_repository.list_reports(page=1, page_size=20)
        assert {a.id for a in got_all} >= {rid_534, rid_601}

        assert report_repository.list_reports(
            task_id=999999, page=1, page_size=20) == []

    def test_grpc_servicer_forwards_task_id(self):
        """gRPC servicer：ListReportsRequest.task_id 不再被忽略（回归主缺陷）。"""
        from shared.proto import report_service_pb2 as report_pb
        from report_service.interfaces.grpc.servicers import ReportServicer

        rid_534 = _make_report('INT262_gRPC_534', task_id=534)
        rid_601 = _make_report('INT262_gRPC_601', task_id=601)

        resp = ReportServicer().ListReports(
            report_pb.ListReportsRequest(page=1, per_page=20, task_id=601),
            context=None)
        assert resp.success is True
        data = grpc_loads(resp.data, {}) or {}
        ids = {i['id'] for i in data['items']}
        assert ids == {rid_601}

        resp_empty = ReportServicer().ListReports(
            report_pb.ListReportsRequest(page=1, per_page=20, task_id=999999),
            context=None)
        assert grpc_loads(resp_empty.data, {})['items'] == []

    def test_http_route_list_reports_filters_by_task(self):
        """report_service HTTP 路由：?task_id= 生效，缺省不过滤（既有用例不回归）。"""
        from report_service.interfaces.api.routes import list_reports

        rid_534 = _make_report('INT262_HTTP_534', task_id=534)
        rid_601 = _make_report('INT262_HTTP_601', task_id=601)

        resp = list_reports(status=None, task_id=601, page=1, page_size=20)
        assert resp['success'] is True
        ids = {i['id'] for i in resp['data']['items']}
        assert ids == {rid_601}

        resp_empty = list_reports(status=None, task_id=999999,
                                  page=1, page_size=20)
        assert resp_empty['success'] is True
        assert resp_empty['data']['items'] == []

        resp_all = list_reports(status=None, task_id=None, page=1, page_size=20)
        assert {i['id'] for i in resp_all['data']['items']} >= {rid_534, rid_601}


class TestGatewayReportTaskQuery:
    """api_gateway：schema 接受 taskId、get_all 透传、by_task 路由透出。"""

    def test_schema_accepts_task_id_both_spellings(self):
        from api_gateway.schemas.report import ReportListQuery

        assert ReportListQuery.model_validate(
            {'task_id': '601'}).task_id == 601
        assert ReportListQuery.model_validate(
            {'taskId': '601'}).task_id == 601
        assert ReportListQuery.model_validate({}).task_id is None

    def test_get_all_forwards_task_id(self, gw_client, monkeypatch):
        """GET /api/v1/reports?task_id=601 → gRPC ListReportsRequest.task_id=601。"""
        from shared.proto import report_service_pb2 as report_pb

        resp = report_pb.ReportConfigResponse(
            success=True, message='ok',
            data=grpc_dumps({'items': [], 'page': 1, 'page_size': 20}))
        fake = _install_fake_stub(monkeypatch, resp)

        r = gw_client.get('/api/v1/reports', params={'task_id': 601})
        assert r.status_code == 200
        assert fake.calls and fake.calls[0].task_id == 601

        # camelCase 拼写同样生效（NamingAliasMiddleware 缺席时靠 schema alias）
        gw_client.get('/api/v1/reports', params={'taskId': 534})
        assert fake.calls[-1].task_id == 534

    def test_gateway_by_task_route_success(self, gw_client, monkeypatch):
        """GET /api/v1/reports/by_task/{task_id} → 200 且数据一致。"""
        from shared.proto import report_service_pb2 as report_pb

        report = {'id': 436, 'task_id': 601, 'name': 'INT262_by_task',
                  'type': 'task', 'status': 'completed'}
        resp = report_pb.ReportConfigResponse(
            success=True, message='ok', data=grpc_dumps(report))
        fake = _install_fake_stub(monkeypatch, resp)

        r = gw_client.get('/api/v1/reports/by_task/601')
        assert r.status_code == 200
        assert fake.calls and fake.calls[0].task_id == 601
        body = r.json()
        assert body['success'] is True
        assert body['data']['id'] == 436
        assert body['data']['task_id'] == 601

    def test_gateway_by_task_route_not_found(self, gw_client, monkeypatch):
        """任务无报告 → HTTP 404（非静默错配）。"""
        from shared.proto import report_service_pb2 as report_pb

        resp = report_pb.ReportConfigResponse(
            success=False, message='report not found', data='')
        _install_fake_stub(monkeypatch, resp)

        r = gw_client.get('/api/v1/reports/by_task/999999')
        assert r.status_code == 404
        assert r.json()['success'] is False
