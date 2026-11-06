# -*- coding: utf-8 -*-
"""INT-674 站点配置端点单测

覆盖：
1. 服务层（HomeService.get_site_config）：system_name/logo/support_email 取
   系统选项 KV（默认基线 ∪ 库内覆盖，显式空值覆盖默认）、version 取平台
   版本常量（只读，不可配）
2. 路由层（GET /api/v1/home/site）：200 信封、snake_case 字段契约
3. 权限（PUBLIC_PATHS）：prod（JWT 强制）态未登录 200 不 401；非白名单
   对照路径仍 401；已登录含权限亦可访问
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
from api_gateway.application.services.home_service import HomeService  # noqa: E402
from api_gateway.routes.home_bp import router as home_router  # noqa: E402
from api_gateway.middleware import RequestAdapterMiddleware, AuthMiddleware  # noqa: E402
from shared.infrastructure.config import BaseConfig  # noqa: E402


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

    app.include_router(home_router, prefix='/api/v1/home')
    return TestClient(app)


@pytest.fixture()
def prod_client(sqlite_db):
    """prod（JWT 强制）态：真实 AuthMiddleware，验证 PUBLIC_PATHS 白名单。"""
    app = FastAPI()
    app.add_middleware(RequestAdapterMiddleware)
    app.add_middleware(AuthMiddleware, auth_mode='prod')
    app.include_router(home_router, prefix='/api/v1/home')
    return TestClient(app)


# ==================== 服务层：站点配置 ====================

class TestHomeServiceSiteConfig:

    def test_defaults(self, sqlite_db):
        result, http = HomeService.get_site_config()
        assert http == 200
        assert result['success'] is True
        data = result['data']
        # wire 字段必须 snake_case（前端 infra 唯一转换层转 camelCase）
        assert set(data) == {'system_name', 'version', 'logo', 'support_email'}
        assert data['system_name'] == '智能语音测试平台'
        assert data['version'] == BaseConfig.PLATFORM_VERSION
        assert data['logo'] == ''
        assert data['support_email'] == ''

    def test_upsert_reflects_in_site_config(self, sqlite_db):
        SystemOptionService.upsert('site.name', '自定义平台')
        SystemOptionService.upsert('site.support_email', 'support@example.com')
        SystemOptionService.upsert('site.logo', '/assets/logo.png')
        result, _ = HomeService.get_site_config()
        data = result['data']
        assert data['system_name'] == '自定义平台'
        assert data['support_email'] == 'support@example.com'
        assert data['logo'] == '/assets/logo.png'
        # version 不可配：库内无 version 键，仍取平台常量
        assert data['version'] == BaseConfig.PLATFORM_VERSION

    def test_explicit_empty_overrides_default(self, sqlite_db):
        SystemOptionService.upsert('site.name', '')
        SystemOptionService.upsert('site.support_email', '')
        result, _ = HomeService.get_site_config()
        assert result['data']['system_name'] == ''
        assert result['data']['support_email'] == ''


# ==================== 路由层 ====================

class TestSiteConfigRoute:

    def test_get_site_returns_200_snake_case(self, client, sqlite_db):
        resp = client.get('/api/v1/home/site')
        assert resp.status_code == 200
        body = resp.json()
        assert body['success'] is True
        assert body['code'] == 0
        data = body['data']
        assert set(data) == {'system_name', 'version', 'logo', 'support_email'}
        assert data['system_name'] == '智能语音测试平台'
        assert data['version'] == BaseConfig.PLATFORM_VERSION
        assert data['support_email'] == ''

    def test_put_then_get_reflects_upsert(self, client, sqlite_db):
        SystemOptionService.upsert('site.name', '新平台')
        SystemOptionService.upsert('site.support_email', 'ops@example.com')
        resp = client.get('/api/v1/home/site')
        assert resp.status_code == 200
        data = resp.json()['data']
        assert data['system_name'] == '新平台'
        assert data['support_email'] == 'ops@example.com'

    def test_logged_in_with_permission_accessible(self, client, sqlite_db):
        """已登录含权限亦可访问（假认证 permissions=['*']）。"""
        resp = client.get('/api/v1/home/site')
        assert resp.status_code == 200


# ==================== 权限：PUBLIC_PATHS ====================

class TestSiteConfigPublicPath:

    def test_public_path_no_token_returns_200(self, prod_client, sqlite_db):
        """prod 强制态未登录 GET /home/site → 200（PUBLIC_PATHS 白名单生效）。"""
        resp = prod_client.get('/api/v1/home/site')
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body['success'] is True
        assert body['data']['system_name'] == '智能语音测试平台'

    def test_control_non_public_path_requires_token(self, prod_client, sqlite_db):
        """对照用例：同应用下非白名单 home 路径无 token → 401（真强制）。"""
        resp = prod_client.get('/api/v1/home/stats/summary')
        assert resp.status_code == 401, resp.text
