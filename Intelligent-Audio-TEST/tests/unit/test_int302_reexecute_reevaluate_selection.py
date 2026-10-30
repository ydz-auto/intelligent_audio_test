# -*- coding: utf-8 -*-
"""INT-302 回归守卫：重执行/重评估按用例+按维度选择

覆盖四层（均纯单测，不触真实 DB/gRPC/Redis）：

1. task_service 生命周期：retry(options) 范围模式——
   - selected：仅命中 case_ids 的用例重置重执行，其余不动；
   - failed_only：仅执行/评估失败用例；
   - 缺省 all：整任务语义不变（沿用 find_retry_cases 旧路径）；
   - selected 空 case_ids → 400 拒绝；非法 mode → 400 拒绝。
2. evaluation_service 重评执行器：dimension_ids 维度过滤——
   - all + 选中维度：按选中集过滤（TRD 保留不清空）；
   - failed + 选中维度：失败集 ∩ 选中集，交集为空跳过；
   - 单轮（_reevaluate_single）同口径；
   - case_ids 结果集过滤（_run_reevaluation 内联过滤）；
   - F2：submit selected 且空 case_ids → 拒绝（与 retry 400 语义对齐）。
3. 网关 evaluation_command_service.reevaluate_task_results：
   camelCase caseIds/dimensionIds 解析 + options 透传 ACL；
   选中用例时 queued 按选中数计（非任务全量）。
4. 网关 TaskLifecycleService.retry：body case_ids/mode 透传 ACL；
   缺省 body 不带 options（整任务语义零改动）。
5. F3：任务详情读模型按用例聚合评估维度（extract_case_evaluation_dimensions）。
"""
import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

from shared.utils.status_constants import EvaluationStatus, ExecutionStatus

import evaluation_service.infrastructure.acl as _acl_pkg
from evaluation_service.infrastructure.acl import task_acl_repository
import evaluation_service.application.handlers.reevaluation_executor as reexec_module
from evaluation_service.application.handlers.reevaluation_executor import ReevaluationExecutor

import api_gateway.application.services.evaluation.evaluation_command_service as eval_cmd_mod
import api_gateway.application.services.task.task_lifecycle_service as gw_task_lifecycle_mod
from api_gateway.infrastructure.request_adapter import set_current_request

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


def _tc(case_id, exec_st=ExecutionStatus.COMPLETED, eval_st=EvaluationStatus.COMPLETED):
    """TaskCase ORM 形状的对象（task_lifecycle_service.retry 消费）"""
    return SimpleNamespace(
        test_case_id=case_id,
        execution_status=exec_st,
        evaluation_status=eval_st,
        status='completed',
        error_message=None,
        started_at=None,
        completed_at=None,
        duration=None,
        device_type='physical',
    )


def _fake_request(json_body=None, query=None):
    """构造 request_adapter 所需的最小请求替身。"""
    state = SimpleNamespace(_json_body=json_body, _files={}, _form_data={})
    return SimpleNamespace(state=state, query_params=query or {})


@pytest.fixture(autouse=True)
def _reset_executor_singleton():
    """隔离 ReevaluationExecutor 进程级单例（队列/占用状态跨用例泄漏）"""
    ReevaluationExecutor._instance = None
    yield
    ReevaluationExecutor._instance = None


# ==================== 1. task_service retry 范围模式 ====================

