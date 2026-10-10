# -*- coding: utf-8 -*-
"""INT-75 专项：用例批量操作 CASE_EVENTS 事件发布 + 幂等去重。

覆盖：
- 14+2 种 batch action 成功后发布 CASE_EVENTS / case_batch_action_completed
  （payload 含 action/ids/success_count/message/status/idempotency_key）
- 异步任务（refresh_reference > 50 条）提交事件 status='submitted' + async_task_id
- ReferenceRefreshTask 终态补发 completed/failed 事件
- 幂等：客户端幂等键回放、内容指纹回放（ids 排序归一）、processing 冲突 409、
  失败释放占位可重试、Redis 不可用降级放行、重复 copy 不产生重复副本
"""
import os

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from shared.utils.redis_pubsub import EventBus, EventChannel, EventType
from task_service.application.testcase import testcase_batch_service as _batch_mod
from task_service.domain.events import testcase_events as _events_mod

# 非 Test* 命名引用：避免 pytest 把 TestCase* 业务类误当测试类收集
BatchService = _batch_mod.TestCaseBatchService
BatchActionEvent = _events_mod.TestCaseBatchAction


# ---------- 测试替身 ----------

class FakeIdempotencyStore:
    """内存幂等仓储：复刻 Redis 两态语义（processing 占位 / completed 回放）。"""

    def __init__(self):
        self.records = {}
        self.completed = []
        self.released = []

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
        self.completed.append((key, dict(response), ttl_seconds))

    def release(self, key):
        self.records.pop(key, None)
        self.released.append(key)


class BrokenStore:
    """模拟 Redis 不可用：所有方法抛异常，要求服务侧降级放行。"""

    def lookup(self, key):
        raise RuntimeError('redis down')

    def reserve(self, key, ttl_seconds):
        raise RuntimeError('redis down')

    def complete(self, key, response, ttl_seconds):
        raise RuntimeError('redis down')

    def release(self, key):
        raise RuntimeError('redis down')


class FakeTC:
    """最小用例替身：复制链路需要的字段。"""

    def __init__(self, tc_id, name='case', group_id='g1'):
        self.id = tc_id
        self.name = name
        self.description = ''
        self.group_id = group_id
        self.config = {'rounds': []}
        self.algorithm_type = 'asr'
        self.test_type = 'api'
        self.tags = []


class FakeKVStore:
    """RedisStore 替身：ReferenceRefreshTask 进度持久化。"""

    def __init__(self):
        self.data = {}

    def save_task(self, key, fields, ttl_seconds=86400):
        self.data[key] = dict(fields)

    def load_task(self, key):
        return dict(self.data.get(key, {}))


@pytest.fixture
def fake_store():
    return FakeIdempotencyStore()


@pytest.fixture
def service(fake_store):
    svc = BatchService(repo=MagicMock(), idempotency_store=fake_store)
    return svc


@pytest.fixture
def published(monkeypatch):
    """捕获 EventBus.publish 调用（含构造时的 Redis 惰性连接，无真实 IO）。"""
    events = []

    def fake_publish(self, channel, event_type, payload):
        events.append({'channel': channel, 'event_type': event_type, 'payload': payload})

    monkeypatch.setattr(EventBus, 'publish', fake_publish)
    return events


@pytest.fixture(autouse=True)
def no_stats_refresh(monkeypatch):
    """屏蔽批量操作后的统计缓存刷新（避免测试环境触达 Redis/gRPC）。"""
    import api_gateway.application.services.stats_cache as stats_cache
    monkeypatch.setattr(stats_cache, 'refresh_stats_cache', lambda: None)


# ---------- 事件发布 ----------

