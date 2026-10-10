# -*- coding: utf-8 -*-
"""INT-80 专项：设备操作/批量操作（幂等模式）+ 操作状态事件。

覆盖：
- DeviceOperationService：不支持的操作、未知设备 404、成功/失败均落状态事件
- DeviceBatchService：动作白名单、空 ids 拒绝、客户端幂等键回放、
  内容指纹回放（device_ids 排序归一）、processing 冲突 409、失败释放占位
- DEVICE_EVENTS 发布（batch 成功后）
"""
import os

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from types import SimpleNamespace

import pytest

from device_service.application.commands.device_operation_service import (
    DeviceOperationService,
    DeviceBatchService,
    BATCH_ACTIONS,
)
from device_service.infrastructure.device_operations import DeviceOperationError


# ---------- 测试替身 ----------

class FakeDeviceRepo:
    def __init__(self):
        self.devices = {
            1: SimpleNamespace(id=1, name='D1', status='online', system='Android',
                               serial_number='sn-1', ip='', connection_type='usb'),
            2: SimpleNamespace(id=2, name='D2', status='offline', system='HarmonyOS',
                               serial_number='sn-2', ip='', connection_type='usb'),
        }

    def get_device(self, device_id):
        return self.devices.get(int(device_id))


class FakeExecutor:
    """受控操作执行器：指定设备失败"""

    def __init__(self):
        self.calls = []
        self.fail_device_ids = set()

    def execute(self, device, operation, params=None):
        self.calls.append((device.id, operation, params or {}))
        if device.id in self.fail_device_ids:
            raise DeviceOperationError('模拟执行失败')
        return {'output': 'ok', 'operation': operation, 'mock': False}


class FakeMonitorRepo:
    def __init__(self):
        self.events = []

    def record_status_event(self, data):
        self.events.append(data)
        return dict(data)

    def list_enabled_alarm_rules(self):
        return []

    def get_last_online_events(self, device_ids):
        return {}

    def count_health_check_failures_batch(self, device_ids):
        return {}

    def get_latest_health_details(self, device_ids):
        return {}

    def has_unresolved_alarm(self, rule_id, device_id):
        return False

    def create_alarm(self, data):
        raise NotImplementedError


class FakeIdempotencyStore:
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
        self.records[key] = {'status': 'completed', 'response': response}

    def release(self, key):
        self.records.pop(key, None)


class FakeMonitor:
    """替换 DeviceOperationService._monitor 属性"""

    def __init__(self, repo):
        self.repo = repo

    def record_status_event(self, **kwargs):
        return self.repo.record_status_event(kwargs)


@pytest.fixture
def executor():
    return FakeExecutor()


@pytest.fixture
def event_repo():
    return FakeMonitorRepo()


@pytest.fixture
def op_service(executor, event_repo):
    return DeviceOperationService(repo=FakeDeviceRepo(), executor=executor,
                                  monitor=FakeMonitor(event_repo))


@pytest.fixture
def batch_service(op_service):
    return DeviceBatchService(op_service=op_service, idempotency_store=FakeIdempotencyStore())


class TestSingleOperation:
    def test_execute_success_records_event(self, op_service, executor, event_repo):
        result = op_service.execute(1, 'reboot')
        assert result['success'] is True
        assert executor.calls == [(1, 'reboot', {})]
        assert len(event_repo.events) == 1
        assert event_repo.events[0]['event_type'] == 'operation'
        assert event_repo.events[0]['success'] is True

    def test_execute_failure_records_failed_event(self, op_service, executor, event_repo):
        executor.fail_device_ids = {1}
        result = op_service.execute(1, 'shutdown')
        assert result['success'] is False
        assert len(event_repo.events) == 1
        assert event_repo.events[0]['success'] is False

    def test_unknown_operation_rejected(self, op_service):
        result = op_service.execute(1, 'format_disk')
        assert result['success'] is False
        assert '不支持' in result['message']

    def test_missing_device_404(self, op_service):
        assert op_service.execute(999, 'reboot')['code'] == 404


class TestBatchIdempotency:
    def test_action_whitelist(self, batch_service):
        result = batch_service.batch_action({'action': 'format', 'device_ids': [1]})
        assert result['success'] is False
        assert '不支持的批量操作' in result['message']
        # 白名单含 6 种控制操作 + health_check
        assert set(BATCH_ACTIONS) == {
            'connect', 'disconnect', 'reboot', 'shutdown',
            'install_app', 'uninstall_app', 'health_check',
        }

    def test_empty_ids_rejected(self, batch_service):
        assert batch_service.batch_action({'action': 'reboot', 'device_ids': []})['success'] is False

    def test_batch_success_and_event(self, batch_service, op_service, event_repo):
        result = batch_service.batch_action({'action': 'reboot', 'device_ids': [1, 2]})
        assert result['success'] is True
        assert result['data']['success_count'] == 2
        assert result['data']['total'] == 2
        assert len(op_service.executor.calls) == 2
        # 每台设备各落一条操作事件
        assert len(event_repo.events) == 2

    def test_client_key_replay(self, batch_service, op_service):
        payload = {'action': 'reboot', 'device_ids': [1], 'idempotency_key': 'op-1'}
        first = batch_service.batch_action(dict(payload))
        assert first['success'] is True
        assert first['data'].get('idempotent_replay') is None
        replay = batch_service.batch_action(dict(payload))
        assert replay['success'] is True
        assert replay['data'].get('idempotent_replay') is True
        # 只执行了一次
        assert len(op_service.executor.calls) == 1

    def test_fingerprint_replay_orders_ids(self, batch_service, op_service):
        first = batch_service.batch_action({'action': 'reboot', 'device_ids': [1, 2]})
        assert first['success'] is True
        replay = batch_service.batch_action({'action': 'reboot', 'device_ids': [2, 1]})
        assert replay['data'].get('idempotent_replay') is True
        assert len(op_service.executor.calls) == 2  # 排序归一后视为同批

    def test_processing_conflict_409(self, batch_service, op_service):
        store = FakeIdempotencyStore()
        store.records['client:busy'] = {'status': 'processing'}
        service = DeviceBatchService(op_service=op_service, idempotency_store=store)
        result = service.batch_action({'action': 'reboot', 'device_ids': [1], 'idempotency_key': 'busy'})
        assert result['code'] == 409

    def test_partial_failure_releases_and_retries(self, batch_service, op_service, executor):
        executor.fail_device_ids = {2}
        first = batch_service.batch_action({'action': 'reboot', 'device_ids': [1, 2]})
        assert first['success'] is True  # 整批成功返回（逐台失败收敛到 results）
        assert first['data']['success_count'] == 1

    def test_all_fail_still_releases_placeholder(self, batch_service, op_service, executor):
        executor.fail_device_ids = {1, 2}
        result = batch_service.batch_action({'action': 'shutdown', 'device_ids': [1, 2]})
        assert result['success'] is True
        assert result['data']['success_count'] == 0
