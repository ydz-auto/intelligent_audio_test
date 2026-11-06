# -*- coding: utf-8 -*-
"""INT-2234 独立复测（测试工程师）：评估写回路由行精度

不复用实施者单测的桩，按 task_service `_task_case_stats_mixin.update_task_case_status`
的真实语义重建落库行为：
- 带 tc_rel_id → 只更新该路由行；
- 不带 tc_rel_id → 按 (task_id, test_case_id) 命中同用例全部路由行；
- 未显式给 status 时按行自身 execution + 本次 evaluation 派生复合 status；
- 只写传入的非空字段（execution_status/evaluation_status 为空即不回写）。

覆盖验收标准与三个补充口径：
1. 多路由同用例（设备行 completed / API 行 running），API 行评估失败 →
   设备行三态不变、API 行执行态不被强写 completed；
2. 组失败兜底链路 `update_all_dimensions_in_group_failed(result_id=…)` 确实把
   result_id 透传到 mark_case_failed_if_active（实施者单测只直接测 _mark_group_case_failed）；
3. `update_task_case_status_in_db` 的 execution_status 默认值已不是 completed（缺陷 2）；
4. 活跃判定读目标行而非首行（兄弟行活跃不得让已终态的目标行被改写）；
5. 延迟重试队列补写时仍带 tc_rel_id。
"""
from types import SimpleNamespace

import os
import tempfile

os.environ.setdefault('DATABASE_URL',
                      'sqlite:///' + tempfile.mkdtemp(prefix='int2234_tv_') + '/guard.db')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

from shared.utils.status_constants import (
    EvaluationStatus, ExecutionStatus, TaskCaseStatus,
)
from shared.utils.status_utils import derive_task_case_status

TASK_ID = 42
CASE_ID = 'case-tester-2234'
DEVICE_ROW_ID = 101
API_ROW_ID = 102
DEVICE_RESULT_ID = 9001
API_RESULT_ID = 9002


def _row(row_id, device_type, bound_id, exec_status, eval_status):
    return SimpleNamespace(
        id=row_id,
        task_id=TASK_ID,
        test_case_id=CASE_ID,
        device_type=device_type,
        device_id=bound_id,
        execution_status=exec_status,
        evaluation_status=eval_status,
        status=derive_task_case_status(exec_status, eval_status),
        error_message=None,
    )


class FakeTaskServiceAcl:
    """task_service UpdateTaskCaseStatus 落库语义的最小忠实实现。"""

    def __init__(self, rows, results):
        self.rows = {r.id: r for r in rows}
        self.results = results
        self.calls = []

    # ---- 读 ----
    def get_task_case_by_ids(self, task_id, case_ids=None):
        wanted = {str(c) for c in (case_ids or [])}
        return [r for r in self.rows.values()
                if r.task_id == task_id and (not wanted or str(r.test_case_id) in wanted)]

    def get_test_result_by_id(self, result_id):
        return self.results.get(int(result_id))

    # ---- 写（对齐 _task_case_stats_mixin.update_task_case_status） ----
    def update_task_case_status(self, task_id, case_id, status='',
                                execution_status='', evaluation_status='',
                                error_message='', tc_rel_id=None, **_ignored):
        self.calls.append({
            'task_id': task_id, 'case_id': case_id, 'status': status,
            'execution_status': execution_status,
            'evaluation_status': evaluation_status,
            'error_message': error_message, 'tc_rel_id': tc_rel_id,
        })
        targets = ([self.rows[tc_rel_id]] if tc_rel_id is not None
                   else [r for r in self.rows.values()
                         if r.task_id == task_id and str(r.test_case_id) == str(case_id)])
        for row in targets:
            # 服务端派生：显式 status 优先，否则按「本次传入 + 行自身现值」推导
            if status:
                derived = status
            elif execution_status or evaluation_status:
                derived = derive_task_case_status(
                    execution_status or row.execution_status or 'pending',
                    evaluation_status or row.evaluation_status or 'pending')
            else:
                derived = ''
            if derived:
                row.status = derived
            if execution_status:
                row.execution_status = execution_status
            if evaluation_status:
                row.evaluation_status = evaluation_status
            if error_message:
                row.error_message = error_message
        return True

    def triple(self, row_id):
        r = self.rows[row_id]
        return r.execution_status, r.evaluation_status, r.status


@pytest.fixture
def acl(monkeypatch):
    # 设备行先返回（旧口径的「首行」），API 行在后：活跃判定若读首行就会走错行
    rows = [
        _row(DEVICE_ROW_ID, 'physical', '301',
             ExecutionStatus.COMPLETED, EvaluationStatus.COMPLETED),
        _row(API_ROW_ID, 'http_api', '302',
             ExecutionStatus.RUNNING, EvaluationStatus.RUNNING),
    ]
    results = {
        DEVICE_RESULT_ID: SimpleNamespace(device_id=301, api_id=None),
        API_RESULT_ID: SimpleNamespace(device_id=None, api_id=302),
    }
    fake = FakeTaskServiceAcl(rows, results)
    import evaluation_service.infrastructure.acl as acl_pkg
    monkeypatch.setattr(acl_pkg, 'task_acl_repository', fake)
    # 需要的模块级引用一并替换
    for mod_name in (
        'evaluation_service.infrastructure.acl.task_case_status_retry',
        'evaluation_service.application.handlers.reevaluation_executor',
        'evaluation_service.infrastructure.evaluation_mixin',
    ):
        module = __import__(mod_name, fromlist=['*'])
        if hasattr(module, 'task_acl_repository'):
            monkeypatch.setattr(module, 'task_acl_repository', fake)
    return fake


