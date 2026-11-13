# -*- coding: utf-8 -*-
"""INT-2454 上下文快照读取端点（调试模式可回放）。

- 归属校验与 GET /runs 一致：非本人 / 不存在 → 404；
- 调试模式返回被裁消息 ID 与备忘（可回放），非调试模式只给统计字段。
"""
import os

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from fastapi.testclient import TestClient

from agent_service.app import create_app
from agent_service.application.context_assembler import CompactionSettings
from agent_service.application.run_worker import InlineRunExecutor
from agent_service.domain.enums import CompactionLevel
from agent_service.domain.model.entities import AgentContextSnapshot
from shared.utils.time_utils import utcnow
from tests.unit.int2451_agent_fakes import (
    FakeLlm, build_stack, text_turn,
)

OWNER = {'X-User-Id': '7', 'X-Tenant-Id': 't1'}
OTHER = {'X-User-Id': '8', 'X-Tenant-Id': 't1'}


def _client(tmp_path, name, *, debug):
    container, _engine, _sf = build_stack(
        tmp_path / name, FakeLlm([text_turn('好的')]),
        executor_factory=lambda orch: InlineRunExecutor(orch),
        context_debug=debug,
        compaction_settings=CompactionSettings(debug=debug))
    return TestClient(create_app(container=container)), container


def _create_run(client, headers=OWNER):
    session = client.post('/api/v1/agent/sessions',
                          json={'title': 't'}, headers=headers)
    assert session.status_code == 201, session.text
    run = client.post(
        f"/api/v1/agent/sessions/{session.json()['id']}/runs",
        json={'message': '你好'}, headers=headers)
    assert run.status_code == 201, run.text
    return run.json()['run']['id']


def _add_snapshot(container, run_id):
    container.repositories['snapshots'].add(AgentContextSnapshot(
        id='snap-1', run_id=run_id, version=1, token_count=123,
        level=CompactionLevel.L3_MEMO,
        dropped_ids=['tool:call-1', 'msg-1'],
        memo={'goal': 'x', 'facts': [
            {'fact': '任务 T1 状态为 SUCCEEDED', 'value': 'SUCCEEDED',
             'source_id': 'tool:call-1'}]},
        created_at=utcnow()))


def test_debug_mode_returns_replay_fields(tmp_path):
    client, container = _client(tmp_path, 'a.db', debug=True)
    with client:
        run_id = _create_run(client)
        _add_snapshot(container, run_id)

        response = client.get(
            f'/api/v1/agent/runs/{run_id}/context-snapshots', headers=OWNER)
        assert response.status_code == 200, response.text
        body = response.json()
        assert body['enabled'] is True
        assert len(body['items']) == 1
        item = body['items'][0]
        assert item['level'] == 'L3_MEMO'
        assert item['token_count'] == 123
        assert item['dropped_ids'] == ['tool:call-1', 'msg-1']
        assert item['memo']['facts'][0]['source_id'] == 'tool:call-1'


def test_non_debug_mode_hides_replay_fields(tmp_path):
    client, container = _client(tmp_path, 'b.db', debug=False)
    with client:
        run_id = _create_run(client)
        _add_snapshot(container, run_id)

        body = client.get(
            f'/api/v1/agent/runs/{run_id}/context-snapshots',
            headers=OWNER).json()
        assert body['enabled'] is False
        item = body['items'][0]
        assert item['dropped_count'] == 2
        assert 'dropped_ids' not in item
        assert 'memo' not in item


def test_snapshot_owner_checked(tmp_path):
    client, container = _client(tmp_path, 'c.db', debug=True)
    with client:
        run_id = _create_run(client)
        _add_snapshot(container, run_id)

        response = client.get(
            f'/api/v1/agent/runs/{run_id}/context-snapshots', headers=OTHER)
        assert response.status_code == 404


def test_gateway_proxies_context_snapshots():
    """网关路由与 agent_service 同口径转发（不绕过鉴权/身份头）。"""
    import httpx
    from fastapi import FastAPI
    from api_gateway.middleware import AuthMiddleware
    from api_gateway.routes import agent_runtime_bp

    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={'enabled': True, 'items': []})

    app = FastAPI()
    app.add_middleware(AuthMiddleware, auth_mode='off')
    app.include_router(agent_runtime_bp.router, prefix='/api/v1/agent')
    agent_runtime_bp._transport_override = httpx.MockTransport(handler)
    try:
        response = TestClient(app).get(
            '/api/v1/agent/runs/r1/context-snapshots')
    finally:
        agent_runtime_bp._transport_override = None
    assert response.status_code == 200
    assert calls[0].url.path == '/api/v1/agent/runs/r1/context-snapshots'
    assert calls[0].headers['X-User-Id'] == '0'