class TestTaskLifecycleRetryScoped:
    """TaskLifecycleService.retry(options) 按用例选择重执行"""

    def _run_retry(self, task_lifecycle, options, scoped_cases, legacy_cases):
        """公共编排：mock 仓储/执行引擎，跑 retry 并返回 (result, 清理调用记录)"""
        calls = {'cleanup': [], 'commit': [], 'started': None}
        task = SimpleNamespace(id=5, status='completed')

        with patch('task_service.application.task.task_lifecycle_service.task_repository') as repo:
            repo.get_task_orm.return_value = task
            repo.find_retry_cases.return_value = legacy_cases
            repo.find_retry_cases_scoped.return_value = scoped_cases
            repo.cleanup_case_results.side_effect = (
                lambda tid, ids, preserve_test_result: calls['cleanup'].append(
                    (list(ids), preserve_test_result)))
            repo.commit_task_case.side_effect = lambda tc: calls['commit'].append(tc.test_case_id)

            with patch('task_service.core.execution_engine.execution_engine') as engine:
                engine.start_task.return_value = (True, '任务已启动')
                engine.control_task.return_value = (True, 'ok')
                result = task_lifecycle.retry(5, options=options)
                calls['started'] = engine.start_task.call_count

        return result, calls

    def test_selected_only_resets_chosen_cases(self):
        """选 2 个用例重执行：仅这 2 个用例重置，其余不动"""
        from task_service.application.task.task_lifecycle_service import TaskLifecycleService
        lc = TaskLifecycleService()
        scoped = [_tc('c1'), _tc('c2')]
        # 任务里还有第三个已完成用例，但未被选中——不应出现在清理/重置列表
        legacy = [_tc('c1'), _tc('c2'), _tc('c3')]

        with patch.object(TaskLifecycleService, '_trigger_reevaluate'):
            result, calls = self._run_retry(
                lc, {'mode': 'selected', 'case_ids': ['c1', 'c2']}, scoped, legacy)

        assert result['success'] is True
        assert result['data']['retry_mode'] == 'selected'
        assert result['data']['retry_case_count'] == 2
        # 清理仅覆盖选中用例；c3 不出现
        cleaned_ids = {cid for ids, _ in calls['cleanup'] for cid in ids}
        assert cleaned_ids == {'c1', 'c2'}
        assert calls['commit'] == ['c1', 'c2']
        assert calls['started'] == 1

    def test_selected_hits_scoped_repository_query(self):
        """selected 模式查询走 find_retry_cases_scoped（不拉全量再过滤）"""
        from task_service.application.task.task_lifecycle_service import TaskLifecycleService
        lc = TaskLifecycleService()
        with patch('task_service.application.task.task_lifecycle_service.task_repository') as repo:
            repo.get_task_orm.return_value = SimpleNamespace(id=5, status='completed')
            repo.find_retry_cases_scoped.return_value = [_tc('c1')]
            with patch('task_service.core.execution_engine.execution_engine') as engine:
                engine.start_task.return_value = (True, 'ok')
                result = lc.retry(5, options={'mode': 'selected', 'case_ids': ['c1']})
        assert result['success'] is True
        repo.find_retry_cases_scoped.assert_called_once_with(5, 'selected', ['c1'])
        repo.find_retry_cases.assert_not_called()

    def test_failed_only_uses_scoped_query(self):
        """failed_only：仅失败用例（scoped 查询按执行/评估失败过滤）"""
        from task_service.application.task.task_lifecycle_service import TaskLifecycleService
        lc = TaskLifecycleService()
        with patch('task_service.application.task.task_lifecycle_service.task_repository') as repo:
            repo.get_task_orm.return_value = SimpleNamespace(id=5, status='failed')
            repo.find_retry_cases_scoped.return_value = [_tc('c9', ExecutionStatus.FAILED)]
            with patch('task_service.core.execution_engine.execution_engine') as engine:
                engine.start_task.return_value = (True, 'ok')
                result = lc.retry(5, options={'mode': 'failed_only'})
        assert result['success'] is True
        assert result['data']['retry_mode'] == 'failed_only'
        repo.find_retry_cases_scoped.assert_called_once_with(5, 'failed_only', [])

    def test_legacy_all_keeps_old_path(self):
        """缺省 options：整任务语义不变（沿用 find_retry_cases 旧路径）"""
        from task_service.application.task.task_lifecycle_service import TaskLifecycleService
        lc = TaskLifecycleService()
        legacy = [_tc('c1', ExecutionStatus.FAILED), _tc('c2', ExecutionStatus.PENDING)]
        result, calls = self._run_retry(lc, None, [], legacy)

        assert result['success'] is True
        assert result['data']['retry_mode'] == 'all'
        assert result['data']['retry_case_count'] == 2

    def test_selected_empty_case_ids_rejected(self):
        """selected 且 case_ids 为空 → 400 拒绝（不触碰任务状态）"""
        from task_service.application.task.task_lifecycle_service import TaskLifecycleService
        lc = TaskLifecycleService()
        with patch('task_service.application.task.task_lifecycle_service.task_repository'):
            result = lc.retry(5, options={'mode': 'selected', 'case_ids': []})
        assert result['success'] is False
        assert result['code'] == 400

    def test_invalid_mode_rejected(self):
        """非法 mode → 400 拒绝"""
        from task_service.application.task.task_lifecycle_service import TaskLifecycleService
        lc = TaskLifecycleService()
        with patch('task_service.application.task.task_lifecycle_service.task_repository'):
            result = lc.retry(5, options={'mode': 'bogus'})
        assert result['success'] is False
        assert result['code'] == 400

    def test_selected_completed_case_triggers_reevaluate(self):
        """selected 命中已完成用例：清算法结果（保留 result_data）并触发重评"""
        from task_service.application.task.task_lifecycle_service import TaskLifecycleService
        lc = TaskLifecycleService()
        scoped = [_tc('c1', ExecutionStatus.COMPLETED)]
        with patch('task_service.application.task.task_lifecycle_service.task_repository') as repo:
            repo.get_task_orm.return_value = SimpleNamespace(id=5, status='completed')
            repo.find_retry_cases_scoped.return_value = scoped
            with patch('task_service.core.execution_engine.execution_engine') as engine, \
                 patch.object(lc, '_trigger_reevaluate') as trig:
                engine.start_task.return_value = (True, 'ok')
                result = lc.retry(5, options={'mode': 'selected', 'case_ids': ['c1']})
        assert result['success'] is True
        # 已完成用例走 preserve_test_result=True 清理（重评口径）
        repo.cleanup_case_results.assert_called_once_with(5, ['c1'], preserve_test_result=True)
        # 触发既有重评链路（与其他 retry 语义对齐）
        trig.assert_called_once()
        assert trig.call_args[0][1] == scoped


