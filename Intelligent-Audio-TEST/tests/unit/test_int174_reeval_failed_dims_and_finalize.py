# -*- coding: utf-8 -*-
"""INT-174 回归守卫：重新评估只重评失败维度 + 旧评估取消隔离 + 任务终态收敛

对齐 V9.7.10 c30d1b24（按 V9.7.31 微服务结构重写，不照抄单体）：
1. 维度过滤矩阵：评估入口 dimension_filter_ids 对 int/str 维度 id 统一转 int 比较
   （防类型不匹配全量误过滤），过滤后为空 → 跳过本轮评估并正常收尾；
2. 重评执行器：failed 类型按 TRD（evaluation_status='failed'）收集
   round_number → {dim_id}，无失败维度跳过（不置 queued）、逐轮无失败维度跳过、
   整体按 None 键过滤；已完成维度 TRD 保留（仅全量重评才 delete_scores）；
   全部轮次被跳过 → 走到统一收尾（防 TaskCase 悬挂 queued）；
3. 维度组失败统一收尾：单组失败不再无条件把 TaskCase 置 failed，交给
   update_task_case_status 统一判定；
4. maybe_finalize：终态判定（提交成功 ≠ 完成）+ 提交窗口防提前收敛 +
   重启兜底分支（全用例执行完成 + 「服务重启」标记才兜底收尾）；
5. eval_task_registry（回调注册表等价物）：pop_by_task 摘除 + 结果按
   __cancelled__ 隔离，不污染新评估；
6. 打回修复：pending 维度纳入 failed 收集范围、重评范围外遗留非终态 TRD
   收口、零提交重评主动收敛任务终态并释放队列、m2 非数字维度 id 容错、
   m1 结果落库前二次核销取消标记。
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
from evaluation_service.domain.services.evaluation_service.case_evaluation import CaseEvaluationMixin
from evaluation_service.infrastructure.evaluation_api.api_request_handler import (
    ApiRequestHandler,
    EvalTaskRegistry,
)
from evaluation_service.infrastructure.evaluation_api.evaluation_api_client import evaluationApiClient
from evaluation_service.infrastructure.acl import task_acl_repository
from evaluation_service.infrastructure.persistence import _result_dimension_mixin as rdm_module
from evaluation_service.infrastructure.persistence._result_dimension_mixin import DimensionResultMixin
from shared.utils.status_constants import (
    EvaluationStatus, ExecutionStatus, TaskStatus,
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


def _tc(exec_st=ExecutionStatus.COMPLETED, eval_st=EvaluationStatus.COMPLETED, err=None):
    """TaskCaseDTO 形状的对象"""
    return SimpleNamespace(
        test_case_id='c1',
        execution_status=exec_st,
        evaluation_status=eval_st,
        error_message=err,
    )


@pytest.fixture(autouse=True)
def _reset_registry():
    """隔离 EvalTaskRegistry 类级状态（注册表为进程级单例）"""
    EvalTaskRegistry._entries = {}
    EvalTaskRegistry._cancelled = {}
    EvalTaskRegistry._cancelled_cases = {}
    yield
    EvalTaskRegistry._entries = {}
    EvalTaskRegistry._cancelled = {}
    EvalTaskRegistry._cancelled_cases = {}


# ==================== 1. eval_task_registry：方案A 摘除与隔离 ====================

class TestEvalTaskRegistry:

    def test_register_and_pop_by_task(self):
        EvalTaskRegistry.register('e1', 5, 'http://ep-a')
        EvalTaskRegistry.register('e2', 5, 'http://ep-b')
        EvalTaskRegistry.register('e3', 6, 'http://ep-c')

        removed = EvalTaskRegistry.pop_by_task(5)

        assert sorted(removed) == [('e1', 'http://ep-a'), ('e2', 'http://ep-b')]
        assert EvalTaskRegistry.is_cancelled('e1') is True
        assert EvalTaskRegistry.is_cancelled('e2') is True
        assert EvalTaskRegistry.is_cancelled('e3') is False
        # 摘除后再次 pop 为空（旧条目已不在册）
        assert EvalTaskRegistry.pop_by_task(5) == []

    def test_pop_by_task_normalizes_task_id_type(self):
        """注册/摘除两侧 task_id 形态不一（str/int）也能命中"""
        EvalTaskRegistry.register('e1', '5', 'http://ep-a')
        assert EvalTaskRegistry.pop_by_task(5) == [('e1', 'http://ep-a')]

    def test_unregister_after_pop_is_noop(self):
        EvalTaskRegistry.register('e1', 5, 'http://ep-a')
        EvalTaskRegistry.pop_by_task(5)
        EvalTaskRegistry.unregister('e1')
        # 摘除标记不因 unregister 丢失（隔离语义保留）
        assert EvalTaskRegistry.is_cancelled('e1') is True


class TestProcessAsyncResultCancelIsolation:

    @staticmethod
    def _fake_client(wait_return):
        return SimpleNamespace(
            _log=MagicMock(),
            wait_for_task_completion=MagicMock(return_value=wait_return),
        )

    def test_cancelled_task_result_is_isolated(self):
        """被 pop_by_task 摘除的旧评估任务：结果按 __cancelled__ 隔离，不解释为成功/失败"""
        EvalTaskRegistry.register('e1', 5, 'http://ep-a')
        EvalTaskRegistry.pop_by_task(5)
        client = self._fake_client({'code': 0, 'data': {'result': {'wer': 0.1}}})

        resp = evaluationApiClient._process_async_result(
            client,
            {'code': 0, 'data': {'eval_task_id': 'e1'}},
            'http://ep-a', 5, 'c1', None,
        )

        assert resp.get('__cancelled__') is True
        # 结果消费完毕，在途登记注销
        assert 'e1' not in EvalTaskRegistry._entries

    def test_normal_task_result_processed_and_unregistered(self):
        EvalTaskRegistry.register('e1', 5, 'http://ep-a')
        client = self._fake_client({'code': 0, 'data': {'result': {'wer': 0.1}}})

        resp = evaluationApiClient._process_async_result(
            client,
            {'code': 0, 'data': {'eval_task_id': 'e1'}},
            'http://ep-a', 5, 'c1', None,
        )

        # 成功结果携带 __eval_task_id__（m1 硬化：消费方写库前二次核销取消标记）
        assert resp.get('wer') == 0.1
        assert resp.get('__eval_task_id__') == 'e1'
        assert EvalTaskRegistry.is_cancelled('e1') is False
        assert 'e1' not in EvalTaskRegistry._entries


class TestWaitForTaskCompletionCancelledExit:

    def test_poll_loop_exits_promptly_when_cancelled(self):
        """等待期间被摘除：立即返回 __cancelled__，不再继续轮询"""
        fake_self = SimpleNamespace(
            _log=MagicMock(),
            _wait_for_redis_callback=MagicMock(return_value=None),
            get_task_status=MagicMock(side_effect=AssertionError('cancelled 后不应再轮询')),
        )
        EvalTaskRegistry.register('e1', 5, 'http://ep-a')
        EvalTaskRegistry.pop_by_task(5)

        resp = ApiRequestHandler.wait_for_task_completion(
            fake_self, 'http://ep-a', 'e1', max_wait_time=30, poll_interval=1,
        )

        assert resp.get('__cancelled__') is True


# ==================== 2. 评估入口 dimension_filter_ids 过滤矩阵 ====================

class _FilterHost(CaseEvaluationMixin):
    """仅实现 _prepare_evaluation_data 依赖的最小桩"""

    def __init__(self):
        self.result_processor = MagicMock()
        self.posted = []
        self.logs = []
        self._evaluation_dimension_repo = MagicMock()

    def _log(self, **kwargs):
        self.logs.append(kwargs)

    @staticmethod
    def _extract_dimension_ids(dimensions_config):
        ids = []
        for d in dimensions_config or []:
            dim_id = d.get('id') if isinstance(d, dict) else d
            if dim_id:
                ids.append(dim_id)
        return ids

    def _load_test_case_and_refs(self, test_case_id, field_mapper, kwargs, task_id, round_number=None):
        # config 维度 id 混用 str/int（真实 config 里维度 id 是字符串）
        return {
            'test_case': SimpleNamespace(name='case-a'),
            'algorithm_type': 'translation',
            'ref_texts': {},
            'dimensions_config': [{'id': '121', 'name': 'a'}, {'id': 122, 'name': 'b'}],
        }

    def _load_dimension_data(self, unique_dimension_ids, task_id, test_case_id, test_case):
        wanted = {int(d) for d in unique_dimension_ids}
        return [{'id': d} for d in (121, 122) if d in wanted]

    def _mark_evaluation_queued(self, task_id, test_case_id, result_id=None):
        pass

    def _post_evaluate_updates(self, task_id, test_case_id=None):
        self.posted.append(test_case_id)


class TestDimensionFilterMatrix:

    @staticmethod
    def _prepare(kwargs):
        host = _FilterHost()
        prepared = host._prepare_evaluation_data(
            task_id=1, result_id=11, test_case_id='c1', algorithm_result={},
            field_mapper=None, kwargs=kwargs, test_type='api', round_number=None,
        )
        return host, prepared

    def test_int_and_str_filter_ids_both_match(self):
        """int/str 过滤 id 与 str/int config 维度 id 统一转 int 比较，不误过滤"""
        host, prepared = self._prepare({'dimension_filter_ids': [121]})
        assert prepared is not False
        assert prepared['dimension_data_list'] == [{'id': 121}]

        host, prepared = self._prepare({'dimension_filter_ids': ['122']})
        assert prepared is not False
        assert prepared['dimension_data_list'] == [{'id': 122}]

        host, prepared = self._prepare({'dimension_filter_ids': [121, '122']})
        assert prepared is not False
        assert [d['id'] for d in prepared['dimension_data_list']] == [121, 122]

    def test_filter_none_keeps_all(self):
        host, prepared = self._prepare({})
        assert [d['id'] for d in prepared['dimension_data_list']] == [121, 122]

    def test_filter_empty_skips_and_finalizes(self):
        """过滤后为空 → 跳过本轮评估并正常走收尾（TestResult 收口 + 用例状态推进）"""
        host, prepared = self._prepare({'dimension_filter_ids': [999]})
        assert prepared is False
        host.result_processor.mark_test_result_completed.assert_called_once_with(11)
        assert host.posted == ['c1']
        # 本轮不可触达的遗留非终态 TRD 就地收口（全轮次）
        host._evaluation_dimension_repo.mark_round_active_scores_failed.assert_called_once_with(
            11, None, None,
            '重新评估未覆盖该维度（重启遗留/维度停用或移除），收口为失败',
        )

    def test_filter_ignores_invalid_entries(self):
        host, prepared = self._prepare({'dimension_filter_ids': ['abc', None, 121]})
        assert prepared is not False
        assert prepared['dimension_data_list'] == [{'id': 121}]

    def test_disabled_dim_dropped_by_loader_swept(self):
        """m2/缺陷1 补口：过滤命中的维度已被软删（加载不到）→ 其遗留非终态 TRD 收口，
        其余维度照常提交（种子任务 529 dim177 场景）"""
        host = _FilterHost()
        host._load_test_case_and_refs = lambda *a, **k: {
            'test_case': SimpleNamespace(name='case-a'),
            'algorithm_type': 'translation',
            'ref_texts': {},
            'dimensions_config': [{'id': '121'}, {'id': '177'}],
        }
        host._load_dimension_data = lambda ids, *a, **k: (
            [{'id': d} for d in (121,) if int(d) in {int(x) for x in ids}])

        prepared = host._prepare_evaluation_data(
            task_id=1, result_id=11, test_case_id='c1', algorithm_result={},
            field_mapper=None, kwargs={'dimension_filter_ids': [121, 177]},
            test_type='api', round_number=None,
        )

        assert prepared is not False
        assert prepared['dimension_data_list'] == [{'id': 121}]
        # 仅收口被排除的 177，不影响正常提交的 121
        host._evaluation_dimension_repo.mark_round_active_scores_failed.assert_called_once_with(
            11, None, {177},
            '重新评估未覆盖该维度（重启遗留/维度停用或移除），收口为失败',
        )


# ==================== 3. 重评执行器：failed 维度收集与逐轮过滤 ====================

def _mk_executor():
    return ReevaluationExecutor()


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


class TestReevaluateFailedDims:

    def test_failed_type_collects_by_round_and_filters(self, patched_acl):
        """failed 类型：按 TRD 收集 round_number → {dim_id}，逐轮仅提交失败维度"""
        patched_acl.list_scores.return_value = [
            _trd(7, 0, EvaluationStatus.FAILED, 'mock fail'),
            _trd(9, 0, EvaluationStatus.COMPLETED),   # 已完成维度 TRD 保留不动
            _trd(8, 1, EvaluationStatus.FAILED, 'mock fail'),
        ]
        ex = _mk_executor()
        with patch.object(reexec_module, 'evaluation_service') as eval_svc:
            eval_svc.evaluate_case.return_value = True

            ok = ex._reevaluate_multi_round(
                task_id=1, result=11, test_case_id='c1',
                algorithm_result={'rounds': [{'output': {}}, {'output': {}}]},
                test_type='e2e', algorithm_type='translation',
                reevaluate_type='failed',
            )

        assert ok is True
        # 全量重评才清空 TRD；failed 类型不删
        patched_acl.del_scores.assert_not_called()
        # 逐轮：round 0 过滤到 [7]、round 1 过滤到 [8]
        round_calls = [c for c in eval_svc.evaluate_case.call_args_list if 'round_number' in c.kwargs]
        assert [c.kwargs['round_number'] for c in round_calls] == [0, 1]
        assert [c.kwargs['dimension_filter_ids'] for c in round_calls] == [[7], [8]]
        # 整体：config.dimensions 为空，不提交
        assert len(eval_svc.evaluate_case.call_args_list) == 2

    def test_failed_type_overall_filter_by_none_key(self, patched_acl):
        """整体（round_number=None）按 None 键失败维度过滤"""
        patched_acl.list_scores.return_value = [
            _trd(7, 0, EvaluationStatus.FAILED, 'mock fail'),
            _trd(12, None, EvaluationStatus.FAILED, 'mock fail'),
        ]
        with patch.object(task_acl_repository, 'get_test_case_detail', MagicMock(return_value=SimpleNamespace(
                config={'rounds': [{'evaluation': {'dimensions': [{'id': 7}]}}],
                        'dimensions': [{'id': 12}]},
                algorithm_params=None, reference_params=None, algorithm_type='translation'))):
            ex = _mk_executor()
            with patch.object(reexec_module, 'evaluation_service') as eval_svc:
                eval_svc.evaluate_case.return_value = True

                ok = ex._reevaluate_multi_round(
                    task_id=1, result=11, test_case_id='c1',
                    algorithm_result={'rounds': [{'output': {}}]},
                    test_type='e2e', algorithm_type='translation',
                    reevaluate_type='failed',
                )

        assert ok is True
        overall_calls = [c for c in eval_svc.evaluate_case.call_args_list if 'round_number' not in c.kwargs]
        assert len(overall_calls) == 1
        assert overall_calls[0].kwargs['dimension_filter_ids'] == [12]

    def test_failed_type_overall_skipped_when_no_none_key_failed(self, patched_acl):
        """整体无失败维度（None 键为空）→ 跳过整体提交"""
        patched_acl.list_scores.return_value = [
            _trd(7, 0, EvaluationStatus.FAILED, 'mock fail'),
        ]
        with patch.object(task_acl_repository, 'get_test_case_detail', MagicMock(return_value=SimpleNamespace(
                config={'rounds': [{'evaluation': {'dimensions': [{'id': 7}]}}],
                        'dimensions': [{'id': 12}]},
                algorithm_params=None, reference_params=None, algorithm_type='translation'))):
            ex = _mk_executor()
            with patch.object(reexec_module, 'evaluation_service') as eval_svc:
                eval_svc.evaluate_case.return_value = True

                ok = ex._reevaluate_multi_round(
                    task_id=1, result=11, test_case_id='c1',
                    algorithm_result={'rounds': [{'output': {}}]},
                    test_type='e2e', algorithm_type='translation',
                    reevaluate_type='failed',
                )

        assert ok is True
        assert all('round_number' in c.kwargs for c in eval_svc.evaluate_case.call_args_list)

    def test_no_failed_dims_skips_before_queued(self, patched_acl):
        """无失败维度 → 跳过该用例：不置 queued、不清 TRD、不提交评估"""
        patched_acl.list_scores.return_value = [
            _trd(7, 0, EvaluationStatus.COMPLETED),
            _trd(9, 0, EvaluationStatus.COMPLETED),
        ]
        ex = _mk_executor()
        with patch.object(reexec_module, 'evaluation_service') as eval_svc:
            ok = ex._reevaluate_multi_round(
                task_id=1, result=11, test_case_id='c1',
                algorithm_result={'rounds': [{'output': {}}]},
                test_type='e2e', algorithm_type='translation',
                reevaluate_type='failed',
            )

        assert ok is False
        patched_acl.upd_tc.assert_not_called()
        patched_acl.del_scores.assert_not_called()
        eval_svc.evaluate_case.assert_not_called()

    def test_all_rounds_skipped_finalizes_failed(self, patched_acl):
        """全部轮次因无失败维度被跳过（失败轮评估已停用）→ 用例按评估失败收口。

        INT-632 口径更新：返回值从「已处理」改为「确有评估提交」——全部轮次跳过
        时无任何评估在途（用例已就地收口为 failed），返回 False 使零提交分支主动
        收敛任务终态，不再伪装有在途评估导致任务卡 running。
        """
        patched_acl.list_scores.return_value = [
            _trd(7, 0, EvaluationStatus.FAILED, 'round-0 mock fail'),
        ]
        with patch.object(task_acl_repository, 'get_test_case_detail', MagicMock(return_value=SimpleNamespace(
                config={'rounds': [{'evaluation': {'enabled': False, 'dimensions': [{'id': 7}]}}],
                        'dimensions': []},
                algorithm_params=None, reference_params=None, algorithm_type='translation'))):
            ex = _mk_executor()
            with patch.object(reexec_module, 'evaluation_service') as eval_svc:
                ok = ex._reevaluate_multi_round(
                    task_id=1, result=11, test_case_id='c1',
                    algorithm_result={'rounds': [{'output': {}}]},
                    test_type='e2e', algorithm_type='translation',
                    reevaluate_type='failed',
                )

        assert ok is False
        eval_svc.evaluate_case.assert_not_called()
        # 收尾：evaluation_status=failed 终态（防 TaskCase 悬挂 queued）
        failed_calls = [c for c in patched_acl.upd_tc.call_args_list
                        if c.kwargs.get('evaluation_status') == EvaluationStatus.FAILED]
        assert len(failed_calls) == 1
        assert failed_calls[0].kwargs['task_id'] == 1
        assert failed_calls[0].kwargs['case_id'] == 'c1'

    def test_api_multi_round_filter(self, patched_acl):
        """API 逐轮链：仅失败轮提交并携带过滤维度"""
        patched_acl.list_scores.return_value = [
            _trd(7, 0, EvaluationStatus.FAILED, 'mock fail'),
            _trd(8, 1, EvaluationStatus.FAILED, 'mock fail'),
        ]
        ex = _mk_executor()
        with patch.object(reexec_module, 'evaluation_service') as eval_svc, \
             patch.object(reexec_module.reevaluation_service, 'compute_api_aggregated',
                          MagicMock(return_value=None)):
            eval_svc.evaluate_case.return_value = True

            ok = ex._reevaluate_multi_round(
                task_id=1, result=11, test_case_id='c1',
                algorithm_result={'rounds': [
                    {'output': 'x', 'evaluation': {'wer': 0.1}},
                    {'output': 'y', 'evaluation': {'wer': 0.2}},
                ]},
                test_type='api', algorithm_type='translation',
                reevaluate_type='failed',
            )

        assert ok is True
        round_calls = [c for c in eval_svc.evaluate_case.call_args_list if 'round_number' in c.kwargs]
        assert [c.kwargs['round_number'] for c in round_calls] == [0, 1]
        assert [c.kwargs['dimension_filter_ids'] for c in round_calls] == [[7], [8]]

    def test_all_type_still_deletes_scores(self, patched_acl):
        """全量重评（all）保持既有口径：清空 TRD 后全量提交"""
        ex = _mk_executor()
        with patch.object(reexec_module, 'evaluation_service') as eval_svc:
            eval_svc.evaluate_case.return_value = True

            ok = ex._reevaluate_multi_round(
                task_id=1, result=11, test_case_id='c1',
                algorithm_result={'rounds': [{'output': {}}]},
                test_type='e2e', algorithm_type='translation',
                reevaluate_type='all',
            )

        assert ok is True
        patched_acl.del_scores.assert_called_once_with(11)
        assert eval_svc.evaluate_case.call_count >= 1
        assert all('dimension_filter_ids' not in c.kwargs for c in eval_svc.evaluate_case.call_args_list)

    def test_single_failed_dims(self, patched_acl):
        """单轮结果 failed 类型：按失败维度过滤提交"""
        patched_acl.list_scores.return_value = [
            _trd(7, None, EvaluationStatus.FAILED, 'mock fail'),
            _trd(9, None, EvaluationStatus.COMPLETED),
        ]
        ex = _mk_executor()
        with patch.object(reexec_module, 'evaluation_service') as eval_svc:
            eval_svc.evaluate_case.return_value = True

            ok = ex._reevaluate_single(
                task_id=1, result_id=11, test_case_id='c1',
                algorithm_result={'output': {}}, reference_params=[],
                test_type='api', algorithm_type='translation',
                reevaluate_type='failed',
            )

        assert ok is True
        patched_acl.del_scores.assert_not_called()
        assert eval_svc.evaluate_case.call_args.kwargs['dimension_filter_ids'] == [7]


# ==================== 4. 维度组失败统一收尾 ====================

class _GroupHost(DimensionResultMixin):
    def __init__(self):
        self.logs = []
        self.unified_calls = []
        self.group_failed_calls = []

    def _log(self, **kwargs):
        self.logs.append(kwargs)

    def update_task_case_status(self, result_id, current_result_all_completed, task_id, test_case_id, test_type=None):
        self.unified_calls.append({
            'result_id': result_id,
            'current_result_all_completed': current_result_all_completed,
            'task_id': task_id,
            'test_case_id': test_case_id,
        })

    def _mark_group_case_failed(self, task_id, test_case_id, error_message=''):
        self.group_failed_calls.append((task_id, test_case_id))


class TestGroupFailureUnifiedFinalization:

    def test_group_failure_delegates_to_unified_finalization(self):
        """单组失败不再无条件置 TaskCase failed，交给统一收尾判定"""
        trd = SimpleNamespace(test_result_id=99)
        host = _GroupHost()
        session = MagicMock()
        session.get.return_value = trd

        with patch.object(rdm_module, 'get_db_session', MagicMock(return_value=session)):
            host.update_all_dimensions_in_group_failed(
                group_items=[({'id': 7, 'name': 'd'}, 42)],
                error_message='boom', task_id=1, test_case_id='c1',
            )

        assert host.group_failed_calls == []
        assert host.unified_calls == [{
            'result_id': 99,
            'current_result_all_completed': False,
            'task_id': 1,
            'test_case_id': 'c1',
        }]

    def test_group_failure_without_trd_still_safe(self):
        """组内 TRD 查不到（脏数据）：不写用例状态、不抛异常"""
        host = _GroupHost()
        session = MagicMock()
        session.get.return_value = None

        with patch.object(rdm_module, 'get_db_session', MagicMock(return_value=session)):
            host.update_all_dimensions_in_group_failed(
                group_items=[({'id': 7, 'name': 'd'}, 42)],
                error_message='boom', task_id=1, test_case_id='c1',
            )

        assert host.unified_calls == []
        assert host.group_failed_calls == []


# ==================== 5. maybe_finalize 终态判定与重启兜底 ====================

class TestMaybeFinalize:

    @staticmethod
    def _setup(cases, task_status, running_task_id=None, submitting=frozenset()):
        ex = ReevaluationExecutor()
        ex.running_task_id = running_task_id
        ex.is_reevaluating = running_task_id is not None
        ex._submitting_tasks = set(submitting)
        ex._check_queue = MagicMock()
        task = SimpleNamespace(id=1, status=task_status)
        return ex, task

    def _run(self, ex, task, cases):
        with patch.object(task_acl_repository, 'get_task_case_by_ids', MagicMock(return_value=cases)), \
             patch.object(task_acl_repository, 'get_task_by_id', MagicMock(return_value=task)), \
             patch('evaluation_service.infrastructure.evaluation_mixin.update_task_status_with_retry') as upd:
            done = ex.maybe_finalize(1)
        return done, upd

    def test_current_task_all_terminal_completes_and_releases_queue(self):
        cases = [_tc(), _tc(eval_st=EvaluationStatus.FAILED)]
        ex, task = self._setup(cases, TaskStatus.RUNNING, running_task_id=1)

        done, upd = self._run(ex, task, cases)

        assert done is True
        upd.assert_called_once_with(1, TaskStatus.COMPLETED)
        assert ex.running_task_id is None
        assert ex.is_reevaluating is False
        ex._check_queue.assert_called_once()

    def test_active_evaluation_blocks(self):
        ex, task = self._setup(
            [_tc(), _tc(eval_st=EvaluationStatus.QUEUED)],
            TaskStatus.RUNNING, running_task_id=1)

        done, upd = self._run(ex, task, [_tc(), _tc(eval_st=EvaluationStatus.QUEUED)])

        assert done is False
        upd.assert_not_called()
        assert ex.running_task_id == 1

    def test_submitting_window_blocks_premature_convergence(self):
        """提交窗口内"全部终态"是提交前旧状态的假象，不得提前收敛"""
        ex, task = self._setup(
            [_tc()], TaskStatus.REEVALUATING, running_task_id=1, submitting={1})

        done, upd = self._run(ex, task, [_tc()])

        assert done is False
        upd.assert_not_called()

    def test_not_current_without_restart_marker_blocked(self):
        """普通执行链评估任务（非当前重评任务、无重启标记）不受影响"""
        ex, task = self._setup(
            [_tc()], TaskStatus.EVALUATING, running_task_id=None)

        done, upd = self._run(ex, task, [_tc()])

        assert done is False
        upd.assert_not_called()

    def test_not_current_with_running_execution_blocked(self):
        """有未执行完用例的普通任务（重启中断场景）不得被兜底收尾"""
        ex, task = self._setup(
            [_tc(), _tc(exec_st=ExecutionStatus.PENDING)],
            TaskStatus.RUNNING, running_task_id=None)

        done, upd = self._run(ex, task, [_tc()])

        assert done is False
        upd.assert_not_called()

    def test_restart_fallback_completes(self):
        """重启兜底：全用例执行完成 + 带「服务重启」标记 → 收敛为 completed"""
        ex, task = self._setup(
            [_tc(err='服务重启导致任务中断'), _tc(eval_st=EvaluationStatus.FAILED)],
            TaskStatus.FAILED, running_task_id=None)

        done, upd = self._run(ex, task, [
            _tc(err='服务重启导致任务中断'), _tc(eval_st=EvaluationStatus.FAILED)])

        assert done is True
        upd.assert_called_once_with(1, TaskStatus.COMPLETED)

    def test_task_already_terminal_blocked(self):
        """任务已是终态（completed）不再重复收尾"""
        ex, task = self._setup([_tc()], TaskStatus.COMPLETED, running_task_id=None)

        done, upd = self._run(ex, task, [_tc()])

        assert done is False
        upd.assert_not_called()

    def test_derives_failed_when_any_case_execution_failed(self):
        """终态按用例执行结果推导：存在执行失败用例 → failed（重评不改写执行结论）"""
        cases = [_tc(), _tc(exec_st=ExecutionStatus.FAILED)]
        ex, task = self._setup(cases, TaskStatus.RUNNING, running_task_id=1)

        done, upd = self._run(ex, task, cases)

        assert done is True
        upd.assert_called_once_with(1, TaskStatus.FAILED)


# ==================== 6. _on_complete：提交成功 ≠ 完成 ====================

class TestOnComplete:

    def test_submit_success_sets_running_and_holds_queue(self):
        ex = ReevaluationExecutor()
        ex.running_task_id = 1
        ex.is_reevaluating = True
        ex._submitting_tasks = {1}
        ex._check_queue = MagicMock()

        with patch('evaluation_service.infrastructure.evaluation_mixin.update_task_status_with_retry') as upd:
            ex._on_complete(1, True)

        upd.assert_called_once_with(1, TaskStatus.RUNNING)
        # 队列保持占用直至评估收敛（maybe_finalize 释放）
        assert ex.running_task_id == 1
        assert ex.is_reevaluating is True
        assert 1 not in ex._submitting_tasks
        ex._check_queue.assert_not_called()

    def test_submit_failure_sets_failed_and_releases_queue(self):
        ex = ReevaluationExecutor()
        ex.running_task_id = 1
        ex.is_reevaluating = True
        ex._check_queue = MagicMock()

        with patch('evaluation_service.infrastructure.evaluation_mixin.update_task_status_with_retry') as upd:
            ex._on_complete(1, False)

        upd.assert_called_once_with(1, TaskStatus.FAILED)
        assert ex.running_task_id is None
        assert ex.is_reevaluating is False
        ex._check_queue.assert_called_once()


# ==================== 7. 提交前清理旧评估（方案A+B） ====================

class TestCancelPreviousEvaluations:

    def test_pop_and_notify_subservice(self):
        EvalTaskRegistry.register('e1', 5, 'http://ep-a/')
        ex = ReevaluationExecutor()

        resp = SimpleNamespace(status_code=200)
        with patch('requests.delete', MagicMock(return_value=resp)) as del_req:
            ex._cancel_previous_evaluations(5)

        del_req.assert_called_once()
        assert del_req.call_args.args[0] == 'http://ep-a/api/cancel_task/e1'
        assert EvalTaskRegistry.is_cancelled('e1') is True

    def test_subservice_unreachable_tolerated(self):
        """子服务无 cancel_task / 不可达：记 WARNING 继续，不失败（契约兼容项）"""
        EvalTaskRegistry.register('e1', 5, 'http://ep-a')
        ex = ReevaluationExecutor()

        with patch('requests.delete', MagicMock(side_effect=Exception('connection refused'))):
            ex._cancel_previous_evaluations(5)  # 不抛异常

        assert EvalTaskRegistry.is_cancelled('e1') is True

    def test_no_inflight_tasks_no_request(self):
        ex = ReevaluationExecutor()
        with patch('requests.delete', MagicMock()) as del_req:
            ex._cancel_previous_evaluations(5)
        del_req.assert_not_called()

    def test_submit_invokes_cleanup(self):
        """submit 入口在入队后、启动执行前完成旧评估清理"""
        ex = ReevaluationExecutor()
        ex._check_queue = MagicMock()

        with patch.object(task_acl_repository, 'update_task_status', MagicMock(return_value=True)), \
             patch.object(ex, '_cancel_previous_evaluations') as cleanup:
            ok, _ = ex.submit(5)

        assert ok is True
        cleanup.assert_called_once_with(5)


# ==================== 8. 打回修复①：pending 维度纳入 failed 收集范围 ====================

class TestPendingDimCollection:
    """缺陷1：failed 型重评收集范围纳入非终态（pending）TRD——重启崩溃遗留的
    进行中维度可被重评触达，不再因「仅收集 failed」而永久无人收尾。"""

    def test_failed_type_collects_pending_dims(self, patched_acl):
        patched_acl.list_scores.return_value = [
            _trd(7, 0, EvaluationStatus.FAILED, 'mock fail'),
            _trd(9, 0, EvaluationStatus.COMPLETED),   # 已完成维度不重评
            _trd(8, 1, EvaluationStatus.PENDING),     # 重启遗留 pending 维度
        ]
        ex = _mk_executor()
        with patch.object(reexec_module, 'evaluation_service') as eval_svc:
            eval_svc.evaluate_case.return_value = True

            ok = ex._reevaluate_multi_round(
                task_id=1, result=11, test_case_id='c1',
                algorithm_result={'rounds': [{'output': {}}, {'output': {}}]},
                test_type='e2e', algorithm_type='translation',
                reevaluate_type='failed',
            )

        assert ok is True
        round_calls = [c for c in eval_svc.evaluate_case.call_args_list if 'round_number' in c.kwargs]
        assert [c.kwargs['dimension_filter_ids'] for c in round_calls] == [[7], [8]]

    def test_single_collects_pending_dims(self, patched_acl):
        patched_acl.list_scores.return_value = [
            _trd(7, None, EvaluationStatus.PENDING),
        ]
        ex = _mk_executor()
        with patch.object(reexec_module, 'evaluation_service') as eval_svc:
            eval_svc.evaluate_case.return_value = True

            ok = ex._reevaluate_single(
                task_id=1, result_id=11, test_case_id='c1',
                algorithm_result={'output': {}}, reference_params=[],
                test_type='api', algorithm_type='translation',
                reevaluate_type='failed',
            )

        assert ok is True
        assert eval_svc.evaluate_case.call_args.kwargs['dimension_filter_ids'] == [7]


# ==================== 9. 打回修复①：重评范围外遗留非终态 TRD 收口 ====================

class TestSweepOutOfScopeActiveScores:
    """被配置排除的轮次（evaluation.enabled=false / 无整体口径维度）里遗留的
    非终态 TRD 永远不会被评估触达，统一收尾的全维终态门控会拒绝收敛——
    提交阶段结束后按「已提交轮次」排除收口为 failed。"""

    def test_pending_trd_on_disabled_round_swept(self, patched_acl):
        patched_acl.list_scores.return_value = [
            _trd(7, 0, EvaluationStatus.FAILED, 'mock fail'),
            _trd(8, 1, EvaluationStatus.PENDING),     # round 1 评估停用 → 收口
        ]
        with patch.object(task_acl_repository, 'get_test_case_detail', MagicMock(return_value=SimpleNamespace(
                config={'rounds': [
                    {'evaluation': {'dimensions': [{'id': 7}]}},
                    {'evaluation': {'enabled': False, 'dimensions': [{'id': 8}]}},
                ], 'dimensions': []},
                algorithm_params=None, reference_params=None, algorithm_type='translation'))):
            ex = _mk_executor()
            with patch.object(reexec_module, 'evaluation_service') as eval_svc:
                eval_svc.evaluate_case.return_value = True

                ex._reevaluate_multi_round(
                    task_id=1, result=11, test_case_id='c1',
                    algorithm_result={'rounds': [{'output': {}}, {'output': {}}]},
                    test_type='e2e', algorithm_type='translation',
                    reevaluate_type='failed',
                )

        patched_acl.sweep.assert_called_once()
        args = patched_acl.sweep.call_args.args
        assert args[0] == 11
        assert args[1] == {0}   # 保留已提交的 round 0，round 1 收口

    def test_pending_trd_on_submitted_round_not_swept(self, patched_acl):
        """已提交轮次的 TRD 被复用重置（评估在途），不得收口"""
        patched_acl.list_scores.return_value = [
            _trd(7, 0, EvaluationStatus.PENDING),
        ]
        ex = _mk_executor()
        with patch.object(reexec_module, 'evaluation_service') as eval_svc:
            eval_svc.evaluate_case.return_value = True

            ex._reevaluate_multi_round(
                task_id=1, result=11, test_case_id='c1',
                algorithm_result={'rounds': [{'output': {}}]},
                test_type='e2e', algorithm_type='translation',
                reevaluate_type='failed',
            )

        patched_acl.sweep.assert_called_once()
        assert patched_acl.sweep.call_args.args[1] == {0}

    def test_overall_pending_swept_when_no_overall_dims(self, patched_acl):
        """config 无整体口径维度：None 键 pending TRD 收口"""
        patched_acl.list_scores.return_value = [
            _trd(7, 0, EvaluationStatus.PENDING),
            _trd(12, None, EvaluationStatus.PENDING),  # 整体口径无处提交 → 收口
        ]
        with patch.object(task_acl_repository, 'get_test_case_detail', MagicMock(return_value=SimpleNamespace(
                config={'rounds': [{'evaluation': {'dimensions': [{'id': 7}]}}],
                        'dimensions': []},
                algorithm_params=None, reference_params=None, algorithm_type='translation'))):
            ex = _mk_executor()
            with patch.object(reexec_module, 'evaluation_service') as eval_svc:
                eval_svc.evaluate_case.return_value = True

                ex._reevaluate_multi_round(
                    task_id=1, result=11, test_case_id='c1',
                    algorithm_result={'rounds': [{'output': {}}]},
                    test_type='e2e', algorithm_type='translation',
                    reevaluate_type='failed',
                )

        patched_acl.sweep.assert_called_once()
        assert patched_acl.sweep.call_args.args[1] == {0}

    def test_single_not_submitted_sweeps_all(self, patched_acl):
        """单轮结果未提交评估（过滤后无可评估维度）：全部非终态 TRD 收口"""
        patched_acl.list_scores.return_value = [
            _trd(7, None, EvaluationStatus.PENDING),
        ]
        ex = _mk_executor()
        with patch.object(reexec_module, 'evaluation_service') as eval_svc:
            eval_svc.evaluate_case.return_value = False

            ex._reevaluate_single(
                task_id=1, result_id=11, test_case_id='c1',
                algorithm_result={'output': {}}, reference_params=[],
                test_type='api', algorithm_type='translation',
                reevaluate_type='failed',
            )

        patched_acl.sweep.assert_called_once()
        assert patched_acl.sweep.call_args.args[0] == 11
        assert patched_acl.sweep.call_args.args[1] is None  # 不排除任何轮次

    def test_all_type_never_sweeps(self, patched_acl):
        """全量重评（all）TRD 已清空重建，无需收口"""
        ex = _mk_executor()
        with patch.object(reexec_module, 'evaluation_service') as eval_svc:
            eval_svc.evaluate_case.return_value = True

            ex._reevaluate_multi_round(
                task_id=1, result=11, test_case_id='c1',
                algorithm_result={'rounds': [{'output': {}}]},
                test_type='e2e', algorithm_type='translation',
                reevaluate_type='all',
            )

        patched_acl.sweep.assert_not_called()


# ==================== 10. 打回修复②：零提交重评主动收敛 ====================

class TestZeroSubmissionConvergence:
    """缺陷2：零提交（无待重评用例 / 全部轮次被跳过）时无任何评估在途，
    端点 Worker 回调（maybe_finalize 唯一触发源）永远不会到达——必须主动
    收敛任务终态并释放重评队列，否则任务永久卡 running、队列被占死。"""

    @staticmethod
    def _running_executor(task_id=491):
        ex = ReevaluationExecutor()
        ex.running_task_id = task_id
        ex.is_reevaluating = True
        ex._submitting_tasks = set()
        ex._check_queue = MagicMock()
        return ex

    def test_zero_submission_converges_and_releases_queue(self):
        """全部用例评估已到终态：直接置 completed 并释放队列"""
        ex = self._running_executor()
        cases = [_tc(), _tc(eval_st=EvaluationStatus.FAILED)]
        task = SimpleNamespace(id=491, status=TaskStatus.REEVALUATING)

        with patch.object(task_acl_repository, 'get_task_case_by_ids', MagicMock(return_value=cases)), \
             patch.object(task_acl_repository, 'get_task_by_id', MagicMock(return_value=task)), \
             patch('evaluation_service.infrastructure.evaluation_mixin.update_task_status_with_retry') as upd:
            ex._on_complete(491, True, submitted_cases=0)

        upd.assert_called_once_with(491, TaskStatus.COMPLETED)
        assert ex.running_task_id is None
        assert ex.is_reevaluating is False
        # maybe_finalize 收敛释放时一次 + 零提交分支兜底释放时一次
        assert ex._check_queue.call_count == 2

    def test_zero_submission_fallback_releases_queue_when_cannot_converge(self):
        """无用例元数据可判定收敛：置 running 兜底，但队列必须释放（不占死）"""
        ex = self._running_executor()

        with patch.object(task_acl_repository, 'get_task_case_by_ids', MagicMock(return_value=[])), \
             patch('evaluation_service.infrastructure.evaluation_mixin.update_task_status_with_retry') as upd:
            ex._on_complete(491, True, submitted_cases=0)

        upd.assert_called_once_with(491, TaskStatus.RUNNING)
        assert ex.running_task_id is None
        assert ex.is_reevaluating is False
        ex._check_queue.assert_called_once()

    def test_zero_submission_converge_check_error_still_releases_queue(self):
        """收敛判定本身异常（如 task_service 不可达）：置 running 兜底且队列释放，不占死"""
        ex = self._running_executor()

        with patch.object(task_acl_repository, 'get_task_case_by_ids',
                          MagicMock(side_effect=RuntimeError('grpc unavailable'))), \
             patch('evaluation_service.infrastructure.evaluation_mixin.update_task_status_with_retry') as upd:
            ex._on_complete(491, True, submitted_cases=0)  # 不抛异常

        upd.assert_called_once_with(491, TaskStatus.RUNNING)
        assert ex.running_task_id is None
        assert ex.is_reevaluating is False
        ex._check_queue.assert_called_once()

    def test_some_submitted_still_holds_queue(self):
        """确有评估在途：维持 running + 队列占用，由 maybe_finalize 收敛（既有语义）。

        INT-632：_on_complete 成功路径在提交窗口关闭后补一次 maybe_finalize 收敛
        检查——用例评估仍在途时返回 False，任务保持 running、队列保持占用、不提前
        收敛（后续由端点回调触发收敛）。
        """
        ex = self._running_executor()

        with patch('evaluation_service.infrastructure.evaluation_mixin.update_task_status_with_retry') as upd, \
             patch.object(task_acl_repository, 'get_task_case_by_ids',
                          MagicMock(return_value=[
                              SimpleNamespace(test_case_id='c1',
                                              execution_status=ExecutionStatus.COMPLETED,
                                              evaluation_status=EvaluationStatus.RUNNING),
                          ])):
            ex._on_complete(491, True, submitted_cases=2)

        upd.assert_called_once_with(491, TaskStatus.RUNNING)
        assert ex.running_task_id == 491
        assert ex.is_reevaluating is True
        ex._check_queue.assert_not_called()

    def test_submit_success_with_all_eval_terminal_converges_immediately(self):
        """INT-632 竞态修复：提交完成时评估已全部到终态（快速端点）→ 直接收敛 completed。

        端点回调在提交窗口（still_submitting）内到达被拒后不会再有回调；_on_complete
        成功路径补一次 maybe_finalize，快速评估已完成时任务不再卡 running。
        """
        ex = self._running_executor()

        with patch('evaluation_service.infrastructure.evaluation_mixin.update_task_status_with_retry') as upd, \
             patch.object(task_acl_repository, 'get_task_case_by_ids',
                          MagicMock(return_value=[
                              SimpleNamespace(test_case_id='c1',
                                              execution_status=ExecutionStatus.COMPLETED,
                                              evaluation_status=EvaluationStatus.COMPLETED),
                          ])), \
             patch.object(task_acl_repository, 'get_task_by_id',
                          MagicMock(return_value=SimpleNamespace(id=491, status=TaskStatus.RUNNING))):
            ex._on_complete(491, True, submitted_cases=1)

        # RUNNING 先写，maybe_finalize 再收敛为 COMPLETED 并释放队列
        upd.assert_any_call(491, TaskStatus.RUNNING)
        upd.assert_any_call(491, TaskStatus.COMPLETED)
        assert ex.running_task_id is None
        assert ex.is_reevaluating is False
        ex._check_queue.assert_called_once()

    def test_form_b_zero_cases_converges_end_to_end(self):
        """形态B（收集到 0 个用例）：_run_reevaluation 全链收敛为 completed"""
        ex = ReevaluationExecutor()
        ex.running_task_id = 491
        ex.is_reevaluating = True
        ex._check_queue = MagicMock()
        cases = [_tc(), _tc(eval_st=EvaluationStatus.FAILED)]
        task = SimpleNamespace(id=491, status=TaskStatus.REEVALUATING)

        with patch.object(task_acl_repository, 'get_test_results_by_task_and_case',
                          MagicMock(return_value=[])), \
             patch.object(task_acl_repository, 'get_task_case_by_ids', MagicMock(return_value=cases)), \
             patch.object(task_acl_repository, 'get_task_by_id', MagicMock(return_value=task)), \
             patch('evaluation_service.application.handlers.reevaluation_executor.log_and_emit'), \
             patch('evaluation_service.infrastructure.evaluation_mixin.update_task_status_with_retry') as upd:
            ex._run_reevaluation(task_id=491, reextract_device_output=False, reevaluate_type='failed')

        upd.assert_called_once_with(491, TaskStatus.COMPLETED)
        assert ex.running_task_id is None
        assert ex.is_reevaluating is False
        # maybe_finalize 收敛释放时一次 + 零提交分支兜底释放时一次
        assert ex._check_queue.call_count == 2


# ==================== 11. 打回修复③：m2 / m1 顺手项 ====================

class TestFilterNonNumericConfigDimId:
    """m2：config 出现非数字维度 id 且带 filter → 跳过该维度，而非 ValueError 中断评估入口"""

    def test_non_numeric_config_dim_id_skipped(self):
        host = _FilterHost()
        host._load_test_case_and_refs = lambda *a, **k: {
            'test_case': SimpleNamespace(name='case-a'),
            'algorithm_type': 'translation',
            'ref_texts': {},
            'dimensions_config': [{'id': '121'}, {'id': 'abc'}],
        }

        prepared = host._prepare_evaluation_data(
            task_id=1, result_id=11, test_case_id='c1', algorithm_result={},
            field_mapper=None, kwargs={'dimension_filter_ids': [121]},
            test_type='api', round_number=None,
        )

        assert prepared is not False
        assert prepared['dimension_data_list'] == [{'id': 121}]


class TestProcessEvaluationResultSecondCancelCheck:
    """m1 硬化：结果写库前二次核销取消标记，收窄「核销→落库」竞态窗口"""

    @staticmethod
    def _worker():
        from evaluation_service.infrastructure.evaluation_api.endpoint_worker import EndpointWorker
        w = object.__new__(EndpointWorker)
        w._log = MagicMock()
        w.eval_service = SimpleNamespace(result_processor=MagicMock())
        return w

    def test_cancelled_before_persist_is_isolated(self):
        """核销后、落库前被取消：结果隔离，不写库"""
        EvalTaskRegistry.register('e1', 5, 'http://ep-a')
        EvalTaskRegistry.pop_by_task(5)
        w = self._worker()
        resp_data = {'wer': 0.1, '__eval_task_id__': 'e1'}

        with patch.object(task_acl_repository, 'get_task_case_by_ids', MagicMock(return_value=[])):
            w._process_evaluation_result(resp_data, [({'id': 7, 'name': 'd'}, 1)],
                                         5, 'c1', 11, {}, 'api')

        w.eval_service.result_processor.process_group_dimension_results.assert_not_called()
        # 标记已消费，不落库泄漏
        assert '__eval_task_id__' not in resp_data

    def test_not_cancelled_processed_without_marker_leak(self):
        """未取消：正常写库，__eval_task_id__ 不随 api_raw_response 落库"""
        EvalTaskRegistry.register('e1', 5, 'http://ep-a')
        w = self._worker()
        resp_data = {'wer': 0.1, '__eval_task_id__': 'e1'}

        with patch.object(task_acl_repository, 'get_task_case_by_ids', MagicMock(return_value=[])):
            w._process_evaluation_result(resp_data, [({'id': 7, 'name': 'd'}, 1)],
                                         5, 'c1', 11, {}, 'api')

        call = w.eval_service.result_processor.process_group_dimension_results
        call.assert_called_once()
        assert call.call_args.kwargs['resp_data'] == {'wer': 0.1}

    def test_result_without_marker_processed_normally(self):
        """无标记（同步链路等）：行为不变"""
        w = self._worker()
        resp_data = {'wer': 0.1}

        with patch.object(task_acl_repository, 'get_task_case_by_ids', MagicMock(return_value=[])):
            w._process_evaluation_result(resp_data, [({'id': 7, 'name': 'd'}, 1)],
                                         5, 'c1', 11, {}, 'api')

        w.eval_service.result_processor.process_group_dimension_results.assert_called_once()


# ==================== 12. 执行未成功的用例不参与重评 ====================

class TestExecutedCaseGate:
    """重评只修正评估结论、不重跑执行：范围内无执行成功用例 → 直接拒绝。"""

    @staticmethod
    def _tc(case_id, exec_st):
        return SimpleNamespace(test_case_id=case_id, execution_status=exec_st)

    @staticmethod
    def _submit(ex, cases, **kwargs):
        with patch.object(task_acl_repository, 'get_task_case_by_ids',
                          MagicMock(return_value=cases)), \
             patch.object(task_acl_repository, 'update_task_status') as upd_status, \
             patch.object(ex, '_cancel_previous_evaluations'), \
             patch.object(ex, '_check_queue') as check_queue:
            ok, message = ex.submit(7, reextract_device_output=False,
                                    reevaluate_type='all', **kwargs)
        return ok, message, upd_status, check_queue

    def test_all_cases_execution_failed_rejected(self):
        """全部用例执行失败 → 拒绝，不入队、不改任务状态、不启动队列"""
        ex = ReevaluationExecutor()
        ok, message, upd_status, check_queue = self._submit(
            ex, [self._tc('c1', ExecutionStatus.FAILED)])

        assert ok is False
        assert '没有执行成功的用例' in message
        assert ex.reevaluation_queue == []
        upd_status.assert_not_called()
        check_queue.assert_not_called()

    def test_any_executed_case_passes(self):
        """存在执行成功的用例 → 放行"""
        ex = ReevaluationExecutor()
        ok, _, upd_status, _ = self._submit(
            ex, [self._tc('c1', ExecutionStatus.COMPLETED),
                 self._tc('c2', ExecutionStatus.FAILED)])

        assert ok is True
        upd_status.assert_called_once()

    def test_selected_scope_only_failed_cases_rejected(self):
        """选中范围只含执行失败用例 → 拒绝（不按任务内其它成功用例放行）"""
        ex = ReevaluationExecutor()
        ok, message, _, _ = self._submit(
            ex, [self._tc('c1', ExecutionStatus.COMPLETED),
                 self._tc('c2', ExecutionStatus.FAILED)],
            options={'case_ids': ['c2'], 'mode': 'selected'})

        assert ok is False
        assert '没有执行成功的用例' in message

    def test_query_failure_does_not_block(self):
        """用例状态查询失败 → 放行（收集阶段同样按用例执行状态过滤兜底）"""
        ex = ReevaluationExecutor()
        with patch.object(task_acl_repository, 'get_task_case_by_ids',
                          MagicMock(side_effect=RuntimeError('grpc down'))), \
             patch.object(task_acl_repository, 'update_task_status'), \
             patch.object(ex, '_cancel_previous_evaluations'), \
             patch.object(ex, '_check_queue'):
            ok, _ = ex.submit(7, reextract_device_output=False, reevaluate_type='all')

        assert ok is True


class TestCollectSkipsUnexecutedCase:
    """收集阶段过滤：TaskCase.execution_status != completed 的用例不进入重评"""

    @staticmethod
    def _result(case_id):
        return SimpleNamespace(test_case_id=case_id, execution_status=ExecutionStatus.COMPLETED,
                               algorithm_result={})

    def _collect(self, collect_fn, cases):
        from evaluation_service.domain.services.reevaluation_service import ReevaluationService
        results = [self._result(cid) for cid in cases]
        task_case_map = {cid: SimpleNamespace(test_case_id=cid, execution_status=st,
                                              evaluation_status=EvaluationStatus.FAILED)
                         for cid, st in cases.items()}
        with patch.object(ReevaluationService, '_build_case_info',
                          MagicMock(return_value={'test_case_id': 'x'})):
            return collect_fn(results, {}, task_case_map, False)

    def test_collect_all_skips_failed_execution(self):
        from evaluation_service.domain.services.reevaluation_service import ReevaluationService
        cases = self._collect(ReevaluationService.collect_cases_all,
                              {'c1': ExecutionStatus.FAILED,
                               'c2': ExecutionStatus.COMPLETED})
        assert len(cases) == 1

    def test_collect_failed_skips_failed_execution(self):
        from evaluation_service.domain.services.reevaluation_service import ReevaluationService
        cases = self._collect(ReevaluationService.collect_cases_failed,
                              {'c1': ExecutionStatus.FAILED,
                               'c2': ExecutionStatus.COMPLETED})
        assert len(cases) == 1
