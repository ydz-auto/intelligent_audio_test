# -*- coding: utf-8 -*-
"""INT-364 回归守卫：failed 重评清理幽灵失败逐轮行 + 逐轮失败兜底整体重评
+ 无维度可提交时回滚用例状态

对齐 V9.7.10 f02ba75e（按 V9.7.31 微服务结构重写，不照抄单体）：
1. 幽灵行清理：failed 型重评收集失败维度后、提交评估前，删除待重评维度的历史
   失败逐轮行（round_number 非空且 failed）——E2E 每轮未配评估维度 + per_round
   投影残留 failed 行场景下，用例不再被幽灵行永久判 failed；整体行与已通过
   逐轮行保留；
2. 逐轮失败兜底：失败维度只存在于逐轮 TRD（整体 per_round 投影写回）且逐轮
   分支全部未提交时，整体评估取逐轮失败维度并集兜底提交（防用例卡 queued
   无人提交）；
3. 无维度可提交回滚：评估入口未提交评估（如无维度跳过路径收尾失效）时，
   仍停留 queued/pending 的用例回滚为终态（failed 型→failed，其余→completed），
   评估入口已收尾（终态）的用例不触碰。
"""
import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

from evaluation_service.application.handlers import reevaluation_executor as reexec_module
from evaluation_service.application.handlers.reevaluation_executor import ReevaluationExecutor
from evaluation_service.infrastructure.persistence.evaluation_dimension_repository import (
    EvaluationDimensionRepository,
)
from evaluation_service.infrastructure.acl import task_acl_repository
from shared.utils.status_constants import (
    EvaluationStatus, ExecutionStatus, TaskCaseStatus,
)

# 导入 evaluation_service 相关模块后清理残留的 scoped session（仓库既有测试同款兜底）
from shared.models.database import remove_db_session as _remove_db_session
_remove_db_session()


# ==================== 公共构造 ====================

def _trd(dim_id, round_number, evaluation_status, error_message=None):
    """TestResultDimension 形状的对象（无需真实 ORM）"""
    return SimpleNamespace(
        id=dim_id * 100 + (round_number or 0),
        test_result_id=11,
        dimension_id=dim_id,
        round_number=round_number,
        evaluation_status=evaluation_status,
        error_message=error_message,
    )


@pytest.fixture
def patched_acl():
    """重评执行器依赖的 ACL/评估服务桩"""
    with patch.object(task_acl_repository, 'get_task_case_by_ids', MagicMock(return_value=[
        SimpleNamespace(test_case_id='c1', device_type='physical',
                        execution_status=ExecutionStatus.COMPLETED,
                        evaluation_status=EvaluationStatus.FAILED),
    ])) as get_tc, \
    patch.object(task_acl_repository, 'update_task_case_status', MagicMock(return_value=True)) as upd_tc, \
    patch.object(task_acl_repository, 'get_test_case_detail', MagicMock(return_value=SimpleNamespace(
        config={'rounds': [
            {'evaluation': {'dimensions': [{'id': 7}, {'id': 9}]}},
            {'evaluation': {'dimensions': [{'id': 8}]}},
        ], 'dimensions': []},
        algorithm_params=None, reference_params=None, algorithm_type='translation',
    ))) as get_detail, \
    patch.object(reexec_module.evaluation_dimension_repository, 'list_scores_by_result_id',
                 MagicMock(return_value=[])) as list_scores, \
    patch.object(reexec_module.evaluation_dimension_repository, 'delete_scores_by_result_id',
                 MagicMock(return_value=0)) as del_scores, \
    patch.object(reexec_module.evaluation_dimension_repository, 'delete_failed_round_scores',
                 MagicMock(return_value=0)) as del_ghost, \
    patch.object(reexec_module.evaluation_dimension_repository,
                 'mark_active_scores_failed_excluding_rounds',
                 MagicMock(return_value=0)) as sweep, \
    patch('evaluation_service.infrastructure.acl.algorithm_acl_repository.algorithm_acl_repository',
          **{'extract_case_all_params.return_value': {'evaluation': {}}}) as algo_acl:
        yield SimpleNamespace(
            get_tc=get_tc, upd_tc=upd_tc, get_detail=get_detail,
            list_scores=list_scores, del_scores=del_scores, algo_acl=algo_acl,
            sweep=sweep, del_ghost=del_ghost,
        )


