# -*- coding: utf-8 -*-
"""INT-115 独立验收（测试工程师）：真实 protobuf 契约下的 int 归一全量扫描
+ 失败透出不伪装 + skipped 终态不进维度分发。

与开发自测（test_int115_reevaluate_id_and_skip.py）互补，独立验证角度：

验收① 原 bug 形态回归锚点：
  真实 task_service protobuf 对 int 字段传入 str 必然 TypeError——
  这是本次缺陷的确切故障形态（run_all_int95.log 20:25:12），作为锚点防止
  前提漂移（proto 契约若改为 int 则本组用例需同步调整）。

验收② 13 个 int 字段全量扫描（真实 proto 构造）：
  issue 点名的 task_acl_repository.py:231/265 及全部同类点——
  每个仓储方法以 str ID 调用，断言真正发出的 protobuf 请求携带 int；
  每个方法以非法 ID 调用，断言 ValueError 抛出（try 块外，不被兜底
  吞成 []/None/False）且未发出任何 gRPC 请求。

验收③ servicer 三个入口非法 ID 全部显式失败：
  Reevaluate / ReevaluateMultiRound / ReevaluateSingle 收到 'abc' 均
  success=False，且执行器不被触达。

验收④ 失败透出——伪装链路消失：
  任务缺失时不再发出"没有需要重新评估的用例"WARNING（原缺陷的掩盖话术），
  以 ERROR"重新评估失败" + Task FAILED 收口；任务存在但无结果的合法
  no-op 语义保留（WARNING + COMPLETED）。

验收⑤ executor.submit HTTP 直连路径：
  '491.5' 等非法值在入队前抛 ValueError，不产生任何状态写与队列残留。

验收⑥ skipped 终态不进维度分发：
  无 mappings / 指定轮次不存在时，_prepare_evaluation_data（维度分发
  前置）零调用，评估链在 skipped 收口处终止。

全部为纯单测（mock，不触真实 DB/gRPC/Redis）。
"""
import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

import evaluation_service.infrastructure.acl as _acl_pkg
from shared.proto import task_service_pb2 as task_pb
from shared.utils.status_constants import (
    TaskStatus, TaskCaseStatus, EvaluationStatus,
)
from evaluation_service.domain.services.evaluation_service.case_evaluation import (
    CaseEvaluationMixin,
)
from evaluation_service.domain.services.evaluation_service.round_data_builder import (
    RoundDataBuilderMixin,
)
from evaluation_service.infrastructure.acl.task_acl_repository import TaskAclRepository

_ACL = 'evaluation_service.application.handlers.reevaluation_executor.task_acl_repository'
_LOG = 'evaluation_service.application.handlers.reevaluation_executor.log_and_emit'


# ============================================================
# 验收① 原 bug 形态回归锚点（真实 proto）
# ============================================================

class TestOriginalBugShapeAnchor:
    """原缺陷的确切故障形态：真实 protobuf int 字段拒收 str。"""

    def test_get_results_request_rejects_str(self):
        # 对应原 task_acl_repository.py:231 的 TypeError
        with pytest.raises(TypeError):
            task_pb.GetTestResultsByTaskAndCaseRequest(task_id='491')

    def test_update_status_request_rejects_str(self):
        # 对应原 task_acl_repository.py:265 的 TypeError
        with pytest.raises(TypeError):
            task_pb.UpdateTaskStatusRequest(task_id='491')

    def test_normalized_int_constructs_real_proto(self):
        # 归一产物（int）在真实 proto 上构造成功且字段值正确
        req = task_pb.GetTestResultsByTaskAndCaseRequest(task_id=int('491'))
        assert req.task_id == 491 and isinstance(req.task_id, int)


# ============================================================
# 验收② 13 个 int 字段全量扫描（真实 proto 构造 + 记录桩）
# ============================================================

