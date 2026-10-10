# -*- coding: utf-8 -*-
"""INT-76 专项：参考参数刷新阈值配置化 + 异步任务可靠性（孤儿恢复）。

覆盖：
- 异步阈值入配置键（默认 50 行为兼容，超阈值边界走异步提交）
- 任务记录含输入 case_ids 与归属实例 instance_id（恢复重放的依据）
- 启动恢复：归属实例已下线的 pending/running 任务同 task_id 重放，
  归属实例存活的不动，终态不动，无 case_ids 的历史遗留标记 failed，
  SETNX 认领锁丢失时跳过，recovered_count 累加
- 轮询响应 additive 字段（recovered_count / error_message），契约向后兼容
"""
import os

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from unittest.mock import MagicMock

import pytest

from shared.utils.redis_pubsub import EventBus
from shared.utils.service_registry import RedisServiceRegistry
from task_service.application.testcase import testcase_batch_service as _batch_mod
from task_service.application.testcase import reference_refresh_task as _rr_mod
from task_service.config.config import Config

# 非 Test* 命名引用：避免 pytest 把 TestCase* 业务类误当测试类收集
BatchService = _batch_mod.TestCaseBatchService
rr = _rr_mod

_TASK_KEY_PREFIX = 'reference_refresh:task:'


# ---------- 测试替身 ----------

class FakeKVStore:
    """RedisStore 替身：复刻 HASH 字段合并语义（HSET 只更新给定字段）。"""

    def __init__(self):
        self.data = {}
        self.redis_client = MagicMock()

    def save_task(self, key, fields, ttl_seconds=86400):
        if not fields:
            return
        self.data.setdefault(key, {}).update(fields)

    def load_task(self, key):
        record = self.data.get(key)
        return dict(record) if record else {}

    def scan_keys(self, pattern):
        prefix = pattern[:-1] if pattern.endswith('*') else pattern
        return [k for k in self.data if k.startswith(prefix)]


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


class FakeTC:
    """最小用例替身：空 rounds 使参考参数生成直接跳过（不触达 gRPC）。"""

    def __init__(self, tc_id):
        self.id = tc_id
        self.config = {'rounds': []}
        self.updated_at = None


@pytest.fixture
def kv(monkeypatch):
    store = FakeKVStore()
    monkeypatch.setattr(rr, '_store', lambda: store)
    return store


@pytest.fixture(autouse=True)
def no_event_io(monkeypatch):
    """屏蔽 EventBus 发布（避免测试环境触达 Redis）。"""
    monkeypatch.setattr(EventBus, 'publish', lambda self, *a, **k: None)


@pytest.fixture(autouse=True)
def no_stats_refresh(monkeypatch):
    """屏蔽批量操作后的统计缓存刷新（避免测试环境触达 Redis/gRPC）。"""
    import api_gateway.application.services.stats_cache as stats_cache
    monkeypatch.setattr(stats_cache, 'refresh_stats_cache', lambda: None)


# ---------- 阈值配置化 ----------

class TestThresholdConfig:
    def test_default_threshold_is_50(self):
        assert Config.REFERENCE_REFRESH_ASYNC_THRESHOLD == 50

    def test_default_task_ttl_is_86400(self):
        assert Config.REFERENCE_REFRESH_TASK_TTL_SECONDS == 86400

    def test_at_threshold_sync(self, monkeypatch):
        monkeypatch.setattr(Config, 'REFERENCE_REFRESH_ASYNC_THRESHOLD', 3)
        repo = MagicMock()
        repo.list_testcases_by_ids.side_effect = lambda ids: [FakeTC(i) for i in ids]
        svc = BatchService(repo=repo, idempotency_store=FakeIdempotencyStore())

        result = svc._batch_refresh_reference({'ids': ['a', 'b', 'c']})

        assert isinstance(result, str)  # 同步路径返回消息字符串
        repo.commit.assert_called_once()

    def test_above_threshold_async_submits(self, monkeypatch):
        monkeypatch.setattr(Config, 'REFERENCE_REFRESH_ASYNC_THRESHOLD', 3)
        submitted = {}

        def fake_submit(case_ids, refresher=None, executor=None, **kwargs):
            submitted['case_ids'] = case_ids
            return 'task-x'

        monkeypatch.setattr(rr, 'submit_reference_refresh_task', fake_submit)
        repo = MagicMock()
        svc = BatchService(repo=repo, idempotency_store=FakeIdempotencyStore())

        result = svc._batch_refresh_reference({'ids': ['a', 'b', 'c', 'd']})

        assert result['task_id'] == 'task-x'
        assert submitted['case_ids'] == ['a', 'b', 'c', 'd']
        repo.commit.assert_not_called()  # 异步路径不做同步提交

    def test_batch_action_default_threshold_50_compat(self, service=None):
        """默认配置下 50 条同步 / 51 条异步（行为兼容回归）。"""
        repo = MagicMock()
        repo.list_testcases_by_ids.side_effect = lambda ids: [FakeTC(i) for i in ids]
        svc = BatchService(repo=repo, idempotency_store=FakeIdempotencyStore())

        sync_result = svc._batch_refresh_reference({'ids': [f'c{i}' for i in range(50)]})
        assert isinstance(sync_result, str)

        async_result = svc._batch_refresh_reference({'ids': [f'c{i}' for i in range(51)]})
        assert isinstance(async_result, dict) and 'task_id' in async_result


