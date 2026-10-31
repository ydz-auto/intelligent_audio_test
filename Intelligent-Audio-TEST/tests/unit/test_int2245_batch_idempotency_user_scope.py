# -*- coding: utf-8 -*-
"""INT-2245 专项：用例批量操作幂等作用域按用户隔离。

背景：INT-75 的幂等键空间全局共享（``client:{key}`` / ``fp:{digest}``），
不同用户相同 action + ids + 参数会在窗口内互相回放——B 的操作被静默跳过，
甚至读到 A 的响应 message。修复后作用域 = 操作人 user_id
（``client:{user_id}:{key}`` / ``fp:{user_id}:{digest}``），未认证归 anonymous。

覆盖：
- 键/指纹解析按用户隔离，payload 里的同名字段不能篡改作用域；
- 不同用户同 payload / 同客户端键各自执行一次，互不回放、互不 409；
- 同一用户重复提交仍回放（保留 INT-75 能力），指纹仍对 ids 排序归一；
- 他用户的 completed 记录对当前用户不可见（响应 message 不跨用户泄漏）。
"""
import os

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from unittest.mock import MagicMock

import pytest

from shared.infrastructure.user_context import set_current_user_id
from shared.utils.redis_pubsub import EventBus
from task_service.application.testcase.testcase_batch_service import (
    TestCaseBatchService as BatchService,
)


class FakeIdempotencyStore:
    """内存幂等仓储：复刻 Redis 两态语义（processing 占位 / completed 回放）。"""

    def __init__(self):
        self.records = {}

    def lookup(self, key):
        record = self.records.get(key)
        return dict(record) if record else None

    def reserve(self, key, ttl_seconds):
        if key in self.records:
            return False
        self.records[key] = {'status': 'processing'}
        return True

    def complete(self, key, response, ttl_seconds):
        self.records[key] = {'status': 'completed', 'response': dict(response)}

    def release(self, key):
        self.records.pop(key, None)


@pytest.fixture(autouse=True)
def _reset_user_context():
    """每个用例前后清空操作人上下文，避免 contextvar 泄漏到其他用例。"""
    set_current_user_id(None)
    yield
    set_current_user_id(None)


@pytest.fixture(autouse=True)
def _no_stats_refresh(monkeypatch):
    import api_gateway.application.services.stats_cache as stats_cache
    monkeypatch.setattr(stats_cache, 'refresh_stats_cache', lambda: None)


@pytest.fixture
def published(monkeypatch):
    events = []

    def fake_publish(self, channel, event_type, payload):
        events.append({'channel': channel, 'event_type': event_type, 'payload': payload})

    monkeypatch.setattr(EventBus, 'publish', fake_publish)
    return events


@pytest.fixture
def store():
    return FakeIdempotencyStore()


@pytest.fixture
def service(store):
    return BatchService(repo=MagicMock(), idempotency_store=store)


# ---------- 键/指纹解析 ----------

class TestScopeResolution:
    def test_client_key_scoped_by_user(self):
        set_current_user_id(101)
        k1, _ = BatchService._resolve_idempotency_key(
            {'action': 'delete', 'ids': ['a'], 'idempotency_key': 'k'})
        set_current_user_id(202)
        k2, _ = BatchService._resolve_idempotency_key(
            {'action': 'delete', 'ids': ['a'], 'idempotency_key': 'k'})

        assert k1 == 'client:101:k'
        assert k2 == 'client:202:k'
        assert k1 != k2

    def test_fingerprint_scoped_by_user(self):
        payload = {'action': 'delete', 'ids': ['a', 'b']}
        set_current_user_id(101)
        k1, _ = BatchService._resolve_idempotency_key(dict(payload))
        set_current_user_id(202)
        k2, _ = BatchService._resolve_idempotency_key(dict(payload))

        assert k1.startswith('fp:101:')
        assert k2.startswith('fp:202:')
        assert k1 != k2

    def test_unauthenticated_falls_back_to_anonymous_scope(self):
        for unauthenticated in (None, 0, '0', ''):
            set_current_user_id(unauthenticated)
            key, _ = BatchService._resolve_idempotency_key(
                {'action': 'delete', 'ids': ['a'], 'idempotency_key': 'k'})
            assert key == 'client:anonymous:k'

    def test_payload_scope_field_cannot_override_operator(self):
        """客户端 payload 里的 scope 字段只是普通参数，不参与作用域判定。"""
        set_current_user_id(101)
        spoofed, _ = BatchService._resolve_idempotency_key(
            {'action': 'delete', 'ids': ['a'], 'scope': 202})
        honest, _ = BatchService._resolve_idempotency_key(
            {'action': 'delete', 'ids': ['a']})
        set_current_user_id(202)
        other_user, _ = BatchService._resolve_idempotency_key(
            {'action': 'delete', 'ids': ['a']})

        assert spoofed.startswith('fp:101:')
        assert honest.startswith('fp:101:')
        assert other_user.startswith('fp:202:')
        assert spoofed != other_user


