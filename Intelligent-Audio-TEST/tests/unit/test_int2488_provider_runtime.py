# -*- coding: utf-8 -*-
"""INT-2488 RunOrchestrator 接入用户供应商（§6.4-3/4 / §8.3 / §9.3）。

验收锚点：
- 无可用 Key → LLM_PROVIDER_NOT_CONFIGURED，且上游模型请求计数为 0；
- run 使用 owner 自己的默认供应商（mock 记录收到的 Key 指纹），A/B 隔离；
- 预算与单轮输出按有效 W 计算；换供应商后新 run 按新窗口重算；
- Key 不进事件；主密钥轮换后旧记录仍可解密调用。
"""
import json
import os

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import httpx
import pytest

from agent_service.application.run_worker import InlineRunExecutor
from agent_service.domain.enums import LlmProtocol, RunStatus
from agent_service.domain.services.context_window_resolver import (
    ContextWindowResolver,
)
from agent_service.infrastructure.llm.credential_store import CredentialStore
from agent_service.infrastructure.persistence.models.agent_models import (
    AgentStep as AgentStepPO,
)
from agent_service.wiring import build_container
from tests.unit.int2451_agent_fakes import TEST_MASTER_KEY, make_engine

KEY_A = 'sk-aaaa-provider-a-000111'
KEY_B = 'sk-bbbb-provider-b-000222'
KEY_C = 'sk-cccc-provider-c-000333'


def _sse(*payloads):
    lines = [f'data: {json.dumps(payload, ensure_ascii=False)}'
             for payload in payloads]
    lines.append('data: [DONE]')
    return ('\n\n'.join(lines) + '\n\n').encode('utf-8')


def _stream_response(body):
    return httpx.Response(200, content=iter([body]),
                          headers={'Content-Type': 'text/event-stream'})


class Recorder:
    def __init__(self):
        self.calls = []

    def __call__(self, request):
        body = {}
        if request.content:
            try:
                body = json.loads(request.content.decode('utf-8'))
            except ValueError:
                body = {}
        self.calls.append({
            'url': str(request.url),
            'authorization': request.headers.get('Authorization'),
            'body': body,
        })
        return _stream_response(_sse(
            {'choices': [{'delta': {'content': '你好'}}]},
            {'choices': [], 'usage': {'prompt_tokens': 10,
                                      'completion_tokens': 2}},
        ))


def _stack(tmp_path, name='run.db', credential_store=None,
           recorder=None):
    engine, session_factory = make_engine(tmp_path / name)
    recorder = recorder or Recorder()
    container = build_container(
        session_factory,
        credential_store=credential_store or
        CredentialStore.from_secret(TEST_MASTER_KEY),
        window_resolver=ContextWindowResolver.from_file(),
        executor_factory=lambda orch: InlineRunExecutor(orch),
        http_transport=httpx.MockTransport(recorder),
    )
    return container, session_factory, recorder


def _create_provider(container, *, owner_id=7, tenant_id='t1',
                     key=KEY_A, base_url='http://a.local/v1',
                     model='deepseek-chat', context_window=None,
                     protocol=LlmProtocol.OPENAI_COMPATIBLE,
                     name='provider'):
    return container.provider_service.create(
        owner_id=owner_id, tenant_id=tenant_id, name=name,
        protocol=protocol, base_url=base_url, model=model,
        api_key=key, context_window=context_window)


def _run(container, owner_id=7, tenant_id='t1'):
    session = container.run_service.create_session(
        owner_id=owner_id, tenant_id=tenant_id, title='测试')
    run, created = container.run_service.create_run(
        session.id, owner_id=owner_id, tenant_id=tenant_id, message='你好')
    assert created
    container.executor.submit(run.id)
    return session, container.repositories['runs'].get(run.id)


def _steps(session_factory, run_id):
    db = session_factory()
    try:
        return db.query(AgentStepPO).filter(
            AgentStepPO.run_id == run_id).order_by(
            AgentStepPO.index.asc()).all()
    finally:
        db.close()


