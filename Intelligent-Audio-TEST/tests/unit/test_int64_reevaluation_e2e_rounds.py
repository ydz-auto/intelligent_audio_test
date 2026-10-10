# -*- coding: utf-8 -*-
"""INT-64 守卫：重评 E2E 分支逐轮 + 整体评估（对齐正常执行链与 V9.7.10 设计）。

原缺陷：reevaluation_executor._reevaluate_e2e_multi_round 整体一次性重评
（round_number=None 单次调用），API 分支逐轮——与正常执行链
（e2e_executor：逐轮 round_number=round_idx + 整体 round_number=None）和
设计文档（多轮评估维度隔离与报告聚合设计文档 §3.3 / V9.7.10 reevaluation_executor）不一致；
配合评估入口按轮过滤维度配置（INT-64 缺陷一）后，单次整体调用会漏掉全部
轮次维度。

裁定（设计文档 §3.3 + V9.7.10 reevaluation_executor E2E 分支）：
- 逐轮评估：遍历每轮，检查 config.rounds[n].evaluation（enabled=False 或
  dimensions 为空 → 跳过），非空时 evaluate_case(round_number=round_idx)，
  算法参数按轮取（config.rounds[n].algorithm_params / algorithm_params_col 第 n 轮）。
- 整体评估：仅当顶层 config.dimensions 非空时提交 evaluate_case(round_number=None)，
  算法参数取第 1 轮。

覆盖（纯单测，不触真实 DB/gRPC，全量 mock 协作方）。
"""
import os
from types import SimpleNamespace
from unittest.mock import MagicMock

# BaseConfig 在 import 时校验环境变量（本用例纯单测不触库，与仓库既有测试同款兜底）
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import evaluation_service.application.handlers.reevaluation_executor as reeval_mod
from evaluation_service.application.handlers.reevaluation_executor import ReevaluationExecutor
import evaluation_service.infrastructure.acl.algorithm_acl_repository as algo_acl_mod

# 导入 reevaluation_executor 会在 collection 期实例化 evaluation_service host 单例，
# 其 _load_all_endpoint_configs 在任何 db 夹具装配 engine 之前创建主线程 scoped session
# （无 bind，查询异常被吞），该残留 session 滞留在 scoped_session 注册表中，
# 会使本进程后续使用 get_db_session() 的测试（如 benchmark 真实链）报
# UnboundExecutionError。导入后立即清理主线程残留 session，恢复注册表干净状态。
from shared.models.database import remove_db_session as _remove_db_session
_remove_db_session()


def _case_config(rounds_dims, top_dims):
    """config：rounds_dims 各轮 evaluation.dimensions（None=无 evaluation 键），top_dims 顶层。"""
    rounds = []
    for i, dims in enumerate(rounds_dims):
        r = {'round_number': i + 1,
             'algorithm_params': {'round': i, 'from': 'config'}}
        if dims is not None:
            r['evaluation'] = {'enabled': True, 'dimensions': [{'id': d} for d in dims]}
        rounds.append(r)
    return {
        'rounds': rounds,
        'dimensions': [{'id': d} for d in (top_dims or [])],
    }


def _algo_rounds(n=3):
    return [{'round': i, 'output': {}, 'reference_params': [{'code': f'r{i}'}]} for i in range(n)]


def _test_case(config):
    return SimpleNamespace(config=config, algorithm_params=None, algorithm_type='translation')


class _ReevalHarness:
    """patch 全部协作方，按序捕获 extract_case_all_params / evaluate_case 调用。"""

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
            return {'evaluation': {'ref': 'x'}}
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

    def run(self, config, n_rounds=3, test_type='e2e'):
        test_case = _test_case(config)
        self.executor._reevaluate_e2e_multi_round(
            task_id='t1', result=99, test_case_id='c1',
            algorithm_result={'rounds': _algo_rounds(n_rounds)},
            test_type=test_type, algorithm_type='translation',
            reference_params_col=None, rounds=_algo_rounds(n_rounds),
            test_case=test_case,
        )
        return self.eval_calls

    def extract_by_index(self, i):
        """第 i 次提交对应的 full_case_params（extract 与 evaluate 1:1 同序）。"""
        return self.extract_calls[i]


