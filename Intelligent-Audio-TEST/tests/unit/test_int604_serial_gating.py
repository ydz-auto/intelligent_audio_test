# -*- coding: utf-8 -*-
"""INT-604 验收测试：serial 逐用例门控（task_dispatch 纯逻辑，不触真实 DB/gRPC）。

覆盖验收标准 2 的分发层语义（集成实测由 tests/integration 负责）：
- 新用例：serial_first=device 时设备侧行先派发；serial_first=api 时 API 侧行先派发；
- 单侧用例不受 serial_first 影响；
- 已开始用例：优先侧内部并行派发（同侧多行不互等）；
- 优先侧未全终态：另一侧不得派发（返回 None 等待）；
- 优先侧全终态后：另一侧最早 PENDING 行派发；
- 更早用例未全终态：后续用例一律不派发。
"""
import os
from types import SimpleNamespace

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from shared.utils.status_constants import (
    ExecutionStatus, EvaluationStatus, TaskCaseStatus,
)
from task_service.core.execution_engine.mixins.task_dispatch import TaskDispatchMixin
from task_service.infrastructure.persistence.models import TaskCase


class _Engine(TaskDispatchMixin):
    """与 ExecutionEngine 同构的最小组合（仅 TaskDispatchMixin）。"""

    def __init__(self, serial_first='device'):
        self.serial_first = serial_first
        self.logs = []

    def _log(self, **kwargs):
        self.logs.append(kwargs)

    def _is_serial_task(self, task_id, session):
        return True

    def _task_serial_first(self, task_id, session):
        return self.serial_first

    def _wait_active_cases_with_backoff(self, task_id, stop_event=None):
        self.logs.append({'level': 'WAIT', 'task_id': task_id})


def _case_row(case_id, device_type, device_id=None,
              exec_status=ExecutionStatus.PENDING,
              eval_status=EvaluationStatus.PENDING):
    """构造属性级 TaskCase 行（不入库）。"""
    from shared.utils.status_utils import derive_task_case_status
    tc = TaskCase()
    tc.id = f'{case_id}-{device_type}-{device_id or "none"}'
    tc.task_id = 1
    tc.test_case_id = case_id
    tc.device_type = device_type
    tc.device_id = device_id
    tc.execution_status = exec_status
    tc.evaluation_status = eval_status
    tc.status = derive_task_case_status(exec_status, eval_status)
    return tc


def _session_for_rows(rows):
    """构造返回指定行的假 session.query(TaskCase)。"""

    class _FakeQuery:
        def __init__(self, rows_):
            self._rows = rows_

        def filter(self, *a, **k):
            return self

        def order_by(self, *a, **k):
            return self

        def all(self):
            return self._rows

        def count(self):
            # 近似模拟 _handle_no_pending_case_serial 的 status.notin_(FINISHED) 过滤
            from shared.utils.status_constants import FINISHED_CASE_STATUSES
            return sum(1 for r in self._rows if (r.status or '') not in FINISHED_CASE_STATUSES)

    session = SimpleNamespace()
    session.close = lambda: None
    session.query = lambda model: _FakeQuery(rows)
    return session


class TestSerialPreferredSideFirst:
    def test_serial_first_device_returns_device_row_first(self):
        """serial_first=device：新用例先派发设备侧行。"""
        rows = [
            _case_row('case-1', 'http_api', '202', ),
            _case_row('case-1', 'physical', '101'),
        ]
        rows[0].created_at = 2
        rows[1].created_at = 1  # device 行 created_at 更晚也应优先（按优先侧取）
        got = _Engine('device')._get_next_pending_case(1, _session_for_rows(rows))
        assert got.device_type == 'physical'

    def test_serial_first_api_returns_api_row_first(self):
        rows = [
            _case_row('case-1', 'http_api', '202'),
            _case_row('case-1', 'physical', '101'),
        ]
        got = _Engine('api')._get_next_pending_case(1, _session_for_rows(rows))
        assert got.device_type == 'http_api'

    def test_single_side_case_ignores_serial_first(self):
        """单侧用例（仅 API 行）不受 serial_first 影响，直接派发。"""
        rows = [_case_row('case-1', 'http_api', '202')]
        got = _Engine('device')._get_next_pending_case(1, _session_for_rows(rows))
        assert got.device_type == 'http_api'


