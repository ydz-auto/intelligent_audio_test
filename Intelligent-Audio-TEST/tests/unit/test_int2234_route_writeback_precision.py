# -*- coding: utf-8 -*-
"""INT-2234 评估写回路由精度（多路由同用例，兄弟行不得被覆盖）

缺陷形态：评估侧写回 TaskCase 时两处缺失——
1. 不传 task_case_relations.id（tc_rel_id），task_service 按
   (task_id, test_case_id) 全量更新，同用例所有路由行一起命中；
2. execution_status 走默认值 completed，把仍在执行的兄弟路由强行写成执行完成。

验收：同用例 2 路由行（一行 completed、一行 running），对其中一行执行
评估失败 / 重评，另一行 execution_status、evaluation_status、status 均不变。

本文件用「按 task_service 语义落库」的 ACL 桩（tc_rel_id 精确命中；未带时
按 (task, case) 全量）驱动评估侧真实写回链路。
"""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import os
import tempfile

os.environ.setdefault('DATABASE_URL',
                      'sqlite:///' + tempfile.mkdtemp(prefix='int2234_t_') + '/guard.db')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

from evaluation_service.infrastructure.acl.task_case_status_retry import (
    TaskStatusRetryQueue,
)
from evaluation_service.infrastructure.persistence._result_dimension_mixin import (
    DimensionResultMixin,
)
from shared.utils.status_constants import EvaluationStatus, ExecutionStatus, TaskCaseStatus
from shared.utils.status_utils import derive_task_case_status

TASK_ID = 7
CASE_ID = 'case-int2234'
DEVICE_ROW_ID = 11      # 设备侧路由行（已完成）
API_ROW_ID = 12         # API 侧路由行（仍在执行）
DEVICE_RESULT_ID = 501
API_RESULT_ID = 502


def _row(row_id, device_type, device_id, execution_status, evaluation_status):
    return SimpleNamespace(
        id=row_id,
        task_id=TASK_ID,
        test_case_id=CASE_ID,
        device_type=device_type,
        device_id=device_id,
        execution_status=execution_status,
        evaluation_status=evaluation_status,
        status=derive_task_case_status(execution_status, evaluation_status),
        error_message=None,
    )


class _FakeTaskAcl:
    """按 task_service UpdateTaskCaseStatus 语义落库的 ACL 桩。"""

    def __init__(self, rows):
        self.rows = {r.id: r for r in rows}
        # 设备侧行已完成，API 侧行仍在执行
        self.rows[DEVICE_ROW_ID] = _row(
            DEVICE_ROW_ID, 'physical', '101',
            ExecutionStatus.COMPLETED, EvaluationStatus.COMPLETED)
        self.rows[API_ROW_ID] = _row(
            API_ROW_ID, 'http_api', '202',
            ExecutionStatus.RUNNING, EvaluationStatus.RUNNING)
        self.results = {
            DEVICE_RESULT_ID: SimpleNamespace(device_id=101, api_id=None),
            API_RESULT_ID: SimpleNamespace(device_id=None, api_id=202),
        }
        self.calls = []

    # ---- 读 ----
    def get_task_case_by_ids(self, task_id, case_ids=None):
        wanted = {str(c) for c in (case_ids or [])}
        return [
            r for r in self.rows.values()
            if r.task_id == task_id and (not wanted or str(r.test_case_id) in wanted)
        ]

    def get_test_result_by_id(self, result_id):
        return self.results.get(int(result_id))

    def get_test_case_detail(self, case_id):
        return SimpleNamespace(
            config={}, algorithm_params=None, reference_params=None,
            algorithm_type='translation')

    # ---- 写（task_service 语义） ----
    def update_task_case_status(self, task_id, case_id, status='',
                                execution_status='', evaluation_status='',
                                error_message='', tc_rel_id=None, **_ignored):
        self.calls.append({
            'task_id': task_id,
            'case_id': case_id,
            'status': status,
            'execution_status': execution_status,
            'evaluation_status': evaluation_status,
            'error_message': error_message,
            'tc_rel_id': tc_rel_id,
        })
        if tc_rel_id is not None:
            targets = [self.rows[tc_rel_id]]
        else:
            targets = [r for r in self.rows.values()
                       if r.task_id == task_id and str(r.test_case_id) == str(case_id)]
        for row in targets:
            if status:
                row.status = status
            elif execution_status or evaluation_status:
                row.status = derive_task_case_status(
                    execution_status or row.execution_status or 'pending',
                    evaluation_status or row.evaluation_status or 'pending')
            if execution_status:
                row.execution_status = execution_status
            if evaluation_status:
                row.evaluation_status = evaluation_status
            if error_message:
                row.error_message = error_message
        return True

    def snapshot(self, row_id):
        row = self.rows[row_id]
        return (row.execution_status, row.evaluation_status, row.status)


@pytest.fixture
def acl(monkeypatch):
    fake = _FakeTaskAcl(rows=[])
    import evaluation_service.infrastructure.acl as acl_pkg

    monkeypatch.setattr(acl_pkg, 'task_acl_repository', fake)
    # 延迟 import 的模块内引用（evaluation_mixin 内部 `from ...acl import task_acl_repository`）
    for mod_name in (
        'evaluation_service.infrastructure.evaluation_mixin',
        'evaluation_service.infrastructure.persistence._result_dimension_mixin',
        'evaluation_service.application.handlers.reevaluation_executor',
    ):
        module = __import__(mod_name, fromlist=['*'])
        if hasattr(module, 'task_acl_repository'):
            monkeypatch.setattr(module, 'task_acl_repository', fake)
    return fake


