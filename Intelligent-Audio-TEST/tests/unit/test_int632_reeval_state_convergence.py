# -*- coding: utf-8 -*-
"""INT-632 回归守卫：重新评估后任务/用例状态不收敛

缺陷：reevaluate_type=all 重评一个已完成任务后，评估已 completed 但
- 用例卡 evaluating：_post_evaluate_updates 收口 queued/pending 用例评估为
  completed 时保留 tc.status（重评/无维度收尾路径下是 evaluating），
  execution/evaluation 均已终态而 status 不重推导；
- 任务卡 running：_reevaluate_multi_round 全部轮次被跳过（无维度可评估）时
  仍返回 True，_submit_cases_for_reevaluation 误计 submitted_count>0，
  _on_complete 置 running 后无端点回调（无评估在途）触发收敛；
- 快速评估竞态：端点回调在提交窗口（still_submitting）内到达被拒后不再有
  回调，_on_complete 提交完成不补收敛检查。

覆盖（纯单测，不触真实 DB/gRPC，全量 mock 协作方）：
1. _post_evaluate_updates 收口用例评估时按 execution+evaluation 重推导 status；
2. _reevaluate_multi_round 无维度可评估时返回 False（零提交收敛）；
3. _run_reevaluation 端到端：无维度 E2E 重评收敛为 completed；
4. _on_complete 提交完成后补 maybe_finalize 收敛检查（快速评估不再卡 running）。
"""
import os
from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

# BaseConfig 在 import 时校验环境变量（本用例纯单测不触库，与仓库既有测试同款兜底）
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

import evaluation_service.application.handlers.reevaluation_executor as reexec_module
from evaluation_service.application.handlers.reevaluation_executor import ReevaluationExecutor
from evaluation_service.domain.services.evaluation_service.post_evaluation import PostEvaluationMixin
from evaluation_service.infrastructure.acl import task_acl_repository
from shared.utils.status_constants import (
    EvaluationStatus, ExecutionStatus, TaskCaseStatus, TaskStatus,
)

# 导入 evaluation_service 相关模块后清理残留的 scoped session（仓库既有测试同款兜底）
from shared.models.database import remove_db_session as _remove_db_session
_remove_db_session()


def _result(test_case_id='c1', result_id=11, device_id=None, algo=None):
    """TestResultDTO 形状的对象（无需真实 ORM）"""
    return SimpleNamespace(
        id=result_id,
        task_id=1,
        test_case_id=test_case_id,
        device_id=device_id,
        execution_status=ExecutionStatus.COMPLETED,
        result_data=None,
        result_data_path=None,
        algorithm_result=algo if algo is not None else {'rounds': [{'output': {}}]},
    )


def _tc(exec_st=ExecutionStatus.COMPLETED, eval_st=EvaluationStatus.COMPLETED,
        status=TaskCaseStatus.COMPLETED, device_type='physical', case_id='c1'):
    """TaskCaseDTO 形状的对象"""
    return SimpleNamespace(
        test_case_id=case_id,
        execution_status=exec_st,
        evaluation_status=eval_st,
        status=status,
        device_type=device_type,
        error_message=None,
    )


def _task(status=TaskStatus.REEVALUATING):
    return SimpleNamespace(id=1, status=status)


def _no_dim_config():
    """E2E 用例：每轮 evaluation 无维度 + 顶层无维度（无任何可评估维度）"""
    return {'rounds': [{'evaluation': {'enabled': True, 'dimensions': []}}],
            'dimensions': []}


@pytest.fixture
def running_executor():
    """重评执行器当前正在处理 task_id=1（提交窗口内）"""
    ex = ReevaluationExecutor()
    ex.running_task_id = 1
    ex.is_reevaluating = True
    ex._submitting_tasks = {1}
    ex._check_queue = MagicMock()
    return ex


# ==================== 1. _post_evaluate_updates 收口重推导 status ====================

class _PostHost(PostEvaluationMixin):
    """PostEvaluationMixin 最小宿主（注入 mock ACL，捕获日志）"""

    def __init__(self, repo):
        self._task_acl_repo = repo
        self.logs = []

    def _log(self, **kwargs):
        self.logs.append(kwargs)


