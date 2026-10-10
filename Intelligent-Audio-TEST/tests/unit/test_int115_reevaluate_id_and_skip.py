# -*- coding: utf-8 -*-
"""INT-115 守卫：任务级重评估链路 str task_id 归一 + 失败透出 + 无 mappings skipped 终态。

覆盖四组修复（均纯单测，不触真实 DB/gRPC/Redis）：

缺陷① 重评估链路 task_id 字符串化：
  evaluation_service.proto 的 ReevaluateRequest.task_id 为 string 契约，
  servicer 原样把 str 传入 executor，task_service protobuf int 字段构造时
  TypeError: 'str' object cannot be interpreted as an integer。
  修复后 servicer / executor.submit 边界归一为 int。

缺陷② ACL protobuf 构造未做 int 归一 + 失败被吞：
  task_acl_repository 构造 int 字段前统一归一（str '491' 可用）；
  归一失败在 try 块外抛 ValueError 透出，不再被兜底返回 []/False 掩盖。

缺陷③ 失败被 success=True 掩盖：
  查询不到任务且无测试结果时按失败收口（Task 置 FAILED），
  不再伪装成"没有需要重新评估的用例"；任务状态写失败升级 ERROR 可见。

缺陷④ INT-118 评估侧尾巴：
  _build_rounds_list 对无 evaluation param mappings 的算法类型，
  从 WARNING+整链静默跳过升级为 ERROR 告警 + TaskCase skipped 终态留痕。
"""
import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

import evaluation_service.infrastructure.acl as _acl_pkg
from shared.utils.id_normalizer import to_int_id
from shared.utils.status_constants import (
    TaskStatus, TaskCaseStatus, EvaluationStatus,
)
from evaluation_service.domain.services.evaluation_service.case_evaluation import (
    CaseEvaluationMixin,
)
from evaluation_service.domain.services.evaluation_service.round_data_builder import (
    RoundDataBuilderMixin,
)
from evaluation_service.infrastructure.acl.task_acl_repository import (
    TaskAclRepository, _norm_task_id,
)


# ============================================================
# 缺陷①前置：归一 helper
# ============================================================

class TestToIntId:
    def test_int_passthrough(self):
        assert to_int_id('task_id', 491) == 491

    def test_numeric_str(self):
        assert to_int_id('task_id', '491') == 491

    def test_empty_str_raises(self):
        with pytest.raises(ValueError, match='task_id'):
            to_int_id('task_id', '')

    def test_none_raises(self):
        with pytest.raises(ValueError, match='task_id'):
            to_int_id('task_id', None)

    def test_non_numeric_raises(self):
        with pytest.raises(ValueError, match='无法转换为整数'):
            to_int_id('task_id', 'abc')

    def test_field_name_in_error(self):
        with pytest.raises(ValueError, match='result_id'):
            to_int_id('result_id', 'xyz')


# ============================================================
# 缺陷②：ACL protobuf 构造 int 归一 + 失败透出
# ============================================================

class TestAclTaskIdNormalization:
    def _repo(self):
        return TaskAclRepository()

    def test_norm_helper_accepts_numeric_str(self):
        assert _norm_task_id('491') == 491

    def test_get_test_results_normalizes_str_task_id(self):
        """str task_id 不再触发 TypeError，protobuf 请求拿到 int。"""
        repo = self._repo()
        captured = {}
        stub = MagicMock()

        def _capture(req):
            captured['task_id'] = req.task_id
            resp = MagicMock()
            resp.success = False
            resp.message = 'stub: not found'
            return resp

        stub.GetTestResultsByTaskAndCase.side_effect = _capture
        with patch('evaluation_service.infrastructure.acl.task_acl_repository.get_task_data_service_stub',
                   return_value=stub):
            repo.get_test_results_by_task_and_case(task_id='491')

        assert captured['task_id'] == 491

    def test_update_task_status_normalizes_str_task_id(self):
        repo = self._repo()
        captured = {}
        stub = MagicMock()

        def _capture(req):
            captured['task_id'] = req.task_id
            resp = MagicMock()
            resp.success = True
            return resp

        stub.UpdateTaskStatus.side_effect = _capture
        with patch('evaluation_service.infrastructure.acl.task_acl_repository.get_task_data_service_stub',
                   return_value=stub):
            ok = repo.update_task_status('491', TaskStatus.COMPLETED)

        assert ok is True
        assert captured['task_id'] == 491

    def test_invalid_task_id_raises_out_of_silence(self):
        """归一失败必须抛 ValueError，不得被仓储兜底吞成空列表。"""
        repo = self._repo()
        with patch('evaluation_service.infrastructure.acl.task_acl_repository.get_task_data_service_stub'):
            with pytest.raises(ValueError, match='task_id'):
                repo.get_test_results_by_task_and_case(task_id='abc')

    def test_empty_task_id_raises(self):
        repo = self._repo()
        with pytest.raises(ValueError, match='不能为空'):
            repo.get_test_results_by_task_and_case(task_id='')

    def test_update_task_case_status_normalizes_str_task_id(self):
        repo = self._repo()
        captured = {}
        stub = MagicMock()

        def _capture(req):
            captured['task_id'] = req.task_id
            resp = MagicMock()
            resp.success = True
            return resp

        stub.UpdateTaskCaseStatus.side_effect = _capture
        with patch('evaluation_service.infrastructure.acl.task_acl_repository.get_task_data_service_stub',
                   return_value=stub):
            ok = repo.update_task_case_status('491', 'case-1', evaluation_status='completed')

        assert ok is True
        assert captured['task_id'] == 491


