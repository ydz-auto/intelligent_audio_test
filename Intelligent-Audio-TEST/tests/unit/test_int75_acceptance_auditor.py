# -*- coding: utf-8 -*-
"""INT-75 验收补充测试（测试工程师独立复核）。

对提测专项 24 测之外的关键验收点补充覆盖：
- 16 种 batch action 全量逐一断言发布 CASE_EVENTS / case_batch_action_completed
  （channel、event_type、payload.action / ids / status / idempotency_key）
- 回放路径不重复发布事件
- 事件发布抛异常不阻断业务结果（EventBus 降级语义）
- 409（processing）→ 完成 → 同键回放 的完整时序（409 不落 completed 记录）
- 幂等 TTL 透传：占位取 min(回放 TTL, 300s)、完成取完整回放 TTL
- 网关：body 无 idempotency_key 时回退标准 Idempotency-Key 请求头，body 优先
"""
import os

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from shared.utils.redis_pubsub import EventBus, EventChannel, EventType
from task_service.application.testcase import testcase_batch_service as _batch_mod
from task_service.config.config import Config
from task_service.domain.events import testcase_events as _events_mod

# 非 Test* 命名引用：避免 pytest 把 TestCase* 业务类误当测试类收集
BatchService = _batch_mod.TestCaseBatchService


# ---------- 测试替身 ----------

class SpyIdempotencyStore:
    """内存幂等仓储，记录 reserve/complete 的 TTL 透传。"""

    def __init__(self):
        self.records = {}
        self.reserve_ttls = {}
        self.complete_ttls = []

    def lookup(self, key):
        record = self.records.get(key)
        return dict(record) if record else None

    def reserve(self, key, ttl_seconds):
        self.reserve_ttls[key] = ttl_seconds
        if key in self.records:
            return False
        self.records[key] = {'status': 'processing'}
        return True

    def complete(self, key, response, ttl_seconds):
        self.complete_ttls.append((key, ttl_seconds))
        self.records[key] = {'status': 'completed', 'response': dict(response)}

    def release(self, key):
        self.records.pop(key, None)


class FakeTC:
    def __init__(self, tc_id, name='case', group_id='g1'):
        self.id = tc_id
        self.name = name
        self.description = ''
        self.group_id = group_id
        self.config = {'rounds': []}
        self.algorithm_type = 'asr'
        self.test_type = 'api'
        self.tags = []


@pytest.fixture
def store():
    return SpyIdempotencyStore()


@pytest.fixture
def service(store):
    return BatchService(repo=MagicMock(), idempotency_store=store)


@pytest.fixture
def published(monkeypatch):
    events = []

    def fake_publish(self, channel, event_type, payload):
        events.append({'channel': channel, 'event_type': event_type, 'payload': payload})

    monkeypatch.setattr(EventBus, 'publish', fake_publish)
    return events


@pytest.fixture(autouse=True)
def no_stats_refresh(monkeypatch):
    import api_gateway.application.services.stats_cache as stats_cache
    monkeypatch.setattr(stats_cache, 'refresh_stats_cache', lambda: None)


def _wire_copy_repo(svc):
    """copy 类 handler 所需的最小仓储替身。"""
    svc.repo.get_group_by_id.return_value = SimpleNamespace(id='g9', name='G9')
    svc.repo.get_testcase.side_effect = lambda tc_id: FakeTC(tc_id)
    svc.repo.create_testcase.side_effect = (
        lambda payload: FakeTC(payload['id'], name=payload['name'], group_id=payload['group_id']))


# ---------- 16 action 全量事件覆盖 ----------

_ACTIONS = [
    ('delete', {}),
    ('move_to_group', {'target_group_id': 'g9'}),
    ('copy_to_group', {'target_group_id': 'g9'}),
    ('copy', {}),
    ('copy_by_group', {'group_name': 'src'}),
    ('copy_by_tag', {'tag_name': 'src'}),
    ('update_algorithm_params', {'algorithm_params': {'threshold': 0.8}}),
    ('update_playback_devices', {'playback_devices': [{'deviceId': 'd1'}]}),
    ('update_spl', {'spl': 60}),
    ('update_dimensions', {'dimensions': ['accuracy']}),
    ('update_noise', {'noise_audio_id': 'n1', 'noise_spl': 40, 'noise_device_ids': ['d1']}),
    ('auto_generate_name', {}),
    ('add_tags', {'tags': ['t1']}),
    ('remove_tags', {'tags': ['t1']}),
    ('rename_tag', {'old_tag_name': 'old', 'new_tag_name': 'new'}),
    ('refresh_reference', {}),
]