# ---------- 跨用户隔离 ----------

class TestCrossUserIsolation:
    def test_two_users_same_payload_each_executes(self, service, store):
        payload = {'action': 'delete', 'ids': ['a', 'b']}

        set_current_user_id(1)
        r1 = service.batch_action(dict(payload))
        set_current_user_id(2)
        r2 = service.batch_action(dict(payload))

        assert r1['success'] is True
        assert r2['success'] is True
        assert r2.get('data') != {'idempotent_replay': True}
        assert service.repo.soft_delete_testcases_by_ids.call_count == 2
        assert len(store.records) == 2

    def test_two_users_same_client_key_each_executes(self, service):
        """自选客户端键（如 "1"）不再跨用户碰撞，B 的破坏性操作真实执行。"""
        set_current_user_id(1)
        r1 = service.batch_action(
            {'action': 'delete', 'ids': ['a', 'b'], 'idempotency_key': '1'})
        set_current_user_id(2)
        r2 = service.batch_action(
            {'action': 'delete', 'ids': ['x'], 'idempotency_key': '1'})

        assert r1['message'] == '已成功批量删除 2 个用例'
        assert r2['message'] == '已成功批量删除 1 个用例'
        assert r2.get('data') != {'idempotent_replay': True}
        assert service.repo.soft_delete_testcases_by_ids.call_count == 2

    def test_other_user_processing_record_does_not_conflict(self, service, store):
        """A 正在处理中的占位不会让 B 收到 409 而跳过自己的操作。"""
        payload = {'action': 'delete', 'ids': ['a'], 'idempotency_key': 'busy'}
        set_current_user_id(1)
        key_a, _ = BatchService._resolve_idempotency_key(payload)
        store.records[key_a] = {'status': 'processing'}

        set_current_user_id(2)
        resp = service.batch_action(dict(payload))

        assert resp['success'] is True
        assert service.repo.soft_delete_testcases_by_ids.call_count == 1

    def test_other_user_completed_record_never_replayed(self, service, store):
        """他用户的完成记录对当前用户不可见：既不回放，也不泄漏其响应 message。"""
        payload = {'action': 'delete', 'ids': ['a'], 'idempotency_key': 'k'}
        set_current_user_id(1)
        key_a, _ = BatchService._resolve_idempotency_key(payload)
        store.records[key_a] = {
            'status': 'completed',
            'response': {'success': True, 'message': 'A 的响应：目标分组 g-secret', 'data': None},
        }

        set_current_user_id(2)
        resp = service.batch_action(dict(payload))

        assert resp['message'] != 'A 的响应：目标分组 g-secret'
        assert 'idempotent_replay' not in (resp.get('data') or {})
        assert service.repo.soft_delete_testcases_by_ids.call_count == 1

    def test_same_user_fingerprint_still_replays(self, service):
        set_current_user_id(1)
        r1 = service.batch_action({'action': 'delete', 'ids': ['a', 'b']})
        r2 = service.batch_action({'action': 'delete', 'ids': ['b', 'a']})

        assert r1['success'] is True
        assert r2['data'] == {'idempotent_replay': True}
        assert service.repo.soft_delete_testcases_by_ids.call_count == 1

    def test_same_user_client_key_still_replays(self, service):
        payload = {'action': 'add_tags', 'ids': ['a'], 'tags': ['x'],
                   'idempotency_key': 'K1'}
        set_current_user_id(1)
        r1 = service.batch_action(dict(payload))
        r2 = service.batch_action(dict(payload))

        assert r1['success'] is True
        assert r2['data'] == {'idempotent_replay': True}
        assert service.repo.add_tags_to_testcases.call_count == 1

    def test_published_event_key_carries_user_scope(self, service, published):
        set_current_user_id(7)
        service.batch_action({'action': 'delete', 'ids': ['a']})

        assert published[0]['payload']['idempotency_key'].startswith('fp:7:')