# ============================================================
# 缺陷①：servicer 边界归一（proto string → int）
# ============================================================

class TestServicerReevaluateBoundary:
    def _servicer(self):
        from evaluation_service.interfaces.grpc.evaluation_servicer import (
            EvaluationServiceServicer,
        )
        return EvaluationServiceServicer()

    def _patch_executor(self, submit_ret=(True, '重新评估任务已提交')):
        executor = MagicMock()
        executor.submit.return_value = submit_ret
        p = patch('evaluation_service.application.handlers.reevaluation_executor.ReevaluationExecutor.get_instance',
                  return_value=executor)
        return p, executor

    def test_reevaluate_converts_str_task_id(self):
        servicer = self._servicer()
        p, executor = self._patch_executor()
        req = SimpleNamespace(task_id='491', reextract_device_output=False, reevaluate_type='all')
        with p:
            resp = servicer.Reevaluate(req)
        assert resp.success is True
        args, kwargs = executor.submit.call_args
        assert args[0] == 491
        assert isinstance(args[0], int)

    def test_reevaluate_empty_task_id_fails_explicitly(self):
        servicer = self._servicer()
        p, executor = self._patch_executor()
        req = SimpleNamespace(task_id='', reextract_device_output=False, reevaluate_type='all')
        with p:
            resp = servicer.Reevaluate(req)
        assert resp.success is False
        executor.submit.assert_not_called()

    def test_reevaluate_multi_round_converts_str_task_id(self):
        servicer = self._servicer()
        executor = MagicMock()
        p = patch('evaluation_service.application.handlers.reevaluation_executor.ReevaluationExecutor.get_instance',
                  return_value=executor)
        req = SimpleNamespace(
            task_id='491', result_json='{}', test_case_id='tc-1',
            algorithm_result='{}', test_type='api', algorithm_type='translation',
        )
        with p:
            resp = servicer.ReevaluateMultiRound(req)
        assert resp.success is True
        kwargs = executor._reevaluate_multi_round.call_args.kwargs
        assert kwargs['task_id'] == 491

    def test_reevaluate_single_converts_str_ids(self):
        servicer = self._servicer()
        executor = MagicMock()
        p = patch('evaluation_service.application.handlers.reevaluation_executor.ReevaluationExecutor.get_instance',
                  return_value=executor)
        req = SimpleNamespace(
            task_id='491', result_id='4855', test_case_id='tc-1',
            algorithm_result='{}', reference_params='{}',
            test_type='api', algorithm_type='translation',
        )
        with p:
            resp = servicer.ReevaluateSingle(req)
        assert resp.success is True
        kwargs = executor._reevaluate_single.call_args.kwargs
        assert kwargs['task_id'] == 491
        assert kwargs['result_id'] == 4855


# ============================================================
# 缺陷③：executor submit 归一 + 失败透出
# ============================================================

_ACL = 'evaluation_service.application.handlers.reevaluation_executor.task_acl_repository'


def _noop_log(*args, **kwargs):
    pass


class TestExecutorSubmitNormalization:
    def _executor(self):
        from evaluation_service.application.handlers.reevaluation_executor import (
            ReevaluationExecutor,
        )
        return ReevaluationExecutor()

    def test_submit_normalizes_str_task_id(self):
        ex = self._executor()
        with patch(_ACL) as acl, patch.object(ex, '_check_queue'):
            ok, _ = ex.submit('491')
        assert ok is True
        assert ex.reevaluation_queue[0]['task_id'] == 491

    def test_submit_invalid_task_id_raises(self):
        ex = self._executor()
        with patch(_ACL), patch.object(ex, '_check_queue'):
            with pytest.raises(ValueError, match='task_id'):
                ex.submit('abc')


class TestRunReevaluationFailureTransparency:
    """空结果 + 查询不到任务：按失败收口，不再伪装 success=True。"""

    def _run(self, get_task_by_id_ret):
        from evaluation_service.application.handlers.reevaluation_executor import (
            ReevaluationExecutor,
        )
        ex = ReevaluationExecutor()
        with patch(_ACL) as acl, patch(
            'evaluation_service.application.handlers.reevaluation_executor.log_and_emit', _noop_log
        ):
            acl.get_test_results_by_task_and_case.return_value = []
            acl.get_task_case_by_ids.return_value = []
            acl.get_task_by_id.return_value = get_task_by_id_ret
            ex._run_reevaluation(task_id=491, reextract_device_output=False, reevaluate_type='all')
        return acl

    def test_task_missing_fails(self):
        acl = self._run(get_task_by_id_ret=None)
        acl.update_task_status.assert_called_once_with(491, TaskStatus.FAILED)

    def test_task_exists_with_no_results_succeeds(self):
        acl = self._run(get_task_by_id_ret=SimpleNamespace(id=491))
        acl.update_task_status.assert_called_once_with(491, TaskStatus.COMPLETED)

    def test_status_write_failure_logged_as_error(self):
        """任务状态写失败（返回 False）必须以 ERROR 级别可见。"""
        from evaluation_service.application.handlers.reevaluation_executor import (
            ReevaluationExecutor,
        )
        ex = ReevaluationExecutor()
        logs = []

        def _capture(level, category, content, **kw):
            logs.append((level, content))

        with patch(_ACL) as acl, patch(
            'evaluation_service.application.handlers.reevaluation_executor.log_and_emit', _capture
        ):
            acl.update_task_status.return_value = False
            ex._on_complete(491, True)
        assert any(lv == 'ERROR' for lv, _ in logs)