def _events(container, run_id):
    return container.repositories['events'].list_after(run_id, 0, 10000)


def test_no_provider_fails_without_model_request(tmp_path):
    container, _sf, recorder = _stack(tmp_path, 'nokey.db')
    _session, run = _run(container)
    assert run.status is RunStatus.FAILED
    assert run.error.startswith('LLM_PROVIDER_NOT_CONFIGURED')
    assert recorder.calls == []  # 不发起任何模型请求

    event_types = [event.type.value for event in _events(container, run.id)]
    assert 'error' in event_types
    error_payload = [event.payload for event in _events(container, run.id)
                     if event.type.value == 'error'][0]
    assert error_payload['code'] == 'LLM_PROVIDER_NOT_CONFIGURED'
    container.shutdown()


def test_run_uses_owner_default_provider(tmp_path):
    container, _sf, recorder = _stack(tmp_path, 'ok.db')
    _create_provider(container)
    _session, run = _run(container)
    assert run.status is RunStatus.SUCCEEDED, run.error
    assert len(recorder.calls) == 1
    call = recorder.calls[0]
    assert call['url'] == 'http://a.local/v1/chat/completions'
    assert call['authorization'] == f'Bearer {KEY_A}'
    assert call['body']['model'] == 'deepseek-chat'
    assert KEY_A not in json.dumps(
        [event.payload for event in _events(container, run.id)],
        ensure_ascii=False)
    container.shutdown()


def test_providers_are_isolated_per_owner(tmp_path):
    container, _sf, recorder = _stack(tmp_path, 'iso.db')
    _create_provider(container, owner_id=7, key=KEY_A,
                     base_url='http://a.local/v1', name='A')
    _create_provider(container, owner_id=8, key=KEY_B,
                     base_url='http://b.local/v1', name='B')

    _sid_a, run_a = _run(container, owner_id=7)
    _sid_b, run_b = _run(container, owner_id=8)
    assert run_a.status is RunStatus.SUCCEEDED
    assert run_b.status is RunStatus.SUCCEEDED
    assert len(recorder.calls) == 2
    assert recorder.calls[0]['authorization'] == f'Bearer {KEY_A}'
    assert recorder.calls[0]['url'].startswith('http://a.local')
    assert recorder.calls[1]['authorization'] == f'Bearer {KEY_B}'
    assert recorder.calls[1]['url'].startswith('http://b.local')

    # A 的事件里没有 B 的 Key（反之亦然）
    assert KEY_B not in json.dumps(
        [e.payload for e in _events(container, run_a.id)], ensure_ascii=False)
    assert KEY_A not in json.dumps(
        [e.payload for e in _events(container, run_b.id)], ensure_ascii=False)
    container.shutdown()


def test_budget_and_output_limit_follow_effective_window(tmp_path):
    container, session_factory, recorder = _stack(tmp_path, 'budget.db')
    _create_provider(container, context_window=32768)
    session, run = _run(container)
    assert run.status is RunStatus.SUCCEEDED

    # 单轮输出 ≤ min(8k, 10% × 32k) → 3200 以内（1024 对齐 = 3072）
    assert recorder.calls[0]['body']['max_tokens'] == 3072
    snapshot = _steps(session_factory, run.id)[0].plan_snapshot
    assert snapshot['context_window'] == 32768
    assert snapshot['context_window_source'] == 'USER_OVERRIDE'
    assert snapshot['token_budget'] == 65536  # 2 × W
    available = 32768 - 3072
    assert snapshot['compaction_soft_tokens'] == int(available * 0.60)
    assert snapshot['compaction_hard_tokens'] == int(available * 0.80)

    # 换默认供应商（目录默认 W=64k）后，同会话下一次 run 按新窗口重算
    second = _create_provider(
        container, key=KEY_C, base_url='http://c.local/v1',
        name='second', model='deepseek-chat')
    container.provider_service.set_default(second.id, 7, 't1')
    run2, created = container.run_service.create_run(
        session.id, owner_id=7, tenant_id='t1', message='再问一次')
    assert created
    container.executor.submit(run2.id)
    stored2 = container.repositories['runs'].get(run2.id)
    assert stored2.status is RunStatus.SUCCEEDED
    assert recorder.calls[-1]['authorization'] == f'Bearer {KEY_C}'
    assert recorder.calls[-1]['body']['max_tokens'] == 6144  # 10% × 64k
    snapshot2 = _steps(session_factory, stored2.id)[0].plan_snapshot
    assert snapshot2['context_window'] == 65536  # deepseek-chat 目录默认
    assert snapshot2['token_budget'] == 131072
    container.shutdown()


