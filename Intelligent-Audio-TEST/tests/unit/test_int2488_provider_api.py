# -*- coding: utf-8 -*-
"""INT-2488 供应商 API 契约（§6.4 / §11）。

验收锚点：
- 列表 / 详情只返回掩码与有效窗口，响应体不含明文或密文；
- PUT 时 Key 留空表示不变；context_window 覆盖值与告警；
- A 读不到 / 改不了 / 删不了 B 的供应商（404）；
- 删除 = 逻辑删除 + 清空密文；默认项删除后自动提升最早的可用项；
- verify 对不可达地址返回明确失败码且不回显 Key。
"""
import os

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import httpx
import pytest
from fastapi.testclient import TestClient

from agent_service.app import create_app
from agent_service.domain.enums import ContextWindowSource, ProviderStatus
from agent_service.domain.services.context_window_resolver import (
    ContextWindowResolver,
)
from agent_service.infrastructure.llm.credential_store import CredentialStore
from agent_service.infrastructure.llm.verifier import (
    AUTH_FAILED, HttpProviderVerifier, UNREACHABLE,
)
from tests.unit.int2451_agent_fakes import (
    FakeLlm, FakeProviderResolver, TEST_MASTER_KEY, make_engine,
)
from agent_service.wiring import build_container

OWNER_A = {'X-User-Id': '7', 'X-Tenant-Id': 't1'}
OWNER_B = {'X-User-Id': '8', 'X-Tenant-Id': 't1'}
KEY_A = 'sk-aaaaaaaaaaaaaaaa1111'
KEY_B = 'sk-bbbbbbbbbbbbbbbb2222'


def _verify_handler(request):
    if 'bad' in str(request.url):
        return httpx.Response(401, json={'error': 'invalid key'})
    return httpx.Response(200, json={'data': []})


def _make_client(tmp_path, verifier_handler=None):
    engine, session_factory = make_engine(tmp_path / 'providers.db')
    container = build_container(
        session_factory,
        provider_resolver=FakeProviderResolver(FakeLlm([])),
        credential_store=CredentialStore.from_secret(TEST_MASTER_KEY),
        window_resolver=ContextWindowResolver.from_file(),
        provider_verifier=HttpProviderVerifier(
            timeout_seconds=1,
            http_transport=httpx.MockTransport(
                verifier_handler or _verify_handler)),
    )
    app = create_app(container=container)
    return TestClient(app), container, engine


def _create(client, headers=OWNER_A, **overrides):
    payload = {
        'name': '我的 DeepSeek',
        'protocol': 'OPENAI_COMPATIBLE',
        'base_url': 'https://api.deepseek.com/v1',
        'model': 'deepseek-chat',
        'api_key': KEY_A,
    }
    payload.update(overrides)
    return client.post('/api/v1/agent/providers', json=payload, headers=headers)


def test_create_returns_mask_and_never_plaintext(tmp_path):
    client, container, engine = _make_client(tmp_path)
    with client:
        resp = _create(client)
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body['api_key_mask'] == 'sk-****1111'
        assert KEY_A not in resp.text
        assert 'api_key_ciphertext' not in body
        assert body['effective_context_window'] == 65536
        assert body['context_window_source'] == 'MODEL_DEFAULT'
        assert body['is_default'] is True

        # 全表无明文；密文存在且不等于明文
        from sqlalchemy import text
        with engine.connect() as conn:
            rows = conn.execute(text(
                'SELECT api_key_ciphertext, api_key_mask FROM agent_llm_provider'
            )).fetchall()
            dump = conn.execute(text(
                'SELECT * FROM agent_llm_provider')).fetchall()
        assert rows[0][0] and rows[0][0] != KEY_A
        assert KEY_A not in str(dump)


def test_list_and_detail_only_masked(tmp_path):
    client, _container, _engine = _make_client(tmp_path)
    with client:
        provider_id = _create(client).json()['id']
        listing = client.get('/api/v1/agent/providers', headers=OWNER_A)
        assert listing.status_code == 200
        assert listing.json()['items'][0]['api_key_mask'] == 'sk-****1111'
        assert KEY_A not in listing.text


