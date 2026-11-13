# -*- coding: utf-8 -*-
"""INT-2509 供应商接口 422 校验回显脱敏（落地方案 §6.4-2 / §13-4）。

缺陷链：缺字段时 FastAPI 默认 422 把**整份请求体**放进 ``detail[].input``，
``api_gateway`` 中间件又把 >=400 响应体原样写进服务日志 → 明文 API Key
落到 ``api_gateway`` 服务日志（保留 30 天）。

验收锚点：
1. ``agent_service`` 的 422 只回 ``type / loc / msg``，不出现任何字段值；
2. POST / PUT（含整份 body 级错误）响应体都不含 Key 明文；
3. verify 没有请求体模型，不存在 422 回显路径，带 Key 的请求同样不回显；
4. 网关错误日志经 ``shared.utils.secret_mask`` 脱敏（兜底），且不改写
   回给调用方的响应体。
"""
import json
import logging
import os

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import httpx
import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from agent_service.app import create_app
from agent_service.domain.services.context_window_resolver import (
    ContextWindowResolver,
)
from agent_service.infrastructure.llm.credential_store import CredentialStore
from agent_service.infrastructure.llm.verifier import HttpProviderVerifier
from agent_service.wiring import build_container
from api_gateway.middleware import RequestAdapterMiddleware
from api_gateway.routes import agent_provider_bp, agent_runtime_bp
from tests.unit.int2451_agent_fakes import (
    FakeLlm, FakeProviderResolver, TEST_MASTER_KEY, make_engine,
)

OWNER_A = {'X-User-Id': '7', 'X-Tenant-Id': 't1'}
# 缺陷卡里的探针 Key（24 位，命中 sk- 裸值规则）
KEY = 'sk-LEAKprobe1111bbbb2222'

_ALLOWED_DETAIL_KEYS = {'type', 'loc', 'msg'}


# ---------------------------------------------------------------- agent_service

def _make_client(tmp_path):
    engine, session_factory = make_engine(tmp_path / 'providers.db')
    container = build_container(
        session_factory,
        provider_resolver=FakeProviderResolver(FakeLlm([])),
        credential_store=CredentialStore.from_secret(TEST_MASTER_KEY),
        window_resolver=ContextWindowResolver.from_file(),
        provider_verifier=HttpProviderVerifier(
            timeout_seconds=1,
            http_transport=httpx.MockTransport(
                lambda _request: httpx.Response(200, json={'data': []})),
        ),
    )
    return TestClient(create_app(container=container)), engine


def _assert_no_echo(resp):
    """响应体不含 Key 明文；422 的 detail 项只保留定位字段。"""
    assert KEY not in resp.text, resp.text
    body = resp.json()
    for item in body.get('detail') or []:
        if not isinstance(item, dict):
            continue
        assert set(item) <= _ALLOWED_DETAIL_KEYS, item
        assert 'input' not in item


def test_create_missing_field_422_does_not_echo_key(tmp_path):
    client, _engine = _make_client(tmp_path)
    with client:
        resp = client.post(
            '/api/v1/agent/providers',
            json={
                'name': 'x',
                'protocol': 'OPENAI_COMPATIBLE',
                'model': 'deepseek-chat',
                'api_key': KEY,
                # 故意缺 base_url
            },
            headers=OWNER_A,
        )
    assert resp.status_code == 422, resp.text
    _assert_no_echo(resp)
    # 仍保留字段定位信息，前端据此标红
    assert resp.json()['detail'][0]['loc'] == ['body', 'base_url']
    assert resp.json()['detail'][0]['type'] == 'missing'


def test_create_body_level_422_does_not_echo_key(tmp_path):
    """整份 body 类型错（非对象）时默认 handler 会回显整个 body。"""
    client, _engine = _make_client(tmp_path)
    with client:
        resp = client.post('/api/v1/agent/providers',
                           json=[{'api_key': KEY}], headers=OWNER_A)
    assert resp.status_code == 422, resp.text
    _assert_no_echo(resp)
    assert resp.json()['detail'][0]['loc'] == ['body']


