# -*- coding: utf-8 -*-
"""INT-42 守卫：task_service 引擎分发侧失败必须同步推进 evaluation_status。

原缺陷：分发侧失败（CreateAPITest gRPC 抛错/返回失败，失败发生在
api_test_service 接手之前）的两个兜底——case_execution._execute_api_case 的
except 块与 task_dispatch._dispatch_api_case 的 except 块——只置
execution_status=FAILED，evaluation_status 恒留 pending。pending 计入主循环
「评估中」活跃集合（ACTIVE_EVALUATION_STATUSES 含 PENDING），
_handle_no_pending_case 判定 evaluating>0 → 死等 _wait_completion_event →
任务永久卡 running，永不收敛到 failed 终态。

修复：新增 TaskDispatchMixin._finalize_dispatch_failure——执行置 FAILED，
评估尚未启动（pending/queued/None）时同步补写 evaluation_status=COMPLETED
（与 api_test_service 侧 _run_single_api 失败逃生门语义对齐，失败由
execution_status 承载），status 由 derive_task_case_status 推导为 failed
（FINISHED_CASE_STATUSES 终态）→ _count_evaluating_cases 不再计入 →
主循环退出 → _finalize_task_status 收敛任务为 FAILED。

本文件覆盖（纯单测，不触真实 DB/gRPC）：
- 兜底语义矩阵：pending/queued/None 补写 completed；running/calculating
  （评估已启动）不越权覆盖；幂等（已 completed 不变）。
- _dispatch_api_case 异常路径：兜底被调用、error_message 落库、commit 发生。
- _execute_api_case gRPC 失败路径（异常抛出 / resp.success=False 两种）：
  同样推进 evaluation_status，并补 started_at/completed_at/duration。
- 收敛不变量：兜底后的用例状态组合必不落入任何活跃评估集合，
  且推导 status ∈ FINISHED_CASE_STATUSES（终态，任务可收敛）。

真实 Postgres + 进程内 gRPC 的端到端验证由
tests/integration/test_task_execute_real_chain.py 覆盖，不在本文件范围。
"""
import os
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

# BaseConfig 在 import 时校验环境变量（本用例纯单测不触库，与仓库既有测试同款兜底）
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import shared.clients.grpc_clients as shared_grpc_clients
from shared.utils.status_constants import (
    ExecutionStatus, EvaluationStatus, TaskCaseStatus,
    ACTIVE_EVALUATION_STATUSES, FINISHED_CASE_STATUSES,
)
from shared.utils.status_utils import derive_task_case_status
from task_service.core.execution_engine.mixins.case_execution import CaseExecutionMixin
from task_service.core.execution_engine.mixins.task_dispatch import TaskDispatchMixin
from task_service.infrastructure.persistence.models import TaskCase


class _Engine(CaseExecutionMixin, TaskDispatchMixin):
    """与 ExecutionEngine 同构的最小组合（CaseExecutionMixin 在前）。"""

    def __init__(self):
        self.utc_plus_8 = timezone(timedelta(hours=8))
        self.logs = []

    def _log(self, **kwargs):
        self.logs.append(kwargs)


def _dispatch_side_failure_case(execution_status=ExecutionStatus.QUEUED,
                                evaluation_status=EvaluationStatus.PENDING):
    """模拟已领取（claim 后）待分发的 TaskCase 行（不入库，仅属性级）。"""
    tc_rel = TaskCase()
    tc_rel.id = 'tc-rel-1'
    tc_rel.task_id = 'task-1'
    tc_rel.execution_status = execution_status
    tc_rel.evaluation_status = evaluation_status
    return tc_rel


class TestInt42FinalizeDispatchFailure:
    """兜底语义矩阵：评估未启动一律补写终态，已启动不越权覆盖。"""

    def test_pending_evaluation_is_bumped_to_completed(self):
        tc_rel = _dispatch_side_failure_case()
        _Engine()._finalize_dispatch_failure(tc_rel)

        assert tc_rel.execution_status == ExecutionStatus.FAILED
        assert tc_rel.evaluation_status == EvaluationStatus.COMPLETED
        assert tc_rel.status == TaskCaseStatus.FAILED

    def test_queued_evaluation_is_bumped_to_completed(self):
        tc_rel = _dispatch_side_failure_case(evaluation_status=EvaluationStatus.QUEUED)
        _Engine()._finalize_dispatch_failure(tc_rel)

        assert tc_rel.evaluation_status == EvaluationStatus.COMPLETED
        assert tc_rel.status == TaskCaseStatus.FAILED

    def test_none_evaluation_legacy_row_is_bumped(self):
        """旧数据/未初始化 ORM 对象 evaluation_status=None 时同样补写（or-PENDING 守卫）。"""
        tc_rel = _dispatch_side_failure_case(evaluation_status=None)
        _Engine()._finalize_dispatch_failure(tc_rel)

        assert tc_rel.evaluation_status == EvaluationStatus.COMPLETED
        assert tc_rel.status == TaskCaseStatus.FAILED

    def test_running_evaluation_is_not_stomped(self):
        """评估已启动（running/calculating）时不动 evaluation_status，交给评估侧收口。"""
        for started in (EvaluationStatus.RUNNING, EvaluationStatus.CALCULATING):
            tc_rel = _dispatch_side_failure_case(evaluation_status=started)
            _Engine()._finalize_dispatch_failure(tc_rel)

            assert tc_rel.evaluation_status == started
            assert tc_rel.execution_status == ExecutionStatus.FAILED
            assert tc_rel.status == TaskCaseStatus.FAILED

    def test_idempotent_when_already_completed(self):
        tc_rel = _dispatch_side_failure_case(evaluation_status=EvaluationStatus.COMPLETED)
        _Engine()._finalize_dispatch_failure(tc_rel)

        assert tc_rel.evaluation_status == EvaluationStatus.COMPLETED


