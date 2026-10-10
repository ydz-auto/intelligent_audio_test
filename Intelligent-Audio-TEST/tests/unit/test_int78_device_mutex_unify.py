# -*- coding: utf-8 -*-
"""INT-78 专项：物理设备互斥全链路统一 DistributedLock（UC-0903 4a / UC-1001 5b）。

覆盖：
- audio_driver：per-device 进程内互斥 dict（_device_locks/_get_device_lock）移除，
  流 open/close 句柄护栏收敛为进程内单锁（仅句柄线程安全，非设备占用互斥）
- e2e_device_manager.initialize_devices：results_lock 仅为并行结果收集线程安全，
  非 设备互斥；并行初始化结果完整收集（回归锁定改名后行为不变）
- task_dispatch busy 收敛（UC-1001 5b）：等锁窗口用例保持 QUEUED、无执行事件；
  抢占失败收敛时同步任务统计并发布告警/进度事件，且 RUNNING 从不在 task_service
  侧置位（由 e2e_test_service 拿锁开始执行后才置位，无"假运行中"）
- 设备占用互斥唯一入口：task_dispatch 派发层 DistributedLock
  （RedisKeyPrefix.TASK_PHYSICAL_LOCK，INT-80 接线，此处回归锁定）
"""
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import task_service.core.execution_engine.mixins.task_dispatch as _td  # noqa: F401
from task_service.core.execution_engine.mixins.task_dispatch import TaskDispatchMixin
from shared.utils.status_constants import TaskCaseStatus


# --------------------------------------------------------------------------- #
#  audio_driver：per-device 进程内互斥移除                                     #
# --------------------------------------------------------------------------- #

@pytest.fixture
def driver_env(monkeypatch):
    """提供可实例化的 PyAudioDriver（桩 pyaudio/pydub/storage，同 test_path_b 口径）。"""
    import importlib
    import sys
    import types
    from unittest import mock

    stubs = {}
    pa = types.ModuleType("pyaudio")
    pa.PyAudio = lambda: mock.MagicMock()
    for cn in ("paInt16", "paFloat32", "paInt32", "paComplete", "paContinue"):
        setattr(pa, cn, 0)
    stubs["pyaudio"] = pa

    pd = types.ModuleType("pydub")

    class _AS:
        @staticmethod
        def from_file(*a, **k):
            raise RuntimeError("pydub stub")
    pd.AudioSegment = _AS
    stubs["pydub"] = pd

    st = types.ModuleType("shared.infrastructure.storage")

    class _S:
        def load_file(self, key):
            raise AssertionError("结构断言不应触发 storage.load_file")
    st.storage = _S()
    stubs["shared.infrastructure.storage"] = st

    for name in ("numpy", "scipy", "scipy.signal"):
        try:
            stubs[name] = importlib.import_module(name)
        except Exception:
            stubs[name] = types.ModuleType(name)

    sys.modules.pop("audio_service.infrastructure.audio.audio_driver", None)
    with mock.patch.dict(sys.modules, stubs, clear=False):
        drv_mod = importlib.import_module("audio_service.infrastructure.audio.audio_driver")
        with mock.patch.object(drv_mod, "log_and_emit", lambda *a, **k: None):
            drv = drv_mod.PyAudioDriver()
            yield drv_mod, drv
    sys.modules.pop("audio_service.infrastructure.audio.audio_driver", None)


class TestAudioDriverMutexRemoved:
    def test_per_device_mutex_dict_removed(self, driver_env):
        _, drv = driver_env
        assert not hasattr(drv, '_device_locks')
        assert not hasattr(drv, '_device_locks_lock')
        assert not hasattr(drv, '_get_device_lock')

    def test_stream_lifecycle_lock_is_working_lock(self, driver_env):
        _, drv = driver_env
        lock = drv._stream_lifecycle_lock
        assert lock.acquire(blocking=False) is True
        lock.release()
        # 串行语义：持有期间他人非阻塞获取失败
        with lock:
            assert lock.acquire(blocking=False) is False


# --------------------------------------------------------------------------- #
#  e2e_device_manager：results_lock 仅为结果收集线程安全                        #
# --------------------------------------------------------------------------- #