class TestAllActionsPublishCaseEvents:
    @pytest.mark.parametrize('action,extra', _ACTIONS)
    def test_each_action_publishes_case_event(self, service, published, action, extra):
        """验收标准①：每个 action 完成后发布 CASE_EVENTS 领域事件。"""
        service.repo.rename_tag.return_value = (SimpleNamespace(id='t1', name='old'), False)
        service.repo.get_group_by_name.side_effect = [
            SimpleNamespace(id='sg', name='src', description='desc'), None]
        service.repo.create_group.return_value = SimpleNamespace(
            id='ng', name='src_copy', description='desc')
        service.repo.get_active_tag_by_name.side_effect = [
            SimpleNamespace(id='t1', name='src'), None]
        service.repo.get_or_create_tag.return_value = SimpleNamespace(id='t2', name='src_copy')
        _wire_copy_repo(service)

        data = {'action': action, 'ids': ['a', 'b'], 'idempotency_key': f'k-{action}', **extra}
        resp = service.batch_action(data)

        assert resp['success'] is True, f"{action}: {resp.get('message')}"
        batch_events = [e for e in published if e['payload'].get('action') == action]
        assert len(batch_events) == 1, f"{action} 应恰好发布 1 条事件"
        ev = batch_events[0]
        assert ev['channel'] == EventChannel.CASE_EVENTS
        assert ev['event_type'] == EventType.CASE_BATCH_ACTION_COMPLETED
        payload = ev['payload']
        assert payload['status'] == 'completed'
        assert payload['idempotency_key'] == f'client:k-{action}'
        assert payload['occurred_at']
        if action not in ('copy_by_group', 'copy_by_tag'):
            # 按分组/标签维度的 action 请求本身无 ids，payload 如实回显请求 ids
            assert payload['ids'] == ['a', 'b']

    def test_group_scope_action_event_payload_shape(self, service, published):
        """copy_by_group 事件契约字段完整（ids=[] 为请求实际形态，计数在 message 中）。"""
        resp = service.batch_action({'action': 'copy_by_group', 'group_name': 'src',
                                     'idempotency_key': 'k-cbg'})
        assert resp['success'] is True
        payload = published[0]['payload']
        assert payload['action'] == 'copy_by_group'
        assert payload['ids'] == []
        assert payload['status'] == 'completed'
        assert set(payload) == {'action', 'ids', 'success_count', 'message', 'idempotency_key',
                                'status', 'async_task_id', 'occurred_at'}


# ---------- 事件降级与回放语义 ----------

class TestEventDegradationAndReplay:
    def test_replay_publishes_no_second_event(self, service, published):
        assert service.batch_action({'action': 'delete', 'ids': ['a']})['success'] is True
        assert service.batch_action({'action': 'delete', 'ids': ['a']})['data'] == {
            'idempotent_replay': True}
        assert len(published) == 1

    def test_event_publish_failure_does_not_break_operation(self, service, monkeypatch):
        def boom(self, *args, **kwargs):
            raise RuntimeError('redis down')

        monkeypatch.setattr(EventBus, 'publish', boom)
        resp = service.batch_action({'action': 'delete', 'ids': ['a']})
        assert resp['success'] is True
        assert service.repo.soft_delete_testcases_by_ids.call_count == 1


# ---------- 幂等时序与 TTL 透传 ----------

