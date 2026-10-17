# -*- coding: utf-8 -*-
"""INT-620 系统选项 KV + 站点状态端点单测

覆盖：
1. 仓储层（SystemOptionRepositoryImpl，SQLite 临时库）：get_all / upsert 语义
2. 服务层（SystemOptionService）：全量 KV = 领域默认基线 ∪ 已存覆盖、显式空值
   覆盖默认；SiteStatusService：X-Forwarded-Proto/Host 优先、snake_case 契约
3. 路由层（GET/PUT /api/option/、GET /api/status）：200 信封、权限 403、请求体 422
"""
import os

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest
from sqlalchemy import BigInteger, create_engine
from sqlalchemy.ext.compiler import compiles


@compiles(BigInteger, 'sqlite')
def _render_bigint_as_integer_sqlite(type_, compiler, **kw):
    return 'INTEGER'


import shared.models.database as database  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from api_gateway.infrastructure.models.system_option_model import SystemOption  # noqa: E402,F401
from api_gateway.infrastructure.system_option_repository import SystemOptionRepositoryImpl  # noqa: E402
from api_gateway.application.services.system_option_service import SystemOptionService  # noqa: E402
from api_gateway.application.services.site_status_service import SiteStatusService  # noqa: E402
from api_gateway.domain.entities.system_option import SYSTEM_OPTION_DEFAULTS  # noqa: E402
from api_gateway.routes.option_bp import router as option_router  # noqa: E402
from api_gateway.routes.status_bp import router as status_router  # noqa: E402
from api_gateway.middleware import RequestAdapterMiddleware  # noqa: E402


def _clear_scoped_sessions():
    """关闭 scoped_session 注册表内全部 session 并清空。

    setup 与 teardown 各调一次：setup 清空可丢弃同进程先前测试文件在主线程
    （或其他 scope）遗留、仍绑定旧 engine 的陈旧 session——否则 configure 新
    engine 后 get_db_session() 可能复用该陈旧 session（INT-620 全量跑隔离
    缺口：单独跑本文件绿、全量跑挂本文件首个用例）。
    """
    _registry = getattr(database._scoped_session, '_registry', None)
    if _registry is not None:
        for sess in list(_registry.values()):
            try:
                sess.close()
            except Exception:
                pass
        _registry.clear()


@pytest.fixture()
def sqlite_db(tmp_path):
    # 库文件放 pytest tmp_path（不手动删除）：路由测试经 TestClient（anyio
    # 工作线程）访问 get_db_session，线程级 scope 的 session 可能挂在复用线程上，
    # Windows 下文件句柄未随 remove_db_session() 释放，os.remove 会 PermissionError
    # （WinError 32）。tmp_path 由 pytest 会话级清理，避免误删正在使用的文件。
    path = str(tmp_path / 'pytest.db')
    engine = create_engine(f'sqlite:///{path}',
                           connect_args={'check_same_thread': False})
    # setup：先清注册表再配置新 engine，确保本文件首个用例拿到的就是绑定新
    # engine 的新 session。
    _clear_scoped_sessions()
    database._engine = engine
    database._SessionFactory.configure(bind=engine)
    database.Base.metadata.create_all(engine)
    yield database
    # teardown：关闭 scoped_session 注册表内全部 session 并清空：确保各线程连接
    # 归还，且下一用例 get_db_session() 重建新 session（绑定新配置的 engine），
    # 不跨用例复用陈旧 session（INT-620 测试基建）。
    _clear_scoped_sessions()
    database.remove_db_session()
    engine.dispose()


@pytest.fixture()
def repo(sqlite_db):
    return SystemOptionRepositoryImpl()


@pytest.fixture()
def client(monkeypatch):
    """带假认证的路由客户端：permissions 注入 ['*']（AUTH_MODE=off 等价）。"""
    app = FastAPI()
    app.add_middleware(RequestAdapterMiddleware)

    @app.middleware('http')
    async def _fake_auth(request, call_next):
        request.state.permissions = ['*']
        return await call_next(request)

    app.include_router(status_router, prefix='/api')
    app.include_router(option_router, prefix='/api')
    return TestClient(app)


# ==================== 仓储层 ====================

class TestSystemOptionRepository:

    def test_get_all_empty_and_after_upsert(self, repo):
        assert repo.get_all() == {}
        repo.upsert('site.name', '测试平台')
        repo.upsert('operations.log_retention_days', 15)
        assert repo.get_all() == {
            'site.name': '测试平台',
            'operations.log_retention_days': 15,
        }

    def test_upsert_overwrites_existing(self, repo):
        repo.upsert('site.footer', 'v1')
        repo.upsert('site.footer', 'v2')
        assert repo.get_all() == {'site.footer': 'v2'}

    def test_upsert_preserves_value_types(self, repo):
        repo.upsert('site.navigation.show_breadcrumb', True)
        repo.upsert('auth.password_login', False)
        repo.upsert('site.notice', '公告')
        repo.upsert('site.tags', ['a', 'b'])
        got = repo.get_all()
        assert got['site.navigation.show_breadcrumb'] is True
        assert got['auth.password_login'] is False
        assert got['site.notice'] == '公告'
        assert got['site.tags'] == ['a', 'b']