# ============================================================
# 缺陷④：无 evaluation param mappings → skipped 终态
# ============================================================

class _Host:
    """聚合评估域 mixin 的最小宿主（仅注入被测依赖）。"""

    class Impl(CaseEvaluationMixin, RoundDataBuilderMixin):
        def __init__(self, **deps):
            self.__dict__.update(deps)
            self.logs = []

        def _log(self, level, content, **kw):
            self.logs.append((level, content))


class TestBuildRoundsListExplicitSkip:
    def test_no_mappings_logs_error_and_returns_empty(self):
        host = _Host.Impl()
        fake_acl = MagicMock()
        fake_acl.get_param_mapping.return_value = []
        with patch.object(_acl_pkg, 'algorithm_acl_repository', fake_acl):
            result = host._build_rounds_list(
                {'rounds': [{'output': {}, 'round': 0}]},
                reference_params_col=None,
                field_mapper=MagicMock(),
                algorithm_type='translation',
                test_type='api',
                task_id=491,
                test_case_id='tc-1',
            )
        assert result == []
        assert any(lv == 'ERROR' and 'evaluation param mappings' in c for lv, c in host.logs)


class TestEvaluateCaseSkippedTerminal:
    def _host(self):
        host = _Host.Impl(
            result_processor=MagicMock(),
            _task_acl_repo=MagicMock(),
        )
        host._post_evaluate_updates = MagicMock()
        return host

    def test_no_mappings_marks_case_skipped(self):
        host = self._host()
        fake_acl = MagicMock()
        fake_acl.get_param_mapping.return_value = []
        with patch.object(_acl_pkg, 'algorithm_acl_repository', fake_acl):
            ret = host.evaluate_case(
                task_id=491, result_id=4855, test_case_id='tc-1',
                algorithm_result={'rounds': [{'output': {'asr_text': 'x'}, 'round': 0}]},
                algorithm_type='translation', test_type='api',
            )
        assert ret is False
        # TestResult 收口 completed
        host.result_processor.mark_test_result_completed.assert_called_once_with(4855)
        # TaskCase 终态 skipped + 评估流程收口 + 原因留痕
        kw = host._task_acl_repo.update_task_case_status.call_args.kwargs
        assert kw['task_id'] == 491
        assert kw['case_id'] == 'tc-1'
        assert kw['status'] == TaskCaseStatus.SKIPPED
        assert kw['evaluation_status'] == EvaluationStatus.COMPLETED
        assert 'evaluation param mappings' in kw['error_message']
        host._post_evaluate_updates.assert_called_once_with(491, 'tc-1')

    def test_missing_round_marks_case_skipped(self):
        """指定轮次不存在同样走显式 skipped，不静默进入维度分发。"""
        host = self._host()
        fake_acl = MagicMock()
        fake_acl.get_param_mapping.return_value = [{'source': 'device', 'target_param': 'asr_text'}]
        with patch.object(_acl_pkg, 'algorithm_acl_repository', fake_acl):
            ret = host.evaluate_case(
                task_id=491, result_id=4855, test_case_id='tc-1',
                algorithm_result={'rounds': [{'output': {'asr_text': 'x'}, 'round': 0}]},
                algorithm_type='translation', test_type='api',
                round_number=3,
            )
        assert ret is False
        kw = host._task_acl_repo.update_task_case_status.call_args.kwargs
        assert kw['status'] == TaskCaseStatus.SKIPPED

    def test_with_rounds_proceeds_to_prepare(self):
        """mappings 正常时行为不变：构建 rounds 后继续准备评估数据。"""
        host = self._host()
        host._prepare_evaluation_data = MagicMock(return_value=False)
        fake_acl = MagicMock()
        fake_acl.get_param_mapping.return_value = [{'source': 'device', 'target_param': 'asr_text'}]
        with patch.object(_acl_pkg, 'algorithm_acl_repository', fake_acl):
            ret = host.evaluate_case(
                task_id=491, result_id=4855, test_case_id='tc-1',
                algorithm_result={'rounds': [{'output': {'asr_text': 'x'}, 'round': 0}]},
                algorithm_type='translation', test_type='api',
            )
        assert ret is False
        host._prepare_evaluation_data.assert_called_once()
        host.result_processor.mark_test_result_completed.assert_not_called()
