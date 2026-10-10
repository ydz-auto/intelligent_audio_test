# -*- coding: utf-8 -*-
"""INT-64 补充守卫：E2E 执行链收尾门控 + API 重评分支逐轮（验收标准 1 的双链锁定）。

E2E 执行链（finalization_mixin._finalize_rounds）整体评估提交条件拆分（本卡修复②的执行链侧）：
- _has_overall_dims（顶层 config.dimensions 非空）→ 才提交 round_number=None 整体评估
  （整体评估只取顶层维度，仅有轮次维度时提交整体评估会被评估入口跳过）
- _has_round_dims（任一轮 evaluation.dimensions 非 False 且非空）→ 聚合各轮分数
- 任务停止 / 执行失败 → 不提交整体评估；停止时聚合也跳过，结果落库收尾不变

API 重评分支（_reevaluate_api_multi_round）为既有逐轮行为（本卡维持不变），
此处锁定防退化：按轮提交 evaluate_case(round_number=...)（0 基），无 round_evaluation 的轮跳过。
"""
import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

# BaseConfig 在 import 时校验环境变量（本用例纯单测不触库，与仓库既有测试同款兜底）
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import e2e_test_service.application.services.e2e_executor.finalization_mixin as fin_mod
from e2e_test_service.application.services.e2e_executor.finalization_mixin import FinalizationMixin
from shared.infrastructure.base_executor import TaskStopSignal

import evaluation_service.application.handlers.reevaluation_executor as reeval_mod
from evaluation_service.application.handlers.reevaluation_executor import ReevaluationExecutor
import evaluation_service.infrastructure.acl.algorithm_acl_repository as algo_acl_mod

# 导入 evaluation_service 会在 collection 期实例化 host 单例并残留无 bind 的主线程
# scoped session（同 test_int64_reevaluation_e2e_rounds.py 的处理），导入后立即清理。
from shared.models.database import remove_db_session as _remove_db_session
_remove_db_session()


# ---------------- E2E 执行链收尾门控 ----------------

def _config(rounds_dims=None, top_dims=None, round_enabled=True):
    rounds = []
    for i, dims in enumerate(rounds_dims or []):
        r = {'round_number': i + 1, 'audios': []}
        if dims is not None:
            r['evaluation'] = {'enabled': round_enabled, 'dimensions': [{'id': d} for d in dims]}
        rounds.append(r)
    cfg = {'rounds': rounds}
    if top_dims is not None:
        cfg['dimensions'] = [{'id': d} for d in top_dims]
    return cfg


class _Host(FinalizationMixin):
    """最小宿主：聚合器与评估提交全部 mock，仅跑真实门控逻辑。"""

    def __init__(self, stopped=False):
        self._aggregator = MagicMock()
        self._aggregator.build_algorithm_result.return_value = {'rounds': [{'output': {}}]}
        self._aggregator.process_results.return_value = True
        self.eval_calls = []
        self.logs = []
        self._stopped_flag = stopped

    def _log(self, **kwargs):
        self.logs.append(kwargs)

    def _handle_control(self, task_id):
        if self._stopped_flag:
            raise TaskStopSignal('stopped')

    def _evaluate_result(self, **kwargs):
        self.eval_calls.append(kwargs)


_RUN_ARGS = dict(
    task_id='t1', tc_rel_id='tc1', data={}, case_name='case-x',
    algorithm_type='translation', test_case_id='c1', result_id=99,
    all_round_results=[{'response_time': 100}],
    case_reference_params=None, last_adjusted_ref_params=None,
    device_info_list=None,
)


def _run(config, execution_success=True, stopped=False):
    host = _Host(stopped=stopped)
    with patch.object(fin_mod, 'write_result_data_file', MagicMock(return_value=None)):
        host._finalize_rounds(case_config=config, execution_success=execution_success, **_RUN_ARGS)
    return host


