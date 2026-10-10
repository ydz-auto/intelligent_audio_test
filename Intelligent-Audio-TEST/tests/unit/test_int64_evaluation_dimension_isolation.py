# -*- coding: utf-8 -*-
"""INT-64 守卫：评估入口按轮过滤维度配置（评估维度隔离闭环）。

原缺陷：evaluate_case 在 round_number 指定轮次时仅切换 rounds 列表
（case_evaluation.py），但 _load_test_case_and_refs → _merge_dimensions_config
仍合并所有轮 + 顶层维度——按轮维度隔离的查询侧语义没有传导到评估入口，
单轮评估把其它轮/顶层配置的维度也评了。

裁定（doc/功能设计文档/04_评估/评估维度隔离设计文档.md §2.2，V9.7.10 同款）：
- round_number=N（单轮评估）→ 只取 rounds[N].evaluation.dimensions
- round_number=None（整体评估）→ 只取顶层 config.dimensions（不合并轮次维度）

覆盖（纯单测，不触真实 DB/gRPC）：
- _merge_dimensions_config 过滤矩阵（指定轮/整体/越界轮/去重/坏结构）。
- _load_test_case_and_refs 将 round_number 传导到维度过滤。
- evaluate_case 多轮 + 指定轮次时按轮取维度、整体评估只取顶层维度。
"""
import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

# BaseConfig 在 import 时校验环境变量（本用例纯单测不触库，与仓库既有测试同款兜底）
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import evaluation_service.infrastructure.acl.algorithm_acl_repository as _algo_acl_mod
from evaluation_service.domain.services.evaluation_service.case_evaluation import CaseEvaluationMixin
from evaluation_service.domain.services.evaluation_service.case_loader import CaseLoaderMixin


def _dim(dim_id, extra=None):
    d = {'id': dim_id}
    if extra:
        d.update(extra)
    return d


def _config(rounds_dims, top_dims):
    """构造 test_case.config：rounds_dims 为各轮 evaluation.dimensions（None=该轮无 evaluation 键）"""
    rounds = []
    for i, dims in enumerate(rounds_dims):
        r = {'round_number': i + 1, 'audios': []}
        if dims is not None:
            r['evaluation'] = {'enabled': True, 'dimensions': [_dim(x) for x in dims]}
        rounds.append(r)
    cfg = {'rounds': rounds, 'dimensions': [_dim(x) for x in (top_dims or [])]}
    return cfg


class _Loader(CaseLoaderMixin):
    """最小组合：仅维度配置加载相关方法。"""

    def __init__(self):
        self._task_acl_repo = None
        self.logs = []

    def _log(self, **kwargs):
        self.logs.append(kwargs)


class TestMergeDimensionsConfigByRound:
    """_merge_dimensions_config 按轮过滤矩阵。"""

    def test_round_number_filters_to_that_round_only(self):
        """单轮评估：只取该轮 dimensions，其它轮与顶层维度不得混入。"""
        cfg = _config([[1], [2, 3]], [9])
        loader = _Loader()
        dims = loader._merge_dimensions_config(cfg, round_number=1)
        assert [d['id'] for d in dims] == [2, 3]

    def test_round_zero_only_first_round(self):
        cfg = _config([[1], [2]], [9])
        loader = _Loader()
        dims = loader._merge_dimensions_config(cfg, round_number=0)
        assert [d['id'] for d in dims] == [1]

    def test_none_round_takes_top_level_only(self):
        """整体评估：只取顶层 config.dimensions，不合并任何轮次维度。"""
        cfg = _config([[1], [2, 3]], [7, 8])
        loader = _Loader()
        dims = loader._merge_dimensions_config(cfg, round_number=None)
        assert [d['id'] for d in dims] == [7, 8]

    def test_none_round_no_top_dims_means_empty(self):
        """整体评估：顶层无维度 → 空（由调用方跳过评估），不回退轮次维度。"""
        cfg = _config([[1], [2]], [])
        loader = _Loader()
        assert loader._merge_dimensions_config(cfg, round_number=None) == []

    def test_round_out_of_range_returns_empty(self):
        cfg = _config([[1]], [9])
        loader = _Loader()
        assert loader._merge_dimensions_config(cfg, round_number=5) == []

    def test_round_without_evaluation_block_returns_empty(self):
        """该轮无 evaluation 键 → 该轮评估无维度。"""
        cfg = _config([None, [2]], [])
        loader = _Loader()
        assert loader._merge_dimensions_config(cfg, round_number=0) == []

    def test_round_dims_dedup_within_scope(self):
        cfg = _config([[1, 1, 2]], [])
        loader = _Loader()
        dims = loader._merge_dimensions_config(cfg, round_number=0)
        assert [d['id'] for d in dims] == [1, 2]

    def test_legacy_case_without_rounds_uses_top_dims(self):
        """无 rounds 的传统用例：整体评估取顶层维度，指定轮评估为空。"""
        cfg = {'dimensions': [_dim(5)]}
        loader = _Loader()
        assert [d['id'] for d in loader._merge_dimensions_config(cfg, round_number=None)] == [5]
        assert loader._merge_dimensions_config(cfg, round_number=0) == []

    def test_malformed_rounds_entries_skipped(self):
        cfg = {'rounds': ['bad', 42, {'evaluation': {'dimensions': [_dim(3)]}}], 'dimensions': []}
        loader = _Loader()
        assert [d['id'] for d in loader._merge_dimensions_config(cfg, round_number=2)] == [3]
        assert loader._merge_dimensions_config(cfg, round_number=0) == []


