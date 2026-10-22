# -*- coding: utf-8 -*-
"""INT-604/INT-1115 验收测试：目标级门控（task_dispatch 纯逻辑，不触真实 DB/gRPC）。

覆盖验收标准 3 的分发层语义（双道 §5.2.4（三），集成实测由 tests/integration 负责）：
- 串行目标（同类型）不重叠：后者在前者用例行全部终态后才启动；
- 跨类型独立性：串行 API 只等同类型道内前序、不等任何设备；串行设备同理不等任何 API；
- 并行目标任务启动即并发派发（不受任何目标门控、不等待任何目标）；
- 串行目标等前序同类型并行目标（含并行目标）全终态后派发；
- 不可解析目标的行（device_id 为空）视为 parallel 可派发；
- 无串行目标 / 历史旧字段（execution_mode/serial_first）→ 全并行（零回归）；
- 主循环 keep-alive：config.target_modes 含任一 serial 时 _is_serial_task 为真。
"""
import os
from types import SimpleNamespace

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from shared.utils.status_constants import (
    ExecutionStatus, EvaluationStatus, TaskCaseStatus,
    FINISHED_CASE_STATUSES,
)
from task_service.core.execution_engine.mixins.task_dispatch import TaskDispatchMixin
from task_service.infrastructure.persistence.models import Task, TaskCase


class _Engine(TaskDispatchMixin):
    """与 ExecutionEngine 同构的最小组合（仅 TaskDispatchMixin，走真实 config 读取）。"""

    def __init__(self):
        self.logs = []

    def _log(self, **kwargs):
        self.logs.append(kwargs)

    def _wait_active_cases_with_backoff(self, task_id, stop_event=None):
        self.logs.append({'level': 'WAIT', 'task_id': task_id})


def _case_row(case_id, device_type, device_id=None,
              exec_status=ExecutionStatus.PENDING,
              eval_status=EvaluationStatus.PENDING, status=None):
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
    tc.status = status or derive_task_case_status(exec_status, eval_status)
    return tc


def _completed(row):
    """将行置为全终态（COMPLETED，FINAL）。"""
    row.execution_status = ExecutionStatus.COMPLETED
    row.evaluation_status = EvaluationStatus.COMPLETED
    row.status = TaskCaseStatus.COMPLETED
    return row


class _FakeQuery:
    def __init__(self, rows_):
        self._rows = rows_

    def filter(self, *a, **k):
        return self

    def order_by(self, *a, **k):
        return self

    def all(self):
        return self._rows

    def first(self):
        return self._rows[0] if self._rows else None

    def count(self):
        # 近似模拟 _handle_no_pending_case_serial 的 status.notin_(FINISHED) 过滤
        return sum(1 for r in self._rows if (r.status or '') not in FINISHED_CASE_STATUSES)


def _session_for(task_config, rows):
    """构造真实读 config 的假 session（Task.config 读取 + query(TaskCase) 行集）。"""
    task = Task()
    task.config = task_config
    session = SimpleNamespace()
    session.get = lambda model, tid: task if model is Task else None
    session.close = lambda: None
    session.query = lambda model: _FakeQuery(rows)
    return session


def _pick(eng, task_config, rows):
    """返回 _get_next_pending_case 选出的行（或 None）。"""
    return eng._get_next_pending_case(1, _session_for(task_config, rows))


