# -*- coding: utf-8 -*-
"""INT-169 回归守卫：EvaluateCase 幂等复用路径 DimensionScore.id + 评估提交失败口径

缺陷背景（INT-95 第 8 轮实机验收，任务 486）：
- DimensionScore 领域实体不含持久化字段 id，dimension_result_recorder 幂等
  复用路径访问 existing.id 必 AttributeError，重复评估（per_round 覆盖产生的
  TRD 行 / Reevaluate 链）崩掉整个用例（E2E 执行真实成功却被判执行失败）。

锁定两部分：
1. 评估侧：DimensionScore 实体补持久化主键 id（Repository 从 PO 加载时填充），
   recorder 幂等复用路径按主键复用/重置不再 AttributeError；
2. 执行侧（对齐 INT-123 API 链口径）：_evaluate_result 提交失败以专用
   EvaluationSubmitError 上抛；E2E 单轮/整体评估提交失败不中止执行链、
   不判执行失败，收尾以 evaluation_status=FAILED 终态承载。
"""
import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

from evaluation_service.domain.entities import DimensionScore
from evaluation_service.domain.services.evaluation_service.dimension_result_recorder import (
    DimensionResultRecorderMixin,
)
from evaluation_service.infrastructure.persistence.evaluation_dimension_repository import (
    _trd_po_to_entity,
)
from shared.infrastructure.base_executor import EvaluationSubmitError
from shared.infrastructure.base_executor._results_mixin import ResultsMixin
from shared.utils.status_constants import EvaluationStatus

# 导入 evaluation_service 相关模块后清理残留的 scoped session（仓库既有测试同款兜底）
from shared.models.database import remove_db_session as _remove_db_session
_remove_db_session()


# ==================== 1. DimensionScore 实体持久化主键 ====================

