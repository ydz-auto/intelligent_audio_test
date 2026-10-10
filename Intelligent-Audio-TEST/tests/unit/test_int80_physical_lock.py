# -*- coding: utf-8 -*-
"""INT-80 专项：物理设备互斥锁接线（lock:task:physical:{device_id}）。

覆盖（02_架构设计.md 预留项落地）：
- _acquire_physical_device_lock：无绑定设备放行（NoOp）、正常构造
  DistributedLock（key 前缀 RedisKeyPrefix.TASK_PHYSICAL_LOCK）并成功抢占
- 抢占失败（设备被占用）→ _handle_physical_lock_busy 将用例置失败收敛
- _dispatch_e2e_case：执行完成后释放锁（finally 语义，异常路径同样释放）
"""
import os

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import task_service.core.execution_engine.mixins.task_dispatch as _td
from task_service.core.execution_engine.mixins.task_dispatch import TaskDispatchMixin
from shared.models.common_enums import RedisKeyPrefix


def _engine(device_id=5, tc_rel_id=101):
    engine = TaskDispatchMixin.__new__(TaskDispatchMixin)
    engine.task_id = 9
    engine._log = MagicMock()  # _log 定义在 ProgressMixin，独立实例测试中打桩
    engine.tc_rel = SimpleNamespace(
        id=tc_rel_id, device_id=device_id, execution_status='queued',
        evaluation_status='pending', error_message=None,
        started_at=None, completed_at=None,
    )
    return engine


class FakeLock:
    def __init__(self, key, acquired=True):
        self.key = key
        self.acquired = acquired
        self.released = False

    def acquire(self, blocking=True):
        return self.acquired

    def release(self):
        self.released = True


class TestAcquirePhysicalLock:
    def test_no_device_binding_returns_noop(self):
        engine = _engine(device_id=None)
        lock = engine._acquire_physical_device_lock(9, engine.tc_rel)
        assert lock is not None
        lock.release()  # NoOp 不抛异常

    @patch('shared.utils.distributed_coordinator.DistributedLock')
    def test_lock_key_and_ttl(self, lock_cls):
        from shared.infrastructure.config import BaseConfig
        lock_cls.return_value = FakeLock('k')
        engine = _engine(device_id=5)
        handle = engine._acquire_physical_device_lock(9, engine.tc_rel)
        assert handle is lock_cls.return_value
        args, kwargs = lock_cls.call_args
        expected_key = f'{RedisKeyPrefix.TASK_PHYSICAL_LOCK.value}:5'
        assert args[0] == expected_key
        # TTL 覆盖 StartE2ETask 同步执行上限 + 余量
        assert kwargs['ttl'] >= int(getattr(BaseConfig, 'GRPC_E2E_SYNC_TIMEOUT_SECONDS', 600))

    @patch('shared.utils.distributed_coordinator.DistributedLock')
    def test_busy_device_returns_none(self, lock_cls):
        lock_cls.return_value = FakeLock('k', acquired=False)
        engine = _engine(device_id=5)
        assert engine._acquire_physical_device_lock(9, engine.tc_rel) is None


class TestBusyConvergence:
    def test_busy_marks_case_failed(self):
        engine = _engine(device_id=5)
        session = MagicMock()
        row = SimpleNamespace(id=101, execution_status='queued', evaluation_status='pending',
                              started_at=None, completed_at=None, error_message=None)
        session.get.return_value = row
        with patch('shared.models.database.create_db_session', return_value=session), \
             patch('shared.utils.status_utils.derive_task_case_status',
                   side_effect=lambda exec_status, eval_status: 'failed'):
            engine._handle_physical_lock_busy(9, engine.tc_rel)
        assert row.execution_status == 'failed'
        assert '占用' in row.error_message
        session.commit.assert_called()
        session.close.assert_called()

    def test_busy_skips_terminal_case(self):
        engine = _engine(device_id=5)
        session = MagicMock()
        row = SimpleNamespace(id=101, execution_status='failed', evaluation_status='pending',
                              started_at=None, completed_at=None, error_message=None)
        session.get.return_value = row
        with patch('shared.models.database.create_db_session', return_value=session):
            engine._handle_physical_lock_busy(9, engine.tc_rel)
        # 终态用例不改写，避免覆盖真实执行结果
        assert row.execution_status == 'failed'
        assert row.completed_at is None
        session.commit.assert_not_called()


class TestDispatchReleaseLock:
    def test_lock_released_after_execution(self):
        engine = _engine(device_id=5)
        lock = FakeLock('k')
        session = MagicMock()
        session.get.return_value = SimpleNamespace(id=101)
        engine._claim_case = MagicMock(return_value=1)
        engine._acquire_physical_device_lock = MagicMock(return_value=lock)
        engine._execute_e2e_case = MagicMock(return_value=True)
        engine._count_cases_by_status = MagicMock(return_value=0)
        engine._handle_e2e_failure = MagicMock()
        engine._dispatch_e2e_case(9, SimpleNamespace(completed_cases=0, failed_cases=0),
                                  engine.tc_rel, session)
        assert lock.released is True
        engine._handle_e2e_failure.assert_not_called()

    def test_lock_released_on_execution_exception(self):
        engine = _engine(device_id=5)
        lock = FakeLock('k')
        session = MagicMock()
        engine._claim_case = MagicMock(return_value=1)
        engine._acquire_physical_device_lock = MagicMock(return_value=lock)
        engine._execute_e2e_case = MagicMock(side_effect=RuntimeError('boom'))
        with pytest.raises(RuntimeError):
            engine._dispatch_e2e_case(9, SimpleNamespace(completed_cases=0, failed_cases=0),
                                      engine.tc_rel, session)
        assert lock.released is True