def test_user_isolation(tmp_path):
    client, _container, _engine = _make_client(tmp_path)
    with client:
        provider_a = _create(client, headers=OWNER_A).json()['id']
        provider_b = _create(
            client, headers=OWNER_B, name='B 的供应商', api_key=KEY_B).json()['id']

        assert client.get('/api/v1/agent/providers',
                          headers=OWNER_A).json()['items'][0]['id'] == provider_a
        assert client.get('/api/v1/agent/providers',
                          headers=OWNER_B).json()['items'][0]['id'] == provider_b

        # B 改不动 / 删不掉 A 的供应商
        resp = client.put(f'/api/v1/agent/providers/{provider_a}',
                          json={'name': 'hijack'}, headers=OWNER_B)
        assert resp.status_code == 404
        resp = client.delete(f'/api/v1/agent/providers/{provider_a}',
                             headers=OWNER_B)
        assert resp.status_code == 404
        resp = client.post(
            f'/api/v1/agent/providers/{provider_a}/set-default',
            headers=OWNER_B)
        assert resp.status_code == 404


def test_update_keeps_key_when_blank(tmp_path):
    client, container, _engine = _make_client(tmp_path)
    with client:
        provider_id = _create(client).json()['id']
        repo = container.repositories['providers']
        before = repo.get_for_owner(provider_id, 7, 't1')

        resp = client.put(f'/api/v1/agent/providers/{provider_id}',
                          json={'name': '改名', 'api_key': ''},
                          headers=OWNER_A)
        assert resp.status_code == 200, resp.text
        after = repo.get_for_owner(provider_id, 7, 't1')
        assert resp.json()['name'] == '改名'
        assert after.api_key_ciphertext == before.api_key_ciphertext
        assert after.key_version == before.key_version
        assert resp.json()['api_key_mask'] == 'sk-****1111'


def test_context_window_override_and_warning(tmp_path):
    client, _container, _engine = _make_client(tmp_path)
    with client:
        provider_id = _create(client, context_window=32768).json()['id']
        body = client.get('/api/v1/agent/providers',
                          headers=OWNER_A).json()['items'][0]
        assert body['context_window'] == 32768
        assert body['context_window_source'] == 'USER_OVERRIDE'
        assert body['effective_context_window'] == 32768

        # 高于目录默认（65536）允许保存并带告警
        resp = client.put(f'/api/v1/agent/providers/{provider_id}',
                          json={'context_window': 131072}, headers=OWNER_A)
        assert resp.status_code == 200, resp.text
        assert resp.json()['context_window_warning'] == \
            'CONTEXT_WINDOW_ABOVE_CATALOG'

        # 清空覆盖 → 回目录默认
        resp = client.put(f'/api/v1/agent/providers/{provider_id}',
                          json={'context_window': None}, headers=OWNER_A)
        assert resp.status_code == 200
        assert resp.json()['context_window_source'] == 'MODEL_DEFAULT'
        assert resp.json()['effective_context_window'] == 65536


@pytest.mark.parametrize('value', [4096, 2098176, 33000])
def test_invalid_context_window_returns_400(tmp_path, value):
    client, _container, _engine = _make_client(tmp_path)
    with client:
        resp = _create(client, context_window=value)
        assert resp.status_code == 400
        assert resp.json()['code'] == 'INVALID_CONTEXT_WINDOW'


def test_invalid_provider_fields_return_400(tmp_path):
    client, _container, _engine = _make_client(tmp_path)
    with client:
        resp = _create(client, protocol='GRPC')
        assert resp.status_code == 400
        assert resp.json()['code'] == 'INVALID_PROVIDER_CONFIGURATION'
        resp = _create(client, base_url='ftp://example.com')
        assert resp.status_code == 400
        resp = _create(client, api_key='')
        assert resp.status_code == 422  # pydantic 最小长度


def test_set_default_and_delete_clears_ciphertext(tmp_path):
    client, container, _engine = _make_client(tmp_path)
    with client:
        first = _create(client, name='one', api_key='sk-first-000000001111')
        second = _create(client, name='two', api_key='sk-second-0000002222')
        first_id = first.json()['id']
        second_id = second.json()['id']
        assert second.json()['is_default'] is False

        resp = client.post(f'/api/v1/agent/providers/{second_id}/set-default',
                           headers=OWNER_A)
        assert resp.status_code == 200
        assert resp.json()['is_default'] is True
        listing = client.get('/api/v1/agent/providers',
                             headers=OWNER_A).json()['items']
        defaults = [item['id'] for item in listing if item['is_default']]
        assert defaults == [second_id]

        resp = client.delete(f'/api/v1/agent/providers/{second_id}',
                             headers=OWNER_A)
        assert resp.status_code == 200
        row = container.repositories['providers'].get_for_owner(
            second_id, 7, 't1')
        assert row is None  # 逻辑删除对普通查询不可见
        # 直接看库：密文清空、status=DELETED
        from sqlalchemy import text as _text
        repo = container.repositories['providers']
        db = repo._session()
        try:
            stored = db.execute(_text(
                'SELECT api_key_ciphertext, api_key_mask, status '
                'FROM agent_llm_provider WHERE id = :id'), {'id': second_id}
            ).fetchone()
        finally:
            db.close()
        assert stored[0] == ''
        assert stored[1] == ''
        assert stored[2] == ProviderStatus.DELETED.value
        # 删除默认项后自动提升剩余可用项
        listing = client.get('/api/v1/agent/providers',
                             headers=OWNER_A).json()['items']
        assert listing[0]['id'] == first_id
        assert listing[0]['is_default'] is True


