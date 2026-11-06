# -*- coding: utf-8 -*-
"""E2E 组派发（task_service）：批量认领、SN 锁全成或全退、行删除跳过收敛。

规格：specs/group-execution/spec.md
组执行语义 = 同实验室、同用例、不同 SN 的多条物理行合并为一次
StartE2ETask(device_ids)，音频每轮只播一次；组内逐行收敛状态。
"""
import os

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from types import SimpleNamespace
from unittest.mock import MagicMock

from task_service.core.execution_engine.mixins.task_dispatch import TaskDispatchMixin
from task_service.core.execution_engine.mixins.e2e_async_dispatch import E2EAsyncDispatchMixin


class _Engine(TaskDispatchMixin, E2EAsyncDispatchMixin):
    def __init__(self):
        self.logs = []
        self.refresh_task_counts_atomic = MagicMock()
        self._emit_progress = MagicMock()

    def _log(self, **kwargs):
        self.logs.append(kwargs)


def _row(row_id, device_id, case_id='c1'):
    return SimpleNamespace(
        id=row_id, device_id=device_id, test_case_id=case_id,
        device_type='physical', execution_status='pending',
    )


def _host():
    eng = _Engine()
    eng._check_e2e_devices = MagicMock(return_value=(True, None))
    eng._handle_device_check_failed = MagicMock()
    eng._execute_e2e_case = MagicMock(return_value=True)
    eng._handle_physical_lock_busy = MagicMock()
    eng._handle_e2e_failure = MagicMock()
    eng._claim_case_group = MagicMock(return_value=2)
    eng._dispatch_e2e_case = MagicMock()
    eng._resolve_physical_lock_key = MagicMock(
        side_effect=lambda task_id, device_id: f'sn-{device_id}')
    return eng


def _session(rows_by_id):
    session = MagicMock()
    session.get.side_effect = lambda model, row_id: rows_by_id.get(row_id)
    session.query.return_value.filter.return_value.update.return_value = 2
    return session


def _lock():
    lock = MagicMock()
    lock.release = MagicMock()
    return lock


class TestGroupDispatchLocks:

    def test_all_sn_locks_acquired_then_single_execute(self):
        """组内 SN 锁全部抢到 → 只调用一次执行，device_ids 覆盖组内全部设备。"""
        eng = _host()
        locks = [_lock(), _lock()]
        eng._acquire_physical_lock_by_sn = MagicMock(side_effect=locks)
        rows = [_row(101, 1), _row(102, 2)]
        session = _session({101: rows[0], 102: rows[1]})

        eng._dispatch_e2e_group(7, SimpleNamespace(id=7), rows, session)

        eng._execute_e2e_case.assert_called_once_with(7, 101, device_ids=[1, 2])
        # 锁键排序后逐把加锁（多组交叉不死锁）
        assert [c.args[0] for c in eng._acquire_physical_lock_by_sn.call_args_list] == \
            ['sn-1', 'sn-2']
        for lock in locks:
            lock.release.assert_called_once()
        # 成功不收敛失败
        eng._handle_e2e_failure.assert_not_called()

    def test_lock_busy_fails_whole_group(self):
        """任意一台设备的 SN 锁被占用 → 整组不执行，组内逐行收敛失败。"""
        eng = _host()
        held, busy = _lock(), None
        eng._acquire_physical_lock_by_sn = MagicMock(side_effect=[held, busy])
        rows = [_row(101, 1), _row(102, 2)]
        session = _session({101: rows[0], 102: rows[1]})

        eng._dispatch_e2e_group(7, SimpleNamespace(id=7), rows, session)

        eng._execute_e2e_case.assert_not_called()
        assert eng._handle_physical_lock_busy.call_count == 2
        held.release.assert_called_once()

    def test_claim_conflict_falls_back_to_single_row(self):
        """组内有行被并发认领（占用数 < 组大小）→ 回滚并退回单行派发。"""
        eng = _host()
        eng._claim_case_group = MagicMock(return_value=1)
        rows = [_row(101, 1), _row(102, 2)]
        session = _session({101: rows[0], 102: rows[1]})

        eng._dispatch_e2e_group(7, SimpleNamespace(id=7), rows, session)

        session.rollback.assert_called_once()
        eng._dispatch_e2e_case.assert_called_once_with(
            7, SimpleNamespace(id=7), rows[0], session, async_dispatch=False)
        eng._execute_e2e_case.assert_not_called()

    def test_deleted_row_skips_convergence(self):
        """执行期间组内行被删除 → 跳过该行收敛，其余行照常收敛。"""
        eng = _host()
        eng._execute_e2e_case = MagicMock(return_value=False)
        eng._acquire_physical_lock_by_sn = MagicMock(side_effect=[_lock(), _lock()])
        rows = [_row(101, 1), _row(102, 2)]
        session = _session({101: rows[0], 102: None})

        eng._dispatch_e2e_group(7, SimpleNamespace(id=7), rows, session)

        eng._handle_e2e_failure.assert_called_once()
        assert eng._handle_e2e_failure.call_args.args[1].id == 101