# ---------- 提交记录：输入与归属 ----------

class TestSubmitRecordsInputAndOwner:
    def test_submit_persists_case_ids_and_owner(self, kv):
        pool = MagicMock()
        executor = MagicMock()
        executor._reference_refresh_pool = pool
        executor.instance_id = 'task_service:h:1:abc'

        task_id = rr.submit_reference_refresh_task(
            ['a', 'b'], executor=executor, refresher=lambda tc: None)

        record = kv.data[f'{_TASK_KEY_PREFIX}{task_id}']
        assert record['status'] == 'pending'
        assert record['case_ids'] == ['a', 'b']
        assert record['instance_id'] == 'task_service:h:1:abc'
        assert record['recovered_count'] == 0
        pool.submit.assert_called_once()

    def test_progress_persist_keeps_owner(self, kv):
        """进度 _persist 不得覆盖归属实例（HSET 合并语义依赖字段值正确）。"""
        pool = MagicMock()
        executor = MagicMock()
        executor._reference_refresh_pool = pool
        executor.instance_id = 'task_service:h:1:abc'

        task_id = rr.submit_reference_refresh_task(
            ['a'], executor=executor, refresher=lambda tc: None)

        # 从提交闭包取出任务实例，模拟 run() 中的进度持久化
        run_lambda = pool.submit.call_args[0][0]
        task = next(c.cell_contents for c in run_lambda.__closure__
                    if isinstance(c.cell_contents, rr.ReferenceRefreshTask))
        task.status = 'running'
        task.updated_count = 1
        task._persist()

        record = kv.data[f'{_TASK_KEY_PREFIX}{task_id}']
        assert record['status'] == 'running'
        assert record['instance_id'] == 'task_service:h:1:abc'
        assert record['case_ids'] == ['a']  # 合并语义保留任务输入


# ---------- 启动恢复（孤儿收养） ----------