class _StubTestCaseDTO:
    def __init__(self, config, algorithm_type='translation'):
        self.config = config
        self.algorithm_type = algorithm_type
        self.name = 'case-x'


class TestLoadTestCaseAndRefsRoundPropagation:
    """_load_test_case_and_refs 将 round_number 传导到维度过滤。"""

    def _make_loader(self, config):
        loader = _Loader()
        loader._task_acl_repo = MagicMock()
        loader._task_acl_repo.get_test_case_detail.return_value = _StubTestCaseDTO(config)
        return loader

    def _field_mapper(self):
        fm = MagicMock()
        fm.get_evaluation_input_fields.return_value = {}
        return fm

    def test_round_number_propagates(self):
        loader = self._make_loader(_config([[1], [2]], [9]))
        data = loader._load_test_case_and_refs('c1', self._field_mapper(), {}, 't1', round_number=1)
        assert [d['id'] for d in data['dimensions_config']] == [2]

    def test_none_round_propagates_top_only(self):
        loader = self._make_loader(_config([[1]], [7]))
        data = loader._load_test_case_and_refs('c1', self._field_mapper(), {}, 't1', round_number=None)
        assert [d['id'] for d in data['dimensions_config']] == [7]

    def test_default_backward_compatible_overall_semantics(self):
        """不传 round_number（旧调用方）= 整体评估语义：只取顶层。"""
        loader = self._make_loader(_config([[1]], [7]))
        data = loader._load_test_case_and_refs('c1', self._field_mapper(), {}, 't1')
        assert [d['id'] for d in data['dimensions_config']] == [7]


class _EvalHost(CaseEvaluationMixin, CaseLoaderMixin):
    """evaluate_case 级最小宿主：捕获分发入参。"""

    def _build_rounds_list(self, algorithm_result, *args, **kwargs):
        # rounds 构建非本卡范围，stub 为与输入轮数等长的非空列表。
        # （INT-115 口径：_build_rounds_list 返回空列表 = 无 evaluation param
        #   mappings，evaluate_case 会走 skipped 终态提前收尾，不再进入维度分发）
        return [dict(item.get('output', {})) for item in algorithm_result.get('rounds', [])]

    def __init__(self, config):
        self._task_acl_repo = MagicMock()
        self._task_acl_repo.get_test_case_detail.return_value = _StubTestCaseDTO(config)
        self.result_processor = MagicMock()
        self.logs = []
        self.dispatched = None
        self.marked_completed = []
        self.posted_updates = []
        self.marked_queued = []

    def _log(self, **kwargs):
        self.logs.append(kwargs)

    def _load_dimension_data(self, unique_dimension_ids, task_id, test_case_id, test_case):
        return [{'id': d, 'name': f'dim{d}'} for d in unique_dimension_ids]

    def _create_dimension_results(self, dimension_data_list, result_id, task_id, test_case_id, algorithm_type, kwargs):
        return {item['id']: f'dr-{item["id"]}' for item in dimension_data_list}

    def _dispatch_evaluation_tasks(self, *args, **kwargs):
        self.dispatched = (args, kwargs)

    def _mark_evaluation_queued(self, task_id, test_case_id):
        self.marked_queued.append((task_id, test_case_id))

    def _post_evaluate_updates(self, task_id, test_case_id):
        self.posted_updates.append((task_id, test_case_id))

    def mark_test_result_completed(self, result_id):
        self.marked_completed.append(result_id)


def _multi_round_algo_result(n=2):
    return {'test_type': 'e2e', 'rounds': [
        {'round': i, 'output': {'asr_text': f'r{i}'}}
        for i in range(n)
    ]}


class TestEvaluateCaseRoundIsolation:
    """evaluate_case：指定轮次评估按轮取维度；整体评估只取顶层维度。"""

    def _evaluate(self, host, **kwargs):
        # get_field_mappings 走真实 gRPC，单测环境 stub 掉
        with patch.object(_algo_acl_mod, 'get_field_mappings', return_value=MagicMock()):
            return host.evaluate_case(**kwargs)

    def test_per_round_eval_uses_only_that_round_dims(self):
        config = _config([[1], [2, 3]], [9])
        host = _EvalHost(config)
        ok = self._evaluate(
            host,
            task_id='t1', result_id=11, test_case_id='c1',
            algorithm_result=_multi_round_algo_result(),
            algorithm_type='translation', test_type='e2e', round_number=1,
        )
        assert ok is True
        args, _kw = host.dispatched
        dimension_data_list = args[0]
        assert [d['id'] for d in dimension_data_list] == [2, 3]

    def test_overall_eval_uses_only_top_dims(self):
        config = _config([[1], [2]], [7])
        host = _EvalHost(config)
        ok = self._evaluate(
            host,
            task_id='t1', result_id=11, test_case_id='c1',
            algorithm_result=_multi_round_algo_result(),
            algorithm_type='translation', test_type='e2e', round_number=None,
        )
        assert ok is True
        args, _kw = host.dispatched
        dimension_data_list = args[0]
        assert [d['id'] for d in dimension_data_list] == [7]

    def test_per_round_without_dims_skips_evaluation(self):
        """该轮无维度 → 跳过评估（不提交空评估），并走完成收尾。"""
        config = _config([[], [2]], [9])
        host = _EvalHost(config)
        ok = self._evaluate(
            host,
            task_id='t1', result_id=11, test_case_id='c1',
            algorithm_result=_multi_round_algo_result(),
            algorithm_type='translation', test_type='e2e', round_number=0,
        )
        assert ok is False
        assert host.dispatched is None
        host.result_processor.mark_test_result_completed.assert_called_once_with(11)
