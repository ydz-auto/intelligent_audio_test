# -*- coding: utf-8 -*-
"""INT-103 验收：API 多轮会话结果落库后 TaskCase 终态回写（真实 Postgres + 进程内 gRPC）。

原缺陷：create_multi_round_test_result 仅 submit_result + log 后 return，TaskCase
停留 running/pending，引擎 _count_in_progress_cases / _count_evaluating_cases 持续
> 0，主循环忙等「等待 N 个执行中/评估中的用例完成」，任务永不收敛
（INT-95 任务 478 实证：result 4851 三轮全成功落库，task_case_relations 8989
停留 running/pending，同秒刷 334 条等待日志）。

回写字段矩阵与 stopped 保护的单测守卫在
tests/unit/test_int103_multi_round_case_finalization.py（ACL mock 层）；本文件补
mock 层验证不到的真实集成面：
- 回写经真实 ACL → gRPC UpdateTaskCaseStatus → task_service 仓储 → Postgres
  全链落库（proto 字段透传、仓储非空字段过滤、status 复合推导等集成缺口）；
- 失败路径 evaluation_status 必须补写终态（INT-42 同款语义），否则 pending 计入
  ACTIVE_EVALUATION_STATUSES 引擎死等——这是单测 kwargs 断言之外的真实落库效果；
- 以引擎主循环自己的计数函数验证回写后活跃集合归零（收敛不变量）；
- 评估腿经真实 EvaluateCase（评估替身）推进 evaluation_status 至终态，复现
  验收标准「多轮完成 → completed → 评估自动触发 → 收敛」的完整收敛链。

多轮执行器（http_api 会话 / websocket_api Realtime）对 result_processor 的调用
条件（result_id 且全轮成功才提交评估）已由单测与代码走查覆盖；全栈真实 E2E
（原缺陷现场级复现）需完整微服务栈 + Redis，本机未起，见验收报告说明。
"""
import time
import uuid
from datetime import datetime
from unittest.mock import MagicMock

import pytest

from tests.integration.test_task_execute_real_chain import (
    _query,
    _seed_execute_scenario,
    api_double,
    eval_double,     # noqa: F401  pytest fixture（评估腿替身）
    grpc_mesh,       # noqa: F401  pytest fixture
    oss_fast_fail,   # noqa: F401  pytest fixture
    pg_db,           # noqa: F401  pytest fixture
    storage_env,     # noqa: F401  pytest fixture
)


def _seed_multi_round_task(execution_status='running', evaluation_status='pending'):
    """播种 Task + 单条 TaskCase（多轮会话执行中形态），返回 (task_id, case_id)。"""
    from shared.models.database import get_db_session
    from task_service.infrastructure.persistence.models import Task, TaskCase

    case_id = f'INT103-{uuid.uuid4().hex[:12]}'
    s = get_db_session()
    task = Task(name=f'int103-multi-{uuid.uuid4().hex[:8]}', status='running',
                total_cases=1, algorithm_type='translation')
    s.add(task)
    s.flush()
    s.add(TaskCase(task_id=task.id, test_case_id=case_id, status='running',
                   execution_status=execution_status,
                   evaluation_status=evaluation_status,
                   device_type='http_api', created_at=datetime.now()))
    s.commit()
    task_id = task.id
    s.close()
    return task_id, case_id


def _aggregated(all_success=True):
    """3 轮会话聚合结果（与 api_session_executor._aggregate_round_results 同形）。"""
    rounds = [
        {'round_number': i, 'success': all_success,
         'output': f'out{i}', 'latency': 0.2}
        for i in range(1, 4)
    ]
    return {
        'success': all_success,
        'algorithm_result': {
            'text_output': 'a b c', 'round_count': 3,
            'success_count': 3 if all_success else 2,
            'total_latency': 0.6, 'avg_latency': 0.2,
            'session_id': str(uuid.uuid4()), 'rounds': rounds,
        },
        'total_latency': 0.6, 'round_count': 3,
        'session_summary': {},
    }


class _EngineStubExecutor:
    """最小执行器替身：execution_engine 为 MagicMock，捕获引擎通知调用。"""

    def __init__(self):
        self.execution_engine = MagicMock()

    def _log(self, **kwargs):
        pass


def _run_multi_round_writeback(task_id, case_id, success):
    """真实 processor 驱动多轮结果落库 + 终态回写，返回 (processor, result_id)。"""
    from api_test_service.core.api_result_processor import APIResultProcessor

    processor = APIResultProcessor(_EngineStubExecutor())
    result_id = processor.create_multi_round_test_result(
        task_id=task_id, test_case_id=case_id, api_config_id=None,
        algorithm_type='translation', aggregated=_aggregated(success),
        success=success)
    return processor, result_id