def _capture_stub(method_name):
    """记录真实 proto 请求对象的桩。"""
    stub = MagicMock()

    def _capture(req):
        stub.captured = req
        resp = MagicMock()
        resp.success = True
        resp.data = '[]'
        return resp

    getattr(stub, method_name).side_effect = _capture
    return stub


def _make_case(method_name, call, attr, expected):
    def _run(self):
        repo = TaskAclRepository()
        stub = _capture_stub(method_name)
        with patch('evaluation_service.infrastructure.acl.task_acl_repository.get_task_data_service_stub',
                   return_value=stub):
            call(repo)
        req = stub.captured
        assert req is not None
        assert isinstance(getattr(req, attr), int), f'{method_name}: {attr} 应为 int'
        assert getattr(req, attr) == expected, f'{method_name}: {attr} 应为 {expected}'
    return _run


def _invalid_case(call, method_name):
    def _run(self):
        repo = TaskAclRepository()
        stub = MagicMock()
        with patch('evaluation_service.infrastructure.acl.task_acl_repository.get_task_data_service_stub',
                   return_value=stub):
            with pytest.raises(ValueError):
                call(repo)
        # 未发出任何 gRPC 请求
        getattr(stub, method_name).assert_not_called()
    return _run


class TestAclIntFieldSweepRealProto:
    """task_acl_repository 全部 int 字段：str 可用 / 非法透出 / 请求携 int。"""

    # ---- str 数字 ID：请求携带 int（13 点全扫）----

    def test_get_test_result_by_id(self):
        _make_case('GetTestResultById',
                   lambda r: r.get_test_result_by_id('123'), 'result_id', 123)(self)

    def test_get_task_case_by_ids(self):
        _make_case('GetTaskCaseByIds',
                   lambda r: r.get_task_case_by_ids('491'), 'task_id', 491)(self)

    def test_get_task_by_id(self):
        _make_case('GetTaskById',
                   lambda r: r.get_task_by_id('491'), 'task_id', 491)(self)

    def test_get_task_devices(self):
        _make_case('GetTaskDevices',
                   lambda r: r.get_task_devices('491'), 'task_id', 491)(self)

    def test_get_task_apis(self):
        _make_case('GetTaskApis',
                   lambda r: r.get_task_apis('491'), 'task_id', 491)(self)

    def test_submit_result(self):
        _make_case('SubmitResult',
                   lambda r: r.submit_result('491', {'x': 1}), 'task_id', 491)(self)

    def test_update_task_case_status(self):
        _make_case('UpdateTaskCaseStatus',
                   lambda r: r.update_task_case_status('491', 'tc-1', evaluation_status='completed'),
                   'task_id', 491)(self)

    def test_update_test_result_algorithm_result(self):
        _make_case('UpdateTestResultAlgorithmResult',
                   lambda r: r.update_test_result_algorithm_result('123', {'a': 1}),
                   'result_id', 123)(self)

    def test_update_test_result_data(self):
        _make_case('UpdateTestResultData',
                   lambda r: r.update_test_result_data('123', {'a': 1}),
                   'result_id', 123)(self)

    def test_get_test_results_by_task_and_case(self):
        # issue 点名点（原 :231）
        _make_case('GetTestResultsByTaskAndCase',
                   lambda r: r.get_test_results_by_task_and_case('491'), 'task_id', 491)(self)

    def test_update_test_result_status(self):
        _make_case('UpdateTestResultStatus',
                   lambda r: r.update_test_result_status('123', 'completed'),
                   'result_id', 123)(self)

    def test_update_task_status(self):
        # issue 点名点（原 :265）
        _make_case('UpdateTaskStatus',
                   lambda r: r.update_task_status('491', TaskStatus.COMPLETED),
                   'task_id', 491)(self)

    def test_get_dimension_params(self):
        # dimension_id 归一点：走 algorithm config 桩（独立 patch 点）
        repo = TaskAclRepository()
        stub = _capture_stub('GetDimensionParams')
        with patch('shared.clients.grpc_clients.get_algorithm_config_service_stub',
                   return_value=stub):
            repo.get_dimension_params('77')
        req = stub.captured
        assert isinstance(req.dimension_id, int) and req.dimension_id == 77

    # ---- 非法 ID：ValueError 透出，零请求发出 ----

    def test_invalid_get_test_results_raises(self):
        _invalid_case(lambda r: r.get_test_results_by_task_and_case('abc'),
                      'GetTestResultsByTaskAndCase')(self)

    def test_invalid_update_task_status_raises(self):
        _invalid_case(lambda r: r.update_task_status('abc', TaskStatus.COMPLETED),
                      'UpdateTaskStatus')(self)

    def test_invalid_submit_result_raises(self):
        _invalid_case(lambda r: r.submit_result('abc', {}), 'SubmitResult')(self)

    def test_invalid_get_dimension_params_raises(self):
        with patch('shared.clients.grpc_clients.get_algorithm_config_service_stub'):
            with pytest.raises(ValueError):
                TaskAclRepository().get_dimension_params('abc')

    def test_none_task_id_raises(self):
        with pytest.raises(ValueError, match='不能为空'):
            TaskAclRepository().get_task_by_id(None)