class TestBatchEventPublishing:
    def test_sync_action_publishes_case_event(self, service, published):
        resp = service.batch_action({'action': 'delete', 'ids': ['a', 'b']})

        assert resp['success'] is True
        assert len(published) == 1
        ev = published[0]
        assert ev['channel'] == EventChannel.CASE_EVENTS
        assert ev['event_type'] == EventType.CASE_BATCH_ACTION_COMPLETED
        payload = ev['payload']
        assert payload['action'] == 'delete'
        assert payload['ids'] == ['a', 'b']
        assert payload['success_count'] == 2
        assert payload['status'] == 'completed'
        assert payload['message']
        assert payload['occurred_at']
        assert payload['idempotency_key'].startswith('fp:')

    @pytest.mark.parametrize('action,extra', [
        ('move_to_group', {'target_group_id': 'g9'}),
        ('copy_to_group', {'target_group_id': 'g9'}),
        ('update_spl', {'spl': 60}),
        ('add_tags', {'tags': ['t1']}),
        ('remove_tags', {'tags': ['t1']}),
        ('auto_generate_name', {}),
    ])
    def test_action_families_publish_event(self, service, fake_store, published, action, extra):
        data = {'action': action, 'ids': ['a', 'b'], 'idempotency_key': f'k-{action}', **extra}
        service.repo.get_group_by_id.return_value = SimpleNamespace(id='g9', name='G9')
        service.repo.get_testcase.side_effect = lambda tc_id: FakeTC(tc_id)
        service.repo.create_testcase.side_effect = (
            lambda payload: FakeTC(payload['id'], name=payload['name'], group_id=payload['group_id']))

        resp = service.batch_action(data)
        assert resp['success'] is True, resp.get('message')
        batch_events = [e for e in published if e['payload'].get('action') == action]
        assert len(batch_events) == 1
        assert batch_events[0]['payload']['status'] == 'completed'
        assert batch_events[0]['payload']['ids'] == ['a', 'b']

    def test_async_refresh_publishes_submitted_event(self, service, published, monkeypatch):
        monkeypatch.setattr(
            'task_service.application.testcase.reference_refresh_task.submit_reference_refresh_task',
            lambda case_ids, refresher=None, executor=None: 'task-123')
        ids = [f'c{i}' for i in range(51)]  # 超阈值走异步提交

        resp = service.batch_action({'action': 'refresh_reference', 'ids': ids})

        assert resp['success'] is True
        assert resp['data']['task_id'] == 'task-123'
        assert len(published) == 1
        payload = published[0]['payload']
        assert payload['status'] == 'submitted'
        assert payload['async_task_id'] == 'task-123'
        assert payload['action'] == 'refresh_reference'
        assert payload['ids'] == ids

    def test_error_path_publishes_no_event(self, service, published):
        # move_to_group 缺 target_group_id → (message, True) 错误提前返回
        resp = service.batch_action({'action': 'move_to_group', 'ids': ['a']})
        assert resp['success'] is False
        assert published == []


class TestReferenceRefreshTaskEvent:
    def _patch_kv(self, monkeypatch):
        from task_service.application.testcase import reference_refresh_task as m
        kv = FakeKVStore()
        monkeypatch.setattr(m, '_store', lambda: kv)
        repo_mock = MagicMock()
        repo_mock.list_testcases_by_ids.return_value = [SimpleNamespace(id='c1', updated_at=None)]
        monkeypatch.setattr(m, 'testcase_repository', repo_mock)
        return m

    def test_terminal_completed_event(self, monkeypatch, published):
        self._patch_kv(monkeypatch)
        from task_service.application.testcase.reference_refresh_task import ReferenceRefreshTask

        task = ReferenceRefreshTask(['c1'])
        task.run(refresher=lambda tc: None)

        assert task.status == 'completed'
        events = [e for e in published if e['payload'].get('async_task_id') == task.task_id]
        assert len(events) == 1
        payload = events[0]['payload']
        assert payload['status'] == 'completed'
        assert payload['action'] == 'refresh_reference'
        assert payload['success_count'] == 1
        assert payload['ids'] == ['c1']

    def test_terminal_failed_event(self, monkeypatch, published):
        self._patch_kv(monkeypatch)
        from task_service.application.testcase.reference_refresh_task import ReferenceRefreshTask

        task = ReferenceRefreshTask(['c1'])
        task.run(refresher=None)  # 缺 refresher → 任务失败分支

        assert task.status == 'failed'
        events = [e for e in published if e['payload'].get('async_task_id') == task.task_id]
        assert len(events) == 1
        assert events[0]['payload']['status'] == 'failed'


class TestEventContract:
    def test_event_frozen_and_payload_keys(self):
        ev = BatchActionEvent(action='copy', case_ids=['1'], success_count=1, idempotency_key='client:k')
        payload = ev.to_dict()
        assert set(payload) == {'action', 'ids', 'success_count', 'message', 'idempotency_key',
                                'status', 'async_task_id', 'occurred_at'}
        assert payload['ids'] == ['1']
        with pytest.raises(Exception):
            ev.action = 'other'  # frozen dataclass


# ---------- 幂等 ----------