# ==================== 1. 幽灵行清理（failed 重评） ====================

class TestGhostRoundRowCleanup:

    def test_failed_reeval_deletes_stale_failed_round_rows(self, patched_acl):
        """failed 重评：待重评维度的历史失败逐轮行在提交前删除"""
        patched_acl.list_scores.return_value = [
            _trd(7, 0, EvaluationStatus.FAILED, 'mock fail'),
            _trd(9, 0, EvaluationStatus.COMPLETED),
            _trd(8, 1, EvaluationStatus.FAILED, 'mock fail'),
            _trd(12, None, EvaluationStatus.FAILED, 'overall fail'),
        ]
        patched_acl.del_ghost.return_value = 3

        ex = ReevaluationExecutor()
        with patch.object(reexec_module, 'evaluation_service') as eval_svc:
            eval_svc.evaluate_case.return_value = True

            ok = ex._reevaluate_multi_round(
                task_id=1, result=11, test_case_id='c1',
                algorithm_result={'rounds': [{'output': {}}, {'output': {}}]},
                device_type='physical', algorithm_type='translation',
                reevaluate_type='failed',
            )

        assert ok is True
        patched_acl.del_ghost.assert_called_once_with(11, {7, 8, 12})
        # 提交链照常（幽灵行删除不影响评估提交）
        assert eval_svc.evaluate_case.call_count >= 2

    def test_completed_round_rows_not_deleted(self, patched_acl):
        """已通过逐轮行（completed）不在删除维度集合限定外——只删待重评维度的失败行"""
        patched_acl.list_scores.return_value = [
            _trd(7, 0, EvaluationStatus.FAILED, 'mock fail'),
            _trd(99, 0, EvaluationStatus.FAILED, '非待重评维度'),  # dim 99 不在失败集
        ]
        # list_scores 已过滤出失败集 {7}；99 行是 COMPLETED 维度（不在失败集合内）
        patched_acl.list_scores.return_value = [
            _trd(7, 0, EvaluationStatus.FAILED, 'mock fail'),
            _trd(9, 0, EvaluationStatus.COMPLETED),
        ]

        ex = ReevaluationExecutor()
        with patch.object(reexec_module, 'evaluation_service') as eval_svc:
            eval_svc.evaluate_case.return_value = True
            ex._reevaluate_multi_round(
                task_id=1, result=11, test_case_id='c1',
                algorithm_result={'rounds': [{'output': {}}]},
                device_type='physical', algorithm_type='translation',
                reevaluate_type='failed',
            )

        # 删除限定失败维度并集 {7}——completed 行（dim 9）不在集合内天然保留
        patched_acl.del_ghost.assert_called_once_with(11, {7})

    def test_no_failed_dims_skips_ghost_cleanup(self, patched_acl):
        """无失败维度 → 跳过重评，不触发幽灵行删除"""
        patched_acl.list_scores.return_value = [
            _trd(7, 0, EvaluationStatus.COMPLETED),
        ]
        ex = ReevaluationExecutor()
        with patch.object(reexec_module, 'evaluation_service') as eval_svc:
            ok = ex._reevaluate_multi_round(
                task_id=1, result=11, test_case_id='c1',
                algorithm_result={'rounds': [{'output': {}}]},
                device_type='physical', algorithm_type='translation',
                reevaluate_type='failed',
            )

        assert ok is False
        patched_acl.del_ghost.assert_not_called()
        eval_svc.evaluate_case.assert_not_called()

    def test_all_type_full_delete_only(self, patched_acl):
        """全量重评（all）走 delete_scores_by_result_id，不走幽灵行删除"""
        ex = ReevaluationExecutor()
        with patch.object(reexec_module, 'evaluation_service') as eval_svc:
            eval_svc.evaluate_case.return_value = True
            ex._reevaluate_multi_round(
                task_id=1, result=11, test_case_id='c1',
                algorithm_result={'rounds': [{'output': {}}]},
                device_type='physical', algorithm_type='translation',
                reevaluate_type='all',
            )

        patched_acl.del_scores.assert_called_once_with(11)
        patched_acl.del_ghost.assert_not_called()

    def test_ghost_deletion_zero_count_still_proceeds(self, patched_acl):
        """无幽灵行（删除 0 条）不阻断重评提交"""
        patched_acl.list_scores.return_value = [
            _trd(7, 0, EvaluationStatus.FAILED, 'mock fail'),
        ]
        patched_acl.del_ghost.return_value = 0

        ex = ReevaluationExecutor()
        with patch.object(reexec_module, 'evaluation_service') as eval_svc:
            eval_svc.evaluate_case.return_value = True

            ok = ex._reevaluate_multi_round(
                task_id=1, result=11, test_case_id='c1',
                algorithm_result={'rounds': [{'output': {}}]},
                device_type='physical', algorithm_type='translation',
                reevaluate_type='failed',
            )

        assert ok is True
        eval_svc.evaluate_case.assert_called()