class TestSerialWithinSideParallel:
    def test_preferred_side_pending_rows_keep_dispatching(self):
        """已开始用例：优先侧仍有 PENDING 行时继续派发（同侧多行不互等）。"""
        dev_a = _case_row('case-1', 'physical', '101')
        dev_a.execution_status = ExecutionStatus.COMPLETED
        dev_a.evaluation_status = EvaluationStatus.COMPLETED
        dev_a.status = TaskCaseStatus.COMPLETED
        dev_b = _case_row('case-1', 'physical', '102')  # 优先侧仍 PENDING
        api = _case_row('case-1', 'http_api', '202')
        rows = [dev_a, dev_b, api]
        got = _Engine('device')._get_next_pending_case(1, _session_for_rows(rows))
        assert got.device_type == 'physical' and got.device_id == '102'

    def test_other_side_blocked_until_preferred_terminal(self):
        """优先侧未全终态（执行中/评估中）：另一侧 PENDING 行不得派发。"""
        dev_a = _case_row('case-1', 'physical', '101',
                          exec_status=ExecutionStatus.COMPLETED,
                          eval_status=EvaluationStatus.RUNNING)
        dev_a.status = TaskCaseStatus.EVALUATING
        api = _case_row('case-1', 'http_api', '202')  # 另一侧 PENDING
        rows = [dev_a, api]
        got = _Engine('device')._get_next_pending_case(1, _session_for_rows(rows))
        assert got is None

    def test_other_side_dispatched_after_preferred_terminal(self):
        """优先侧全终态后：另一侧最早 PENDING 行派发。"""
        dev_a = _case_row('case-1', 'physical', '101',
                          exec_status=ExecutionStatus.COMPLETED,
                          eval_status=EvaluationStatus.COMPLETED)
        dev_a.status = TaskCaseStatus.COMPLETED
        api = _case_row('case-1', 'http_api', '202')
        rows = [dev_a, api]
        got = _Engine('device')._get_next_pending_case(1, _session_for_rows(rows))
        assert got.device_type == 'http_api'


class TestSerialNextCaseGating:
    def test_later_case_blocked_while_earlier_case_active(self):
        """更早用例未全终态：后续用例一律不派发。"""
        case1_api = _case_row('case-1', 'http_api', '202',
                              exec_status=ExecutionStatus.RUNNING)
        case1_api.status = TaskCaseStatus.RUNNING
        case2_dev = _case_row('case-2', 'physical', '301')
        case2_api = _case_row('case-2', 'http_api', '302')
        rows = [case1_api, case2_dev, case2_api]
        got = _Engine('device')._get_next_pending_case(1, _session_for_rows(rows))
        assert got is None

    def test_next_case_started_after_earlier_case_terminal(self):
        """更早用例全终态后：下一用例按优先侧派发。"""
        case1_api = _case_row('case-1', 'http_api', '202',
                              exec_status=ExecutionStatus.COMPLETED,
                              eval_status=EvaluationStatus.COMPLETED)
        case1_api.status = TaskCaseStatus.COMPLETED
        case2_dev = _case_row('case-2', 'physical', '301')
        case2_api = _case_row('case-2', 'http_api', '302')
        rows = [case1_api, case2_dev, case2_api]
        got = _Engine('device')._get_next_pending_case(1, _session_for_rows(rows))
        assert got.device_type == 'physical' and got.device_id == '301'

    def test_mixed_case_completes_before_next_case(self):
        """上一用例两侧全终态 + 下一用例存在：按序推进。"""
        # 上一用例：设备侧已终态、API 侧已终态
        c1_dev = _case_row('case-1', 'physical', '101',
                           exec_status=ExecutionStatus.COMPLETED,
                           eval_status=EvaluationStatus.COMPLETED)
        c1_dev.status = TaskCaseStatus.COMPLETED
        c1_api = _case_row('case-1', 'http_api', '202',
                           exec_status=ExecutionStatus.COMPLETED,
                           eval_status=EvaluationStatus.COMPLETED)
        c1_api.status = TaskCaseStatus.COMPLETED
        # 下一用例：设备侧已部分完成（等待评估）——不得提前派发其 API 侧
        c2_dev = _case_row('case-2', 'physical', '301',
                           exec_status=ExecutionStatus.COMPLETED,
                           eval_status=EvaluationStatus.RUNNING)
        c2_dev.status = TaskCaseStatus.EVALUATING
        c2_api = _case_row('case-2', 'http_api', '302')
        rows = [c1_dev, c1_api, c2_dev, c2_api]
        got = _Engine('device')._get_next_pending_case(1, _session_for_rows(rows))
        assert got is None