class TestIdempotency:
    def test_fingerprint_replay_no_duplicate_execution(self, service):
        payload = {'action': 'delete', 'ids': ['a', 'b']}

        r1 = service.batch_action(dict(payload))
        assert r1['success'] is True
        assert service.repo.soft_delete_testcases_by_ids.call_count == 1

        r2 = service.batch_action(dict(payload))
        assert r2['success'] is True
        assert r2['data'] == {'idempotent_replay': True}
        assert service.repo.soft_delete_testcases_by_ids.call_count == 1  # 未重复执行

    def test_fingerprint_normalizes_ids_order(self, service):
        service.batch_action({'action': 'delete', 'ids': ['a', 'b']})
        r2 = service.batch_action({'action': 'delete', 'ids': ['b', 'a']})
        assert r2['data'] == {'idempotent_replay': True}
        assert service.repo.soft_delete_testcases_by_ids.call_count == 1

    def test_different_payload_executes_again(self, service):
        service.batch_action({'action': 'delete', 'ids': ['a', 'b']})
        r2 = service.batch_action({'action': 'delete', 'ids': ['a', 'c']})
        assert r2['success'] is True
        assert service.repo.soft_delete_testcases_by_ids.call_count == 2

    def test_client_key_replay_even_with_different_payload(self, service):
        r1 = service.batch_action({'action': 'add_tags', 'ids': ['a'], 'tags': ['x'],
                                   'idempotency_key': 'K1'})
        assert r1['success'] is True
        r2 = service.batch_action({'action': 'add_tags', 'ids': ['a'], 'tags': ['y'],
                                   'idempotency_key': 'K1'})
        assert r2['data'].get('idempotent_replay') is True
        assert service.repo.add_tags_to_testcases.call_count == 1
        # 回放返回首次请求的原始结果
        assert r2['message'] == r1['message']

    def test_processing_conflict_returns_409(self, service, fake_store):
        fake_store.records['client:K9'] = {'status': 'processing'}
        resp = service.batch_action({'action': 'delete', 'ids': ['a'], 'idempotency_key': 'K9'})
        assert resp['success'] is False
        assert resp['code'] == 409

    def test_handler_exception_releases_and_allows_retry(self, service, fake_store):
        service.repo.soft_delete_testcases_by_ids.side_effect = RuntimeError('boom')
        r1 = service.batch_action({'action': 'delete', 'ids': ['a']})
        assert r1['success'] is False
        assert fake_store.released  # 占位已释放
        assert fake_store.records == {}

        service.repo.soft_delete_testcases_by_ids.side_effect = None
        r2 = service.batch_action({'action': 'delete', 'ids': ['a']})
        assert r2['success'] is True  # 可重试

    def test_validation_error_releases(self, service, fake_store):
        resp = service.batch_action({'action': 'move_to_group', 'ids': ['a']})
        assert resp['code'] == 400
        assert fake_store.records == {}  # 未残留占位

    def test_unknown_action_skips_store(self, service, fake_store):
        resp = service.batch_action({'action': 'nope', 'ids': []})
        assert resp['code'] == 400
        assert fake_store.records == {}

    def test_copy_duplicate_submit_no_duplicate_copies(self, service):
        service.repo.get_testcase.side_effect = lambda tc_id: FakeTC(tc_id, name='case1')
        created = []

        def fake_create(payload):
            new = FakeTC(payload['id'], name=payload['name'], group_id=payload['group_id'])
            created.append(new)
            return new

        service.repo.create_testcase.side_effect = fake_create
        payload = {'action': 'copy', 'ids': ['c1']}

        r1 = service.batch_action(dict(payload))
        assert r1['success'] is True
        assert len(created) == 1

        r2 = service.batch_action(dict(payload))
        assert len(created) == 1  # 同批次重复提交不产生重复副本
        assert r2['data'] == {'idempotent_replay': True}

    def test_store_failure_degrades_to_normal_execution(self, published):
        svc = BatchService(repo=MagicMock(), idempotency_store=BrokenStore())
        resp = svc.batch_action({'action': 'delete', 'ids': ['a']})
        assert resp['success'] is True
        svc.repo.soft_delete_testcases_by_ids.assert_called_once_with(['a'])
        assert len(published) == 1  # 事件发布不受幂等降级影响


# ---------- 网关 schema 透传 ----------

class TestGatewaySchema:
    def test_idempotency_key_alias_passthrough(self):
        from api_gateway.schemas.testcase import TestCaseBatchActionRequest
        req = TestCaseBatchActionRequest.model_validate(
            {'action': 'delete', 'ids': ['a'], 'idempotencyKey': 'K1'})
        dumped = req.model_dump(by_alias=False, exclude_none=True)
        assert dumped['idempotency_key'] == 'K1'

    def test_idempotency_key_optional(self):
        from api_gateway.schemas.testcase import TestCaseBatchActionRequest
        req = TestCaseBatchActionRequest.model_validate({'action': 'delete', 'ids': ['a']})
        dumped = req.model_dump(by_alias=False, exclude_none=True)
        assert 'idempotency_key' not in dumped