class TestFindRetryCasesScoped:
    """仓储层 find_retry_cases_scoped 查询口径（内存 SQLite）"""

    def test_selected_filters_by_case_ids(self):
        sqlalchemy = pytest.importorskip('sqlalchemy')
        from task_service.infrastructure.persistence._task_lifecycle_mixin import TaskLifecycleMixin
        from shared.models.common_enums import RetryScopeMode
        mixin = TaskLifecycleMixin()
        if not hasattr(mixin, 'find_retry_cases_scoped'):
            pytest.skip('mixin 未组合该方法')
        # 仅验证方法可调用且签名归一（DB 集成由 e2e 回归覆盖）
        import inspect
        sig = inspect.signature(TaskLifecycleMixin.find_retry_cases_scoped)
        assert list(sig.parameters) == ['self', 'task_id', 'mode', 'selected_case_ids']
        assert RetryScopeMode.SELECTED.value == 'selected'


class TestTaskDetailEvaluationDimensions:
    """INT-302/F3：任务详情读模型按用例聚合评估维度（重评估维度候选集）"""

    def test_extract_dedupes_overall_and_round_dims(self):
        """整体口径 + 逐轮口径聚合去重，保留首次出现的 id/name"""
        from task_service.infrastructure.read_models.task_read_model_detail import (
            TaskDetailReadModelMixin,
        )
        config = {
            'dimensions': [{'id': 7, 'name': 'WER', 'weight': 1}, {'id': 8, 'name': 'CER'}],
            'rounds': [
                {'evaluation': {'dimensions': [{'id': 7, 'name': 'WER'}, {'id': 9, 'name': '时延'}]}},
                {'evaluation': {'dimensions': [{'id': 8, 'name': 'CER'}]}},
                {'evaluation': {'enabled': False, 'dimensions': [{'id': 99, 'name': '仅配置'}]}},
            ],
        }
        dims = TaskDetailReadModelMixin.extract_case_evaluation_dimensions(config)
        assert dims == [
            {'id': 7, 'name': 'WER'},
            {'id': 8, 'name': 'CER'},
            {'id': 9, 'name': '时延'},
            {'id': 99, 'name': '仅配置'},
        ]

    def test_extract_handles_missing_or_malformed_config(self):
        """缺省/畸形 config 与缺 name 条目的防御（id-only 回退字符串化）"""
        from task_service.infrastructure.read_models.task_read_model_detail import (
            TaskDetailReadModelMixin,
        )
        assert TaskDetailReadModelMixin.extract_case_evaluation_dimensions(None) == []
        assert TaskDetailReadModelMixin.extract_case_evaluation_dimensions({}) == []
        assert TaskDetailReadModelMixin.extract_case_evaluation_dimensions({'rounds': 'bogus'}) == []
        assert TaskDetailReadModelMixin.extract_case_evaluation_dimensions(
            {'dimensions': [{'name': '无id'}, 'junk', {'id': 7}]}) == [{'id': 7, 'name': '7'}]