def _submit_evaluation_like_executor(task_id, result_id, case_id, aggregated):
    """复刻 APISessionExecutor._submit_evaluation 的真实评估提交调用。"""
    from api_test_service.core.api_session_executor import APISessionExecutor

    parent = MagicMock()
    parent._log = MagicMock()
    session_executor = APISessionExecutor(parent)
    session_executor._submit_evaluation(
        task_id=task_id, result_id=result_id, test_case_id=case_id,
        case_name='int103-multi', case_config={'algorithm_params': [],
                                               'reference_params': {}},
        case_algorithm_params={}, algorithm_type='translation',
        aggregated=aggregated, api_id=None)


def _engine_counts(task_id):
    """用引擎主循环自己的计数函数读活跃执行/评估用例数。"""
    from shared.models.database import get_db_session
    from task_service.core.execution_engine.mixins.task_dispatch import (
        TaskDispatchMixin,
    )

    counter = TaskDispatchMixin()
    s = get_db_session()
    try:
        return (counter._count_in_progress_cases(task_id, s),
                counter._count_evaluating_cases(task_id, s))
    finally:
        s.close()


def _wait_eval_terminal(task_id, timeout=60):
    """轮询 TaskCase 评估状态至终态，返回 (终态bool, 状态值)。"""
    from task_service.infrastructure.persistence.models import TaskCase

    deadline = time.time() + timeout
    status = None
    while time.time() < deadline:
        tcs = _query(TaskCase, task_id=task_id)
        status = tcs[0].evaluation_status if tcs else None
        if status in ('completed', 'failed', 'stopped'):
            return True, status
        time.sleep(0.5)
    return False, status


class TestInt103WriteBackRealChain:
    """多轮回写经真实 ACL → gRPC UpdateTaskCaseStatus → 仓储 → Postgres 落库。"""

    def test_success_writeback_persists_completed(
            self, pg_db, grpc_mesh, oss_fast_fail):
        task_id, case_id = _seed_multi_round_task()
        processor, result_id = _run_multi_round_writeback(task_id, case_id, success=True)

        assert result_id, '多轮结果应落库'
        from task_service.infrastructure.persistence.models import (
            TaskCase, TestResult,
        )
        tc = _query(TaskCase, task_id=task_id)[0]
        assert tc.execution_status == 'completed', \
            f'INT-103 核心：回写后 exec 应 completed，实际 {tc.execution_status}'
        # completed_at 由引擎任务收尾 _fix_stale_case_statuses 补写（与单轮路径
        # 同职责划分），回写时不写；失败路径由回写直接落（见下条用例）
        # 评估腿尚未运行（执行器随后才提交评估）：evaluation_status 保持 pending，
        # 复合状态由仓储按 (exec=completed, eval=pending) 推导为 evaluating
        # （评估进行中）；评估终态后转 completed 由全收敛用例验证
        assert tc.evaluation_status == 'pending'
        assert tc.status == 'evaluating', \
            f'评估未跑完时复合状态应推导为 evaluating，实际 {tc.status}'

        trs = _query(TestResult, task_id=task_id)
        assert len(trs) == 1, '多轮结果应写一条 TestResult'
        assert isinstance(trs[0].algorithm_result, dict), 'algorithm_result 应为 dict'
        assert trs[0].algorithm_result.get('round_count') == 3
        assert trs[0].algorithm_result.get('success_count') == 3

        engine = processor._executor.execution_engine
        engine._emit_progress.assert_called_once_with(task_id, force=True)
        engine.notify_case_completed.assert_called_once_with(task_id)

    def test_success_writeback_clears_engine_in_progress_count(
            self, pg_db, grpc_mesh, oss_fast_fail):
        """收敛不变量：回写后引擎自己的 _count_in_progress_cases 必须归零。"""
        task_id, case_id = _seed_multi_round_task()
        _run_multi_round_writeback(task_id, case_id, success=True)

        in_progress, _ = _engine_counts(task_id)
        assert in_progress == 0, \
            f'回写后执行中用例计数应归零（原缺陷此处恒为 1 死等），实际 {in_progress}'

    def test_partial_failure_writeback_persists_failed_with_eval_terminal(
            self, pg_db, grpc_mesh, oss_fast_fail):
        """部分轮次失败 → failed 且 evaluation_status 补写 completed（INT-103 核心）。

        修复前：仅 submit_result 后 return，exec 恒停 running、eval 恒停 pending，
        pending 计入 ACTIVE_EVALUATION_STATUSES 引擎死等。本断言验证真实 gRPC
        落库效果（proto 字段透传、仓储非空过滤是 mock 层验证不到的集成面）。
        """
        task_id, case_id = _seed_multi_round_task()
        _run_multi_round_writeback(task_id, case_id, success=False)

        from task_service.infrastructure.persistence.models import TaskCase
        tc = _query(TaskCase, task_id=task_id)[0]
        assert tc.execution_status == 'failed', \
            f'exec 应 failed，实际 {tc.execution_status}'
        assert tc.evaluation_status == 'completed', \
            f'INT-103 核心断言：失败用例必须补写 evaluation_status=completed，' \
            f'实际 {tc.evaluation_status}（pending 将被引擎计入活跃评估集合死等）'
        assert tc.status == 'failed', f'复合状态应推导为 failed，实际 {tc.status}'
        assert tc.completed_at is not None, '失败用例应写 completed_at'
        assert tc.error_message and '失败' in tc.error_message, \
            f'失败原因应落 error_message，实际 {tc.error_message!r}'

        in_progress, evaluating = _engine_counts(task_id)
        assert (in_progress, evaluating) == (0, 0), \
            f'失败回写后引擎活跃集合必须双归零，实际 exec={in_progress} eval={evaluating}'

    def test_stopped_case_not_overwritten(
            self, pg_db, grpc_mesh, oss_fast_fail):
        """stopped 保护：任务停止后不回写、不通知引擎（对齐单轮路径）。"""
        task_id, case_id = _seed_multi_round_task(execution_status='stopped')
        processor, result_id = _run_multi_round_writeback(task_id, case_id, success=True)

        assert result_id, '结果仍应落库（停止只影响状态回写，不影响结果保存）'
        from task_service.infrastructure.persistence.models import TaskCase
        tc = _query(TaskCase, task_id=task_id)[0]
        assert tc.execution_status == 'stopped', \
            f'stopped 态不得被回写覆盖，实际 {tc.execution_status}'

        engine = processor._executor.execution_engine
        engine._emit_progress.assert_not_called()
        engine.notify_case_completed.assert_not_called()