class TestIdempotencySequenceAndTtl:
    def test_conflict_then_complete_then_replay(self, service, store):
        data = {'action': 'delete', 'ids': ['a', 'b'], 'idempotency_key': 'seq-1'}
        key, _ = service._resolve_idempotency_key(data)

        # 模拟同批次正在执行：占位已存在
        store.records[key] = {'status': 'processing'}
        resp = service.batch_action(dict(data))
        assert resp['success'] is False
        assert resp['code'] == 409
        # 409 不落 completed 记录（不污染回放窗口）
        assert store.records[key] == {'status': 'processing'}

        # 执行完成 → 同键回放首次响应（message 保留 + 回放标记）
        store.records[key] = {'status': 'completed',
                              'response': {'success': True, 'message': '已成功批量删除 2 个用例',
                                           'data': None}}
        replay = service.batch_action(dict(data))
        assert replay['success'] is True
        assert replay['message'] == '已成功批量删除 2 个用例'
        assert replay['data'] == {'idempotent_replay': True}

        # 占位释放后重新提交 → 正常执行
        store.records.pop(key)
        service.repo.soft_delete_testcases_by_ids.reset_mock()
        fresh = service.batch_action(dict(data))
        assert fresh['success'] is True
        assert 'idempotent_replay' not in (fresh.get('data') or {})
        assert service.repo.soft_delete_testcases_by_ids.call_count == 1

    def test_ttl_passthrough(self, store):
        svc = BatchService(repo=MagicMock(), idempotency_store=store)
        reserve_cap = Config.IDEMPOTENCY_RESERVE_TTL_SECONDS

        client_data = {'action': 'delete', 'ids': ['a'], 'idempotency_key': 'ttl-1'}
        key, client_ttl = svc._resolve_idempotency_key(client_data)
        svc.batch_action(dict(client_data))
        assert key == 'client:ttl-1'
        assert client_ttl == Config.IDEMPOTENCY_CLIENT_KEY_TTL_SECONDS
        assert store.reserve_ttls[key] == min(client_ttl, reserve_cap)
        assert store.complete_ttls[-1] == (key, client_ttl)

        fp_data = {'action': 'delete', 'ids': ['b']}
        key_fp, fp_ttl = svc._resolve_idempotency_key(fp_data)
        svc.batch_action(dict(fp_data))
        assert key_fp.startswith('fp:')
        assert fp_ttl == Config.IDEMPOTENCY_FINGERPRINT_TTL_SECONDS
        assert store.reserve_ttls[key_fp] == min(fp_ttl, reserve_cap)
        assert store.complete_ttls[-1] == (key_fp, fp_ttl)


# ---------- 网关幂等键透传 ----------

class _StubState:
    def __init__(self, json_body):
        self._json_body = json_body


class _StubRequest:
    """FastAPI 风格请求桩：request_adapter 中间件契约（state._json_body 预解析 + headers）。"""

    def __init__(self, json_body, headers):
        self.state = _StubState(json_body)
        self.headers = headers
        self.method = 'POST'
        self.query_params = {}


@pytest.fixture
def gateway_request():
    from api_gateway.infrastructure import request_adapter as adapter

    def _set(json_body, headers):
        adapter.set_current_request(_StubRequest(json_body, headers))

    yield _set
    adapter.set_current_request(None)


class TestGatewayHeaderFallback:
    def _invoke(self, monkeypatch, gateway_request, payload, headers):
        from api_gateway.application.services.testcase import testcase_command_service as gw
        captured = {}

        class FakeAcl:
            def batch_action(self, data):
                captured.update(data)
                return {'success': True, 'message': 'ok', 'data': None}

        monkeypatch.setattr(gw, '_testcase_acl', FakeAcl())
        gateway_request(payload, headers)
        gw.TestCaseCommandService.batch_action()
        return captured

    def test_header_fallback_when_body_missing(self, monkeypatch, gateway_request):
        captured = self._invoke(monkeypatch, gateway_request,
                                {'action': 'delete', 'ids': ['a']},
                                {'Idempotency-Key': 'hdr-123'})
        assert captured['idempotency_key'] == 'hdr-123'

    def test_body_key_takes_precedence_over_header(self, monkeypatch, gateway_request):
        captured = self._invoke(monkeypatch, gateway_request,
                                {'action': 'delete', 'ids': ['a'], 'idempotencyKey': 'body-1'},
                                {'Idempotency-Key': 'hdr-123'})
        assert captured['idempotency_key'] == 'body-1'

    def test_no_key_anywhere_keeps_field_absent(self, monkeypatch, gateway_request):
        captured = self._invoke(monkeypatch, gateway_request,
                                {'action': 'delete', 'ids': ['a']}, {})
        assert 'idempotency_key' not in captured