class TestSameTypeSerialChain:
    """同类型串行链：两个同类型串行目标不重叠（后者在前者全终态后启动）。"""

    def test_later_serial_blocked_until_earlier_terminal(self):
        rows = [_case_row('c1', 'physical', '1'), _case_row('c2', 'physical', '2')]
        eng = _Engine()
        cfg = {'target_modes': [
            {'target_type': 'device', 'target_id': 1, 'mode': 'serial'},
            {'target_type': 'device', 'target_id': 2, 'mode': 'serial'},
        ]}
        # 前序串行目标（device 1）全 PENDING：先派发它
        got = _pick(eng, cfg, rows)
        assert got is not None and got.device_id == '1'
        # 前序串行目标在途（RUNNING）：后序（device 2）不得派发
        rows[0].execution_status = ExecutionStatus.RUNNING
        rows[0].status = TaskCaseStatus.RUNNING
        got = _pick(eng, cfg, rows)
        assert got is None
        # 前序全终态后：后序串行目标派发
        _completed(rows[0])
        got = _pick(eng, cfg, rows)
        assert got is not None and got.device_id == '2'

    def test_serial_waits_prior_same_type_parallel(self):
        """串行目标等前序同类型并行目标全终态（含并行目标也计入门控）。"""
        rows = [_case_row('c1', 'physical', '1'), _case_row('c2', 'physical', '2')]
        eng = _Engine()
        cfg = {'target_modes': [
            {'target_type': 'device', 'target_id': 1, 'mode': 'parallel'},
            {'target_type': 'device', 'target_id': 2, 'mode': 'serial'},
        ]}
        got = _pick(eng, cfg, rows)
        assert got.device_id == '1'
        rows[0].execution_status = ExecutionStatus.RUNNING
        rows[0].status = TaskCaseStatus.RUNNING
        got = _pick(eng, cfg, rows)
        assert got is None, '串行 device2 应等前序并行 device1 终态'
        _completed(rows[0])
        got = _pick(eng, cfg, rows)
        assert got.device_id == '2'


class TestCrossLaneIndependence:
    """跨类型独立性：设备道与 API 道始终并发、互不等待。"""

    def test_serial_api_dispatches_while_device_lane_running(self):
        """设备道串行目标在途时，API 道串行目标（无前序 API）可派发。"""
        dev = _case_row('c1', 'physical', '1')
        dev.execution_status = ExecutionStatus.RUNNING
        dev.status = TaskCaseStatus.RUNNING
        api = _case_row('c2', 'http_api', '10')
        eng = _Engine()
        cfg = {'target_modes': [
            {'target_type': 'device', 'target_id': 1, 'mode': 'serial'},
            {'target_type': 'api', 'target_id': 10, 'mode': 'serial'},
        ]}
        got = _pick(eng, cfg, [dev, api])
        assert got is not None and got.device_type == 'http_api', \
            '串行 API 不等设备道（跨类型独立）'

    def test_serial_device_dispatches_while_api_lane_running(self):
        """API 道串行目标在途时，设备道串行目标（无前序设备）可派发。"""
        api = _case_row('c1', 'http_api', '10')
        api.execution_status = ExecutionStatus.RUNNING
        api.status = TaskCaseStatus.RUNNING
        dev = _case_row('c2', 'physical', '1')
        eng = _Engine()
        cfg = {'target_modes': [
            {'target_type': 'api', 'target_id': 10, 'mode': 'serial'},
            {'target_type': 'device', 'target_id': 1, 'mode': 'serial'},
        ]}
        got = _pick(eng, cfg, [api, dev])
        assert got is not None and got.device_type == 'physical', \
            '串行设备不等 API 道（跨类型独立）'

    def test_api_serial_chain_independent_of_device_lane(self):
        """API 道内两串行目标：后序只等前序 API，设备道在途不影响。"""
        api1 = _case_row('c1', 'http_api', '10')
        api1.execution_status = ExecutionStatus.RUNNING
        api1.status = TaskCaseStatus.RUNNING
        api2 = _case_row('c2', 'http_api', '11')
        dev = _case_row('c3', 'physical', '1')
        dev.execution_status = ExecutionStatus.RUNNING
        dev.status = TaskCaseStatus.RUNNING
        eng = _Engine()
        cfg = {'target_modes': [
            {'target_type': 'api', 'target_id': 10, 'mode': 'serial'},
            {'target_type': 'api', 'target_id': 11, 'mode': 'serial'},
            {'target_type': 'device', 'target_id': 1, 'mode': 'serial'},
        ]}
        # 前序 API(10) 在途 → 后序 API(11) 不得派发（同类型链）
        got = _pick(eng, cfg, [api1, api2, dev])
        assert got is None, '同类型前序 API 未终态，后序 API 不得派发'
        # 前序 API 终态后 → API(11) 派发（即使设备道仍在途）
        _completed(api1)
        got = _pick(eng, cfg, [api1, api2, dev])
        assert got is not None and got.device_id == '11'