def _trd_po(**kwargs):
    """构造 TestResultDimension PO 形状的对象（无需真实 ORM）"""
    defaults = dict(
        id=42,
        test_result_id=99,
        dimension_id=7,
        algorithm_type='voice_llm',
        round_number=1,
        dimension_value=None,
        score=None,
        status=None,
        evaluation_status=EvaluationStatus.PENDING,
        error_message=None,
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


class TestDimensionScoreEntityId:

    def test_trd_po_to_entity_fills_id(self):
        """Repository 从 PO 加载时必须填充持久化主键 id（INT-169 根因点）"""
        entity = _trd_po_to_entity(_trd_po(id=42))
        assert entity.id == 42
        assert entity.test_result_id == 99
        assert entity.dimension_id == 7
        assert entity.round_number == 1

    def test_new_entity_id_defaults_to_none(self):
        """新建未落库实体 id 为 None（create_score 不依赖实体 id）"""
        score = DimensionScore(test_result_id=99, dimension_id=7, algorithm_type='v')
        assert score.id is None


# ==================== 2. recorder 幂等复用路径 ====================

class _RecorderHost(DimensionResultRecorderMixin):
    def __init__(self, repo):
        self._evaluation_dimension_repo = repo
        self._task_acl_repo = MagicMock()
        self.logs = []

    def _log(self, **kwargs):
        self.logs.append(kwargs)


def _run_create(host, round_number=1):
    return host._create_dimension_results(
        [{'id': 7, 'name': 'dim-a'}], result_id=99, task_id='t1', test_case_id='c1',
        algorithm_type='voice_llm', kwargs={'round_number': round_number},
    )


class TestRecorderIdempotentReuse:

    def test_reuse_completed_record_no_attribute_error(self):
        """已存在 completed 记录：按实体 id 复用并重置 pending，不再 AttributeError。

        INT-95 第 8 轮事故场景：round-0 评估响应经 per_round 覆盖已创建
        round-1 TRD 行，round-1 独立 EvaluateCase 提交命中复用路径。
        """
        repo = MagicMock()
        repo.find_score.return_value = DimensionScore(
            id=42, test_result_id=99, dimension_id=7, algorithm_type='voice_llm',
            round_number=1, evaluation_status=EvaluationStatus.COMPLETED,
        )
        host = _RecorderHost(repo)

        result_map = _run_create(host)

        assert result_map == {7: 42}
        repo.find_score.assert_called_once_with(99, 7, 1)
        repo.reset_score_to_pending.assert_called_once_with(42)

    def test_reuse_pending_record_keeps_pending(self):
        """已存在 pending 记录：直接复用，不重复重置"""
        repo = MagicMock()
        repo.find_score.return_value = DimensionScore(
            id=42, test_result_id=99, dimension_id=7, algorithm_type='voice_llm',
            round_number=1, evaluation_status=EvaluationStatus.PENDING,
        )
        host = _RecorderHost(repo)

        result_map = _run_create(host)

        assert result_map == {7: 42}
        repo.reset_score_to_pending.assert_not_called()

    def test_no_existing_record_creates_new(self):
        """无已有记录：走创建路径（行为不变）"""
        repo = MagicMock()
        repo.find_score.return_value = None
        repo.create_score_with_commit.return_value = 43
        host = _RecorderHost(repo)

        result_map = _run_create(host)

        assert result_map == {7: 43}
        repo.create_score_with_commit.assert_called_once()

    def test_overall_round_none_reuse(self):
        """整体评估（round_number=None）的复用路径同样按主键工作"""
        repo = MagicMock()
        repo.find_score.return_value = DimensionScore(
            id=51, test_result_id=99, dimension_id=7, algorithm_type='voice_llm',
            round_number=None, evaluation_status=EvaluationStatus.FAILED,
        )
        host = _RecorderHost(repo)

        result_map = _run_create(host, round_number=None)

        assert result_map == {7: 51}
        repo.find_score.assert_called_once_with(99, 7, None)
        repo.reset_score_to_pending.assert_called_once_with(51)


# ==================== 3. 评估提交失败口径（E2E 执行链） ====================

class _ResultsHost(ResultsMixin):
    def __init__(self, submit_side_effect):
        self._task_data_acl = MagicMock()
        self._task_data_acl.submit_evaluate_case.side_effect = submit_side_effect
        self._algo_acl = MagicMock()
        self._algo_acl.extract_case_all_params.return_value = {'evaluation': {}}
        self.logs = []

    def _get_task_data_acl(self):
        return self._task_data_acl

    def _get_algorithm_acl(self):
        return self._algo_acl

    def _log(self, **kwargs):
        self.logs.append(kwargs)


class TestEvaluateResultWrapsSubmitFailure:

    def test_submit_failure_raises_evaluation_submit_error(self):
        """_evaluate_result 把提交异常包装为 EvaluationSubmitError（保留原始信息）"""
        host = _ResultsHost(
            RuntimeError("EvaluateCase gRPC 调用失败: 'DimensionScore' object has no attribute 'id'"))

        with pytest.raises(EvaluationSubmitError,
                           match="EvaluateCase gRPC 调用失败: 'DimensionScore' object"):
            host._evaluate_result(
                task_id='t1', result_id=99, test_case_id='c1',
                algo_result={'rounds': []}, case_config={},
                case_reference_params=None, algorithm_type='voice_llm',
                device_type='physical', round_number=0,
            )

    def test_submit_success_not_wrapped(self):
        host = _ResultsHost(None)
        host._evaluate_result(
            task_id='t1', result_id=99, test_case_id='c1',
            algo_result={'rounds': []}, case_config={},
            case_reference_params=None, algorithm_type='voice_llm',
            device_type='physical', round_number=0,
        )
        host._task_data_acl.submit_evaluate_case.assert_called_once()


def _executor_host():
    """E2EExecutor 最小宿主（同 test_int158 的 __new__ 模式）"""
    from e2e_test_service.application.services.e2e_executor.executor import E2EExecutor
    ex = E2EExecutor.__new__(E2EExecutor)
    ex._aggregator = MagicMock()
    ex._task_data_repo = MagicMock()
    ex._device_repo = MagicMock()
    ex._playback_repo = MagicMock()
    ex._playback_repo.start_background_noise.return_value = None
    ex._playback_repo.stop_background_noise.return_value = None
    ex._thread_ctx = SimpleNamespace()
    ex._eval_submit_failures = []
    ex.logs = []
    return ex


class TestRoundEvalSubmitFailureContinues:

    def test_round_submit_failure_returns_round_data(self):
        """单轮评估提交失败：不中止本轮，round_data 正常返回并留痕"""
        import e2e_test_service.application.services.e2e_executor.rounds_loop_mixin as loop_mod

        ex = _executor_host()
        ex._log = MagicMock()
        ex._evaluate_result = MagicMock(
            side_effect=EvaluationSubmitError('EvaluateCase gRPC 调用失败: grpc down'))
        with patch.object(loop_mod, 'E2ECalculationService', MagicMock()):
            round_data = ex._build_and_submit_round_data(
                task_id='t1', tc_rel_id='tc1',
                data={'case_algorithm_params': None},
                case_config={'rounds': [{'round_number': 1, 'audios': [],
                                         'evaluation': {'dimensions': [{'id': 7}]}}]},
                case_name='case-x', algorithm_type='voice_llm', test_case_id='c1',
                rounds=[{'round_number': 1, 'audios': []}],
                result_id=99, case_reference_params=None,
                round_idx=0, primary={'success': True},
                tagged_results=[{'success': True}],
                rounds_data=[], round_algo_params={},
            )

        assert round_data is not None
        assert len(ex._eval_submit_failures) == 1
        assert '第 1 轮评估提交失败' in ex._eval_submit_failures[0]


class TestOverallEvalSubmitFailureCompletes:

    _ARGS = dict(
        task_id='t1', tc_rel_id='tc1', data={}, case_name='case-x',
        algorithm_type='voice_llm', test_case_id='c1', result_ids={1: 99},
        all_round_results=[{'response_time': 100}],
        case_reference_params=None, last_adjusted_ref_params=None,
        device_info_list=None,
    )

    def test_overall_submit_failure_does_not_abort_finalize(self):
        """整体评估提交失败：聚合与 TaskCase 状态更新照常完成，失败留痕"""
        import e2e_test_service.application.services.e2e_executor.finalization_mixin as fin_mod

        ex = _executor_host()
        ex._log = MagicMock()
        ex._handle_control = MagicMock()
        ex._evaluate_result = MagicMock(
            side_effect=EvaluationSubmitError('EvaluateCase gRPC 调用失败: grpc down'))
        ex._aggregator.build_algorithm_result.return_value = {'rounds': [{'output': {}}]}
        ex._aggregator.process_results.return_value = True

        config = {'rounds': [{'round_number': 1, 'audios': [], 'evaluation': {'dimensions': []}}],
                  'dimensions': [{'id': 7}]}
        with patch.object(fin_mod, 'write_result_data_file', MagicMock(return_value=None)):
            success = ex._finalize_rounds(case_config=config, execution_success=True, **self._ARGS)

        assert success is True
        ex._aggregator.process_results.assert_called_once()
        assert len(ex._eval_submit_failures) == 1
        # 组执行收口带设备上下文：整体评估提交失败(device_id=1): ...
        assert '整体评估提交失败' in ex._eval_submit_failures[0]
        assert 'EvaluateCase gRPC 调用失败: grpc down' in ex._eval_submit_failures[0]


class TestEvalSubmitFailureClosure:

    def test_closure_writes_failed_eval_only(self):
        """收口：仅补 evaluation_status=FAILED 与留痕，不动 execution_status。

        契约（INT-169 审计 P1）：executor 不传 status/execution_status，由
        ACL 默认空 status 交 task_service 按 derive_task_case_status(completed,
        failed) 推导复合终态——真实 ACL 签名约束见 TestRealAclContract。
        """
        ex = _executor_host()
        ex._log = MagicMock()
        ex._eval_submit_failures = ['第 1 轮评估提交失败: boom']

        ex._finalize_eval_submit_failures('t1', 'c1')

        kwargs = ex._task_data_repo.update_task_case_status.call_args.kwargs
        assert kwargs['evaluation_status'] == EvaluationStatus.FAILED
        assert '第 1 轮评估提交失败: boom' in kwargs['error_message']
        assert 'execution_status' not in kwargs
        assert 'status' not in kwargs

    def test_closure_noop_without_failures(self):
        ex = _executor_host()
        ex._log = MagicMock()

        ex._finalize_eval_submit_failures('t1', 'c1')

        ex._task_data_repo.update_task_case_status.assert_not_called()

    def test_closure_write_error_swallowed(self):
        """收口写状态自身失败不外抛（收口路径不得再打断执行循环）"""
        ex = _executor_host()
        ex._log = MagicMock()
        ex._task_data_repo.update_task_case_status.side_effect = RuntimeError('grpc down')
        ex._eval_submit_failures = ['整体评估提交失败: boom']

        ex._finalize_eval_submit_failures('t1', 'c1')

        ex._log.assert_called()  # 留痕告警即可


class TestRealAclContract:
    """真实 ACL impl 契约（INT-169 审计 P1：mock 屏蔽签名失配，需直呼真实 impl）

    守卫：E2E ACL 的 update_task_case_status 必须与 task_service 服务端契约
    对齐——status 可缺省（空值由服务端推导复合状态），executor 收口调用形状
    （仅 task_id/case_id/evaluation_status/error_message）可直接调用。
    """

    _EXECUTOR_SHAPE = dict(
        task_id='123', case_id='456',
        evaluation_status=EvaluationStatus.FAILED,
        error_message='整体评估提交失败: boom',
    )

    def test_acl_signature_status_optional(self):
        """ABC 与 impl 的 status 均必须有默认值（审计 P1 根因点）"""
        import inspect
        from e2e_test_service.domain.repositories.task_data_acl_repository import (
            TaskDataAclRepository,
        )
        from e2e_test_service.infrastructure.acl.task_data_acl_repository_impl import (
            TaskDataAclRepositoryImpl,
        )
        for cls in (TaskDataAclRepository, TaskDataAclRepositoryImpl):
            param = inspect.signature(cls.update_task_case_status).parameters['status']
            assert param.default == '', f"{cls.__name__}.update_task_case_status 的 status 必须可缺省"

    def test_real_impl_accepts_executor_call_shape(self):
        """executor 收口调用形状直呼真实 impl：请求按空 status 组包成功（INT-169 审计 P1）"""
        from e2e_test_service.infrastructure.acl.task_data_acl_repository_impl import (
            TaskDataAclRepositoryImpl,
        )

        captured = {}

        class _FakeStub:
            def UpdateTaskCaseStatus(self, request):
                captured['request'] = request
                return SimpleNamespace(success=True, message='ok')

        impl = TaskDataAclRepositoryImpl()
        with patch('shared.clients.grpc_clients.get_task_data_service_stub',
                   return_value=_FakeStub()):
            ok = impl.update_task_case_status(**self._EXECUTOR_SHAPE)

        assert ok is True
        req = captured['request']
        assert req.status == ''
        assert req.evaluation_status == EvaluationStatus.FAILED
        assert req.error_message == '整体评估提交失败: boom'


_DATA = {
    'case_name': 'case-x',
    'case_config': {'rounds': [{'round_number': 1, 'audios': []}]},
    'case_reference_params': [],
    'test_case_id': 'c1',
    'algorithm_type': 'voice_llm',
}


class TestExecuteClosesEvalSubmitFailures:

    def test_success_case_with_eval_failure_not_marked_execution_failed(self):
        """端到端口径：评估提交失败时用例不被标执行失败，evaluation_status 终态收口"""
        ex = _executor_host()
        ex._log = MagicMock()
        ex._handle_control = MagicMock()
        ex._get_control_events = MagicMock(return_value=(None, None))
        ex._update_tc_rel_status = MagicMock()
        ex._prepare_rounds = MagicMock(return_value=([{'device_id': 1}], 99))

        def _fake_finalize(*args, **kwargs):
            ex._eval_submit_failures.append('整体评估提交失败: boom')
            return True
        ex._finalize_rounds = MagicMock(side_effect=_fake_finalize)
        ex._run_rounds_loop = MagicMock(return_value=([{'r': 1}], [{'r': 1}], True, None))

        ok = ex._execute_e2e_with_rounds('t1', 'tc1', dict(_DATA))

        assert ok is True
        kwargs = ex._task_data_repo.update_task_case_status.call_args.kwargs
        assert kwargs['evaluation_status'] == EvaluationStatus.FAILED
        assert 'execution_status' not in kwargs
        # 执行口径保持：TaskCase 状态从不写 execution FAILED
        for _, call_kwargs in ex._update_tc_rel_status.call_args_list:
            assert call_kwargs.get('execution_status') != 'failed'
