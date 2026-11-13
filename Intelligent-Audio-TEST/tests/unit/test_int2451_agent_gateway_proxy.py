# -*- coding: utf-8 -*-
"""INT-2451 网关代理：鉴权不绕过 / 身份头透传 / 不泄漏存在性 / SSE 预检。

验收锚点（卡面第 7 条）：无权限用户 401/403，不泄漏 run 是否存在。
"""
import json
import os

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')
# INT-2456：网关 Agent 总开关默认关闭，本组代理用例必须显式开启。
os.environ.setdefault('AGENT_ENABLED', 'true')

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api_gateway.middleware import AuthMiddleware
from api_gateway.routes import agent_runtime_bp


@pytest.fixture()
def harness():
    calls = []

    def make_app(mode='off', handler=None):
        app = FastAPI()
        app.add_middleware(AuthMiddleware, auth_mode=mode)
        app.include_router(agent_runtime_bp.router, prefix='/api/v1/agent')
        transport = httpx.MockTransport(handler)
        agent_runtime_bp._transport_override = transport
        return TestClient(app)

    yield make_app, calls
    agent_runtime_bp._transport_override = None


def test_unauthenticated_is_401_and_never_reaches_upstream(harness):
    make_app, calls = harness

    def handler(request):  # pragma: no cover - 不应被调用
        calls.append(request)
        return httpx.Response(200, json={})

    client = make_app(mode='prod', handler=handler)
    resp = client.get('/api/v1/agent/runs/r1')
    assert resp.status_code == 401
    assert calls == []


def test_off_mode_forwards_identity_headers(harness):
    make_app, calls = harness

    def handler(request):
        calls.append(request)
        return httpx.Response(201, json={'id': 's1'})

    client = make_app(mode='off', handler=handler)
    resp = client.post('/api/v1/agent/sessions', json={'title': 'x'})
    assert resp.status_code == 201
    assert resp.json() == {'id': 's1'}
    forwarded = calls[0].headers
    assert forwarded['X-User-Id'] == '0'
    assert forwarded['X-Tenant-Id'] == 'default'


def test_idempotency_key_is_forwarded(harness):
    make_app, calls = harness

    def handler(request):
        calls.append(request)
        return httpx.Response(201, json={'run': {'id': 'r1'}, 'created': True})

    client = make_app(mode='off', handler=handler)
    resp = client.post('/api/v1/agent/sessions/s1/runs',
                       json={'message': 'hi'},
                       headers={'Idempotency-Key': 'k-1'})
    assert resp.status_code == 201
    assert calls[0].headers['Idempotency-Key'] == 'k-1'


def test_ownership_404_passes_through_without_leak(harness):
    make_app, calls = harness

    def handler(request):
        calls.append(request)
        return httpx.Response(404, json={'detail': 'not found'})

    client = make_app(mode='off', handler=handler)
    resp = client.get('/api/v1/agent/runs/other-run')
    assert resp.status_code == 404
    assert resp.json() == {'detail': 'not found'}


def test_sse_preflight_failure_returns_json_not_stream(harness):
    make_app, calls = harness

    def handler(request):
        calls.append(request)
        return httpx.Response(404, json={'detail': 'not found'})

    client = make_app(mode='off', handler=handler)
    resp = client.get('/api/v1/agent/runs/r1/events')
    assert resp.status_code == 404
    assert resp.headers['content-type'].startswith('application/json')
    assert len(calls) == 1  # 只做快照预检，没有拉起事件流


def test_sse_stream_is_passed_through(harness):
    make_app, calls = harness

    def handler(request):
        calls.append(request)
        if request.url.path.endswith('/events'):
            body = ('id: 1\nevent: run_started\ndata: {"sequence": 1}\n\n'
                    'id: 2\nevent: run_finished\ndata: {"sequence": 2}\n\n')
            # 用迭代器保持「流式响应」形态（MockTransport 下 content=bytes 会预读，
            # iter_raw 会抛 StreamConsumed，测不到透传路径）
            return httpx.Response(200, content=iter([body.encode('utf-8')]),
                                  headers={'Content-Type': 'text/event-stream'})
        return httpx.Response(200, json={'id': 'r1', 'status': 'SUCCEEDED'})

    client = make_app(mode='off', handler=handler)
    resp = client.get('/api/v1/agent/runs/r1/events?cursor=0')
    assert resp.status_code == 200
    assert resp.headers['content-type'].startswith('text/event-stream')
    assert 'event: run_started' in resp.text
    assert 'event: run_finished' in resp.text
    assert 'cursor=0' in str(calls[-1].url)


def test_upstream_unavailable_is_503(harness):
    make_app, calls = harness

    def handler(request):
        raise httpx.ConnectError('refused', request=request)

    client = make_app(mode='off', handler=handler)
    resp = client.get('/api/v1/agent/runs/r1')
    assert resp.status_code == 503
    assert resp.json() == {'detail': 'agent service unavailable'}


# ---------------------------------------------- INT-2487 P2-2：合成 error 帧同口径

def _error_payload(text):
    """取出 SSE 里的 error 帧并校验 5 项字段，返回 data 载荷。"""
    frames = [frame for frame in text.split('\n\n') if 'event: error' in frame]
    assert len(frames) == 1, text
    lines = frames[0].split('\n')
    ids = [line for line in lines if line.startswith('id: ')]
    data = [line for line in lines if line.startswith('data: ')]
    assert len(ids) == 1 and len(data) == 1, text
    payload = json.loads(data[0][len('data: '):])
    assert ids[0] == f"id: {payload['sequence']}"  # id 即 sequence
    for key in ('run_id', 'sequence', 'type', 'timestamp'):
        assert key in payload, (key, payload)
    assert payload['type'] == 'error'
    assert payload['timestamp']
    return payload


def test_sse_upstream_error_uses_unified_frame(harness):
    make_app, calls = harness

    def handler(request):
        calls.append(request)
        if request.url.path.endswith('/events'):
            return httpx.Response(403, json={'detail': 'forbidden'})
        return httpx.Response(200, json={'id': 'r1', 'status': 'RUNNING'})

    client = make_app(mode='off', handler=handler)
    resp = client.get('/api/v1/agent/runs/r1/events',
                      headers={'Last-Event-ID': '7'})
    assert resp.status_code == 200
    payload = _error_payload(resp.text)
    assert payload['code'] == 'UPSTREAM_ERROR'
    assert payload['run_id'] == 'r1'
    # 未下发过任何事件：sequence 取客户端续传游标，续传不会跳过真实事件
    assert payload['sequence'] == 7


def test_sse_transport_break_emits_unified_frame(harness):
    make_app, calls = harness

    def broken_body():
        # id 行跨 chunk 断开，验证网关仍能跟踪到最后一个 sequence
        yield b'id: 4\nevent: message_delta\ndata: {"sequence": 4}\n\n'
        raise httpx.ReadError('connection reset')

    def handler(request):
        calls.append(request)
        if request.url.path.endswith('/events'):
            return httpx.Response(200, content=broken_body(),
                                  headers={'Content-Type': 'text/event-stream'})
        return httpx.Response(200, json={'id': 'r1', 'status': 'RUNNING'})

    client = make_app(mode='off', handler=handler)
    resp = client.get('/api/v1/agent/runs/r1/events')
    assert resp.status_code == 200
    assert 'event: message_delta' in resp.text  # 已下发的帧原样透传
    payload = _error_payload(resp.text)
    assert payload['code'] == 'UPSTREAM_UNAVAILABLE'
    assert payload['run_id'] == 'r1'
    assert payload['sequence'] == 4  # 与已下发帧的 id 对齐，续传不跳过缺口

