# -*- coding: utf-8 -*-
"""INT-2451 REST + SSE 契约。

验收锚点：
1. SSSE 回放 run_started / message_delta / run_finished，sequence 严格递增；
2. 断线重连（Last-Event-ID / cursor）不丢事件、不重复；
3. Idempotency-Key 重复提交只产生一个 run；
6. 归属不符一律 404（不泄漏存在性）、缺身份 401；
7. approvals 先返回空列表占位。
"""
import json
import os
import threading
import time
import uuid

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from fastapi.testclient import TestClient

from agent_service.app import create_app
from agent_service.application.run_worker import InlineRunExecutor
from tests.unit.int2451_agent_fakes import (
    FakeLlm, build_stack, events_of, text_turn,
)

OWNER = {'X-User-Id': '7', 'X-Tenant-Id': 't1'}
OTHER = {'X-User-Id': '8', 'X-Tenant-Id': 't1'}


def _client(tmp_path, name='api.db', llm=None):
    llm = llm or FakeLlm([text_turn('第一段', '第二段')])
    container, _engine, _sf = build_stack(
        tmp_path / name, llm,
        executor_factory=lambda orch: InlineRunExecutor(orch))
    app = create_app(container=container)
    return TestClient(app), container


def _parse_sse(text):
    frames = []
    for block in text.split('\n\n'):
        if not block.strip() or block.startswith(':'):
            continue
        frame = {}
        for line in block.splitlines():
            if line.startswith('id: '):
                frame['id'] = int(line[4:])
            elif line.startswith('event: '):
                frame['event'] = line[7:]
            elif line.startswith('data: '):
                frame['data'] = json.loads(line[6:])
        if frame:
            frames.append(frame)
    return frames


def _create_session_and_run(client, headers=OWNER, key=None):
    session = client.post('/api/v1/agent/sessions',
                          json={'title': 't'}, headers=headers)
    assert session.status_code == 201, session.text
    session_id = session.json()['id']
    run_headers = dict(headers)
    if key:
        run_headers['Idempotency-Key'] = key
    run = client.post(f'/api/v1/agent/sessions/{session_id}/runs',
                      json={'message': '你好'}, headers=run_headers)
    assert run.status_code == 201, run.text
    return session_id, run.json()['run']


def test_full_sse_replay_and_sequence(tmp_path):
    client, container = _client(tmp_path)
    with client:
        _sid, run = _create_session_and_run(client)
        assert run['status'] == 'SUCCEEDED'
        resp = client.get(f"/api/v1/agent/runs/{run['id']}/events",
                          headers=OWNER)
        assert resp.status_code == 200
        assert resp.headers['content-type'].startswith('text/event-stream')
        frames = _parse_sse(resp.text)
        assert [f['event'] for f in frames] == [
            'run_started', 'message_delta', 'message_delta', 'run_finished']
        assert [f['id'] for f in frames] == [1, 2, 3, 4]
        assert all(f['data']['run_id'] == run['id'] for f in frames)
        assert frames[1]['data']['message_id'] == frames[2]['data']['message_id']
        assert frames[-1]['data']['status'] == 'SUCCEEDED'


def test_reconnect_with_last_event_id_no_loss_no_duplicate(tmp_path):
    client, container = _client(tmp_path)
    with client:
        _sid, run = _create_session_and_run(client)
        full = _parse_sse(client.get(
            f"/api/v1/agent/runs/{run['id']}/events", headers=OWNER).text)
        first_two = full[:2]
        resp = client.get(
            f"/api/v1/agent/runs/{run['id']}/events",
            headers={**OWNER, 'Last-Event-ID': str(first_two[-1]['id'])})
        resumed = _parse_sse(resp.text)
        assert [f['id'] for f in resumed] == [f['id'] for f in full[2:]]
        assert len({f['id'] for f in resumed} & {f['id'] for f in first_two}) == 0

        cursor_resp = client.get(
            f"/api/v1/agent/runs/{run['id']}/events?cursor=3", headers=OWNER)
        assert [f['id'] for f in _parse_sse(cursor_resp.text)] == [4]