class TestInitializeDevicesResultsLock:
    def _manager(self):
        from e2e_test_service.application.services.e2e_device_manager import E2EDeviceManager
        mgr = E2EDeviceManager.__new__(E2EDeviceManager)
        mgr._executor = SimpleNamespace(
            _log=MagicMock(),
            execution_engine=SimpleNamespace(device_control_pool=ThreadPoolExecutor(max_workers=2)),
        )
        mgr._device_repo = MagicMock()
        mgr._device_repo.create_driver.return_value = True
        return mgr

    def test_parallel_results_fully_collected(self):
        mgr = self._manager()
        infos = [
            {'device_name': f'd{i}', 'system': 'android', 'keywords': [], 'device_sn': f'sn{i}'}
            for i in range(4)
        ]
        mgr.initialize_devices(infos, task_id=9, test_case_id='c1')
        assert mgr._device_repo.create_driver.call_count == 4

    def test_failed_init_raises_with_all_results(self):
        mgr = self._manager()
        infos = [
            {'device_name': 'd_ok', 'system': 'android', 'keywords': [], 'device_sn': 'sn_ok'},
            {'device_name': 'd_bad', 'system': 'android', 'keywords': [], 'device_sn': 'sn_bad'},
        ]
        mgr._device_repo.create_driver.side_effect = [True, False]
        with pytest.raises(RuntimeError, match='d_bad'):
            mgr.initialize_devices(infos, task_id=9, test_case_id='c1')


# --------------------------------------------------------------------------- #
#  task_dispatch：UC-1001 5b 等锁窗口/收敛可观测                                #
# --------------------------------------------------------------------------- #

def _engine(device_id=5, tc_rel_id=101):
    engine = TaskDispatchMixin.__new__(TaskDispatchMixin)
    engine.task_id = 9
    engine._log = MagicMock()
    engine._emit_alert = MagicMock()
    engine._emit_progress = MagicMock()
    engine._count_cases_by_status = MagicMock(return_value=0)
    engine.tc_rel = SimpleNamespace(
        id=tc_rel_id, device_id=device_id, execution_status='queued',
        evaluation_status='pending', error_message=None,
        started_at=None, completed_at=None,
    )
    return engine


class TestBusyObservableConvergence:
    def _run_busy(self, engine, row, task_row):
        session = MagicMock()
        session.get.side_effect = lambda model, pk: (
            row if model.__name__ == 'TaskCase' else task_row
        )
        with patch('shared.models.database.create_db_session', return_value=session), \
             patch('shared.utils.status_utils.derive_task_case_status',
                   side_effect=lambda exec_status, eval_status: 'failed'):
            engine._handle_physical_lock_busy(9, engine.tc_rel)
        return session

    def test_busy_syncs_task_stats_and_emits_alert_progress(self):
        engine = _engine(device_id=5)
        row = SimpleNamespace(id=101, execution_status='queued', evaluation_status='pending',
                              started_at=None, completed_at=None, error_message=None)
        task_row = SimpleNamespace(id=9, completed_cases=0, failed_cases=0)
        session = self._run_busy(engine, row, task_row)

        engine._count_cases_by_status.assert_any_call(9, session, TaskCaseStatus.COMPLETED)
        engine._count_cases_by_status.assert_any_call(9, session, TaskCaseStatus.FAILED, use_filter_by=True)
        assert task_row.completed_cases == 0
        assert task_row.failed_cases == 0
        assert engine._emit_alert.call_count == 1
        alert_args = engine._emit_alert.call_args[0]
        assert alert_args[0] == 9 and '占用' in alert_args[1]
        assert engine._emit_progress.call_count == 1
        assert engine._emit_progress.call_args[0][0] is task_row

    def test_busy_converges_queued_to_failed_directly(self):
        # UC-1001 5b：排队中（QUEUED）被占用收敛直接置 FAILED，
        # task_service 侧从不置 RUNNING（RUNNING 仅由 e2e 拿锁执行后置位）
        engine = _engine(device_id=5)
        row = SimpleNamespace(id=101, execution_status='queued', evaluation_status='pending',
                              started_at=None, completed_at=None, error_message=None)
        self._run_busy(engine, row, SimpleNamespace(id=9))
        assert row.execution_status == 'failed'
        assert row.started_at is not None
        assert row.completed_at is not None

    def test_busy_without_task_row_still_converges_case(self):
        # 任务行缺失（异常清理后）不阻塞用例收敛，也不误发任务级事件
        engine = _engine(device_id=5)
        row = SimpleNamespace(id=101, execution_status='queued', evaluation_status='pending',
                              started_at=None, completed_at=None, error_message=None)
        session = self._run_busy(engine, row, None)
        assert row.execution_status == 'failed'
        session.commit.assert_called()
        engine._emit_alert.assert_not_called()
        engine._emit_progress.assert_not_called()


class TestDeviceMutexSingleEntryPoint:
    def test_dispatch_lock_uses_physical_prefix(self):
        # 设备占用互斥唯一入口：task_dispatch 派发层
        # DistributedLock(RedisKeyPrefix.TASK_PHYSICAL_LOCK:{device_id})
        import inspect
        source = inspect.getsource(TaskDispatchMixin._acquire_physical_device_lock)
        assert 'RedisKeyPrefix.TASK_PHYSICAL_LOCK' in source
        assert 'DistributedLock' in source
        assert 'ttl=' in source