class TestInt42DispatchApiCaseExceptPath:
    """_dispatch_api_case 异常兜底（领取/提交阶段的意外异常）必须走新兜底。"""

    def _run(self, tc_rel):
        eng = _Engine()
        eng._claim_case = lambda *a, **k: 1

        def _boom(*a, **k):
            raise RuntimeError('gRPC channel unavailable')
        eng._execute_api_case = _boom

        session = MagicMock()
        eng._dispatch_api_case('task-1', tc_rel, session)
        return session

    def test_failure_advances_evaluation_status(self):
        tc_rel = _dispatch_side_failure_case()
        self._run(tc_rel)

        assert tc_rel.execution_status == ExecutionStatus.FAILED
        assert tc_rel.evaluation_status == EvaluationStatus.COMPLETED
        assert tc_rel.status == TaskCaseStatus.FAILED
        assert 'API任务执行异常' in (tc_rel.error_message or '')

    def test_session_committed(self):
        tc_rel = _dispatch_side_failure_case()
        session = self._run(tc_rel)
        session.commit.assert_called()


class TestInt42ExecuteApiCaseGrpcFailurePath:
    """_execute_api_case gRPC 失败（CreateAPITest 抛错 / resp.success=False）——
    真实链路中分发侧失败的主要落点，必须推进 evaluation_status。"""

    def _run_grpc_failure(self, tc_rel, stub):
        import task_service.core.execution_engine.mixins.case_execution as mod

        eng = _Engine()
        fake_session = MagicMock()
        fake_session.get.side_effect = lambda model, obj_id: (
            tc_rel if model is TaskCase else None)

        original_db = mod.get_db_session
        saved_stub_getter = shared_grpc_clients.get_api_test_service_stub
        mod.get_db_session = lambda: fake_session
        shared_grpc_clients.get_api_test_service_stub = lambda: stub
        try:
            ok = eng._execute_api_case('task-1', 'tc-rel-1')
        finally:
            mod.get_db_session = original_db
            shared_grpc_clients.get_api_test_service_stub = saved_stub_getter
        return ok, fake_session

    def test_grpc_exception_advances_evaluation_status(self):
        tc_rel = _dispatch_side_failure_case()
        tc_rel.started_at = datetime.now(timezone(timedelta(hours=8)))

        def _raise(req):
            raise RuntimeError('CreateAPITest unavailable')
        stub = SimpleNamespace(CreateAPITest=_raise)

        ok, _ = self._run_grpc_failure(tc_rel, stub)

        assert ok is False
        assert tc_rel.execution_status == ExecutionStatus.FAILED
        assert tc_rel.evaluation_status == EvaluationStatus.COMPLETED
        assert tc_rel.status == TaskCaseStatus.FAILED
        assert tc_rel.completed_at is not None
        assert 'API 执行异常' in (tc_rel.error_message or '')

    def test_grpc_failure_response_advances_evaluation_status(self):
        tc_rel = _dispatch_side_failure_case()
        tc_rel.started_at = datetime.now(timezone(timedelta(hours=8)))
        stub = SimpleNamespace(CreateAPITest=lambda req: SimpleNamespace(
            success=False, message='api_test_service 内部错误'))

        ok, _ = self._run_grpc_failure(tc_rel, stub)

        assert ok is False
        assert tc_rel.execution_status == ExecutionStatus.FAILED
        assert tc_rel.evaluation_status == EvaluationStatus.COMPLETED
        assert tc_rel.status == TaskCaseStatus.FAILED

    def test_duration_computed_when_started_at_missing(self):
        """started_at 为空时兜底补齐（原逻辑保留），duration 落库为非负整数。"""
        tc_rel = _dispatch_side_failure_case()
        tc_rel.started_at = None
        stub = SimpleNamespace(CreateAPITest=lambda req: SimpleNamespace(
            success=False, message='boom'))

        ok, _ = self._run_grpc_failure(tc_rel, stub)

        assert ok is False
        assert tc_rel.started_at is not None
        assert isinstance(tc_rel.duration, int) and tc_rel.duration >= 0


class TestInt42WaitLoopConvergence:
    """收敛不变量：兜底后的状态组合必不落入活跃评估集合，且推导 status 为终态。"""

    def test_finalized_case_not_counted_as_evaluating(self):
        tc_rel = _dispatch_side_failure_case()
        _Engine()._finalize_dispatch_failure(tc_rel)

        assert tc_rel.evaluation_status not in ACTIVE_EVALUATION_STATUSES, \
            '兜底后 evaluation_status 不得再被 _count_evaluating_cases 计入'
        assert tc_rel.execution_status not in (ExecutionStatus.QUEUED, ExecutionStatus.RUNNING)

    def test_finalized_case_status_is_terminal(self):
        tc_rel = _dispatch_side_failure_case()
        _Engine()._finalize_dispatch_failure(tc_rel)

        assert tc_rel.status in FINISHED_CASE_STATUSES
        assert derive_task_case_status(tc_rel.execution_status,
                                       tc_rel.evaluation_status) == TaskCaseStatus.FAILED