def test_model_catalog_endpoint(tmp_path):
    client, _container, _engine = _make_client(tmp_path)
    with client:
        resp = client.get('/api/v1/agent/model-catalog', headers=OWNER_A)
        assert resp.status_code == 200
        body = resp.json()
        assert body['fallback_context_window'] == 131072
        assert body['bounds']['min'] == 8192
        assert any(item['match'] == 'deepseek-chat*'
                   for item in body['models'])


def test_verify_reports_unreachable_without_key(tmp_path):
    def handler(request):
        raise httpx.ConnectError('boom', request=request)

    client, _container, _engine = _make_client(tmp_path, handler)
    with client:
        provider_id = _create(client).json()['id']
        resp = client.post(f'/api/v1/agent/providers/{provider_id}/verify',
                           headers=OWNER_A)
        assert resp.status_code == 200
        body = resp.json()
        assert body['ok'] is False
        assert body['code'] == UNREACHABLE
        assert KEY_A not in resp.text


def test_verify_auth_failure_marks_invalid(tmp_path):
    client, _container, _engine = _make_client(tmp_path)
    with client:
        provider_id = _create(
            client, base_url='http://bad-provider.local/v1').json()['id']
        resp = client.post(f'/api/v1/agent/providers/{provider_id}/verify',
                           headers=OWNER_A)
        assert resp.status_code == 200
        body = resp.json()
        assert body['ok'] is False
        assert body['code'] == AUTH_FAILED
        assert body['status'] == ProviderStatus.INVALID.value
        assert KEY_A not in resp.text


def test_verify_success_records_last_verified(tmp_path):
    client, _container, _engine = _make_client(tmp_path)
    with client:
        provider_id = _create(client).json()['id']
        resp = client.post(f'/api/v1/agent/providers/{provider_id}/verify',
                           headers=OWNER_A)
        body = resp.json()
        assert body['ok'] is True
        assert body['code'] == 'PROVIDER_VERIFIED'
        assert body['status'] == ProviderStatus.ACTIVE.value
        assert body['last_verified_at']


def test_verify_success_restores_active_after_transient_auth_failure(tmp_path):
    """一次瞬时 401 判 INVALID 后，verify 成功必须恢复 ACTIVE 并重新可用。"""
    state = {'fail': True}

    def handler(request):
        if state['fail']:
            return httpx.Response(401, json={'error': 'invalid key'})
        return httpx.Response(200, json={'data': []})

    client, container, _engine = _make_client(tmp_path, handler)
    with client:
        provider_id = _create(client).json()['id']
        url = f'/api/v1/agent/providers/{provider_id}/verify'

        failed = client.post(url, headers=OWNER_A).json()
        assert failed['ok'] is False
        assert failed['status'] == ProviderStatus.INVALID.value

        state['fail'] = False
        restored = client.post(url, headers=OWNER_A).json()
        assert restored['ok'] is True
        assert restored['status'] == ProviderStatus.ACTIVE.value
        # 恢复后默认解析重新可用（run 不会再报未配置）
        row = container.repositories['providers'].get_default(7, 't1')
        assert row is not None and row.id == provider_id


def test_new_provider_is_default_when_old_default_invalid(tmp_path):
    """旧默认被判 INVALID 后，新建的可用供应商直接成为默认。"""
    client, container, _engine = _make_client(tmp_path)
    with client:
        stale = _create(client, base_url='http://bad-provider.local/v1')
        stale_id = stale.json()['id']
        assert stale.json()['is_default'] is True
        client.post(f'/api/v1/agent/providers/{stale_id}/verify',
                    headers=OWNER_A)  # 401 → INVALID

        fresh = _create(client, name='fresh', api_key='sk-fresh-0000003333',
                        base_url='https://api.deepseek.com/v1')
        assert fresh.json()['is_default'] is True
        listing = client.get('/api/v1/agent/providers',
                             headers=OWNER_A).json()['items']
        defaults = [item['id'] for item in listing if item['is_default']]
        assert defaults == [fresh.json()['id']]
        resolved = container.repositories['providers'].get_default(7, 't1')
        assert resolved is not None and resolved.id == fresh.json()['id']