def test_key_rotation_old_record_still_usable(tmp_path):
    old_store = CredentialStore(keyring={1: b'x' * 32}, current_version=1)
    container, session_factory, _recorder = _stack(
        tmp_path, 'rotate.db', credential_store=old_store)
    # 旧主密钥（v1）写入的记录：轮换后应仍能解密
    v1_provider = _create_provider(container, key=KEY_A, name='v1-only')
    # 这条记录在轮换后用新版本重写
    rotated_provider = _create_provider(container, key=KEY_C, name='rotated')

    rotated = CredentialStore(
        keyring={1: b'x' * 32, 2: b'y' * 32}, current_version=2)
    recorder = Recorder()
    container2 = build_container(
        session_factory, credential_store=rotated,
        window_resolver=ContextWindowResolver.from_file(),
        executor_factory=lambda orch: InlineRunExecutor(orch),
        http_transport=httpx.MockTransport(recorder))
    updated = container2.provider_service.update(
        rotated_provider.id, 7, 't1', {'api_key': KEY_B})
    assert updated.api_key_mask == CredentialStore.mask(KEY_B)
    # 新主密钥（v2）写入的新记录
    new_provider = container2.provider_service.create(
        owner_id=7, tenant_id='t1', name='new',
        protocol=LlmProtocol.OPENAI_COMPATIBLE,
        base_url='http://a.local/v1', model='deepseek-chat', api_key=KEY_C,
        context_window=None)

    def default_of(provider_id):
        container2.provider_service.set_default(provider_id, 7, 't1')

    # v1 旧记录仍可解密并成功调用
    default_of(v1_provider.id)
    _sid, run_v1 = _run(container2)
    assert run_v1.status is RunStatus.SUCCEEDED, run_v1.error
    assert recorder.calls[-1]['authorization'] == f'Bearer {KEY_A}'

    # 轮换后重写的记录（v2）
    default_of(updated.id)
    _sid2, run_rotated = _run(container2)
    assert run_rotated.status is RunStatus.SUCCEEDED, run_rotated.error
    assert recorder.calls[-1]['authorization'] == f'Bearer {KEY_B}'

    # 轮换后新建的记录（v2）
    default_of(new_provider.id)
    _sid3, run_new = _run(container2)
    assert run_new.status is RunStatus.SUCCEEDED, run_new.error
    assert recorder.calls[-1]['authorization'] == f'Bearer {KEY_C}'
    container.shutdown()
    container2.shutdown()


def test_run_uses_new_provider_after_old_default_invalidated(tmp_path):
    """旧默认被判 INVALID 后新建供应商即可直接跑（无需手工改默认）。"""
    container, _sf, recorder = _stack(tmp_path, 'recover.db')
    stale = _create_provider(container, key=KEY_A,
                             base_url='http://a.local/v1', name='stale')
    container.repositories['providers'].update(
        stale.id, 7, 't1', status='INVALID')  # verify 401 后的真实状态

    fresh = _create_provider(container, key=KEY_B,
                             base_url='http://b.local/v1', name='fresh')
    assert fresh.is_default is True

    _session, run = _run(container)
    assert run.status is RunStatus.SUCCEEDED, run.error
    assert recorder.calls[-1]['authorization'] == f'Bearer {KEY_B}'
    assert recorder.calls[-1]['url'].startswith('http://b.local')
    assert KEY_A not in json.dumps(
        [event.payload for event in _events(container, run.id)],
        ensure_ascii=False)
    container.shutdown()
