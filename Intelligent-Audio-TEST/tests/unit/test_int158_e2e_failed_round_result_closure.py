# -*- coding: utf-8 -*-
"""INT-158 守卫：E2E 失败早退路径必须收口预创建的 TestResult 行。

缺陷背景（INT-158 附带观察）：失败轮的 test_results.execution_status 停留
running（任务 427 result 5623），用例已 failed——结果行未随失败轮收口。
根因：_execute_e2e_with_rounds 的失败早退路径只更新 TaskCase 状态，
不更新预创建的 TestResult（正常路径由 _finalize_rounds 收口）。

锁定三条失败路径：
- 轮次失败（execution_success=False）→ update_test_result(FAILED, 累积轮次)
- 无有效结果（all_round_results 为空）→ 同上
- 执行异常 → update_test_result_status(FAILED)（仅收口状态，不覆盖已写轮次）
"""
import os
from types import SimpleNamespace
from unittest.mock import MagicMock

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from e2e_test_service.application.services.e2e_executor.executor import E2EExecutor
from shared.utils.status_constants import ExecutionStatus, TaskCaseStatus

_DATA = {
    'case_name': 'case-x',
    'case_config': {'rounds': [{'round_number': 1, 'audios': []}]},
    'case_reference_params': [],
    'test_case_id': 'c1',
    'algorithm_type': 'voice_llm',
}

_ROUNDS_DATA = [{'round': 0, 'output': {'question': 'q'}}]


def _host():
    ex = E2EExecutor.__new__(E2EExecutor)
    ex._aggregator = MagicMock()
    ex._task_data_repo = MagicMock()
    ex._device_repo = MagicMock()
    ex._playback_repo = MagicMock()
    ex._playback_repo.start_background_noise.return_value = None
    ex._playback_repo.stop_background_noise.return_value = None
    ex.current_test_case_id = 'c1'
    ex._thread_ctx = SimpleNamespace()
    ex._tc_rel_calls = []
    ex.logs = []
    return ex


def _patch_host(ex, loop_result=None, loop_exc=None, result_id=99):
    ex._log = MagicMock()
    ex._handle_control = MagicMock()
    ex._update_tc_rel_status = MagicMock(
        side_effect=lambda *a, **k: ex._tc_rel_calls.append((a, k)))
    ex._get_control_events = MagicMock(return_value=(None, None))
    ex._prepare_rounds = MagicMock(return_value=([{'device_id': 1}], result_id))
    if loop_exc is not None:
        ex._run_rounds_loop = MagicMock(side_effect=loop_exc)
    else:
        ex._run_rounds_loop = MagicMock(return_value=loop_result)


class TestFailedRoundResultClosure:

    def test_round_failure_closes_result_row_with_rounds(self):
        """轮次失败：结果行收口为 FAILED 且带已累积轮次数据。"""
        ex = _host()
        _patch_host(ex, loop_result=([], _ROUNDS_DATA, False, None))
        ok = ex._execute_e2e_with_rounds('t1', 'tc1', dict(_DATA))
        assert ok is False
        ex._aggregator.update_test_result.assert_called_once()
        kwargs = ex._aggregator.update_test_result.call_args.kwargs
        assert kwargs['result_id'] == 99
        assert kwargs['execution_status'] == ExecutionStatus.FAILED
        assert kwargs['algo_result']['rounds'] == _ROUNDS_DATA
        assert kwargs['algo_result']['total_rounds'] == 1
        ex._task_data_repo.update_test_result_status.assert_not_called()
        # TaskCase 状态同步落 FAILED（首次调用是开跑时的 RUNNING，取最后一次）
        assert ex._tc_rel_calls[-1][1]['execution_status'] == ExecutionStatus.FAILED
        assert ex._tc_rel_calls[-1][1]['status'] == TaskCaseStatus.FAILED

    def test_no_valid_results_closes_result_row(self):
        """所有轮次均未产生有效结果：结果行同样收口为 FAILED。"""
        ex = _host()
        _patch_host(ex, loop_result=([], [], True, None))
        ok = ex._execute_e2e_with_rounds('t1', 'tc1', dict(_DATA))
        assert ok is False
        ex._aggregator.update_test_result.assert_called_once()
        kwargs = ex._aggregator.update_test_result.call_args.kwargs
        assert kwargs['execution_status'] == ExecutionStatus.FAILED

    def test_exception_closes_status_only(self):
        """执行异常：仅收口状态（update_test_result_status），不覆盖已写轮次。"""
        ex = _host()
        _patch_host(ex, loop_exc=RuntimeError('boom'))
        ok = ex._execute_e2e_with_rounds('t1', 'tc1', dict(_DATA))
        assert ok is False
        ex._aggregator.update_test_result.assert_not_called()
        ex._task_data_repo.update_test_result_status.assert_called_once_with(99, ExecutionStatus.FAILED)
        assert ex._tc_rel_calls[-1][1]['status'] == TaskCaseStatus.FAILED

    def test_no_result_id_skips_closure(self):
        """准备阶段前失败（result_id 未创建）：不触发收口调用。"""
        ex = _host()
        _patch_host(ex, loop_result=([], [], False, None), result_id=None)
        ok = ex._execute_e2e_with_rounds('t1', 'tc1', dict(_DATA))
        assert ok is False
        ex._aggregator.update_test_result.assert_not_called()
        ex._task_data_repo.update_test_result_status.assert_not_called()