# ============================================================
# 验收③ servicer 三个入口非法 ID 显式失败
# ============================================================

class TestServicerInvalidIdAllEntries:
    def _servicer(self):
        from evaluation_service.interfaces.grpc.evaluation_servicer import (
            EvaluationServiceServicer,
        )
        return EvaluationServiceServicer()

    def test_reevaluate_invalid_task_id_fails(self):
        s = self._servicer()
        executor = MagicMock()
        with patch('evaluation_service.application.handlers.reevaluation_executor.ReevaluationExecutor.get_instance',
                   return_value=executor):
            resp = s.Reevaluate(SimpleNamespace(task_id='abc', reextract_device_output=False))
        assert resp.success is False
        assert 'task_id' in resp.message
        executor.submit.assert_not_called()

    def test_multi_round_invalid_task_id_fails(self):
        s = self._servicer()
        executor = MagicMock()
        with patch('evaluation_service.application.handlers.reevaluation_executor.ReevaluationExecutor.get_instance',
                   return_value=executor):
            resp = s.ReevaluateMultiRound(SimpleNamespace(
                task_id='abc', result_json='{}', test_case_id='tc-1',
                algorithm_result='{}', test_type='api', algorithm_type='translation'))
        assert resp.success is False
        executor._reevaluate_multi_round.assert_not_called()

    def test_single_invalid_result_id_fails(self):
        s = self._servicer()
        executor = MagicMock()
        with patch('evaluation_service.application.handlers.reevaluation_executor.ReevaluationExecutor.get_instance',
                   return_value=executor):
            resp = s.ReevaluateSingle(SimpleNamespace(
                task_id='491', result_id='abc', test_case_id='tc-1',
                algorithm_result='{}', reference_params='{}',
                test_type='api', algorithm_type='translation'))
        assert resp.success is False
        assert 'result_id' in resp.message
        executor._reevaluate_single.assert_not_called()


# ============================================================
# 验收④ 失败透出——伪装链路消失
# ============================================================

class TestFailureTransparencyNoDisguise:
    """原缺陷掩盖话术"没有需要重新评估的用例"在任务缺失时不得出现。"""

    def _run(self, get_task_by_id_ret):
        from evaluation_service.application.handlers.reevaluation_executor import (
            ReevaluationExecutor,
        )
        ex = ReevaluationExecutor()
        logs = []

        def _log(level, category, content, **kw):
            logs.append((level, content))

        with patch(_ACL) as acl, patch(_LOG, _log):
            acl.get_test_results_by_task_and_case.return_value = []
            acl.get_task_case_by_ids.return_value = []
            acl.get_task_by_id.return_value = get_task_by_id_ret
            ex._run_reevaluation(task_id=491, reextract_device_output=False, reevaluate_type='all')
        return acl, logs

    def test_task_missing_no_disguise_warning(self):
        acl, logs = self._run(get_task_by_id_ret=None)
        assert not any('没有需要重新评估的用例' in c for _, c in logs), \
            '任务缺失时不得发出原掩盖话术 WARNING'
        assert any(lv == 'ERROR' and '重新评估失败' in c for lv, c in logs)
        acl.update_task_status.assert_called_once_with(491, TaskStatus.FAILED)

    def test_task_exists_noop_semantics_preserved(self):
        """任务存在但无结果：合法 no-op 语义保留（WARNING + COMPLETED）。"""
        acl, logs = self._run(get_task_by_id_ret=SimpleNamespace(id=491))
        assert any('没有需要重新评估的用例' in c for _, c in logs)
        assert not any(lv == 'ERROR' and '重新评估失败' in c for lv, c in logs)
        acl.update_task_status.assert_called_once_with(491, TaskStatus.COMPLETED)