# ==================== 2. 逐轮失败兜底走整体重评 ====================

class TestPerRoundFailureOverallFallback:

    def test_round_only_failure_falls_back_to_overall(self, patched_acl):
        """失败维度只在逐轮 TRD、逐轮全未提交（每轮未配评估维度）→ 整体兜底提交"""
        patched_acl.list_scores.return_value = [
            _trd(12, 0, EvaluationStatus.FAILED, 'ghost round fail'),
            _trd(12, 1, EvaluationStatus.FAILED, 'ghost round fail'),
        ]
        # 每轮未配置逐轮评估维度，只有顶层整体维度 12
        with patch.object(task_acl_repository, 'get_test_case_detail', MagicMock(return_value=SimpleNamespace(
                config={'rounds': [{'evaluation': {'dimensions': []}}, {'evaluation': {'dimensions': []}}],
                        'dimensions': [{'id': 12}]},
                algorithm_params=None, reference_params=None, algorithm_type='translation'))):
            ex = ReevaluationExecutor()
            with patch.object(reexec_module, 'evaluation_service') as eval_svc:
                eval_svc.evaluate_case.return_value = True

                ok = ex._reevaluate_multi_round(
                    task_id=1, result=11, test_case_id='c1',
                    algorithm_result={'rounds': [{'output': {}}, {'output': {}}]},
                    device_type='physical', algorithm_type='translation',
                    reevaluate_type='failed',
                )

        assert ok is True
        # 逐轮分支全部 continue（未配维度），整体分支兜底提交，过滤=逐轮失败维度并集
        overall_calls = [c for c in eval_svc.evaluate_case.call_args_list if 'round_number' not in c.kwargs]
        assert len(overall_calls) == 1
        assert overall_calls[0].kwargs['dimension_filter_ids'] == [12]
        round_calls = [c for c in eval_svc.evaluate_case.call_args_list if 'round_number' in c.kwargs]
        assert round_calls == []

    def test_overall_failed_present_no_fallback_needed(self, patched_acl):
        """整体口径本身有失败维度：直接按 None 键过滤提交（不进入兜底分支）"""
        patched_acl.list_scores.return_value = [
            _trd(12, None, EvaluationStatus.FAILED, 'overall fail'),
            _trd(7, 0, EvaluationStatus.FAILED, 'round fail'),
        ]
        with patch.object(task_acl_repository, 'get_test_case_detail', MagicMock(return_value=SimpleNamespace(
                config={'rounds': [{'evaluation': {'dimensions': [{'id': 7}]}}],
                        'dimensions': [{'id': 12}]},
                algorithm_params=None, reference_params=None, algorithm_type='translation'))):
            ex = ReevaluationExecutor()
            with patch.object(reexec_module, 'evaluation_service') as eval_svc:
                eval_svc.evaluate_case.return_value = True

                ok = ex._reevaluate_multi_round(
                    task_id=1, result=11, test_case_id='c1',
                    algorithm_result={'rounds': [{'output': {}}]},
                    device_type='physical', algorithm_type='translation',
                    reevaluate_type='failed',
                )

        assert ok is True
        overall_calls = [c for c in eval_svc.evaluate_case.call_args_list if 'round_number' not in c.kwargs]
        # 整体只按 None 键失败维度 [12]，不混入逐轮失败 7
        assert overall_calls[0].kwargs['dimension_filter_ids'] == [12]

    def test_round_submitted_no_overall_fallback(self, patched_acl):
        """逐轮已有提交（round 0 正常提交）：整体无 None 键失败维度 → 仍跳过整体"""
        patched_acl.list_scores.return_value = [
            _trd(7, 0, EvaluationStatus.FAILED, 'round fail'),
            _trd(12, 1, EvaluationStatus.FAILED, 'ghost round fail'),
        ]
        with patch.object(task_acl_repository, 'get_test_case_detail', MagicMock(return_value=SimpleNamespace(
                config={'rounds': [
                    {'evaluation': {'dimensions': [{'id': 7}]}},
                    {'evaluation': {'dimensions': []}},
                ], 'dimensions': [{'id': 12}]},
                algorithm_params=None, reference_params=None, algorithm_type='translation'))):
            ex = ReevaluationExecutor()
            with patch.object(reexec_module, 'evaluation_service') as eval_svc:
                eval_svc.evaluate_case.return_value = True

                ok = ex._reevaluate_multi_round(
                    task_id=1, result=11, test_case_id='c1',
                    algorithm_result={'rounds': [{'output': {}}, {'output': {}}]},
                    device_type='physical', algorithm_type='translation',
                    reevaluate_type='failed',
                )

        assert ok is True
        overall_calls = [c for c in eval_svc.evaluate_case.call_args_list if 'round_number' not in c.kwargs]
        assert overall_calls == []  # 逐轮已提交 round 0，整体不兜底

    def test_all_type_selection_no_fallback(self, patched_acl):
        """INT-302 维度选择链路不受兜底影响：selection 过滤直通整体"""
        with patch.object(task_acl_repository, 'get_test_case_detail', MagicMock(return_value=SimpleNamespace(
                config={'rounds': [{'evaluation': {'dimensions': []}}],
                        'dimensions': [{'id': 12}]},
                algorithm_params=None, reference_params=None, algorithm_type='translation'))):
            ex = ReevaluationExecutor()
            with patch.object(reexec_module, 'evaluation_service') as eval_svc:
                eval_svc.evaluate_case.return_value = True

                ok = ex._reevaluate_multi_round(
                    task_id=1, result=11, test_case_id='c1',
                    algorithm_result={'rounds': [{'output': {}}]},
                    device_type='physical', algorithm_type='translation',
                    reevaluate_type='all',
                    dimension_filter_ids=[12],
                )

        assert ok is True
        overall_calls = [c for c in eval_svc.evaluate_case.call_args_list if 'round_number' not in c.kwargs]
        assert len(overall_calls) == 1
        assert overall_calls[0].kwargs['dimension_filter_ids'] == [12]