# ==================== 服务层：系统选项 ====================

class TestSystemOptionService:

    def test_get_all_merges_defaults_and_stored(self, repo):
        repo.upsert('site.name', '自定义平台')
        result, http = SystemOptionService.get_all()
        assert http == 200
        data = result['data']
        # 已存覆盖默认
        assert data['site.name'] == '自定义平台'
        # 未落库键回退默认（全量 KV 语义）
        for key, default in SYSTEM_OPTION_DEFAULTS.items():
            assert key in data, f'全量 KV 缺键 {key}'
            if key != 'site.name':
                assert data[key] == default

    def test_explicit_empty_overrides_default(self, repo):
        repo.upsert('site.footer', '')
        result, _ = SystemOptionService.get_all()
        assert result['data']['site.footer'] == ''
        assert SYSTEM_OPTION_DEFAULTS['site.footer'] != ''

    def test_upsert_writes_and_returns_success(self, repo):
        result, http = SystemOptionService.upsert('security.rate_limit', False)
        assert http == 200
        assert result['success'] is True
        assert repo.get_all()['security.rate_limit'] is False


# ==================== 服务层：站点状态 ====================

class TestSiteStatusService:

    def _make_request(self, headers=None):
        from starlette.requests import Request
        from starlette.datastructures import Headers
        scope = {
            'type': 'http',
            'method': 'GET',
            'path': '/api/status',
            'headers': Headers(headers or {}).raw,
            'scheme': 'http',
            'server': ('testserver', 80),
        }
        return Request(scope)

    def test_snake_case_contract(self):
        req = self._make_request({'host': 'example.com:5000'})
        result, http = SiteStatusService.get_site_status(req)
        assert http == 200
        data = result['data']
        # wire 字段必须是 snake_case（前端 infra 唯一转换层转 camelCase）
        assert set(data) == {'api_base_url', 'server_address'}
        assert data['server_address'] == 'http://example.com:5000'
        assert data['api_base_url'] == 'http://example.com:5000/api/v1'

    def test_forwarded_headers_take_precedence(self):
        req = self._make_request({
            'host': 'internal:5000',
            'x-forwarded-proto': 'https',
            'x-forwarded-host': 'public.example.com',
        })
        result, _ = SiteStatusService.get_site_status(req)
        data = result['data']
        assert data['server_address'] == 'https://public.example.com'
        assert data['api_base_url'] == 'https://public.example.com/api/v1'


# ==================== 路由层 ====================

class TestStatusRoute:

    def test_get_status_returns_200_snake_case(self, client):
        resp = client.get('/api/status')
        assert resp.status_code == 200
        body = resp.json()
        assert body['success'] is True
        data = body['data']
        assert set(data) == {'api_base_url', 'server_address'}
        # TestClient 默认 host=testserver
        assert data['server_address'] == 'http://testserver'
        assert data['api_base_url'] == 'http://testserver/api/v1'


class TestOptionRoute:

    def test_get_option_defaults(self, client, sqlite_db):
        resp = client.get('/api/option/')
        assert resp.status_code == 200
        body = resp.json()
        assert body['success'] is True
        data = body['data']
        assert data['site.name'] == '智能语音测试平台'
        assert data['operations.log_retention_days'] == 30

    def test_put_then_get_roundtrip(self, client, sqlite_db):
        put = client.put('/api/option/', json={'key': 'site.name', 'value': '新平台'})
        assert put.status_code == 200
        assert put.json()['success'] is True
        get = client.get('/api/option/')
        assert get.json()['data']['site.name'] == '新平台'

    def test_put_boolean_value_preserved(self, client, sqlite_db):
        client.put('/api/option/', json={
            'key': 'site.navigation.show_breadcrumb', 'value': False,
        })
        data = client.get('/api/option/').json()['data']
        assert data['site.navigation.show_breadcrumb'] is False

    def test_put_empty_key_returns_422(self, client, sqlite_db):
        resp = client.put('/api/option/', json={'key': '', 'value': 'x'})
        assert resp.status_code == 422

    def test_put_non_primitive_value_returns_422(self, client, sqlite_db):
        resp = client.put('/api/option/', json={'key': 'site.name', 'value': {'nested': 1}})
        assert resp.status_code == 422


class TestPermissionGuard:

    def _make_app_with_perms(self, perms):
        app = FastAPI()
        app.add_middleware(RequestAdapterMiddleware)

        @app.middleware('http')
        async def _fake_auth(request, call_next):
            request.state.permissions = list(perms)
            return await call_next(request)

        app.include_router(status_router, prefix='/api')
        app.include_router(option_router, prefix='/api')
        return TestClient(app)

    def test_status_requires_status_read(self):
        client = self._make_app_with_perms([])
        resp = client.get('/api/status')
        assert resp.status_code == 403

    def test_option_get_requires_option_read(self):
        client = self._make_app_with_perms(['status:read'])
        resp = client.get('/api/option/')
        assert resp.status_code == 403

    def test_option_put_requires_option_write(self):
        client = self._make_app_with_perms(['option:read'])
        resp = client.put('/api/option/', json={'key': 'site.name', 'value': 'x'})
        assert resp.status_code == 403