class TestInt103FullConvergence:
    """完整收敛链：回写 completed → 真实 EvaluateCase 评估 → 活跃集合双归零。"""

    def test_success_then_evaluation_progresses_to_terminal(
            self, pg_db, grpc_mesh, oss_fast_fail, api_double, eval_double):
        """复现验收标准主链路（引擎计数口径）：
        多轮 3 轮全成功 → 用例 completed → 评估自动触发（执行器同款提交）→
        评估完成 evaluation_status 终态 → 引擎活跃集合 (0, 0) → 任务可收敛。

        原缺陷在此链路的第 2 步断裂（无回写），评估与收敛永不发生。
        """
        ids = _seed_execute_scenario(api_double, eval_double)
        task_id, case_id = ids['task_id'], ids['case_id']

        processor, result_id = _run_multi_round_writeback(task_id, case_id, success=True)
        assert result_id, '多轮结果应落库'

        from task_service.infrastructure.persistence.models import TaskCase
        tc = _query(TaskCase, task_id=task_id)[0]
        assert tc.execution_status == 'completed', '回写后用例应 completed'

        # 执行器在回写成功后立即以同款调用提交评估（result_id 且全轮成功）
        _submit_evaluation_like_executor(
            task_id, result_id, case_id, _aggregated(all_success=True))

        reached, eval_status = _wait_eval_terminal(task_id)
        assert reached, f'评估应在窗口内收敛终态，实际 {eval_status}'

        tc = _query(TaskCase, task_id=task_id)[0]
        assert tc.evaluation_status == 'completed', \
            f'评估完成后 evaluation_status 应 completed，实际 {tc.evaluation_status}'
        # 复合 status 为终态即可：评估侧能构建轮次数据时 completed；无法构建时按
        # INT-115/INT-118 skipped 语义显式收口（INT-115 交付后本场景走 skipped）
        assert tc.status in ('completed', 'skipped'), \
            f'复合状态应为终态 completed/skipped，实际 {tc.status}'

        in_progress, evaluating = _engine_counts(task_id)
        assert (in_progress, evaluating) == (0, 0), \
            f'收敛终态：引擎活跃集合必须双归零，实际 exec={in_progress} eval={evaluating}'