# ==================== 3. 无维度可提交时回滚用例状态 ====================

class TestRollbackCaseIfStuckQueued:

    def test_failed_type_rolls_back_to_failed(self, patched_acl):
        """failed 型重评未提交：仍 queued 的用例回滚为 failed 终态"""
        patched_acl.get_tc.return_value = [
            SimpleNamespace(test_case_id='c1', execution_status=ExecutionStatus.COMPLETED,
                            evaluation_status=EvaluationStatus.QUEUED),
        ]

        ex = ReevaluationExecutor()
        ex._rollback_case_if_stuck_queued(1, 'c1', reevaluate_type='failed')

        patched_acl.upd_tc.assert_called_once()
        kwargs = patched_acl.upd_tc.call_args.kwargs
        assert kwargs['task_id'] == 1
        assert kwargs['case_id'] == 'c1'
        assert kwargs['evaluation_status'] == EvaluationStatus.FAILED
        assert kwargs['status'] == TaskCaseStatus.FAILED
        assert '回滚' in (kwargs.get('error_message') or '')

    def test_non_failed_type_rolls_back_to_completed(self, patched_acl):
        """非 failed 型（全量重评）未提交：仍 queued 的用例回滚为 completed 终态"""
        patched_acl.get_tc.return_value = [
            SimpleNamespace(test_case_id='c1', execution_status=ExecutionStatus.COMPLETED,
                            evaluation_status=EvaluationStatus.PENDING),
        ]

        ex = ReevaluationExecutor()
        ex._rollback_case_if_stuck_queued(1, 'c1', reevaluate_type='all')

        kwargs = patched_acl.upd_tc.call_args.kwargs
        assert kwargs['evaluation_status'] == EvaluationStatus.COMPLETED
        assert kwargs['status'] == TaskCaseStatus.COMPLETED

    def test_terminal_case_not_touched(self, patched_acl):
        """评估入口已收尾（终态）的用例不触碰"""
        patched_acl.get_tc.return_value = [
            SimpleNamespace(test_case_id='c1', execution_status=ExecutionStatus.COMPLETED,
                            evaluation_status=EvaluationStatus.COMPLETED),
        ]

        ex = ReevaluationExecutor()
        ex._rollback_case_if_stuck_queued(1, 'c1', reevaluate_type='failed')

        patched_acl.upd_tc.assert_not_called()

    def test_running_case_not_touched(self, patched_acl):
        """评估在途（running）的用例不触碰（避免误杀在途评估）"""
        patched_acl.get_tc.return_value = [
            SimpleNamespace(test_case_id='c1', execution_status=ExecutionStatus.COMPLETED,
                            evaluation_status=EvaluationStatus.RUNNING),
        ]

        ex = ReevaluationExecutor()
        ex._rollback_case_if_stuck_queued(1, 'c1', reevaluate_type='failed')

        patched_acl.upd_tc.assert_not_called()

    def test_single_path_invokes_rollback_on_no_submit(self, patched_acl):
        """单轮链：evaluate_case 返回 False（无维度提交）→ 触发回滚"""
        patched_acl.list_scores.return_value = [
            _trd(7, None, EvaluationStatus.FAILED, 'mock fail'),
        ]
        ex = ReevaluationExecutor()
        with patch.object(reexec_module, 'evaluation_service') as eval_svc, \
             patch.object(ex, '_rollback_case_if_stuck_queued') as rollback, \
             patch.object(ex, '_sweep_out_of_scope_active_scores') as sweep:
            eval_svc.evaluate_case.return_value = False
            # 评估入口无维度跳过路径未收尾（TaskCase 仍 queued）
            patched_acl.get_tc.return_value = [
                SimpleNamespace(test_case_id='c1', execution_status=ExecutionStatus.COMPLETED,
                                evaluation_status=EvaluationStatus.QUEUED),
            ]

            submitted = ex._reevaluate_single(
                task_id=1, result_id=11, test_case_id='c1',
                algorithm_result={'output': {}}, reference_params=[],
                device_type='http_api', algorithm_type='translation',
                reevaluate_type='failed',
            )

        assert submitted is False
        sweep.assert_called_once()
        rollback.assert_called_once_with(1, 'c1', reevaluate_type='failed')

    def test_single_path_no_rollback_on_submit(self, patched_acl):
        """单轮链：提交成功 → 不触发回滚"""
        patched_acl.list_scores.return_value = [
            _trd(7, None, EvaluationStatus.FAILED, 'mock fail'),
        ]
        ex = ReevaluationExecutor()
        with patch.object(reexec_module, 'evaluation_service') as eval_svc, \
             patch.object(ex, '_rollback_case_if_stuck_queued') as rollback:
            eval_svc.evaluate_case.return_value = True

            submitted = ex._reevaluate_single(
                task_id=1, result_id=11, test_case_id='c1',
                algorithm_result={'output': {}}, reference_params=[],
                device_type='http_api', algorithm_type='translation',
                reevaluate_type='failed',
            )

        assert submitted is True
        rollback.assert_not_called()