class TestSerialNoPendingReturnsNone:
    def test_no_pending_rows_returns_none(self):
        rows = [
            _case_row('case-1', 'physical', '101',
                      exec_status=ExecutionStatus.COMPLETED,
                      eval_status=EvaluationStatus.COMPLETED),
        ]
        rows[0].status = TaskCaseStatus.COMPLETED
        got = _Engine('device')._get_next_pending_case(1, _session_for_rows(rows))
        assert got is None

    def test_all_cases_terminal_returns_none(self):
        c1 = _case_row('case-1', 'physical', '101',
                       exec_status=ExecutionStatus.COMPLETED,
                       eval_status=EvaluationStatus.COMPLETED)
        c1.status = TaskCaseStatus.COMPLETED
        c2 = _case_row('case-2', 'http_api', '202',
                       exec_status=ExecutionStatus.COMPLETED,
                       eval_status=EvaluationStatus.COMPLETED)
        c2.status = TaskCaseStatus.COMPLETED
        rows = [c1, c2]
        got = _Engine('device')._get_next_pending_case(1, _session_for_rows(rows))
        assert got is None


class TestSerialHandleNoPendingKeepsLoopAlive:
    """serial 主循环收口：仍有用例未全终态时 _handle_no_pending_case 返回 True 继续等。"""

    def _engine(self):
        return _Engine('device')

    def test_waits_while_evaluation_pending(self):
        """评估中（exec 已终态、eval 未终态）→ 继续等待（True），不退出主循环。"""
        c = _case_row('case-1', 'physical', '101',
                      exec_status=ExecutionStatus.COMPLETED,
                      eval_status=EvaluationStatus.RUNNING)
        c.status = TaskCaseStatus.EVALUATING
        eng = self._engine()
        ok = eng._handle_no_pending_case_serial(1, _session_for_rows([c]))
        assert ok is True
        assert any(x.get('level') == 'WAIT' for x in eng.logs)

    def test_exits_when_all_terminal(self):
        """全部用例终态 → 返回 False，主循环退出。"""
        c = _case_row('case-1', 'physical', '101',
                      exec_status=ExecutionStatus.COMPLETED,
                      eval_status=EvaluationStatus.COMPLETED)
        c.status = TaskCaseStatus.COMPLETED
        eng = self._engine()
        ok = eng._handle_no_pending_case_serial(1, _session_for_rows([c]))
        assert ok is False


class TestSerialConfigReading:
    """serial 判定与优先侧读取来自 Task.config（缺省 parallel/device）。

    用不覆写 _is_serial_task/_task_serial_first 的 _ConfigEngine 验证真实读取路径。
    """

    def _engine(self):
        class _ConfigEngine(TaskDispatchMixin):
            def _log(self, **kwargs):
                pass

            def _wait_active_cases_with_backoff(self, task_id, stop_event=None):
                pass

        return _ConfigEngine()

    def _task(self, config=None):
        from task_service.infrastructure.persistence.models import Task
        t = Task()
        t.config = config
        return t

    def _session_with_task(self, task):
        from task_service.infrastructure.persistence.models import Task
        session = SimpleNamespace()
        session.get = lambda model, tid: task if model is Task else None
        session.query = lambda model: SimpleNamespace(
            filter=lambda *a, **k: SimpleNamespace(
                order_by=lambda *a, **k: SimpleNamespace(all=lambda: []),
            ),
        )
        return session

    def test_serial_detected_from_config(self):
        eng = self._engine()
        assert eng._is_serial_task(1, self._session_with_task(
            self._task({'execution_mode': 'serial'}))) is True
        assert eng._is_serial_task(1, self._session_with_task(
            self._task({'execution_mode': 'parallel'}))) is False
        assert eng._is_serial_task(1, self._session_with_task(self._task(None))) is False
        assert eng._is_serial_task(1, self._session_with_task(self._task({}))) is False

    def test_serial_first_default_device(self):
        eng = self._engine()
        from shared.models.common_enums import SerialFirst
        assert eng._task_serial_first(1, self._session_with_task(
            self._task({'execution_mode': 'serial'}))) == SerialFirst.DEVICE.value
        assert eng._task_serial_first(1, self._session_with_task(
            self._task({'serial_first': 'api'}))) == 'api'