class TestPostEvaluateUpdatesStatusConvergence:
    """INT-632 缺陷1：queued/pending 用例评估收口为 completed 时 status 必须重推导"""

    def test_queued_case_with_finished_execution_derives_completed(self):
        """execution=completed、evaluation=queued、status=evaluating（重评置 queued 后的
        派生态）→ 收口为 completed 时 status 落 completed，不再残留 evaluating。"""
        repo = MagicMock()
        repo.get_task_case_by_ids.return_value = [
            _tc(exec_st=ExecutionStatus.COMPLETED,
                eval_st=EvaluationStatus.QUEUED,
                status=TaskCaseStatus.EVALUATING),
        ]
        repo.get_task_by_id.return_value = _task(status=TaskStatus.RUNNING)
        host = _PostHost(repo)

        host._update_task_case_and_progress(1, 'c1')

        repo.update_task_case_status.assert_called_once()
        kwargs = repo.update_task_case_status.call_args.kwargs
        assert kwargs['evaluation_status'] == EvaluationStatus.COMPLETED
        assert kwargs['status'] == TaskCaseStatus.COMPLETED
        assert kwargs['status'] != TaskCaseStatus.EVALUATING

    def test_failed_execution_stays_failed(self):
        """execution=failed 的用例收口评估为 completed → status 保持 failed"""
        repo = MagicMock()
        repo.get_task_case_by_ids.return_value = [
            _tc(exec_st=ExecutionStatus.FAILED,
                eval_st=EvaluationStatus.QUEUED,
                status=TaskCaseStatus.FAILED),
        ]
        repo.get_task_by_id.return_value = _task(status=TaskStatus.RUNNING)
        host = _PostHost(repo)

        host._update_task_case_and_progress(1, 'c1')

        kwargs = repo.update_task_case_status.call_args.kwargs
        assert kwargs['evaluation_status'] == EvaluationStatus.COMPLETED
        assert kwargs['status'] == TaskCaseStatus.FAILED

    def test_completed_case_already_terminal_not_touched(self):
        """已终态（eval=completed）的用例不触碰（幂等）"""
        repo = MagicMock()
        repo.get_task_case_by_ids.return_value = [
            _tc(exec_st=ExecutionStatus.COMPLETED,
                eval_st=EvaluationStatus.COMPLETED,
                status=TaskCaseStatus.COMPLETED),
        ]
        repo.get_task_by_id.return_value = _task(status=TaskStatus.RUNNING)
        host = _PostHost(repo)

        host._update_task_case_and_progress(1, 'c1')

        repo.update_task_case_status.assert_not_called()


# ==================== 2. _reevaluate_multi_round 无维度返回 False ====================

class TestReevalMultiRoundNoSubmission:
    """INT-632 缺陷2：无维度可评估时返回值必须是「是否确有评估提交」"""

    @staticmethod
    def _patched(ex, eval_svc):
        with patch.object(task_acl_repository, 'get_task_case_by_ids',
                          MagicMock(return_value=[_tc(eval_st=EvaluationStatus.COMPLETED)])), \
             patch.object(task_acl_repository, 'get_test_case_detail',
                          MagicMock(return_value=SimpleNamespace(
                              config=_no_dim_config(), algorithm_params=None,
                              reference_params=None, algorithm_type='translation'))), \
             patch.object(reexec_module.evaluation_dimension_repository,
                          'delete_scores_by_result_id', MagicMock(return_value=0)), \
             patch.object(reexec_module.evaluation_dimension_repository,
                          'list_scores_by_result_id', MagicMock(return_value=[])):
            return ex._reevaluate_multi_round(
                task_id=1, result=11, test_case_id='c1',
                algorithm_result={'rounds': [{'output': {}}]},
                device_type='physical', algorithm_type='translation',
                reevaluate_type='all',
            )

    def test_all_type_no_dims_returns_false(self):
        """all 型 E2E 无维度：全部轮次跳过、无评估在途 → 返回 False（零提交收敛）"""
        ex = ReevaluationExecutor()
        with patch.object(reexec_module, 'evaluation_service') as eval_svc:
            eval_svc.evaluate_case.return_value = True
            ok = self._patched(ex, eval_svc)

        assert ok is False
        eval_svc.evaluate_case.assert_not_called()
        # 就地收尾（mark_test_result_completed + _post_evaluate_updates）
        eval_svc.result_processor.mark_test_result_completed.assert_called_once_with(11)
        eval_svc._post_evaluate_updates.assert_called_once_with(1, 'c1')

    def test_submitted_rounds_still_returns_true(self):
        """确有轮次提交（有可评估维度）：返回 True（评估在途，由端点回调收敛）"""
        ex = ReevaluationExecutor()
        with patch.object(reexec_module, 'evaluation_service') as eval_svc, \
             patch.object(task_acl_repository, 'get_task_case_by_ids',
                          MagicMock(return_value=[_tc(eval_st=EvaluationStatus.COMPLETED)])), \
             patch.object(task_acl_repository, 'get_test_case_detail',
                          MagicMock(return_value=SimpleNamespace(
                              config={'rounds': [{'evaluation': {'enabled': True,
                                                                 'dimensions': [{'id': 7}]}}],
                                      'dimensions': []},
                              algorithm_params=None, reference_params=None,
                              algorithm_type='translation'))), \
             patch.object(reexec_module.evaluation_dimension_repository,
                          'delete_scores_by_result_id', MagicMock(return_value=0)):
            eval_svc.evaluate_case.return_value = True
            ok = ex._reevaluate_multi_round(
                task_id=1, result=11, test_case_id='c1',
                algorithm_result={'rounds': [{'output': {}}]},
                device_type='physical', algorithm_type='translation',
                reevaluate_type='all',
            )

        assert ok is True
        eval_svc.evaluate_case.assert_called_once()