def _assert_device_row_untouched(acl):
    assert acl.triple(DEVICE_ROW_ID) == (
        ExecutionStatus.COMPLETED, EvaluationStatus.COMPLETED, TaskCaseStatus.COMPLETED)


class TestGroupFailureFallbackWiring:
    """组失败兜底：result_id 必须透传成路由行，不得整体覆盖。"""

    def test_group_failure_fallback_targets_api_row(self, acl):
        from evaluation_service.infrastructure.persistence._result_dimension_mixin import (
            DimensionResultMixin,
        )
        host = DimensionResultMixin()
        host._log = lambda **kw: None
        # 强制本地 TRD 落库失败，走 gRPC 兜底收口（result_id 透传的关键分支）
        host._write_group_trd_failed_with_retry = lambda *a, **kw: False
        host.update_task_case_status = lambda **kw: None

        host.update_all_dimensions_in_group_failed(
            group_items=[], error_message='维度评估失败', task_id=TASK_ID,
            test_case_id=CASE_ID, result_id=API_RESULT_ID,
        )

        assert acl.calls, '兜底收口必须写回 task_case_relations'
        for call in acl.calls:
            assert call['tc_rel_id'] == API_ROW_ID, '兜底写回必须带本次结果的路由行 id'
            assert not call['execution_status'], '评估侧不得写执行状态'
        api_exec, api_eval, api_status = acl.triple(API_ROW_ID)
        assert api_eval == EvaluationStatus.FAILED
        assert api_exec == ExecutionStatus.RUNNING, '兄弟路由执行态不得被强写 completed'
        assert api_status == TaskCaseStatus.RUNNING
        _assert_device_row_untouched(acl)


class TestActiveGateIsRowScoped:
    """活跃判定必须看目标行：目标行已终态时不得因兄弟行活跃而被改写。"""

    def test_terminal_target_row_not_rewritten_by_active_sibling(self, acl):
        from evaluation_service.infrastructure.persistence._result_dimension_mixin import (
            DimensionResultMixin,
        )
        acl.rows[API_ROW_ID].evaluation_status = EvaluationStatus.COMPLETED
        acl.rows[DEVICE_ROW_ID].evaluation_status = EvaluationStatus.RUNNING  # 首行活跃

        proc = DimensionResultMixin()
        proc._log = lambda **kw: None
        proc.mark_case_failed_if_active(
            TASK_ID, CASE_ID, '端点评估失败', result_id=API_RESULT_ID)

        assert acl.calls == [], '目标行已是终态，不应再写回（旧口径会误判首行活跃而改写整例）'


class TestExecutionStatusDefault:
    """缺陷 2：execution_status 默认值不得再是 completed。"""

    def test_default_execution_status_no_longer_completed(self, acl):
        from evaluation_service.infrastructure.evaluation_mixin import (
            update_task_case_status_in_db,
        )

        # 不传 execution_status，只回写评估失败（含 tc_rel_id）
        rc = update_task_case_status_in_db(
            None, TASK_ID, CASE_ID, TaskCaseStatus.FAILED,
            EvaluationStatus.FAILED, tc_rel_id=API_ROW_ID)

        assert rc == 1
        assert len(acl.calls) == 1
        call = acl.calls[0]
        assert not call['execution_status'], \
            '默认值必须为空（旧实现默认 completed 会强写兄弟路由执行态）'
        assert not call['status'], '复合 status 交由 task_service 派生，不直写'
        assert call['tc_rel_id'] == API_ROW_ID
        api_exec, api_eval, _ = acl.triple(API_ROW_ID)
        assert api_exec == ExecutionStatus.RUNNING
        assert api_eval == EvaluationStatus.FAILED
        _assert_device_row_untouched(acl)


class TestReevalRollback:
    """重评无维度回滚：只动本行，且不直写复合 status。"""

    def test_rollback_targets_only_its_row(self, acl):
        from evaluation_service.application.handlers import reevaluation_executor as reexec
        from shared.utils.status_constants import (
            EvaluationStatus as ES,  # noqa: N813
        )

        acl.rows[API_ROW_ID].evaluation_status = ES.QUEUED
        ex = reexec.ReevaluationExecutor()

        ex._rollback_case_if_stuck_queued(
            TASK_ID, CASE_ID, reevaluate_type='all', result_id=API_RESULT_ID)

        assert len(acl.calls) == 1
        call = acl.calls[0]
        assert call['tc_rel_id'] == API_ROW_ID
        assert not call['status'], '回滚不得直写复合 status（INT-2234 修复建议）'
        api_exec, api_eval, api_status = acl.triple(API_ROW_ID)
        assert api_eval == EvaluationStatus.COMPLETED
        assert api_exec == ExecutionStatus.RUNNING
        assert api_status == TaskCaseStatus.RUNNING  # running + completed 派生
        _assert_device_row_untouched(acl)


class TestRetryQueueRepairCarriesRoute:
    """task_service 短暂不可用的补写：仍按路由行补写，不碰兄弟行。"""

    def test_repair_flush_keeps_tc_rel_id(self, acl):
        from evaluation_service.infrastructure.acl.task_case_status_retry import (
            TaskStatusRetryQueue,
        )
        queue = TaskStatusRetryQueue()
        queue._ensure_worker_locked = lambda: None
        queue._arm_locked = lambda item: None  # next_attempt_at=0 → 立即到期

        queue.enqueue_case_status(TASK_ID, CASE_ID, '', EvaluationStatus.FAILED,
                                  tc_rel_id=API_ROW_ID)
        queue._process_due_cases()

        assert len(acl.calls) == 1
        assert acl.calls[0]['tc_rel_id'] == API_ROW_ID
        assert not acl.calls[0]['execution_status']
        assert acl.triple(API_ROW_ID)[1] == EvaluationStatus.FAILED
        _assert_device_row_untouched(acl)