def test_update_422_does_not_echo_key(tmp_path):
    client, _engine = _make_client(tmp_path)
    with client:
        # 整份 body 级错误（UpdateProviderRequest 期望对象）
        resp = client.put('/api/v1/agent/providers/any-id',
                          json=[{'api_key': KEY}], headers=OWNER_A)
        assert resp.status_code == 422, resp.text
        _assert_no_echo(resp)

        # 字段类型错误：只会带出错字段的值，同样不出现 input
        resp = client.put('/api/v1/agent/providers/any-id',
                          json={'api_key': KEY, 'context_window': 'zzz'},
                          headers=OWNER_A)
        assert resp.status_code == 422, resp.text
        _assert_no_echo(resp)
        assert resp.json()['detail'][0]['loc'] == ['body', 'context_window']


def test_verify_request_never_echoes_key(tmp_path):
    """verify 无请求体模型（不存在 422 回显路径），带 Key 的请求也不回显。"""
    client, _engine = _make_client(tmp_path)
    with client:
        resp = client.post('/api/v1/agent/providers/does-not-exist/verify',
                           json={'api_key': KEY}, headers=OWNER_A)
    assert resp.status_code == 404, resp.text
    assert KEY not in resp.text


# ---------------------------------------------------------------- api_gateway

def _gateway_logs(caplog):
    return '\n'.join(
        record.getMessage() for record in caplog.records
        if record.name == 'api_gateway.middleware')


def _leaky_422_body():
    return {
        'detail': [{
            'type': 'missing',
            'loc': ['body', 'base_url'],
            'msg': 'Field required',
            'input': {
                'name': 'x',
                'protocol': 'OPENAI_COMPATIBLE',
                'model': 'deepseek-chat',
                'api_key': KEY,
            },
        }],
    }


def test_gateway_error_log_is_masked_without_rewriting_body(caplog):
    """兜底：上游仍回显 Key 时，网关日志脱敏，响应体原样透传。"""
    leaky = _leaky_422_body()
    app = FastAPI()
    app.add_middleware(RequestAdapterMiddleware)

    @app.post('/api/v1/agent/providers')
    def create_provider():  # pragma: no cover - 测试替身
        return JSONResponse(status_code=422, content=leaky)

    caplog.set_level(logging.INFO, logger='api_gateway.middleware')
    with TestClient(app) as client:
        resp = client.post('/api/v1/agent/providers', json={'api_key': KEY})

    assert resp.status_code == 422
    # 网关不改写响应体（契约仍由 agent_service 收口）
    assert resp.json() == leaky

    logs = _gateway_logs(caplog)
    assert 'API Response' in logs
    assert KEY not in logs
    assert '"api_key":"****"' in logs


def test_provider_proxy_422_log_is_masked(caplog):
    """网关供应商代理链路：上游 422 回显 Key → 日志无明文、响应原样。"""
    leaky = _leaky_422_body()
    leaky_body = json.dumps(leaky, ensure_ascii=False).encode('utf-8')
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(422, content=leaky_body,
                              headers={'Content-Type': 'application/json'})

    original = agent_runtime_bp._transport_override
    agent_runtime_bp._transport_override = httpx.MockTransport(handler)
    try:
        app = FastAPI()
        app.add_middleware(RequestAdapterMiddleware)
        app.include_router(agent_provider_bp.router, prefix='/api/v1/agent')

        @app.middleware('http')
        async def inject_identity(request, call_next):
            request.state.user_id = 7
            request.state.permissions = ['agent:provider:manage']
            return await call_next(request)

        caplog.set_level(logging.INFO, logger='api_gateway.middleware')
        with TestClient(app) as client:
            resp = client.post('/api/v1/agent/providers',
                               json={'name': 'x', 'api_key': KEY},
                               headers={'X-User-Id': '7'})
    finally:
        agent_runtime_bp._transport_override = original

    assert resp.status_code == 422
    # 请求体确实按原样转发给 agent_service（脱敏只作用于日志）
    assert calls and json.loads(calls[0].content)['api_key'] == KEY
    assert resp.json() == leaky

    logs = _gateway_logs(caplog)
    assert 'API Response' in logs
    assert KEY not in logs