# ==================== 3. _run_reevaluation 端到端收敛 ====================

class TestRunReevaluationNoDimConverges:
    """INT-632 端到端：无维度 E2E 重评提交 0 个用例 → 零提交主动收敛为 completed"""

    def test_no_dim_e2e_task_converges_completed(self, running_executor):
        ex = running_executor
        # 最终收敛视角：用例评估已终态（_post_evaluate_updates 收口后）
        tc = _tc(exec_st=ExecutionStatus.COMPLETED,
                 eval_st=EvaluationStatus.COMPLETED,
                 status=TaskCaseStatus.COMPLETED)

        with patch.object(reexec_module.task_acl_repository, 'get_test_results_by_task_and_case',
                          MagicMock(return_value=[_result()])), \
             patch.object(reexec_module.task_acl_repository, 'get_task_case_by_ids',
                          MagicMock(return_value=[tc])), \
             patch.object(reexec_module.task_acl_repository, 'get_test_case_detail',
                          MagicMock(return_value=SimpleNamespace(
                              config=_no_dim_config(), algorithm_params=None,
                              reference_params=None, algorithm_type='translation'))), \
             patch.object(reexec_module.task_acl_repository, 'get_task_by_id',
                          MagicMock(return_value=_task())), \
             patch.object(reexec_module.task_acl_repository, 'update_task_case_status',
                          MagicMock(return_value=True)) as upd_tc, \
             patch.object(reexec_module.evaluation_dimension_repository,
                          'delete_scores_by_result_id', MagicMock(return_value=0)), \
             patch.object(reexec_module, 'evaluation_service', MagicMock()), \
             patch('evaluation_service.application.handlers.reevaluation_executor.log_and_emit'), \
             patch('evaluation_service.infrastructure.evaluation_mixin.update_task_status_with_retry') as upd:
            ex._run_reevaluation(task_id=1, reextract_device_output=False, reevaluate_type='all')

        # 提交阶段未误传 status=evaluating（用例状态收口由 _post_evaluate_updates 推导）
        submitted_calls = [c for c in upd_tc.call_args_list
                           if c.kwargs.get('evaluation_status') == EvaluationStatus.QUEUED]
        assert len(submitted_calls) == 1
        assert submitted_calls[0].kwargs.get('status') not in (TaskCaseStatus.EVALUATING,)
        # 零提交收敛：任务终态直接 completed（不再卡 running）
        upd.assert_has_calls([call(1, TaskStatus.COMPLETED)])
        assert ex.running_task_id is None
        assert ex.is_reevaluating is False
        ex._check_queue.assert_called()


# ==================== 4. _on_complete 提交完成后补收敛检查 ====================

class TestOnCompletePostSubmitRecheck:
    """INT-632 竞态：快速评估在提交窗口内完成 → _on_complete 补 maybe_finalize 收敛"""

    def test_reeval_done_during_submission_converges(self, running_executor):
        ex = running_executor
        tc = _tc(exec_st=ExecutionStatus.COMPLETED,
                 eval_st=EvaluationStatus.COMPLETED,
                 status=TaskCaseStatus.COMPLETED)

        with patch('evaluation_service.infrastructure.evaluation_mixin.update_task_status_with_retry') as upd, \
             patch.object(reexec_module.task_acl_repository, 'get_task_case_by_ids',
                          MagicMock(return_value=[tc])), \
             patch.object(reexec_module.task_acl_repository, 'get_task_by_id',
                          MagicMock(return_value=_task(status=TaskStatus.RUNNING))):
            ex._on_complete(1, True, submitted_cases=1)

        # 先置 running，提交窗口关闭后再收敛为 completed
        upd.assert_any_call(1, TaskStatus.RUNNING)
        upd.assert_any_call(1, TaskStatus.COMPLETED)
        assert ex.running_task_id is None
        assert ex.is_reevaluating is False

    def test_eval_still_inflight_keeps_queue_held(self, running_executor):
        """评估仍在途：补检返回 False，任务保持 running、队列占用（由端点回调收敛）"""
        ex = running_executor
        tc = _tc(exec_st=ExecutionStatus.COMPLETED,
                 eval_st=EvaluationStatus.RUNNING,
                 status=TaskCaseStatus.EVALUATING)

        with patch('evaluation_service.infrastructure.evaluation_mixin.update_task_status_with_retry') as upd, \
             patch.object(reexec_module.task_acl_repository, 'get_task_case_by_ids',
                          MagicMock(return_value=[tc])):
            ex._on_complete(1, True, submitted_cases=1)

        upd.assert_called_once_with(1, TaskStatus.RUNNING)
        assert ex.running_task_id == 1
        assert ex.is_reevaluating is True
        ex._check_queue.assert_not_called()
