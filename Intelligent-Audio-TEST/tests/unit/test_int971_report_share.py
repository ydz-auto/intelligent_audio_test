# -*- coding: utf-8 -*-
"""INT-971 专项：报告分享端点（生成/列表/撤销/公开读取）全链贯通。

覆盖三层：
- report_service ReportShareService：创建（token/有效期换算/密码哈希/recipients）、
  列表、撤销（幂等）、公开读取鉴权（public/login/specific × 密码 × 过期 ×
  计数，仅 200 计次）
- report_service gRPC servicer：CreateReportShare / ListReportShares /
  RevokeReportShare / GetSharedReport（错误经 code 透出 404/410/401/403）
- api_gateway：POST/GET/DELETE /reports/{id}/share + GET /reports/shared/{token}
  路由、schema、share_url 拼接、路由顺序（/shared/{token} 注册在 /{report_id}
  之前，不被捕获返回 422）

DB：进程级 SQLite（tests/conftest.py 注入），按需 create_all 涉及表，
用例内自行清理，对齐 test_int791_report_statistics.py 口径。
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
        # GetSharedReport 200 走 query_handler.handle_get（加载摘要/完整数据），
        # 需报告 7 表全建
        from report_service.infrastructure.persistence.models import (
            Report, ReportSummary, ReportSummaryMeta, ReportRawData,
            ReportCase, ReportMetricStats, ReportComparisonMatrix,
            ReportShare,
        )
        _TABLES = [t.__table__ for t in (
            Report, ReportSummary, ReportSummaryMeta, ReportRawData,
            ReportCase, ReportMetricStats, ReportComparisonMatrix,
            ReportShare,
        )]
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


def _make_report(name='r1', status='published'):
    """创建报告样本，返回 report_id。"""
    from report_service.infrastructure.persistence.models import Report
    session = get_db_session()
    po = Report(name=name, type='task', status=status)
    session.add(po)
    session.flush()
    rid = po.id
    session.commit()
    return rid


def _create_share(report_id=None, **kwargs):
    """创建分享（默认新建报告），返回 (result_dict, report_id)。"""
    from report_service.application.services.report_share_service import report_share_service
    if report_id is None:
        report_id = _make_report()
    params = {
        'report_id': report_id,
        'access': 'public',
        'expiry': 'none',
        'password': '',
        'recipients': [],
    }
    params.update(kwargs)
    result = report_share_service.create_share(params)
    return result, report_id


# ======================================================================
# report_service ReportShareService
# ======================================================================

class TestShareService:
    """ReportShareService：创建/列表/撤销/公开读取/计数。"""

    def setup_method(self):
        _ensure_tables()

    def teardown_method(self):
        _cleanup_tables(_TABLES)

    def test_create_share_and_list(self):
        """创建分享 → 落库字段正确；列表按 created_at 倒序返回。"""
        from report_service.application.services.report_share_service import report_share_service
        from report_service.infrastructure.persistence.models import ReportShare
        result, rid = _create_share()
        assert result['success'] is True
        data = result['data']
        assert data['token'] and len(data['token']) >= 24
        assert data['access'] == 'public'
        assert data['expires_at'] is None          # none → NULL
        assert data['password_set'] is False
        assert data['recipients'] == []
        assert data['visits'] == 0

        # 落库核对（验收 #1）
        session = get_db_session()
        share = session.query(ReportShare).filter_by(token=data['token']).first()
        assert share is not None
        assert share.access == 'public'
        assert share.visits == 0 and share.revoked is False
        rid = share.report_id

        listed = report_share_service.list_shares(rid)
        assert listed['success'] is True
        items = listed['data']['shares']
        assert len(items) == 1
        assert items[0]['token'] == data['token']

    def test_create_share_report_not_found(self):
        """报告不存在 → 404 语义。"""
        from report_service.application.services.report_share_service import report_share_service
        result = report_share_service.create_share({'report_id': 999999, 'access': 'public'})
        assert result['success'] is False and result['code'] == 404

    def test_create_share_validation(self):
        """非法 access/expiry、custom 缺 expires_at → 400。"""
        from report_service.application.services.report_share_service import report_share_service
        rid = _make_report()
        result = report_share_service.create_share({'report_id': rid, 'access': 'bogus'})
        assert result['success'] is False and result['code'] == 400
        result = report_share_service.create_share({'report_id': rid, 'expiry': 'bogus'})
        assert result['success'] is False and result['code'] == 400
        result = report_share_service.create_share({'report_id': rid, 'expiry': 'custom'})
        assert result['success'] is False and result['code'] == 400
        # access=specific 缺 recipients
        result = report_share_service.create_share({'report_id': rid, 'access': 'specific'})
        assert result['success'] is False and result['code'] == 400

    def test_expiry_7d_30d_and_custom(self):
        """有效期换算：7d/30d → now+7/30 天；custom → 给定时间。"""
        from datetime import datetime, timedelta
        from report_service.application.services.report_share_service import report_share_service
        rid = _make_report()

        r7 = report_share_service.create_share(
            {'report_id': rid, 'expiry': '7d'})
        exp7 = datetime.fromisoformat(r7['data']['expires_at'])
        assert abs((datetime.now() + timedelta(days=7) - exp7).total_seconds()) < 3600

        r30 = report_share_service.create_share(
            {'report_id': rid, 'expiry': '30d'})
        exp30 = datetime.fromisoformat(r30['data']['expires_at'])
        assert abs((datetime.now() + timedelta(days=30) - exp30).total_seconds()) < 3600

        # custom：带 Z 的 UTC 时间 → 东八区换算落值
        r_custom = report_share_service.create_share({
            'report_id': rid, 'expiry': 'custom',
            'expires_at': '2030-01-01T00:00:00Z'})
        assert r_custom['success'] is True
        exp = datetime.fromisoformat(r_custom['data']['expires_at'])
        # 2030-01-01T00:00:00Z = 2030-01-01T08:00:00+08
        assert exp.hour == 8

    def test_password_hash_not_plaintext(self):
        """密码非空 → 落 password_hash（bcrypt），响应只回 password_set。"""
        from report_service.infrastructure.persistence.models import ReportShare
        result, _ = _create_share(password='secret123')
        assert result['data']['password_set'] is True
        assert 'token' in result['data']
        session = get_db_session()
        share = session.query(ReportShare).filter_by(token=result['data']['token']).first()
        assert share.password_hash and share.password_hash != 'secret123'
        assert 'secret123' not in share.password_hash

    def test_specific_recipients_stored(self):
        """access=specific → recipients [{user_id, label}] 落库。"""
        from report_service.infrastructure.persistence.models import ReportShare
        result, _ = _create_share(access='specific',
                                recipients=[{'user_id': 42, 'label': 'alice'},
                                            {'user_id': 43, 'label': 'bob@example.com'}])
        assert result['data']['recipients'][0]['user_id'] == 42
        session = get_db_session()
        share = session.query(ReportShare).filter_by(token=result['data']['token']).first()
        assert share.recipients[1]['label'] == 'bob@example.com'

    # ---------- 公开读取鉴权 ----------

    def test_public_anonymous_read_and_count(self):
        """public：匿名 200，读取计数 +1（访问统计唯一入口）。"""
        from report_service.application.services.report_share_service import report_share_service
        result, rid = _create_share()
        token = result['data']['token']
        res = report_share_service.get_shared_report(token)
        assert res['success'] is True and res['data']['report_id'] == rid
        listed = report_share_service.list_shares(rid)
        assert listed['data']['shares'][0]['visits'] == 1

    def test_visits_increment_only_on_200(self):
        """同一 token 读取 2 次 → visits=2；403/404 不计次。"""
        from report_service.application.services.report_share_service import report_share_service
        result, rid = _create_share(access='public', password='pw')
        token = result['data']['token']
        # 缺密码 403 不计次
        res = report_share_service.get_shared_report(token, password=None)
        assert res['success'] is False and res['code'] == 403
        # 正确密码 200 两次
        assert report_share_service.get_shared_report(token, password='pw')['success'] is True
        assert report_share_service.get_shared_report(token, password='pw')['success'] is True
        # 不存在 token 404 不计次
        assert report_share_service.get_shared_report('no_such_token')['code'] == 404
        listed = report_share_service.list_shares(rid)
        assert listed['data']['shares'][0]['visits'] == 2
        assert listed['data']['shares'][0]['last_visited_at'] is not None

    def test_login_access(self):
        """login：匿名 401；带 user_id 200。"""
        from report_service.application.services.report_share_service import report_share_service
        result, _ = _create_share(access='login')
        token = result['data']['token']
        assert report_share_service.get_shared_report(token, user_id=None)['code'] == 401
        assert report_share_service.get_shared_report(token, user_id=1)['success'] is True

    def test_specific_access(self):
        """specific：匿名 401；非指定人 403；指定人 200。"""
        from report_service.application.services.report_share_service import report_share_service
        result, _ = _create_share(access='specific',
                                recipients=[{'user_id': 42, 'label': 'alice'}])
        token = result['data']['token']
        assert report_share_service.get_shared_report(token, user_id=None)['code'] == 401
        assert report_share_service.get_shared_report(token, user_id=43)['code'] == 403
        assert report_share_service.get_shared_report(token, user_id=42)['success'] is True

    def test_password_required_and_invalid(self):
        """设密码：缺 → 403 share_password_required；错 → 403 share_password_invalid。"""
        from report_service.application.services.report_share_service import report_share_service
        result, _ = _create_share(password='pw')
        token = result['data']['token']
        res = report_share_service.get_shared_report(token, password=None)
        assert res['code'] == 403
        assert res['message'] == 'share_password_required'
        assert res['data'].get('share_requires_password') is True
        res = report_share_service.get_shared_report(token, password='wrong')
        assert res['code'] == 403
        assert res['message'] == 'share_password_invalid'
        assert report_share_service.get_shared_report(token, password='pw')['success'] is True

    def test_expired_410(self):
        """过期 token → 410。"""
        from report_service.application.services.report_share_service import report_share_service
        rid = _make_report()
        result = report_share_service.create_share({
            'report_id': rid, 'access': 'public', 'expiry': 'custom',
            'expires_at': '2020-01-01T00:00:00Z'})
        assert result['success'] is True
        res = report_share_service.get_shared_report(result['data']['token'])
        assert res['success'] is False and res['code'] == 410

    def test_revoked_404(self):
        """撤销后原 token 404。"""
        from report_service.application.services.report_share_service import report_share_service
        result, rid = _create_share()
        token = result['data']['token']
        revoked = report_share_service.revoke_share(rid, token)
        assert revoked['success'] is True and revoked['data']['revoked'] is True
        res = report_share_service.get_shared_report(token)
        assert res['success'] is False and res['code'] == 404

    def test_revoke_idempotent_and_wrong_token(self):
        """撤销幂等：已撤销再次撤销仍 200；token 不存在/不属于该报告 → 404。"""
        from report_service.application.services.report_share_service import report_share_service
        result, rid = _create_share()
        token = result['data']['token']
        assert report_share_service.revoke_share(rid, token)['success'] is True
        assert report_share_service.revoke_share(rid, token)['success'] is True
        assert report_share_service.revoke_share(rid, 'bad_token')['code'] == 404
        # 不属于该报告
        other, other_rid = _create_share()
        assert report_share_service.revoke_share(other_rid,
                                                 token)['code'] == 404


# ======================================================================
# report_service gRPC servicer
# ======================================================================

class TestShareServicer:
    """gRPC servicer：四新 RPC 透传 + GetSharedReport code 透出。"""

    def setup_method(self):
        _ensure_tables()

    def teardown_method(self):
        _cleanup_tables(_TABLES)

    def test_create_report_share_servicer(self):
        from shared.proto import report_service_pb2 as report_pb
        from report_service.interfaces.grpc.servicers import ReportServicer

        rid = _make_report()
        resp = ReportServicer().CreateReportShare(
            report_pb.CreateReportShareRequest(
                data=grpc_dumps({'report_id': rid, 'access': 'public',
                                 'expiry': 'none', 'password': '',
                                 'recipients': []})),
            context=None)
        assert resp.success is True
        data = grpc_loads(resp.data, {}) or {}
        assert data['token'] and data['password_set'] is False

    def test_list_and_revoke_servicer(self):
        from shared.proto import report_service_pb2 as report_pb
        from report_service.interfaces.grpc.servicers import ReportServicer

        servicer = ReportServicer()
        rid = _make_report()
        created = servicer.CreateReportShare(
            report_pb.CreateReportShareRequest(
                data=grpc_dumps({'report_id': rid, 'access': 'public'})),
            context=None)
        token = grpc_loads(created.data, {})['token']

        listed = servicer.ListReportShares(
            report_pb.ListReportSharesRequest(data=grpc_dumps({'report_id': rid})),
            context=None)
        assert listed.success is True
        assert grpc_loads(listed.data, {})['shares'][0]['token'] == token

        revoked = servicer.RevokeReportShare(
            report_pb.RevokeReportShareRequest(
                data=grpc_dumps({'report_id': rid, 'token': token})),
            context=None)
        assert revoked.success is True and grpc_loads(revoked.data, {})['revoked'] is True

    def test_get_shared_report_servicer_code(self):
        """GetSharedReport：404/401/200 经 code 透出；200 返回报告详情。"""
        from shared.proto import report_service_pb2 as report_pb
        from report_service.interfaces.grpc.servicers import ReportServicer

        servicer = ReportServicer()
        rid = _make_report()
        created = servicer.CreateReportShare(
            report_pb.CreateReportShareRequest(
                data=grpc_dumps({'report_id': rid, 'access': 'login'})),
            context=None)
        token = grpc_loads(created.data, {})['token']

        # 匿名 login → 401
        resp = servicer.GetSharedReport(
            report_pb.GetSharedReportRequest(
                data=grpc_dumps({'token': token, 'password': '', 'user_id': None})),
            context=None)
        assert resp.success is False and resp.code == 401

        # 已登录 → 200 + 报告详情
        resp = servicer.GetSharedReport(
            report_pb.GetSharedReportRequest(
                data=grpc_dumps({'token': token, 'password': '', 'user_id': 1})),
            context=None)
        assert resp.success is True
        detail = grpc_loads(resp.data, {}) or {}
        assert detail.get('id') == rid

        # 不存在 token → 404
        resp = servicer.GetSharedReport(
            report_pb.GetSharedReportRequest(
                data=grpc_dumps({'token': 'bad', 'password': '', 'user_id': None})),
            context=None)
        assert resp.success is False and resp.code == 404


# ======================================================================
# api_gateway 路由
# ======================================================================

class _FakeStub:
    """report_config_service.stub 桩：记录请求并返回预设响应。"""

    def __init__(self, resp=None):
        self.resp = resp
        self.calls = []

    def CreateReportShare(self, req):
        self.calls.append(req)
        return self.resp

    def ListReportShares(self, req):
        self.calls.append(req)
        return self.resp

    def RevokeReportShare(self, req):
        self.calls.append(req)
        return self.resp

    def GetSharedReport(self, req):
        self.calls.append(req)
        return self.resp


def _install_fake_stub(monkeypatch, resp):
    from api_gateway.infrastructure.grpc_proxies import report_proxies
    fake = _FakeStub(resp)
    monkeypatch.setattr(report_proxies, 'get_report_config_service_stub',
                        lambda: fake)
    return fake


class _FakeAuthStub:
    """auth_config_service.stub 桩：ListUsers 按 keyword 精确过滤。"""

    def __init__(self, users_items):
        self.users_items = users_items
        self.calls = []

    def ListUsers(self, req):
        from shared.proto import auth_service_pb2 as auth_pb
        self.calls.append(req)
        kw = req.keyword or ''
        items = [u for u in self.users_items
                 if kw in (u.get('username') or '')
                 or kw in (u.get('email') or '')]
        return auth_pb.AuthResponse(
            success=True, message='ok',
            data=grpc_dumps({'items': items, 'total': len(items)}))


def _install_fake_auth_stub(monkeypatch, users_items):
    from api_gateway.infrastructure.grpc_proxies import auth_proxies
    fake = _FakeAuthStub(users_items)
    monkeypatch.setattr(auth_proxies, 'get_auth_service_stub', lambda: fake)
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


class TestGatewayShareRoutes:
    """api_gateway：四端点路由 + schema + share_url + 路由顺序。"""

    def test_create_share_route(self, gw_client, monkeypatch):
        """POST /reports/{id}/share → 透传 + share_url 拼接。"""
        from shared.proto import report_service_pb2 as report_pb

        created = {'token': 'abc123', 'access': 'public', 'expires_at': None,
                   'password_set': False, 'recipients': [], 'visits': 0,
                   'last_visited_at': None}
        resp = report_pb.ReportConfigResponse(
            success=True, message='ok', data=grpc_dumps(created))
        fake = _install_fake_stub(monkeypatch, resp)

        r = gw_client.post('/api/v1/reports/42/share',
                           json={'access': 'public', 'expiry': 'none'})
        assert r.status_code == 200
        body = r.json()
        assert body['success'] is True
        assert body['data']['token'] == 'abc123'
        assert body['data']['share_url'] == 'http://testserver/report/42?share=abc123'
        assert fake.calls and 'report_id' in grpc_loads(fake.calls[0].data, {})

    def test_create_share_route_custom_expiry_validation(self, gw_client, monkeypatch):
        """expiry=custom 缺 expires_at → 400。"""
        from shared.proto import report_service_pb2 as report_pb
        _install_fake_stub(monkeypatch, report_pb.ReportConfigResponse(
            success=True, message='ok', data='{}'))
        r = gw_client.post('/api/v1/reports/42/share',
                           json={'access': 'public', 'expiry': 'custom'})
        assert r.status_code == 400

    def test_create_share_recipients_resolution(self, gw_client, monkeypatch):
        """access=specific：经 auth ListUsers 解析；未识别项 → 400 带明细。"""
        from shared.proto import report_service_pb2 as report_pb

        users = [
            {'id': 1, 'username': 'alice', 'email': 'alice@example.com'},
            {'id': 2, 'username': 'bob', 'email': 'bob@example.com'},
        ]
        auth_fake = _install_fake_auth_stub(monkeypatch, users)
        created = {'token': 't1', 'access': 'specific', 'expires_at': None,
                   'password_set': False,
                   'recipients': [{'user_id': 1, 'label': 'alice'}],
                   'visits': 0, 'last_visited_at': None}
        resp = report_pb.ReportConfigResponse(
            success=True, message='ok', data=grpc_dumps(created))
        fake = _install_fake_stub(monkeypatch, resp)

        r = gw_client.post('/api/v1/reports/42/share',
                           json={'access': 'specific', 'expiry': 'none',
                                 'recipients': 'alice,bob@example.com,unknown_user'})
        assert r.status_code == 400
        assert r.json()['success'] is False
        assert 'unknown_user' in r.json()['message']
        assert r.json()['detail']['unrecognized'] == ['unknown_user']

        # 全部可识别 → 200，RPC 收到解析后的 [{user_id, label}]
        r = gw_client.post('/api/v1/reports/42/share',
                           json={'access': 'specific', 'expiry': 'none',
                                 'recipients': 'alice,bob@example.com'})
        assert r.status_code == 200
        assert auth_fake.calls
        payload = grpc_loads(fake.calls[0].data, {})
        assert payload['recipients'] == [
            {'user_id': 1, 'label': 'alice'},
            {'user_id': 2, 'label': 'bob'},
        ]

    def test_list_shares_route(self, gw_client, monkeypatch):
        """GET /reports/{id}/share → 分享列表。"""
        from shared.proto import report_service_pb2 as report_pb

        resp = report_pb.ReportConfigResponse(
            success=True, message='ok', data=grpc_dumps({
                'shares': [{'token': 't1', 'access': 'public', 'expires_at': None,
                            'password_set': False, 'recipients': [], 'visits': 2,
                            'last_visited_at': None, 'revoked': False,
                            'created_at': '2026-10-20T00:00:00+08:00'}]}))
        fake = _install_fake_stub(monkeypatch, resp)

        r = gw_client.get('/api/v1/reports/42/share')
        assert r.status_code == 200
        assert r.json()['data']['shares'][0]['visits'] == 2
        assert fake.calls and grpc_loads(fake.calls[0].data, {})['report_id'] == 42

    def test_revoke_share_route(self, gw_client, monkeypatch):
        """DELETE /reports/{id}/share/{token} → 200 {revoked: true}。"""
        from shared.proto import report_service_pb2 as report_pb

        resp = report_pb.ReportConfigResponse(
            success=True, message='ok', data=grpc_dumps({'revoked': True}))
        fake = _install_fake_stub(monkeypatch, resp)

        r = gw_client.delete('/api/v1/reports/42/share/abc123')
        assert r.status_code == 200
        assert r.json()['data']['revoked'] is True
        payload = grpc_loads(fake.calls[0].data, {})
        assert payload['report_id'] == 42 and payload['token'] == 'abc123'

    def test_revoke_share_route_not_found(self, gw_client, monkeypatch):
        """撤销不存在 token → 404（code 透出）。"""
        from shared.proto import report_service_pb2 as report_pb

        resp = report_pb.ReportConfigResponse(
            success=False, message='分享不存在或不属于该报告',
            data=grpc_dumps({'code': 404}), code=404)
        _install_fake_stub(monkeypatch, resp)

        r = gw_client.delete('/api/v1/reports/42/share/bad')
        assert r.status_code == 404

    def test_get_shared_report_route(self, gw_client, monkeypatch):
        """GET /reports/shared/{token} → 报告详情 200（路由顺序正确）。"""
        from shared.proto import report_service_pb2 as report_pb

        detail = {'id': 42, 'name': 'r1', 'type': 'task', 'status': 'published'}
        resp = report_pb.ReportConfigResponse(
            success=True, message='ok', data=grpc_dumps(detail))
        fake = _install_fake_stub(monkeypatch, resp)

        r = gw_client.get('/api/v1/reports/shared/abc123')
        assert r.status_code == 200
        assert r.json()['data']['id'] == 42
        assert fake.calls and grpc_loads(fake.calls[0].data, {})['token'] == 'abc123'

    def test_get_shared_report_password_required(self, gw_client, monkeypatch):
        """缺密码 → 403 + share_password_required + share_requires_password。"""
        from shared.proto import report_service_pb2 as report_pb

        resp = report_pb.ReportConfigResponse(
            success=False, message='share_password_required',
            data=grpc_dumps({'code': 403, 'share_requires_password': True}), code=403)
        _install_fake_stub(monkeypatch, resp)

        r = gw_client.get('/api/v1/reports/shared/abc123')
        assert r.status_code == 403
        body = r.json()
        assert body['message'] == 'share_password_required'
        assert body['detail'] == {'share_requires_password': True}

    def test_get_shared_report_invalid_password(self, gw_client, monkeypatch):
        """密码错误 → 403 share_password_invalid。"""
        from shared.proto import report_service_pb2 as report_pb

        resp = report_pb.ReportConfigResponse(
            success=False, message='share_password_invalid',
            data=grpc_dumps({'code': 403}), code=403)
        _install_fake_stub(monkeypatch, resp)

        r = gw_client.get('/api/v1/reports/shared/abc123', params={'password': 'x'})
        assert r.status_code == 403
        assert r.json()['message'] == 'share_password_invalid'

    def test_get_shared_report_expired_410(self, gw_client, monkeypatch):
        """过期 → 410。"""
        from shared.proto import report_service_pb2 as report_pb

        resp = report_pb.ReportConfigResponse(
            success=False, message='分享已过期',
            data=grpc_dumps({'code': 410}), code=410)
        _install_fake_stub(monkeypatch, resp)

        r = gw_client.get('/api/v1/reports/shared/abc123')
        assert r.status_code == 410

    def test_get_shared_report_not_found_404(self, gw_client, monkeypatch):
        """token 不存在/已撤销 → 404。"""
        from shared.proto import report_service_pb2 as report_pb

        resp = report_pb.ReportConfigResponse(
            success=False, message='分享不存在',
            data=grpc_dumps({'code': 404}), code=404)
        _install_fake_stub(monkeypatch, resp)

        r = gw_client.get('/api/v1/reports/shared/abc123')
        assert r.status_code == 404

    def test_shared_route_not_captured_by_report_id(self, gw_client, monkeypatch):
        """路由顺序：/shared/{token} 不被 /{report_id} int 捕获（200 而非 422）。"""
        from shared.proto import report_service_pb2 as report_pb

        resp = report_pb.ReportConfigResponse(
            success=True, message='ok', data=grpc_dumps({'id': 1}))
        _install_fake_stub(monkeypatch, resp)

        r = gw_client.get('/api/v1/reports/shared/abc123')
        assert r.status_code == 200
        assert r.json()['success'] is True