def _assert_sibling_untouched(acl):
    assert acl.snapshot(DEVICE_ROW_ID) == (
        ExecutionStatus.COMPLETED, EvaluationStatus.COMPLETED, TaskCaseStatus.COMPLETED)


class TestEvaluationFailureWriteback:

    def test_failed_api_route_does_not_stomp_device_route(self, acl):
        """API 路由评估失败 → 只改 API 行评估态，设备侧（已完成）与 API 行执行态不变。"""
        proc = DimensionResultMixin()
        proc._log = lambda **kw: None

        proc.mark_case_failed_if_active(
            TASK_ID, CASE_ID, '端点评估失败: HTTP 500', result_id=API_RESULT_ID)

        assert acl.calls, '评估失败必须写回 task_case_relations'
        for call in acl.calls:
            assert call['tc_rel_id'] == API_ROW_ID, '必须按路由行精确命中'
            assert not call['execution_status'], '评估侧不得回写执行状态'
        api_exec, api_eval, api_status = acl.snapshot(API_ROW_ID)
        assert api_eval == EvaluationStatus.FAILED
        assert api_exec == ExecutionStatus.RUNNING, '兄弟路由执行态不得被写成 completed'
        assert api_status == TaskCaseStatus.RUNNING    # 由 running+failed 派生
        _assert_sibling_untouched(acl)

    def test_group_failure_carries_tc_rel_id_and_no_execution_status(self, acl):
        """组维度失败写回：带 tc_rel_id、execution_status=None，设备侧不受影响。"""
        proc = DimensionResultMixin()
        proc._log = lambda **kw: None

        proc._mark_group_case_failed(
            TASK_ID, CASE_ID, '维度评估失败', tc_rel_id=API_ROW_ID)

        assert len(acl.calls) == 1
        call = acl.calls[0]
        assert call['tc_rel_id'] == API_ROW_ID
        assert not call['execution_status']
        assert acl.rows[API_ROW_ID].evaluation_status == EvaluationStatus.FAILED
        _assert_sibling_untouched(acl)


class TestReevaluationWriteback:

    def _run_reevaluate_single(self, acl):
        from evaluation_service.application.handlers import reevaluation_executor as reexec_mod

        with patch.object(reexec_mod, 'evaluation_service') as eval_svc, \
                patch.object(reexec_mod.evaluation_dimension_repository,
                             'delete_scores_by_result_id', MagicMock(return_value=0)), \
                patch('evaluation_service.infrastructure.acl.algorithm_acl_repository'
                      '.algorithm_acl_repository') as algo_acl:
            eval_svc.evaluate_case.return_value = False   # 无维度可提交 → 触发回滚
            algo_acl.extract_case_all_params.return_value = {'evaluation': {}}
            ex = reexec_mod.ReevaluationExecutor()
            ex._reevaluate_single(
                task_id=TASK_ID, result_id=API_RESULT_ID, test_case_id=CASE_ID,
                algorithm_result={'output': {}}, reference_params=[],
                device_type='http_api', algorithm_type='translation',
                reevaluate_type='all',
            )

    def test_reevaluation_only_touches_its_own_route_row(self, acl):
        """重评（置 queued + 无维度回滚）只命中 API 行，设备侧行三态不变。"""
        self._run_reevaluate_single(acl)

        assert acl.calls, '重评路径必须写回 task_case_relations'
        for call in acl.calls:
            assert call['tc_rel_id'] == API_ROW_ID
            assert not call['execution_status']
            assert not call['status'], '复合 status 不得直写（由 task_service 派生）'
        api_exec, api_eval, api_status = acl.snapshot(API_ROW_ID)
        assert api_eval == EvaluationStatus.COMPLETED   # 回滚落评估终态
        assert api_exec == ExecutionStatus.RUNNING
        assert api_status == TaskCaseStatus.RUNNING
        _assert_sibling_untouched(acl)


class TestRetryQueueKeepsRouteIdentity:

    @staticmethod
    def _queue():
        queue = TaskStatusRetryQueue()
        queue._ensure_worker_locked = lambda: None
        queue._arm_locked = lambda item: None
        return queue

    def test_same_case_routes_enqueue_separately(self):
        """同用例的两条路由行各自保留待补写项，互不覆盖；旧口径键保持不变。"""
        queue = self._queue()
        queue.enqueue_case_status(TASK_ID, CASE_ID, '', EvaluationStatus.FAILED,
                                  tc_rel_id=DEVICE_ROW_ID)
        queue.enqueue_case_status(TASK_ID, CASE_ID, '', EvaluationStatus.FAILED,
                                  tc_rel_id=API_ROW_ID)

        assert set(queue._pending_case) == {
            (TASK_ID, CASE_ID, DEVICE_ROW_ID),
            (TASK_ID, CASE_ID, API_ROW_ID),
        }
        assert queue._pending_case[(TASK_ID, CASE_ID, API_ROW_ID)].tc_rel_id == API_ROW_ID

        # 未带路由行的旧调用仍是 (task, case) 键（零回归）
        queue.enqueue_case_status(TASK_ID, 'legacy-case', 'failed', EvaluationStatus.FAILED)
        assert (TASK_ID, 'legacy-case') in queue._pending_case