def test_idempotency_key_duplicate_only_one_run(tmp_path):
    client, container = _client(tmp_path)
    with client:
        session = client.post('/api/v1/agent/sessions', json={},
                              headers=OWNER).json()
        headers = {**OWNER, 'Idempotency-Key': 'req-1'}
        first = client.post(
            f"/api/v1/agent/sessions/{session['id']}/runs",
            json={'message': '一次'}, headers=headers)
        second = client.post(
            f"/api/v1/agent/sessions/{session['id']}/runs",
            json={'message': '一次'}, headers=headers)
        assert first.status_code == 201 and first.json()['created'] is True
        assert second.status_code == 200 and second.json()['created'] is False
        assert second.json()['run']['id'] == first.json()['run']['id']
        assert container.repositories['runs'].count_for_session(
            session['id']) == 1


def test_ownership_mismatch_is_404_not_403(tmp_path):
    client, _container = _client(tmp_path)
    with client:
        sid, run = _create_session_and_run(client)
        assert client.get(f'/api/v1/agent/runs/{run["id"]}',
                          headers=OTHER).status_code == 404
        assert client.get(f'/api/v1/agent/sessions/{sid}',
                          headers=OTHER).status_code == 404
        assert client.get(f'/api/v1/agent/runs/{run["id"]}/events',
                          headers=OTHER).status_code == 404
        # 不存在与越权同一响应，避免存在性泄漏
        assert client.get('/api/v1/agent/runs/does-not-exist',
                          headers=OTHER).status_code == 404


def test_missing_identity_is_401(tmp_path):
    client, _container = _client(tmp_path)
    with client:
        assert client.get('/api/v1/agent/runs/x').status_code == 401


def test_session_detail_and_approvals_placeholder(tmp_path):
    client, _container = _client(tmp_path)
    with client:
        sid, run = _create_session_and_run(client)
        detail = client.get(f'/api/v1/agent/sessions/{sid}', headers=OWNER)
        assert detail.status_code == 200
        body = detail.json()
        assert body['session']['id'] == sid
        assert [m['role'] for m in body['messages']] == ['user', 'assistant']
        assert body['messages'][1]['content'] == '第一段第二段'
        approvals = client.get(
            f"/api/v1/agent/runs/{run['id']}/approvals", headers=OWNER)
        assert approvals.status_code == 200
        assert approvals.json() == {'items': []}


def test_empty_message_rejected(tmp_path):
    client, _container = _client(tmp_path)
    with client:
        session = client.post('/api/v1/agent/sessions', json={},
                              headers=OWNER).json()
        resp = client.post(
            f"/api/v1/agent/sessions/{session['id']}/runs",
            json={'message': ''}, headers=OWNER)
        assert resp.status_code == 422


def test_event_stream_follows_live_updates(tmp_path):
    """SSE 先回放后跟随：等待期间落库的事件会被推送，终态后结束。"""
    container, _engine, _sf = build_stack(tmp_path / 'live.db', FakeLlm([]))
    session = container.run_service.create_session(
        owner_id=7, tenant_id='t1', title='live')
    run, _created = container.run_service.create_run(
        session.id, owner_id=7, tenant_id='t1', message='live')

    stream = container.event_stream.iter_events(run.id, 0)
    first = next(stream)
    assert first.type.value == 'run_started'

    def produce():
        from agent_service.domain.enums import EventType, RunStatus
        time.sleep(0.05)
        container.repositories['events'].append(
            run.id, EventType.MESSAGE_DELTA,
            {'message_id': 'm1', 'delta': 'hi', 'index': 0, 'turn': 0})
        container.wakeup.notify(run.id)
        time.sleep(0.05)
        container.repositories['runs'].transition_if(
            run.id, {RunStatus.QUEUED}, RunStatus.RUNNING)
        container.repositories['runs'].transition_if(
            run.id, {RunStatus.RUNNING}, RunStatus.SUCCEEDED)
        container.repositories['events'].append(
            run.id, EventType.RUN_FINISHED, {'status': 'SUCCEEDED'})
        container.wakeup.notify(run.id)

    producer = threading.Thread(target=produce)
    producer.start()
    second = next(stream)
    third = next(stream)
    assert second.type.value == 'message_delta'
    assert third.type.value == 'run_finished'
    try:
        next(stream)
        raise AssertionError('SSE 应在 run 终态后结束')
    except StopIteration:
        pass
    producer.join(timeout=5)
    container.shutdown()