class TestOrphanRecovery:
    @pytest.fixture
    def submitted(self, monkeypatch):
        calls = []

        def fake_submit(case_ids, refresher=None, executor=None, task_id=None, recovered_count=0):
            calls.append({'case_ids': list(case_ids), 'task_id': task_id,
                          'recovered_count': recovered_count, 'refresher': refresher})
            return task_id

        monkeypatch.setattr(rr, 'submit_reference_refresh_task', fake_submit)
        return calls

    @pytest.fixture
    def alive_ids(self, monkeypatch):
        ids = set()
        monkeypatch.setattr(RedisServiceRegistry, 'get_alive_ids',
                            lambda self, service_name: ids)
        return ids

    @staticmethod
    def _record(kv, task_id, status='running', owner='task_service:h:9:dead',
               case_ids=('a', 'b'), recovered_count=0):
        kv.data[f'{_TASK_KEY_PREFIX}{task_id}'] = {
            'task_id': task_id,
            'status': status,
            'total': len(case_ids),
            'updated': 0,
            'failed': 0,
            'instance_id': owner,
            'recovered_count': recovered_count,
            'case_ids': list(case_ids),
        }

    def test_dead_owner_adopted_with_same_task_id(self, kv, submitted, alive_ids):
        self._record(kv, 't1', status='running', owner='task_service:h:9:dead')

        adopted = rr.recover_orphan_reference_refresh_tasks(instance_id='task_service:h:1:new')

        assert adopted == 1
        assert len(submitted) == 1
        call = submitted[0]
        assert call['task_id'] == 't1'  # 同 task_id 重放，前端轮询 ID 不变
        assert call['case_ids'] == ['a', 'b']
        assert call['recovered_count'] == 1
        assert call['refresher'] is not None

    def test_pending_orphan_adopted_too(self, kv, submitted, alive_ids):
        self._record(kv, 't2', status='pending', owner='task_service:h:9:dead')

        assert rr.recover_orphan_reference_refresh_tasks() == 1
        assert submitted[0]['task_id'] == 't2'

    def test_alive_owner_not_adopted(self, kv, submitted, alive_ids):
        alive_ids.add('task_service:h:2:live')
        self._record(kv, 't3', status='running', owner='task_service:h:2:live')

        assert rr.recover_orphan_reference_refresh_tasks() == 0
        assert submitted == []
        assert kv.data[f'{_TASK_KEY_PREFIX}t3']['status'] == 'running'

    def test_terminal_records_ignored(self, kv, submitted, alive_ids):
        self._record(kv, 't4', status='completed')
        self._record(kv, 't5', status='failed')

        assert rr.recover_orphan_reference_refresh_tasks() == 0
        assert submitted == []

    def test_legacy_record_without_case_ids_marked_failed(self, kv, submitted, alive_ids):
        kv.data[f'{_TASK_KEY_PREFIX}t6'] = {
            'task_id': 't6', 'status': 'running', 'total': 5,
            'updated': 2, 'failed': 0, 'instance_id': 'task_service:h:9:dead',
        }

        rr.recover_orphan_reference_refresh_tasks()

        record = kv.data[f'{_TASK_KEY_PREFIX}t6']
        assert record['status'] == 'failed'
        assert 'case_ids' in record['error_message']
        assert record['completed_at']
        assert submitted == []

    def test_adoption_lock_lost_skips(self, kv, submitted, alive_ids):
        kv.redis_client.set.return_value = None  # SETNX 失败：已被其他实例认领
        self._record(kv, 't7', status='running', owner='task_service:h:9:dead')

        assert rr.recover_orphan_reference_refresh_tasks() == 0
        assert submitted == []
        assert kv.data[f'{_TASK_KEY_PREFIX}t7']['status'] == 'running'

    def test_recovered_count_increments(self, kv, submitted, alive_ids):
        self._record(kv, 't8', status='running', owner='task_service:h:9:dead',
                     recovered_count=2)

        rr.recover_orphan_reference_refresh_tasks()

        assert submitted[0]['recovered_count'] == 3

    def test_unowned_legacy_record_adopted(self, kv, submitted, alive_ids):
        self._record(kv, 't9', status='running', owner=None)

        assert rr.recover_orphan_reference_refresh_tasks() == 1
        assert submitted[0]['task_id'] == 't9'

    def test_adopt_lock_uses_setnx(self, kv, submitted, alive_ids):
        self._record(kv, 't10', status='running', owner='task_service:h:9:dead')

        rr.recover_orphan_reference_refresh_tasks()

        args, kwargs = kv.redis_client.set.call_args
        assert args[0] == f'reference_refresh:adopt:t10'
        assert kwargs.get('nx') is True


# ---------- 状态读取（additive 字段） ----------

class TestStatusReader:
    def test_recovered_and_error_fields_returned(self, kv):
        kv.data[f'{_TASK_KEY_PREFIX}t20'] = {
            'task_id': 't20', 'status': 'failed', 'total': 3,
            'updated': 1, 'failed': 0, 'recovered_count': 2,
            'error_message': '任务记录缺少 case_ids，进程重启后无法重放',
        }

        status = rr.get_reference_refresh_task_status('t20')

        assert status['recovered_count'] == 2
        assert 'case_ids' in status['error_message']

    def test_defaults_when_fields_absent(self, kv):
        kv.data[f'{_TASK_KEY_PREFIX}t21'] = {
            'task_id': 't21', 'status': 'completed', 'total': 1,
            'updated': 1, 'failed': 0,
        }

        status = rr.get_reference_refresh_task_status('t21')

        assert status['recovered_count'] == 0
        assert status['error_message'] is None

    def test_not_found_contract_unchanged(self, kv):
        status = rr.get_reference_refresh_task_status('missing')

        assert status['status'] == 'not_found'
        assert status['message'].startswith('任务')
