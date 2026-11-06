# -*- coding: utf-8 -*-
"""INT-2186 参数策略 scope 枚举校验单测。

缺陷：``POST /api/v1/algorithm/param-profiles`` 的 ``scope`` 无枚举校验，
任意字符串（如 ``bogus``）都能入库。期望按契约只允许 ``api`` / ``device``：

- 网关 schema（``ParamProfileSaveRequest``）用 Literal 拒绝非法值 → 400；
- 仓储侧（``ParamProfileCommandRepository.save``）再兜一道白名单，
  防止绕过网关直连 gRPC 写脏数据，且校验发生在连库之前。
"""
import os

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from api_gateway.application.services.algorithm import (  # noqa: E402
    algorithm_profile_service as profile_service,
)
from api_gateway.middleware import RequestAdapterMiddleware  # noqa: E402
from api_gateway.routes.algorithm_bp import router as algorithm_router  # noqa: E402
from api_gateway.schemas._algorithm_api_param_schemas import (  # noqa: E402
    ParamProfileSaveRequest,
)
from algorithm_service.infrastructure.persistence import (  # noqa: E402
    _param_profile_repositories as repo_module,
)


_BASE_PAYLOAD = {'algorithm_type': 'voice_llm', 'name': '接线测试_走查B3_bad_scope'}


class _FakeRequest:
    def __init__(self, payload):
        self._payload = payload

    def get_json(self):
        return self._payload


class _FakeProxy:
    def __init__(self):
        self.calls = []

    def save_param_profile(self, data):
        self.calls.append(data)
        return {'success': True, 'data': {'id': 1}, 'message': 'ok'}


@pytest.fixture()
def proxy(monkeypatch):
    fake = _FakeProxy()
    monkeypatch.setattr(profile_service, '_algo_proxy', fake)
    return fake


# ========== schema 层 ==========

def test_schema_accepts_contract_scopes_and_default():
    assert ParamProfileSaveRequest.model_validate(_BASE_PAYLOAD).scope == 'api'
    assert ParamProfileSaveRequest.model_validate(
        {**_BASE_PAYLOAD, 'scope': 'api'}).scope == 'api'
    assert ParamProfileSaveRequest.model_validate(
        {**_BASE_PAYLOAD, 'scope': 'device'}).scope == 'device'


@pytest.mark.parametrize('bad', ['bogus', 'API', 'Device', 'physical', '', ' api'])
def test_schema_rejects_out_of_vocabulary_scope(bad):
    with pytest.raises(ValidationError):
        ParamProfileSaveRequest.model_validate({**_BASE_PAYLOAD, 'scope': bad})


# ========== 网关写路径：非法 scope 是 400，不调 gRPC ==========

def test_create_profile_rejects_bad_scope_with_400(monkeypatch, proxy):
    monkeypatch.setattr(profile_service, 'request', _FakeRequest(
        {**_BASE_PAYLOAD, 'scope': 'bogus'}))
    payload, http_code = profile_service.AlgorithmProfileService.create_profile()
    assert http_code == 400
    assert '请求数据验证失败' in payload['message']
    assert proxy.calls == []  # 非法值不得下发到 algorithm_service


def test_update_profile_rejects_bad_scope_with_400(monkeypatch, proxy):
    monkeypatch.setattr(profile_service, 'request', _FakeRequest(
        {**_BASE_PAYLOAD, 'scope': 'bogus'}))
    payload, http_code = profile_service.AlgorithmProfileService.update_profile(11)
    assert http_code == 400
    assert proxy.calls == []


def test_create_profile_passes_legal_scope_through(monkeypatch, proxy):
    monkeypatch.setattr(profile_service, 'request', _FakeRequest(
        {**_BASE_PAYLOAD, 'scope': 'device'}))
    _, http_code = profile_service.AlgorithmProfileService.create_profile()
    assert http_code == 200
    assert proxy.calls[0]['scope'] == 'device'


# ========== 仓储层：绕过网关也有白名单，且先校验后连库 ==========

@pytest.fixture()
def no_db(monkeypatch):
    """连库即失败：用来证明非法 scope 在连接数据库之前就被拒绝。"""
    def _boom():
        raise AssertionError('非法 scope 不应走到连库')

    monkeypatch.setattr(repo_module, 'get_db_session', _boom)


@pytest.mark.parametrize('bad', ['bogus', 'API', 'physical', ''])
def test_repository_save_rejects_bad_scope_before_db(no_db, bad):
    with pytest.raises(ValueError) as exc:
        repo_module.param_profile_command_repository.save(
            {**_BASE_PAYLOAD, 'scope': bad})
    assert 'scope' in str(exc.value)


def test_repository_save_allows_legal_scope_past_whitelist(monkeypatch):
    """合法 scope 通过白名单，随后才去连库（这里用自造的连库异常断点）。"""
    def _db_reached():
        raise RuntimeError('db-reached')

    monkeypatch.setattr(repo_module, 'get_db_session', _db_reached)
    for scope in ('api', 'device'):
        with pytest.raises(RuntimeError):
            repo_module.param_profile_command_repository.save(
                {**_BASE_PAYLOAD, 'scope': scope})


# ========== 真实路由端到端：POST /api/v1/algorithm/param-profiles ==========

def _make_app() -> FastAPI:
    """最小 app（同 test_int233：RequestAdapterMiddleware + 假 auth 全权限）。"""
    app = FastAPI()
    app.add_middleware(RequestAdapterMiddleware)

    @app.middleware('http')
    async def _fake_auth(request, call_next):
        request.state.permissions = ['*']
        return await call_next(request)

    app.include_router(
        algorithm_router, prefix='/api/v1/algorithm', tags=['algorithm'])
    return app


@pytest.fixture()
def client(proxy):
    return TestClient(_make_app())


def test_http_post_rejects_bad_scope(client, proxy):
    """复现卡内请求：scope=bogus → 400，且不下发到 algorithm_service。"""
    resp = client.post('/api/v1/algorithm/param-profiles',
                       json={**_BASE_PAYLOAD, 'scope': 'bogus'})
    assert resp.status_code == 400
    assert proxy.calls == []


@pytest.mark.parametrize('scope', ['api', 'device'])
def test_http_post_accepts_contract_scope(client, proxy, scope):
    resp = client.post('/api/v1/algorithm/param-profiles',
                       json={**_BASE_PAYLOAD, 'scope': scope})
    assert resp.status_code == 200
    assert proxy.calls[0]['scope'] == scope


def test_http_post_default_scope_is_api(client, proxy):
    resp = client.post('/api/v1/algorithm/param-profiles', json=_BASE_PAYLOAD)
    assert resp.status_code == 200
    assert proxy.calls[0]['scope'] == 'api'