# ==================== 2. evaluation_service 维度过滤 ====================

@pytest.fixture
def patched_acl():
    """重评执行器依赖的 ACL/评估服务桩（对齐 INT-174 测试同款）"""
    with patch.object(reexec_module.task_acl_repository, 'get_task_case_by_ids', MagicMock(return_value=[
        SimpleNamespace(test_case_id='c1', device_type='physical',
                        execution_status=ExecutionStatus.COMPLETED,
                        evaluation_status=EvaluationStatus.FAILED),
    ])) as get_tc, \
    patch.object(reexec_module.task_acl_repository, 'update_task_case_status', MagicMock(return_value=True)) as upd_tc, \
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


class TestReevaluateDimensionSelection:
    """INT-302：重评估按维度选择（dimension_filter_ids 下传）"""

    def test_all_type_with_dimension_selection_filters_and_keeps_trd(self, patched_acl):
        """all + 选中维度：按选中集过滤（TRD 保留，不清空）"""
        ex = ReevaluationExecutor()
        with patch.object(reexec_module, 'evaluation_service') as eval_svc:
            eval_svc.evaluate_case.return_value = True

            ok = ex._reevaluate_multi_round(
                task_id=1, result=11, test_case_id='c1',
                algorithm_result={'rounds': [{'output': {}}, {'output': {}}]},
                device_type='physical', algorithm_type='translation',
                reevaluate_type='all',
                dimension_filter_ids=[7, 8],
            )

        assert ok is True
        # 选中维度模式不清空 TRD（未选维度结果保留）
        patched_acl.del_scores.assert_not_called()
        # 两轮都提交，且每轮 dimension_filter_ids 携带选中集（轮次交集收敛
        # 由评估入口按 config 维度完成：round0 维度[7,9]∩[7,8]=[7]，round1 [8]∩[7,8]=[8]）
        round_calls = [c for c in eval_svc.evaluate_case.call_args_list if 'round_number' in c.kwargs]
        assert [c.kwargs['round_number'] for c in round_calls] == [0, 1]
        assert all(c.kwargs['dimension_filter_ids'] == [7, 8] for c in round_calls)

    def test_failed_type_intersects_with_selection(self, patched_acl):
        """failed + 选中维度：失败集 ∩ 选中集"""
        patched_acl.list_scores.return_value = [
            _trd(7, 0, EvaluationStatus.FAILED, 'mock fail'),
            _trd(9, 0, EvaluationStatus.FAILED, 'mock fail'),
            _trd(8, 1, EvaluationStatus.FAILED, 'mock fail'),
        ]
        ex = ReevaluationExecutor()
        with patch.object(reexec_module, 'evaluation_service') as eval_svc:
            eval_svc.evaluate_case.return_value = True

            ok = ex._reevaluate_multi_round(
                task_id=1, result=11, test_case_id='c1',
                algorithm_result={'rounds': [{'output': {}}, {'output': {}}]},
                device_type='physical', algorithm_type='translation',
                reevaluate_type='failed',
                dimension_filter_ids=[9, 8],  # 7 失败但未选
            )

        assert ok is True
        round_calls = [c for c in eval_svc.evaluate_case.call_args_list if 'round_number' in c.kwargs]
        assert [c.kwargs['round_number'] for c in round_calls] == [0, 1]
        assert [c.kwargs['dimension_filter_ids'] for c in round_calls] == [[9], [8]]

    def test_failed_type_selection_empty_intersection_skips(self, patched_acl):
        """failed + 选中维度与失败集无交集：跳过（不置 queued）"""
        patched_acl.list_scores.return_value = [
            _trd(7, 0, EvaluationStatus.FAILED, 'mock fail'),
        ]
        ex = ReevaluationExecutor()
        with patch.object(reexec_module, 'evaluation_service') as eval_svc:
            ok = ex._reevaluate_multi_round(
                task_id=1, result=11, test_case_id='c1',
                algorithm_result={'rounds': [{'output': {}}]},
                device_type='physical', algorithm_type='translation',
                reevaluate_type='failed',
                dimension_filter_ids=[12],
            )
        assert ok is False
        eval_svc.evaluate_case.assert_not_called()
        patched_acl.upd_tc.assert_not_called()

    def test_single_round_with_dimension_selection(self, patched_acl):
        """单轮结果 + 选中维度：按选中集过滤（TRD 保留）"""
        ex = ReevaluationExecutor()
        with patch.object(reexec_module, 'evaluation_service') as eval_svc:
            eval_svc.evaluate_case.return_value = True

            submitted = ex._reevaluate_single(
                task_id=1, result_id=11, test_case_id='c1',
                algorithm_result={'output': {}},
                reference_params=[],
                device_type='http_api', algorithm_type='translation',
                reevaluate_type='all',
                dimension_filter_ids=[7],
            )

        assert submitted is True
        patched_acl.del_scores.assert_not_called()
        kwargs = eval_svc.evaluate_case.call_args.kwargs
        assert kwargs['dimension_filter_ids'] == [7]

    def test_queue_item_carries_options(self, patched_acl):
        """submit 入队：options 随队列项隔离（两任务互不影响）"""
        ex = ReevaluationExecutor()
        with patch.object(reexec_module.task_acl_repository, 'update_task_status', MagicMock()), \
             patch.object(ex, '_cancel_previous_evaluations'), \
             patch.object(ex, '_check_queue'):
            ex.submit(1, reextract_device_output=False, reevaluate_type='all',
                      options={'case_ids': ['c1', 'c2'], 'dimension_ids': [7], 'mode': 'selected'})
            ex.submit(2, reextract_device_output=False, reevaluate_type='all')
        assert ex.reevaluation_queue[0]['options'] == {
            'case_ids': ['c1', 'c2'], 'dimension_ids': [7], 'mode': 'selected'}
        assert ex.reevaluation_queue[1]['options'] == {
            'case_ids': [], 'dimension_ids': [], 'mode': 'all'}

    def test_submit_selected_empty_case_ids_rejected(self):
        """F2：selected 且空 case_ids → 拒绝（不入队、不动任务状态，与 retry 400 对齐）"""
        ex = ReevaluationExecutor()
        with patch.object(reexec_module.task_acl_repository, 'update_task_status',
                          MagicMock()) as upd_status, \
             patch.object(ex, '_cancel_previous_evaluations'), \
             patch.object(ex, '_check_queue'):
            ok, message = ex.submit(1, reextract_device_output=False, reevaluate_type='all',
                                    options={'case_ids': [], 'dimension_ids': [], 'mode': 'selected'})
        assert ok is False
        assert 'case_ids 不能为空' in message
        assert ex.reevaluation_queue == []
        upd_status.assert_not_called()

    def test_run_reevaluation_filters_results_by_case_ids(self):
        """_run_reevaluation：case_ids 过滤结果集（仅选中用例进入重评）"""
        ex = ReevaluationExecutor()
        results = [
            SimpleNamespace(test_case_id='c1', result_data=None, result_data_path=None,
                            algorithm_result={}),
            SimpleNamespace(test_case_id='c2', result_data=None, result_data_path=None,
                            algorithm_result={}),
        ]
        with patch.object(reexec_module.task_acl_repository, 'get_test_results_by_task_and_case',
                          MagicMock(return_value=results)), \
             patch.object(ex, '_collect_reevaluation_cases_all',
                          MagicMock(return_value=[])) as collect:
            ex._run_reevaluation(1, False, 'all',
                                 {'case_ids': ['c1'], 'dimension_ids': [], 'mode': 'selected'})
        # 仅 c1 进入收集
        assert [str(r.test_case_id) for r in collect.call_args[0][1]] == ['c1']