# ==================== 4. Repository.delete_failed_round_scores ====================

class TestDeleteFailedRoundScoresRepo:
    """仓储方法 SQL 语义单测（conftest 进程级临时 sqlite 文件库）"""

    @pytest.fixture(autouse=True)
    def _init_db(self):
        from shared.models.database import init_db, Base, get_engine
        from evaluation_service.infrastructure.persistence.models.result_models import (
            TestResultDimension,
        )
        init_db()
        Base.metadata.create_all(get_engine(), tables=[TestResultDimension.__table__])
        self._model = TestResultDimension
        yield

    def test_deletes_only_failed_round_rows_of_given_dims(self):
        TestResultDimension = self._model
        from shared.models.database import get_db_session

        session = get_db_session()
        try:
            session.add_all([
                # 幽灵行：逐轮失败（会被删）
                TestResultDimension(id=1, test_result_id=11, dimension_id=7, round_number=0,
                                    evaluation_status='failed', error_message='ghost'),
                TestResultDimension(id=2, test_result_id=11, dimension_id=7, round_number=1,
                                    evaluation_status='failed', error_message='ghost'),
                # 已通过逐轮行（保留）
                TestResultDimension(id=3, test_result_id=11, dimension_id=7, round_number=2,
                                    evaluation_status='completed'),
                # 整体行 failed（round_number IS NULL，保留——由评估入口复用重置）
                TestResultDimension(id=4, test_result_id=11, dimension_id=7, round_number=None,
                                    evaluation_status='failed', error_message='overall'),
                # 非指定维度的逐轮失败行（保留）
                TestResultDimension(id=5, test_result_id=11, dimension_id=99, round_number=0,
                                    evaluation_status='failed'),
                # 其他 result 的同维度失败行（保留）
                TestResultDimension(id=6, test_result_id=22, dimension_id=7, round_number=0,
                                    evaluation_status='failed'),
            ])
            session.commit()
        finally:
            session.close()

        repo = EvaluationDimensionRepository()
        deleted = repo.delete_failed_round_scores(11, {7})

        assert deleted == 2
        session = get_db_session()
        try:
            rows = session.query(TestResultDimension).filter(
                TestResultDimension.test_result_id.in_([11, 22])).all()
            by_key = {(r.test_result_id, r.dimension_id, r.round_number): r.evaluation_status
                      for r in rows}
            # 幽灵行已删
            assert (11, 7, 0) not in by_key
            assert (11, 7, 1) not in by_key
            # 保留项完好
            assert by_key[(11, 7, 2)] == 'completed'
            assert by_key[(11, 7, None)] == 'failed'
            assert by_key[(11, 99, 0)] == 'failed'
            assert by_key[(22, 7, 0)] == 'failed'
        finally:
            # 清理本用例数据（内存库随进程销毁，此处仅保持会话整洁）
            session.query(TestResultDimension).filter(
                TestResultDimension.test_result_id.in_([11, 22])).delete(
                synchronize_session=False)
            session.commit()
            session.close()