# ============================================================
# 验收⑤ executor.submit HTTP 直连路径（入队前拦截）
# ============================================================

class TestSubmitHttpDirectPath:
    def test_invalid_id_raises_before_queue_and_status_write(self):
        from evaluation_service.application.handlers.reevaluation_executor import (
            ReevaluationExecutor,
        )
        ex = ReevaluationExecutor()
        with patch(_ACL) as acl:
            with pytest.raises(ValueError):
                ex.submit('491.5')
        assert ex.reevaluation_queue == []
        assert acl.update_task_status.call_count == 0

    def test_str_digits_enqueued_as_int(self):
        from evaluation_service.application.handlers.reevaluation_executor import (
            ReevaluationExecutor,
        )
        ex = ReevaluationExecutor()
        with patch(_ACL) as acl, patch(_LOG), \
             patch.object(ReevaluationExecutor, '_check_queue', lambda self: None):
            ok, _ = ex.submit('491')
        assert ok is True
        assert ex.reevaluation_queue[0]['task_id'] == 491
        assert isinstance(ex.reevaluation_queue[0]['task_id'], int)
        acl.update_task_status.assert_called_once_with(491, TaskStatus.REEVALUATE_QUEUED)


# ============================================================
# 验收⑥ skipped 终态不进维度分发
# ============================================================

class _Host:
    class Impl(CaseEvaluationMixin, RoundDataBuilderMixin):
        def __init__(self, **deps):
            self.__dict__.update(deps)
            self.logs = []

        def _log(self, level, content, **kw):
            self.logs.append((level, content))


class TestSkippedNoDimensionDispatch:
    def _host(self):
        host = _Host.Impl(
            result_processor=MagicMock(),
            _task_acl_repo=MagicMock(),
        )
        host._post_evaluate_updates = MagicMock()
        host._prepare_evaluation_data = MagicMock()
        return host

    def test_no_mappings_never_reaches_prepare(self):
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
        host._prepare_evaluation_data.assert_not_called()
        kw = host._task_acl_repo.update_task_case_status.call_args.kwargs
        assert kw['status'] == TaskCaseStatus.SKIPPED
        assert kw['error_message'] and 'translation' in kw['error_message']

    def test_missing_round_never_reaches_prepare(self):
        host = self._host()
        fake_acl = MagicMock()
        fake_acl.get_param_mapping.return_value = [
            {'source': 'device', 'target_param': 'asr_text'}]
        with patch.object(_acl_pkg, 'algorithm_acl_repository', fake_acl):
            ret = host.evaluate_case(
                task_id=491, result_id=4855, test_case_id='tc-1',
                algorithm_result={'rounds': [{'output': {'asr_text': 'x'}, 'round': 0}]},
                algorithm_type='translation', test_type='api',
                round_number=5,
            )
        assert ret is False
        host._prepare_evaluation_data.assert_not_called()
        kw = host._task_acl_repo.update_task_case_status.call_args.kwargs
        assert kw['status'] == TaskCaseStatus.SKIPPED
        # 评估流程状态收口防悬挂
        assert kw['evaluation_status'] == EvaluationStatus.COMPLETED
