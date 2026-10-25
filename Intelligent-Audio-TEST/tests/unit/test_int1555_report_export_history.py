# -*- coding: utf-8 -*-
"""INT-1555 专项：报告导出历史（GET /reports/export/history）全链贯通。

覆盖三层：
- report_service ReportExportHistoryService：导出结束登记（done/failed/scope）、
  分页倒序、creator 可见性、写库异常不影响导出
- report_service gRPC servicer：ExportReports 成功/失败都登记、ListExportHistory
- api_gateway：GET /reports/export/history 路由、schema、RPC 透传、路由顺序
  （/export/history 不被 /{report_id} int 捕获返回 422）

DB：进程级 SQLite（tests/conftest.py 注入），按需 create_all 涉及表，
用例内自行清理，对齐 test_int971_report_share.py 口径。
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

_TABLES = None


def _ensure_tables():
    init_db(pool_size=2)
    global _TABLES
    if _TABLES is None:
        from report_service.infrastructure.persistence.models import (
            Report, ReportExportRecord,
        )
        _TABLES = [t.__table__ for t in (Report, ReportExportRecord)]
        Base.metadata.create_all(bind=get_engine(), tables=_TABLES)
    return _TABLES


def _cleanup_tables(tables):
    session = get_db_session()
    try:
        for table in tables:
            session.execute(table.delete())
        session.commit()
    finally:
        remove_db_session()


def _make_report(name='r1'):
    """创建报告样本，返回 report_id。"""
    from report_service.infrastructure.persistence.models import Report
    session = get_db_session()
    po = Report(name=name, type='task', status='published', visibility='shared')
    session.add(po)
    session.flush()
    rid = po.id
    session.commit()
    return rid


def _export_result(**overrides):
    """导出成功结果（handler 产物形状）。"""
    result = {
        'filename': 'reports_export_20261023.csv',
        'format': 'csv',
        'content_base64': 'YSxiCjEsMg==',
        'mime_type': 'text/csv',
        'success': True,
    }
    result.update(overrides)
    return result


def _set_user(user_id, is_admin=False):
    from shared.infrastructure.user_context import (
        set_current_user_id, set_current_user_is_admin,
    )
    set_current_user_id(user_id)
    set_current_user_is_admin(is_admin)


def _reset_user():
    _set_user(None, False)


# ======================================================================
# report_service ReportExportHistoryService
# ======================================================================

class TestExportHistoryService:
    """登记 + 读侧：字段、scope、状态、分页、可见性。"""

    def setup_method(self):
        _ensure_tables()
        _reset_user()

    def teardown_method(self):
        _reset_user()
        _cleanup_tables(_TABLES)

    def _service(self):
        from report_service.application.services.report_export_history_service import (
            ReportExportHistoryService,
        )
        return ReportExportHistoryService()

    def test_record_success_single_report_scope(self):
        """成功导出：scope = 报告名，status=done，error 为空。"""
        service = self._service()
        rid = _make_report(name='旗舰音箱全量回归 · 第 3 轮报告')
        assert service.record([rid], 'csv', _export_result()) is not None

        data = service.list_history({})
        assert data['total'] == 1 and data['page'] == 1
        item = data['items'][0]
        assert item['scope'] == '旗舰音箱全量回归 · 第 3 轮报告'
        assert item['format'] == 'csv'
        assert item['status'] == 'done'
        assert item['error'] is None
        assert item['report_ids'] == [rid]
        assert item['created_at']

    def test_record_failure_keeps_error(self):
        """失败导出：status=failed，error 保留 handler 的 message。"""
        service = self._service()
        rid = _make_report(name='r-fail')
        service.record([rid], 'html',
                       {'success': False, 'message': 'HTML 导出仅支持单个报告，请选择一个报告'})

        item = service.list_history({})['items'][0]
        assert item['status'] == 'failed'
        assert 'HTML 导出仅支持单个报告' in item['error']
        assert item['format'] == 'html'

    def test_record_multi_report_scope(self):
        """批量导出：scope 固定为「已选择 N 个报告」，不拼报告名。"""
        service = self._service()
        ids = [_make_report(name='a'), _make_report(name='b'), _make_report(name='c')]
        service.record(ids, 'excel', _export_result(format='excel'))

        item = service.list_history({})['items'][0]
        assert item['scope'] == '已选择 3 个报告'
        assert item['format'] == 'excel'
        assert item['report_ids'] == ids

    def test_pagination_and_desc_order(self):
        """分页 + 导出时间倒序（总数为过滤后全量）。"""
        service = self._service()
        rid = _make_report(name='r')
        for _ in range(3):
            service.record([rid], 'csv', _export_result())

        page1 = service.list_history({'page': 1, 'per_page': 2})
        assert page1['total'] == 3 and len(page1['items']) == 2
        page2 = service.list_history({'page': 2, 'per_page': 2})
        assert len(page2['items']) == 1
        # 倒序：第一页首条 id 大于第二页
        assert page1['items'][0]['id'] > page2['items'][0]['id']

    def test_per_page_clamped(self):
        """per_page 上限 100、负值取下限 1、缺省/0 取默认 20；page 最小 1。"""
        service = self._service()
        rid = _make_report(name='r')
        service.record([rid], 'csv', _export_result())
        assert service.list_history({'per_page': 500})['per_page'] == 100
        assert service.list_history({'per_page': -5})['per_page'] == 1
        assert service.list_history({'per_page': 0})['per_page'] == 20
        assert service.list_history({'page': 0})['page'] == 1

    def test_visibility_filter_by_creator(self):
        """普通用户只看本人导出；admin / 未认证看全部。"""
        service = self._service()
        rid = _make_report(name='r')
        _set_user(1)
        service.record([rid], 'csv', _export_result())
        _set_user(2)
        service.record([rid], 'csv', _export_result())

        assert service.list_history({})['total'] == 1          # user 2 只看自己
        _set_user(2, is_admin=True)
        assert service.list_history({})['total'] == 2          # admin 全部
        _reset_user()
        assert service.list_history({})['total'] == 2          # AUTH_MODE=off 全部

    def test_record_never_raises_on_db_error(self, monkeypatch):
        """登记失败（写库异常）不影响导出，返回 None。"""
        service = self._service()

        def _boom(**_kwargs):
            raise RuntimeError('db down')

        monkeypatch.setattr(service.repository, 'create', _boom)
        assert service.record([1], 'csv', _export_result()) is None


# ======================================================================
# report_service gRPC servicer
# ======================================================================

class TestExportHistoryServicer:
    """ExportReports 登记历史 + ListExportHistory 读回。"""

    def setup_method(self):
        _ensure_tables()
        _reset_user()

    def teardown_method(self):
        _reset_user()
        _cleanup_tables(_TABLES)

    def test_export_success_records_history(self, monkeypatch):
        from shared.proto import report_service_pb2 as report_pb
        from report_service.interfaces.grpc.servicers import ReportServicer

        rid = _make_report(name='r-ok')
        servicer = ReportServicer()
        monkeypatch.setattr(servicer.query_handler, 'handle_export_reports',
                            lambda ids, fmt: _export_result(format=fmt))

        resp = servicer.ExportReports(
            report_pb.ExportReportsRequest(
                data=grpc_dumps({'ids': [rid], 'format': 'csv'})),
            context=None)
        assert resp.success is True

        listed = servicer.ListExportHistory(
            report_pb.ListExportHistoryRequest(data=grpc_dumps({'page': 1})),
            context=None)
        assert listed.success is True
        payload = grpc_loads(listed.data, {}) or {}
        assert payload['total'] == 1
        assert payload['items'][0]['status'] == 'done'
        assert payload['items'][0]['scope'] == 'r-ok'

    def test_export_failure_records_history(self, monkeypatch):
        from shared.proto import report_service_pb2 as report_pb
        from report_service.interfaces.grpc.servicers import ReportServicer

        servicer = ReportServicer()
        monkeypatch.setattr(servicer.query_handler, 'handle_export_reports',
                            lambda ids, fmt: {'success': False,
                                              'message': '未找到指定报告'})

        resp = servicer.ExportReports(
            report_pb.ExportReportsRequest(
                data=grpc_dumps({'ids': [999999], 'format': 'csv'})),
            context=None)
        assert resp.success is False

        payload = grpc_loads(servicer.ListExportHistory(
            report_pb.ListExportHistoryRequest(data='{}'),
            context=None).data, {}) or {}
        assert payload['total'] == 1
        assert payload['items'][0]['status'] == 'failed'
        assert payload['items'][0]['error'] == '未找到指定报告'


# ======================================================================
# api_gateway 路由
# ======================================================================

class _FakeStub:
    """report_config_service.stub 桩：记录请求并返回预设响应。"""

    def __init__(self, resp=None):
        self.resp = resp
        self.calls = []

    def ListExportHistory(self, req):
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


class TestGatewayExportHistoryRoute:
    """GET /reports/export/history：契约 + 参数透传 + 路由顺序。"""

    def test_history_route(self, gw_client, monkeypatch):
        from shared.proto import report_service_pb2 as report_pb

        payload = {
            'items': [{'id': 7, 'scope': '已选择 3 个报告', 'format': 'excel',
                       'created_at': '2026-10-23T19:40:00', 'status': 'done',
                       'error': None, 'report_ids': [1, 2, 3]}],
            'total': 1, 'page': 2, 'per_page': 5,
        }
        resp = report_pb.ReportConfigResponse(
            success=True, message='ok', data=grpc_dumps(payload))
        fake = _install_fake_stub(monkeypatch, resp)

        r = gw_client.get('/api/v1/reports/export/history',
                          params={'page': 2, 'per_page': 5})
        assert r.status_code == 200
        body = r.json()
        assert body['success'] is True
        assert body['data']['items'][0]['scope'] == '已选择 3 个报告'
        assert body['data']['total'] == 1
        sent = grpc_loads(fake.calls[0].data, {})
        assert sent == {'page': 2, 'per_page': 5}

    def test_history_route_defaults(self, gw_client, monkeypatch):
        from shared.proto import report_service_pb2 as report_pb

        resp = report_pb.ReportConfigResponse(
            success=True, message='ok', data=grpc_dumps({'items': [], 'total': 0}))
        fake = _install_fake_stub(monkeypatch, resp)

        r = gw_client.get('/api/v1/reports/export/history')
        assert r.status_code == 200
        assert r.json()['data'] == {'items': [], 'total': 0}
        assert grpc_loads(fake.calls[0].data, {}) == {'page': 1, 'per_page': 20}

    def test_history_route_invalid_page(self, gw_client, monkeypatch):
        """page 非整数 → 400（schema 校验）。"""
        from shared.proto import report_service_pb2 as report_pb
        _install_fake_stub(monkeypatch, report_pb.ReportConfigResponse(
            success=True, message='ok', data='{}'))

        r = gw_client.get('/api/v1/reports/export/history', params={'page': 'abc'})
        assert r.status_code == 400

    def test_history_not_captured_by_report_id(self, gw_client, monkeypatch):
        """路由顺序：/export/history 不被 /{report_id} int 捕获（200 而非 422）。"""
        from shared.proto import report_service_pb2 as report_pb

        _install_fake_stub(monkeypatch, report_pb.ReportConfigResponse(
            success=True, message='ok',
            data=grpc_dumps({'items': [], 'total': 0})))
        r = gw_client.get('/api/v1/reports/export/history')
        assert r.status_code == 200