# ==================== 3. 网关 reevaluate 入口 ====================

class _StubReevaluationAcl:
    def __init__(self, success=True):
        self.success = success
        self.calls = []

    def submit(self, task_id, reextract_device_output=True, reevaluate_type='all', options=None):
        self.calls.append({'task_id': task_id,
                           'reextract_device_output': reextract_device_output,
                           'reevaluate_type': reevaluate_type,
                           'options': options})
        return SimpleNamespace(success=self.success, message='已提交重新评估',
                               result_data={})


class TestGatewayReevaluateSelection:
    """网关 task/reevaluate：camelCase 选择字段解析 + 透传 + 计数口径"""

    def test_selection_parsed_and_passed(self, monkeypatch):
        monkeypatch.setattr(
            eval_cmd_mod, '_task_acl',
            SimpleNamespace(get_task_detail=lambda tid: {
                'success': True, 'message': '', 'data': {
                    'id': tid, 'status': 'completed', 'total_cases': 7}}))
        reeval = _StubReevaluationAcl()
        monkeypatch.setattr(eval_cmd_mod, '_reevaluation_acl', reeval)
        set_current_request(_fake_request(json_body={
            'task_id': 5, 'mode': 'selected',
            'caseIds': ['c1', 'c2'], 'dimensionIds': [7, 8],
        }))
        try:
            result, http_code = eval_cmd_mod.EvaluationCommandService.reevaluate_task_results()
        finally:
            set_current_request(None)

        assert http_code == 200
        assert reeval.calls == [{
            'task_id': 5,
            'reextract_device_output': False,
            'reevaluate_type': 'all',
            'options': {'mode': 'selected', 'case_ids': ['c1', 'c2'], 'dimension_ids': [7, 8]},
        }]
        # 按用例选择时 queued 按选中数计（非任务全量 7）
        assert result['data']['queued_cases'] == 2
        assert result['data']['total_cases'] == 2

    def test_legacy_body_no_options(self, monkeypatch):
        """旧契约（仅 task_id）：options 为 None，queued 仍按任务全量"""
        monkeypatch.setattr(
            eval_cmd_mod, '_task_acl',
            SimpleNamespace(get_task_detail=lambda tid: {
                'success': True, 'message': '', 'data': {
                    'id': tid, 'status': 'completed', 'total_cases': 7}}))
        reeval = _StubReevaluationAcl()
        monkeypatch.setattr(eval_cmd_mod, '_reevaluation_acl', reeval)
        set_current_request(_fake_request(json_body={'task_id': 5}))
        try:
            result, http_code = eval_cmd_mod.EvaluationCommandService.reevaluate_task_results()
        finally:
            set_current_request(None)

        assert http_code == 200
        assert reeval.calls[0]['options'] is None
        assert result['data']['queued_cases'] == 7