class TestParallelTargetAndUnparseable:
    """并行目标与不可解析行：不受目标门控。"""

    def test_parallel_target_rows_always_dispatchable(self):
        """并行目标行在途不阻塞任何行；无前序依赖时直接派发。"""
        rows = [_case_row('c1', 'physical', '1'), _case_row('c2', 'physical', '2')]
        eng = _Engine()
        cfg = {'target_modes': [
            {'target_type': 'device', 'target_id': 1, 'mode': 'parallel'},
            {'target_type': 'device', 'target_id': 2, 'mode': 'parallel'},
        ]}
        got = _pick(eng, cfg, rows)
        assert got.device_id == '1'

    def test_unparseable_row_treated_as_parallel(self):
        """device_id 为空的历史派生行：不受门控，视为 parallel 可派发。"""
        unparseable = _case_row('c1', 'physical', None)
        serial = _case_row('c2', 'physical', '2')
        eng = _Engine()
        cfg = {'target_modes': [
            {'target_type': 'device', 'target_id': 2, 'mode': 'serial'},
        ]}
        got = _pick(eng, cfg, [unparseable, serial])
        assert got is not None and got.device_id is None, \
            '不可解析行（device_id 为空）应视为 parallel 可派发'


class TestNoSerialDefaultsParallel:
    """无串行目标 / 历史旧字段：维持现行为（最早 PENDING 先取，零回归）。"""

    def test_no_serial_target_takes_earliest_pending(self):
        rows = [_case_row('c1', 'http_api', '10'), _case_row('c2', 'physical', '1')]
        eng = _Engine()
        got = _pick(eng, {'target_modes': [
            {'target_type': 'device', 'target_id': 1, 'mode': 'parallel'},
            {'target_type': 'api', 'target_id': 10, 'mode': 'parallel'},
        ]}, rows)
        assert got.device_type == 'http_api'

    def test_legacy_execution_fields_treated_as_all_parallel(self):
        """历史任务旧 execution_mode/serial_first：引擎不再读取，按全并行。"""
        rows = [_case_row('c1', 'http_api', '10'), _case_row('c2', 'physical', '1')]
        eng = _Engine()
        cfg = {'execution_mode': 'serial', 'serial_first': 'device'}
        assert eng._is_serial_task(1, _session_for(cfg, rows)) is False
        got = _pick(eng, cfg, rows)
        assert got.device_type == 'http_api'

    def test_absent_target_modes_is_all_parallel(self):
        rows = [_case_row('c1', 'http_api', '10'), _case_row('c2', 'physical', '1')]
        eng = _Engine()
        got = _pick(eng, None, rows)
        assert got.device_type == 'http_api'


class TestSerialKeepAliveDecision:
    """主循环 keep-alive：target_modes 含任一 serial 时 _is_serial_task 为真。"""

    def test_serial_detected_from_target_modes(self):
        eng = _Engine()
        assert eng._is_serial_task(1, _session_for({'target_modes': [
            {'target_type': 'device', 'target_id': 1, 'mode': 'serial'}]}, [])) is True
        assert eng._is_serial_task(1, _session_for({'target_modes': [
            {'target_type': 'device', 'target_id': 1, 'mode': 'parallel'}]}, [])) is False
        assert eng._is_serial_task(1, _session_for({'target_modes': []}, [])) is False
        assert eng._is_serial_task(1, _session_for(None, [])) is False
        assert eng._is_serial_task(1, _session_for({}, [])) is False

    def test_waits_while_non_terminal_rows_exist(self):
        """串行门控等待期：仍有用例行未全终态时 _handle_no_pending_case_serial 返回 True。"""
        c = _case_row('case-1', 'physical', '101',
                      exec_status=ExecutionStatus.COMPLETED,
                      eval_status=EvaluationStatus.RUNNING)
        c.status = TaskCaseStatus.EVALUATING
        eng = _Engine()
        ok = eng._handle_no_pending_case_serial(1, _session_for({}, [c]))
        assert ok is True
        assert any(x.get('level') == 'WAIT' for x in eng.logs)

    def test_exits_when_all_terminal(self):
        c = _case_row('case-1', 'physical', '101',
                      exec_status=ExecutionStatus.COMPLETED,
                      eval_status=EvaluationStatus.COMPLETED)
        c.status = TaskCaseStatus.COMPLETED
        eng = _Engine()
        ok = eng._handle_no_pending_case_serial(1, _session_for({}, [c]))
        assert ok is False
