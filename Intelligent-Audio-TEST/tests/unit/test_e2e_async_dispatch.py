# -*- coding: utf-8 -*-
"""E2E 异步派发（task_service，spec group-execution §9 阶段 B）。

覆盖「不同实验室并行」的派发口径：
- 可异步派发的行：物理 + 已绑定实验室 + 目标 mode 非 serial；
- 认领后提交线程池，主循环不阻塞（不就地抢锁/执行）；
- 执行阶段：SN 锁全成或全退、逐行收敛、执行异常不悬挂；
- 在途容量门控与线程池回收。
"""
import os
import threading

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from types import SimpleNamespace
from unittest.mock import MagicMock

from task_service.core.execution_engine.mixins.task_dispatch import TaskDispatchMixin
from task_service.core.execution_engine.mixins.e2e_async_dispatch import (
    E2EAsyncDispatchMixin,
)


class _Engine(TaskDispatchMixin, E2EAsyncDispatchMixin):
    def __init__(self):
        self.logs = []
        self.refresh_task_counts_atomic = MagicMock()
        self._emit_progress = MagicMock()
        self.e2e_dispatch_lock = threading.Lock()
        self.e2e_dispatch_pools = {}
        self.e2e_dispatch_inflight = {}
        self.e2e_dispatch_user_ids = {}

    def _log(self, **kwargs):
        self.logs.append(kwargs)


def _row(row_id=101, device_id=5, case_id='c1', device_type='physical',
         execution_status='pending'):
    return SimpleNamespace(
        id=row_id, device_id=device_id, test_case_id=case_id,
        device_type=device_type, execution_status=execution_status,
        evaluation_status='pending', error_message=None,
        started_at=None, completed_at=None, duration=None, status=None,
    )


def _lock():
    lock = MagicMock()
    return lock


def _session(rows_by_id):
    session = MagicMock()
    session.get.side_effect = lambda model, pk: (
        rows_by_id.get(pk) if model.__name__ == 'TaskCase' else None
    )
    return session


def _host():
    eng = _Engine()
    eng._check_e2e_devices = MagicMock(return_value=(True, None))
    eng._handle_device_check_failed = MagicMock()
    eng._execute_e2e_case = MagicMock(return_value=True)
    eng._handle_physical_lock_busy = MagicMock()
    eng._handle_e2e_failure = MagicMock()
    eng._resolve_physical_lock_key = MagicMock(
        side_effect=lambda task_id, device_id: f'sn-{device_id}')
    eng._acquire_physical_device_lock = MagicMock(return_value=_lock())
    return eng


class TestAsyncDispatchSelection:

    def _engine(self, lab_id=38, mode='parallel', device_type='physical', device_id=5):
        eng = _host()
        eng._device_fingerprint = MagicMock(return_value={'lab_id': lab_id, 'serial_number': 'sn'})
        eng._target_mode = MagicMock(return_value=mode)
        return eng, _row(device_type=device_type, device_id=device_id)

    def test_parallel_row_in_lab_is_async(self):
        eng, row = self._engine()
        assert eng._is_async_dispatch_row(7, MagicMock(), row) is True

    def test_serial_target_stays_sync(self):
        eng, row = self._engine(mode='serial')
        assert eng._is_async_dispatch_row(7, MagicMock(), row) is False

    def test_unbound_lab_stays_sync(self):
        eng, row = self._engine(lab_id=None)
        assert eng._is_async_dispatch_row(7, MagicMock(), row) is False

    def test_api_row_not_async(self):
        eng, row = self._engine(device_type='http_api')
        assert eng._is_async_dispatch_row(7, MagicMock(), row) is False

    def test_row_without_device_not_async(self):
        eng, row = self._engine(device_id=None)
        assert eng._is_async_dispatch_row(7, MagicMock(), row) is False


