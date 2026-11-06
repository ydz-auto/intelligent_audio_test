# -*- coding: utf-8 -*-
"""INT-133 守卫：task_service 事件/进度链对遗留任务键的防御与收敛。

原缺陷：事件总线推送 task_id 字面值为 'task-1' 的用例/任务事件（外部进程经
共享 Redis 发布，如复验期 pytest 直连总线）时，引擎事件处理器 int() 失败被
静默 pass 后继续以 'task-1' 调 _emit_progress，emit_progress 内 int() 再抛
ValueError → ERROR + re-raise → 调用方 WARNING，每 5-7 分钟爆发刷屏；同时
对不存在任务键（1/2）的周期性进度推送每次都打 WARNING 并完整走一遍
gRPC+DB 查询，空闲期 ~34 行/5min 违反洪泛阈值（<20 行/5min/同一 logger）。

修复语义（本文件覆盖，纯单测不触真实 DB/gRPC/Redis）：
- 引擎侧：事件 task_id 非整型 → 一次性 DEBUG 丢弃，不进入进度推送链；
- 进度链入口：task_id 非整型 → DEBUG 丢弃且不再向上抛断调用方；
- 不存在任务：首个周期 WARNING 留痕一次，抑制窗口内静默跳过（不查库
  不记日志），窗口过期放行一轮重新核实；任务重新出现时摘除登记；
- 抑制登记内存上界：超限淘汰最早登记条目。
"""
import os
import threading
import time
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

# BaseConfig 在 import 时校验环境变量（本用例纯单测不触库，与仓库既有测试同款兜底）
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from shared.utils.event_manager import EventManager
from shared.utils.event_manager._progress import (
    MISSING_TASK_MAX_ENTRIES,
    MISSING_TASK_SUPPRESS_SECONDS,
)
from task_service.core.execution_engine import ExecutionEngine

_PROGRESS_MOD = 'shared.utils.event_manager._progress'


def _engine_stub():
    """与 ExecutionEngine 事件处理器依赖同构的最小桩。"""
    stub = SimpleNamespace(task_completion_events={})
    stub.emitted = []
    stub.scheduler_checks = []
    stub.refreshed = []
    stub._emit_progress = lambda task, force=False: stub.emitted.append((task, force))
    stub.trigger_scheduler_check = lambda: stub.scheduler_checks.append(True)
    # INT-161：_on_case_event 在用例事件侧原子刷新任务行计数
    stub.refresh_task_counts_atomic = lambda task_id: stub.refreshed.append(task_id)
    return stub


def _make_em():
    """EventManager 实例：日志收集到内存，隔离外部查询。"""
    em = EventManager(None)
    em.logs = []

    def _record(level, content, task_id=None, **kwargs):
        em.logs.append((level, content))

    em._log = _record
    return em


class TestEngineEventTaskIdDiscard:
    """引擎事件处理器：非整型 task_id 一次性丢弃（INT-133 期望 1）。"""

    def test_case_event_non_int_task_id_discarded(self):
        stub = _engine_stub()
        ExecutionEngine._on_case_event(stub, {'task_id': 'task-1', 'success': False})
        assert stub.emitted == []
        assert stub.scheduler_checks == []

    def test_task_event_non_int_task_id_discarded(self):
        stub = _engine_stub()
        ExecutionEngine._on_task_event(stub, {'task_id': 'task-1', 'status': 'failed'})
        assert stub.emitted == []

    def test_case_event_numeric_str_still_processed(self):
        """回归守卫：合法数字串（事件序列化常态）不受丢弃影响。"""
        stub = _engine_stub()
        completion = threading.Event()
        stub.task_completion_events[5] = completion
        ExecutionEngine._on_case_event(stub, {'task_id': '5'})
        assert stub.emitted == [(5, True)]
        assert completion.is_set()
        assert stub.scheduler_checks == [True]


class TestEmitProgressNonIntDiscard:
    """进度链入口：非整型 task_id DEBUG 丢弃，不再向上抛（INT-133 期望 1）。"""

    def test_non_int_task_id_dropped_without_error(self):
        em = _make_em()
        with patch(f'{_PROGRESS_MOD}.get_task_progress_via_grpc') as grpc_mock:
            em.emit_progress('task-1', force=True)
        grpc_mock.assert_not_called()
        assert em._missing_tasks == {}
        levels = [level for level, _ in em.logs]
        assert 'ERROR' not in levels
        assert 'WARNING' not in levels

    def test_non_int_task_id_does_not_raise(self):
        """原缺陷路径：int('task-1') ValueError 沿 emit_progress → 调用方传播。"""
        em = _make_em()
        try:
            em.emit_progress('task-1', force=True)
        except ValueError:
            raise AssertionError("非整型 task_id 不应再向上抛 ValueError")