class TestE2EFinalizationGate:

    def test_only_round_dims_aggregates_but_no_overall(self):
        """仅有轮次维度：不提交整体评估（round_number=None），但聚合各轮分数照常触发。"""
        host = _run(_config(rounds_dims=[[1], [2]], top_dims=[]))
        assert host.eval_calls == []
        host._aggregator.update_algorithm_result_evaluation.assert_called_once_with('t1', 99)

    def test_only_top_dims_overall_submitted_no_aggregation(self):
        """仅顶层维度：提交整体评估（round_number=None），无轮次聚合。"""
        host = _run(_config(rounds_dims=[[], []], top_dims=[7]))
        assert len(host.eval_calls) == 1
        assert host.eval_calls[0]['round_number'] is None
        assert host.eval_calls[0]['test_type'] == 'e2e'
        host._aggregator.update_algorithm_result_evaluation.assert_not_called()

    def test_both_dims_both_paths(self):
        host = _run(_config(rounds_dims=[[1]], top_dims=[7]))
        assert len(host.eval_calls) == 1
        assert host.eval_calls[0]['round_number'] is None
        host._aggregator.update_algorithm_result_evaluation.assert_called_once_with('t1', 99)

    def test_no_dims_neither_path(self):
        host = _run(_config(rounds_dims=[[], []], top_dims=[]))
        assert host.eval_calls == []
        host._aggregator.update_algorithm_result_evaluation.assert_not_called()

    def test_disabled_rounds_no_aggregation(self):
        """所有轮 evaluation.enabled=False：不触发聚合。"""
        host = _run(_config(rounds_dims=[[1], [2]], top_dims=[], round_enabled=False))
        host._aggregator.update_algorithm_result_evaluation.assert_not_called()
        assert host.eval_calls == []

    def test_execution_failure_no_overall_submission(self):
        """执行失败：不提交整体评估；轮次聚合不受 execution_success 门控（既有行为）。"""
        host = _run(_config(rounds_dims=[[1]], top_dims=[7]), execution_success=False)
        assert host.eval_calls == []
        host._aggregator.update_algorithm_result_evaluation.assert_called_once_with('t1', 99)

    def test_stopped_task_skips_overall_and_aggregation(self):
        """任务已停：整体评估与聚合都跳过，结果落库收尾照常。"""
        host = _run(_config(rounds_dims=[[1]], top_dims=[7]), stopped=True)
        assert host.eval_calls == []
        host._aggregator.update_algorithm_result_evaluation.assert_not_called()
        host._aggregator.update_test_result.assert_called_once()


# ---------------- API 重评分支逐轮（既有行为锁定） ----------------

def _api_rounds(n=3, with_eval_from=0):
    rounds = []
    for i in range(n):
        rd = {'round_number': i + 1, 'reference_params': [{'code': f'r{i}'}]}
        if i >= with_eval_from:
            rd['round_evaluation'] = {'dimensions': [{'id': i}]}
        rounds.append(rd)
    return rounds


class _ApiHarness:
    """patch API 分支协作方，按序捕获 evaluate_case / extract_case_all_params。"""

    def __init__(self):
        self.executor = ReevaluationExecutor()
        self.eval_calls = []
        self.extract_calls = []

        self._eval_svc = MagicMock()

        def _capture_eval(**kwargs):
            self.eval_calls.append(kwargs)
            return True
        self._eval_svc.evaluate_case.side_effect = _capture_eval

        self._algo_acl = MagicMock()

        def _capture_extract(full_case_params):
            self.extract_calls.append(full_case_params)
            return {'evaluation': {}}
        self._algo_acl.extract_case_all_params.side_effect = _capture_extract

        self._patches = [
            (reeval_mod, 'evaluation_service', self._eval_svc),
            (reeval_mod, 'task_acl_repository', MagicMock()),
            (reeval_mod, 'evaluation_dimension_repository', MagicMock()),
            (algo_acl_mod, 'extract_case_all_params', self._algo_acl.extract_case_all_params),
        ]

    def __enter__(self):
        for target, name, value in self._patches:
            setattr(target, name, value)
        return self

    def __exit__(self, *exc):
        return False

    def run(self, rounds, config=None):
        self.executor._compute_and_store_api_aggregated = MagicMock()
        self.executor._reevaluate_api_multi_round(
            task_id='t1', result=99, test_case_id='c1',
            algorithm_result={'rounds': [{'round': i, 'output': {}} for i in range(len(rounds))]},
            test_type='api', algorithm_type='translation',
            reference_params_col=None, rounds=rounds,
            test_case=SimpleNamespace(config=config or {}, algorithm_params=None,
                                      algorithm_type='translation'),
        )
        return self.eval_calls


class TestApiReevalPerRoundGuard:

    def test_per_round_submitted_with_0_based_round_number(self):
        """逐轮提交，round_number 为 0 基（round_data.round_number 1 基减 1）。"""
        with _ApiHarness() as h:
            calls = h.run(_api_rounds(3))
        assert [c.get('round_number') for c in calls] == [0, 1, 2]
        for c in calls:
            assert c['test_type'] == 'api'
            assert c['result_id'] == 99

    def test_round_without_round_evaluation_skipped(self):
        """无 round_evaluation 的轮不提交评估。"""
        with _ApiHarness() as h:
            calls = h.run(_api_rounds(3, with_eval_from=1))
        assert [c.get('round_number') for c in calls] == [1, 2]

    def test_algo_params_from_config_round(self):
        """无 algorithm_params_col 时按 config.rounds[n].algorithm_params 取轮参数。"""
        config = {'rounds': [
            {'round_number': 1, 'algorithm_params': {'round': 0, 'from': 'config'}},
            {'round_number': 2, 'algorithm_params': {'round': 1, 'from': 'config'}},
        ]}
        with _ApiHarness() as h:
            calls = h.run(_api_rounds(2), config=config)
        assert len(calls) == 2
        assert h.extract_calls[0]['algorithm_params'] == {'round': 0, 'from': 'config'}
        assert h.extract_calls[1]['algorithm_params'] == {'round': 1, 'from': 'config'}