def _round_numbers(calls):
    return [c.get('round_number') for c in calls]


class TestReevaluateE2EPerRound:
    """E2E 重评分支：逐轮 + 整体。"""

    def test_per_round_then_overall(self):
        """每轮都有维度 + 顶层有维度：逐轮 3 次指定轮 + 1 次整体。"""
        config = _case_config([[1], [2], [3]], [9])
        with _ReevalHarness() as h:
            calls = h.run(config)
        assert _round_numbers(calls) == [0, 1, 2, None]

    def test_round_with_empty_dims_skipped(self):
        """dimensions 为空的轮不提交评估。"""
        config = _case_config([[1], [], [3]], [9])
        with _ReevalHarness() as h:
            calls = h.run(config)
        assert _round_numbers(calls) == [0, 2, None]

    def test_round_without_evaluation_block_skipped(self):
        config = _case_config([None, [2]], [9])
        with _ReevalHarness() as h:
            calls = h.run(config, n_rounds=2)
        assert _round_numbers(calls) == [1, None]

    def test_disabled_round_skipped(self):
        """enabled=False 的轮不提交评估。"""
        config = _case_config([[1], [2]], [9])
        config['rounds'][0]['evaluation']['enabled'] = False
        with _ReevalHarness() as h:
            calls = h.run(config, n_rounds=2)
        assert _round_numbers(calls) == [1, None]

    def test_no_top_dims_no_overall_call(self):
        """顶层无维度：不提交整体评估（避免空评估提交）。"""
        config = _case_config([[1], [2]], [])
        with _ReevalHarness() as h:
            calls = h.run(config, n_rounds=2)
        assert _round_numbers(calls) == [0, 1]
        # 有提交 → 不走无维度收尾
        h._eval_svc.result_processor.mark_test_result_completed.assert_not_called()

    def test_no_round_dims_and_no_top_dims_nothing_submitted(self):
        """全无维度：不提交任何评估，且收尾（标记结果完成+推进用例评估状态，不悬挂 queued）。"""
        config = _case_config([[], []], [])
        with _ReevalHarness() as h:
            calls = h.run(config, n_rounds=2)
        assert calls == []
        h._eval_svc.result_processor.mark_test_result_completed.assert_called_once_with(99)
        h._eval_svc._post_evaluate_updates.assert_called_once_with('t1', 'c1')

    def test_per_round_algo_params_from_config_round(self):
        """每轮算法参数取 config.rounds[n].algorithm_params。"""
        config = _case_config([[1], [2]], [])
        with _ReevalHarness() as h:
            calls = h.run(config, n_rounds=2)
        assert h.extract_by_index(0)['algorithm_params'] == {'round': 0, 'from': 'config'}
        assert h.extract_by_index(1)['algorithm_params'] == {'round': 1, 'from': 'config'}

    def test_overall_uses_first_round_algo_params(self):
        """整体评估算法参数取第 1 轮（对齐既有实现与 V9.7.10）。"""
        config = _case_config([[1], [2]], [9])
        with _ReevalHarness() as h:
            calls = h.run(config, n_rounds=2)
        overall_idx = [i for i, c in enumerate(calls) if c.get('round_number') is None]
        assert len(overall_idx) == 1
        assert h.extract_by_index(overall_idx[0])['algorithm_params'] == {'round': 0, 'from': 'config'}

    def test_all_calls_pass_full_algo_result(self):
        """每轮调用都传完整 algorithm_result（rounds 全量），由评估入口按轮取数据。"""
        config = _case_config([[1], [2]], [9])
        with _ReevalHarness() as h:
            calls = h.run(config, n_rounds=2)
        for c in calls:
            assert len(c['algorithm_result']['rounds']) == 2
            assert c['test_type'] == 'e2e'
            assert c['result_id'] == 99