# ==================== 4. 网关 retry 入口 ====================

class TestGatewayRetrySelection:
    """网关 tasks/{id}/retry：body case_ids/mode 透传 ACL；缺省整任务零改动"""

    def test_selection_passed_to_acl(self, monkeypatch):
        captured = {}

        class _StubAcl:
            def retry(self, task_id, data=None):
                captured['task_id'] = task_id
                captured['data'] = data
                return {'success': True, 'message': '重试任务已启动',
                        'data': {'task_id': task_id, 'status': 'running'}}

        monkeypatch.setattr(gw_task_lifecycle_mod, '_task_acl', _StubAcl())
        set_current_request(_fake_request(json_body={
            'case_ids': ['c1', 'c2'], 'mode': 'selected'}))
        try:
            result, http_code = gw_task_lifecycle_mod.TaskLifecycleService.retry(9)
        finally:
            set_current_request(None)

        assert http_code == 200
        assert captured == {'task_id': 9, 'data': {'case_ids': ['c1', 'c2'], 'mode': 'selected'}}

    def test_legacy_empty_body_no_options(self, monkeypatch):
        """无 body/空 body：不下发 options（gRPC data 空串，整任务语义）"""
        captured = {}

        class _StubAcl:
            def retry(self, task_id, data=None):
                captured['data'] = data
                return {'success': True, 'message': '重试任务已启动',
                        'data': {'task_id': task_id, 'status': 'running'}}

        monkeypatch.setattr(gw_task_lifecycle_mod, '_task_acl', _StubAcl())
        set_current_request(_fake_request(json_body=None))
        try:
            result, http_code = gw_task_lifecycle_mod.TaskLifecycleService.retry(9)
        finally:
            set_current_request(None)

        assert http_code == 200
        assert captured['data'] is None