class TestMissingTaskSuppression:
    """不存在任务：WARNING 留痕一次 + 抑制窗口内静默（INT-133 期望 2）。"""

    def _patch_query_paths(self, grpc_mock=None):
        grpc_patcher = patch(f'{_PROGRESS_MOD}.get_task_progress_via_grpc',
                             grpc_mock or MagicMock(return_value=None))
        db_patcher = patch(f'{_PROGRESS_MOD}.get_db_session', MagicMock())
        return grpc_patcher, db_patcher

    def test_first_push_warns_once_then_suppressed(self):
        em = _make_em()
        grpc_patcher, db_patcher = self._patch_query_paths()
        with grpc_patcher as grpc_mock, db_patcher:
            em._build_progress_from_po = lambda *a, **k: (None, None)
            em.emit_progress(1, force=True)   # 首推：WARNING 留痕
            em.emit_progress(1, force=True)   # 窗口内：静默
            em.emit_progress('1', force=True) # 同键异型：同表键 '1'，静默
        warnings = [log for log in em.logs if log[0] == 'WARNING']
        assert len(warnings) == 1
        assert '1' in em._missing_tasks
        # 抑制期内不重复查询（收敛：非无限重试）
        assert grpc_mock.call_count == 1

    def test_suppression_window_expiry_reverifies(self):
        em = _make_em()
        em._missing_tasks['1'] = time.time() - MISSING_TASK_SUPPRESS_SECONDS - 1
        grpc_patcher, db_patcher = self._patch_query_paths()
        with grpc_patcher, db_patcher:
            em._build_progress_from_po = lambda *a, **k: (None, None)
            em.emit_progress(1, force=True)  # 窗口过期 → 放行重新核实 → 仍不存在
        warnings = [log for log in em.logs if log[0] == 'WARNING']
        assert len(warnings) == 1
        assert '1' in em._missing_tasks  # 重新登记（续期）

    def test_task_found_again_clears_registration(self):
        """窗口过期后的重新核实若任务已出现：摘除登记并正常推送。

        （抑制窗口内不查库——DB 返回「不存在」是确定结论而非瞬时故障，
        登记只在窗口过期重核实 / 成功路径被摘除。）
        """
        em = _make_em()
        em._missing_tasks['7'] = time.time() - MISSING_TASK_SUPPRESS_SECONDS - 1
        grpc_progress = {'status': 'running', 'total_cases': 1, 'completed_cases': 0}
        with patch(f'{_PROGRESS_MOD}.get_task_progress_via_grpc',
                   MagicMock(return_value=grpc_progress)):
            em._build_progress_from_grpc = lambda *a, **k: (SimpleNamespace(), None)
            em._finalize_and_emit = lambda **k: None
            em.emit_progress(7, force=True)
        assert '7' not in em._missing_tasks

    def test_po_found_again_clears_registration(self):
        em = _make_em()
        em._missing_tasks['7'] = time.time() - MISSING_TASK_SUPPRESS_SECONDS - 1
        grpc_patcher, db_patcher = self._patch_query_paths()
        with grpc_patcher, db_patcher:
            em._build_progress_from_po = lambda *a, **k: (SimpleNamespace(), None)
            em._finalize_and_emit = lambda **k: None
            em.emit_progress(7, force=True)
        assert '7' not in em._missing_tasks

    def test_registration_memory_cap(self):
        """抑制登记上界：超限淘汰最早条目，防异常键无限堆积。"""
        em = _make_em()
        for i in range(MISSING_TASK_MAX_ENTRIES):
            em._missing_tasks[f'k{i}'] = i
        grpc_patcher, db_patcher = self._patch_query_paths()
        with grpc_patcher, db_patcher:
            em._build_progress_from_po = lambda *a, **k: (None, None)
            em.emit_progress(999999, force=True)
        assert len(em._missing_tasks) <= MISSING_TASK_MAX_ENTRIES
        assert '999999' in em._missing_tasks
        assert 'k0' not in em._missing_tasks  # 最早登记被淘汰
