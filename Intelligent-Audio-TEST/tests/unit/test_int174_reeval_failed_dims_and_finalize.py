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
   __cancelled__ 隔离，不污染新评估。
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
    yield
    EvalTaskRegistry._entries = {}
    EvalTaskRegistry._cancelled = {}


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

        assert resp == {'wer': 0.1}
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

    def _mark_evaluation_queued(self, task_id, test_case_id):
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

    def test_filter_ignores_invalid_entries(self):
        host, prepared = self._prepare({'dimension_filter_ids': ['abc', None, 121]})
        assert prepared is not False
        assert prepared['dimension_data_list'] == [{'id': 121}]


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
    patch('evaluation_service.infrastructure.acl.algorithm_acl_repository.algorithm_acl_repository',
          **{'extract_case_all_params.return_value': {'evaluation': {}}}) as algo_acl:
        yield SimpleNamespace(
            get_tc=get_tc, upd_tc=upd_tc, get_detail=get_detail,
            list_scores=list_scores, del_scores=del_scores, algo_acl=algo_acl,
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
        """全部轮次因无失败维度被跳过（失败轮评估已停用）→ 用例按评估失败收口"""
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

        assert ok is True
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
                    {'output': 'x', 'round_evaluation': {'wer': 0.1}},
                    {'output': 'y', 'round_evaluation': {'wer': 0.2}},
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