class TestAsyncDispatchSubmit:

    def test_single_row_claimed_then_submitted(self):
        """单行：主线程只做原子认领，执行阶段交给线程池（不就地抢锁/执行）。"""
        eng = _host()
        eng._build_e2e_execution_group = MagicMock(return_value=[])
        eng._claim_case = MagicMock(return_value=1)
        eng._submit_e2e_execution = MagicMock()
        row = _row()
        session = MagicMock()

        eng._dispatch_e2e_case(7, SimpleNamespace(id=7), row, session,
                               async_dispatch=True)

        session.commit.assert_called()
        eng._submit_e2e_execution.assert_called_once_with(7, [101], [5])
        eng._execute_e2e_case.assert_not_called()
        eng._acquire_physical_device_lock.assert_not_called()

    def test_group_claimed_then_submitted_once(self):
        """组：一次提交覆盖组内全部行与设备（组内仍是一次 StartE2ETask）。"""
        eng = _host()
        eng._claim_case_group = MagicMock(return_value=2)
        eng._submit_e2e_execution = MagicMock()
        rows = [_row(101, 1), _row(102, 2)]
        session = MagicMock()

        eng._dispatch_e2e_group(7, SimpleNamespace(id=7), rows, session,
                                async_dispatch=True)

        eng._submit_e2e_execution.assert_called_once_with(7, [101, 102], [1, 2])
        eng._execute_e2e_case.assert_not_called()

    def test_submit_failure_falls_back_to_inline(self):
        """线程池提交失败（行已认领）→ 回退就地执行，不丢用例。"""
        eng = _host()
        eng._get_e2e_dispatch_pool = MagicMock(side_effect=RuntimeError('pool down'))
        eng._run_e2e_execution = MagicMock()

        eng._submit_e2e_execution(7, [101], [5])

        eng._run_e2e_execution.assert_called_once_with(7, [101], [5])
        assert eng._e2e_dispatch_inflight_count(7) == 0


class TestRunExecutionStage:

    def test_locks_all_acquired_then_single_execute_and_release(self):
        eng = _host()
        locks = [_lock(), _lock()]
        eng._acquire_physical_lock_by_sn = MagicMock(side_effect=locks)
        rows = {101: _row(101, 1), 102: _row(102, 2)}
        session = _session(rows)

        success = eng._run_e2e_execution(7, [101, 102], [1, 2], session=session)

        assert success is True
        eng._execute_e2e_case.assert_called_once_with(7, 101, device_ids=[1, 2])
        assert [c.args[0] for c in eng._acquire_physical_lock_by_sn.call_args_list] == \
            ['sn-1', 'sn-2']
        for lock in locks:
            lock.release.assert_called_once()
        eng._handle_e2e_failure.assert_not_called()

    def test_single_row_uses_device_id_path(self):
        eng = _host()
        eng._acquire_physical_lock_by_sn = MagicMock(return_value=_lock())
        session = _session({101: _row(101, 5)})

        eng._run_e2e_execution(7, [101], [5], session=session)

        eng._execute_e2e_case.assert_called_once_with(7, 101, device_id=5)

    def test_lock_busy_releases_held_and_fails_rows(self):
        """任一 SN 锁被占用 → 已持有的锁全部释放，逐行按占用收敛，不执行。"""
        eng = _host()
        held = _lock()
        eng._acquire_physical_lock_by_sn = MagicMock(side_effect=[held, None])
        session = _session({101: _row(101, 1), 102: _row(102, 2)})

        eng._run_e2e_execution(7, [101, 102], [1, 2], session=session)

        eng._execute_e2e_case.assert_not_called()
        assert eng._handle_physical_lock_busy.call_count == 2
        held.release.assert_called_once()

    def test_execution_exception_converges_rows_as_failed(self):
        """执行抛异常 → 行收敛失败并带异常文案，锁仍释放（不悬挂）。"""
        eng = _host()
        lock = _lock()
        eng._acquire_physical_lock_by_sn = MagicMock(return_value=lock)
        eng._execute_e2e_case = MagicMock(side_effect=RuntimeError('grpc down'))
        row = _row(101, 5)
        session = _session({101: row})

        eng._run_e2e_execution(7, [101], [5], session=session)

        eng._handle_e2e_failure.assert_called_once()
        assert 'grpc down' in row.error_message
        lock.release.assert_called_once()
        session.commit.assert_called()


class TestDispatchCapacity:

    def test_returns_immediately_when_below_limit(self):
        eng = _host()
        eng.e2e_dispatch_inflight[7] = 1
        assert eng._await_e2e_dispatch_capacity(7) is True

    def test_waits_then_aborts_on_stop(self):
        eng = _host()
        eng._e2e_dispatch_worker_count = MagicMock(return_value=1)
        eng.e2e_dispatch_inflight[7] = 1
        stop_event = threading.Event()
        stop_event.set()

        assert eng._await_e2e_dispatch_capacity(7, stop_event) is False

    def test_drain_waits_and_reclaims_pool(self):
        eng = _host()
        pool = MagicMock()
        eng.e2e_dispatch_pools[7] = pool
        eng._drain_e2e_dispatch(7)
        pool.shutdown.assert_called_once_with(wait=False)
        assert 7 not in eng.e2e_dispatch_pools
