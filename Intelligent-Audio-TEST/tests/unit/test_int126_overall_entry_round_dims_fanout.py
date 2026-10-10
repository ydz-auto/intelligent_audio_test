# -*- coding: utf-8 -*-
"""INT-126 守卫：多轮整体评估入口按 round_scope 分流出分（0 维度空转修复）。

原缺陷：上传口径把评估维度逐轮注入 rounds[].evaluation.dimensions（case 级
config.dimensions 为空，带音频参数的维度配 case 级会被校验拒绝），而 API 多轮链
只提交一次整体评估（round_number=None）；整体路径只取顶层维度 → dimensions_config=[]
→ "没有配置任何维度，跳过评估" → TestResult/TaskCase 置 completed，0 条
TestResultDimension、无任何出分，主链评估步空转完成。

裁定（INT-126 修复方向一，评估侧）：
- _merge_dimensions_config 按口径分流：
  round_number=N（单轮）→ 该轮 dimensions 剔除 round_scope=multi；
  round_number=None（整体）→ 顶层 config.dimensions + 轮次注入的 multi 维度（去重）；
  未标注 round_scope 的维度按逐轮口径处理（维持 INT-64 既有隔离语义）。
- 整体评估入口（round_number=None + 多轮结果）补提交逐轮维度：
  per_round 维度按轮出分（round_number=N 走既有单轮路径），multi 维度归整体评估；
  已有逐轮 TRD 记录的轮次幂等跳过（E2E 轮次循环/重评链已逐轮提交，不重复评估）。

覆盖（纯单测，不触真实 DB/gRPC）：
- _merge_dimensions_config 的 round_scope 过滤矩阵。
- evaluate_case 整体入口：逐轮补提交 + 整体出分 / 幂等跳过 / 仅逐轮维度 /
  全无维度走既有跳过收尾 / enabled=False 轮跳过 / 结果轮数少于配置轮数。
"""
import os
from unittest.mock import MagicMock, patch

# BaseConfig 在 import 时校验环境变量（本用例纯单测不触库，与仓库既有测试同款兜底）
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import evaluation_service.infrastructure.acl.algorithm_acl_repository as _algo_acl_mod
from evaluation_service.domain.services.evaluation_service.case_evaluation import CaseEvaluationMixin
from evaluation_service.domain.services.evaluation_service.case_loader import CaseLoaderMixin


def _dim(dim_id, scope=None):
    d = {'id': dim_id}
    if scope is not None:
        d['round_scope'] = scope
    return d


def _config(rounds_dims, top_dims):
    """构造 test_case.config：rounds_dims 为各轮 (dim_id, scope) 列表（None=该轮无 evaluation 键）"""
    rounds = []
    for i, dims in enumerate(rounds_dims):
        r = {'round_number': i + 1, 'audios': []}
        if dims is not None:
            r['evaluation'] = {'enabled': True, 'dimensions': [_dim(x, s) for x, s in dims]}
        rounds.append(r)
    cfg = {'rounds': rounds}
    if top_dims is not None:
        cfg['dimensions'] = [_dim(x, s) for x, s in top_dims]
    return cfg


class _Loader(CaseLoaderMixin):
    """最小组合：仅维度配置加载相关方法。"""

    def __init__(self):
        self._task_acl_repo = None
        self.logs = []

    def _log(self, **kwargs):
        self.logs.append(kwargs)


class TestMergeDimensionsConfigRoundScope:
    """_merge_dimensions_config 的 round_scope 过滤矩阵。"""

    def test_round_path_excludes_multi_scope_dims(self):
        """单轮评估：剔除该轮中 round_scope=multi 的整体口径维度。"""
        cfg = _config([[(1, 'per_round'), (2, 'multi')], []], [])
        loader = _Loader()
        dims = loader._merge_dimensions_config(cfg, round_number=0)
        assert [d['id'] for d in dims] == [1]

    def test_overall_path_merges_round_injected_multi_dims(self):
        """整体评估：顶层维度 + 轮次注入的 multi 维度，per_round 维度不混入。"""
        cfg = _config([[(72, 'per_round'), (134, 'multi')] for _ in range(3)], [])
        loader = _Loader()
        dims = loader._merge_dimensions_config(cfg, round_number=None)
        assert [d['id'] for d in dims] == [134]

    def test_overall_path_dedups_between_top_and_rounds(self):
        """整体评估：multi 维度同时存在于顶层与轮次时按维度 ID 去重。"""
        cfg = _config([[(72, 'per_round'), (134, 'multi')]], [(134, 'multi')])
        loader = _Loader()
        dims = loader._merge_dimensions_config(cfg, round_number=None)
        assert [d['id'] for d in dims] == [134]

    def test_per_round_scope_dims_not_merged_into_overall(self):
        """整体评估：仅有 per_round 维度（顶层为空）→ 空（逐轮口径由按轮评估出分）。"""
        cfg = _config([[(72, 'per_round')], [(72, 'per_round')]], [])
        loader = _Loader()
        assert loader._merge_dimensions_config(cfg, round_number=None) == []

    def test_legacy_single_scope_unchanged(self):
        """legacy single 口径：单轮取该轮、整体不合并（维持 INT-64 语义）。"""
        cfg = _config([[(1, 'single')], [(2, 'single')]], [(7, None)])
        loader = _Loader()
        assert [d['id'] for d in loader._merge_dimensions_config(cfg, round_number=0)] == [1]
        assert [d['id'] for d in loader._merge_dimensions_config(cfg, round_number=None)] == [7]

    def test_unmarked_scope_dims_treated_as_per_round(self):
        """未标注 round_scope 的维度按逐轮口径：单轮取到、整体不合并。"""
        cfg = _config([[(1, None)], [(2, None)]], [])
        loader = _Loader()
        assert [d['id'] for d in loader._merge_dimensions_config(cfg, round_number=0)] == [1]
        assert loader._merge_dimensions_config(cfg, round_number=None) == []


class _StubTestCaseDTO:
    def __init__(self, config, algorithm_type='translation'):
        self.config = config
        self.algorithm_type = algorithm_type
        self.name = 'case-x'


class _EvalHost(CaseEvaluationMixin, CaseLoaderMixin):
    """evaluate_case 级最小宿主：按序捕获每次分发的 (round_number, dims)。"""

    def _build_rounds_list(self, algorithm_result, *args, **kwargs):
        # rounds 构建非本卡范围，stub 为与输入轮数等长的非空列表
        return [dict(item.get('output', {})) for item in algorithm_result.get('rounds', [])]

    def __init__(self, config, existing_round_scores=()):
        self._task_acl_repo = MagicMock()
        self._task_acl_repo.get_test_case_detail.return_value = _StubTestCaseDTO(config)
        self._evaluation_dimension_repo = MagicMock()
        self._evaluation_dimension_repo.list_scores_by_result_id.return_value = [
            MagicMock(round_number=rn) for rn in existing_round_scores
        ]
        self.result_processor = MagicMock()
        self.logs = []
        self.dispatched = []  # [(round_number, [dim_id, ...]), ...]
        self.marked_completed = []
        self.posted_updates = []

    def _log(self, **kwargs):
        self.logs.append(kwargs)

    def _load_dimension_data(self, unique_dimension_ids, task_id, test_case_id, test_case):
        return [{'id': d, 'name': f'dim{d}'} for d in unique_dimension_ids]

    def _create_dimension_results(self, dimension_data_list, result_id, task_id, test_case_id, algorithm_type, kwargs):
        return {item['id']: f'dr-{item["id"]}' for item in dimension_data_list}

    def _dispatch_evaluation_tasks(self, dimension_data_list, dimension_result_map, result_id,
                                    task_id, test_case_id, algorithm_result, algorithm_type,
                                    test_type, round_number, *args, **kwargs):
        self.dispatched.append((round_number, [d['id'] for d in dimension_data_list]))

    def _mark_evaluation_queued(self, task_id, test_case_id):
        pass

    def _post_evaluate_updates(self, task_id, test_case_id):
        self.posted_updates.append((task_id, test_case_id))

    def mark_test_result_completed(self, result_id):
        self.marked_completed.append(result_id)


def _upload_shaped_algo_result(n=3):
    """API 多轮执行结果的算法结果形态（rounds 0-indexed）。"""
    return {'rounds': [
        {'round': i, 'output': {'asr_text': f'r{i}'}}
        for i in range(n)
    ]}


class TestOverallEntryRoundDimsFanout:
    """evaluate_case 整体入口（round_number=None）：逐轮补提交 + 整体出分。"""

    def _evaluate(self, host, **kwargs):
        # get_field_mappings 走真实 gRPC，单测环境 stub 掉
        with patch.object(_algo_acl_mod, 'get_field_mappings', return_value=MagicMock()):
            return host.evaluate_case(**kwargs)

    def test_upload_shaped_case_fans_out_rounds_and_overall(self):
        """上传口径用例（逐轮注入 72 per_round + 134 multi，顶层为空）：
        逐轮 3 次提交 round_number=0/1/2 出分维度 72，整体 1 次出分维度 134。"""
        config = _config([[(72, 'per_round'), (134, 'multi')] for _ in range(3)], [])
        host = _EvalHost(config)
        ok = self._evaluate(
            host,
            task_id='t1', result_id=11, test_case_id='c1',
            algorithm_result=_upload_shaped_algo_result(),
            algorithm_type='translation', test_type='api',
        )
        assert ok is True
        assert host.dispatched == [(0, [72]), (1, [72]), (2, [72]), (None, [134])]
        # 逐轮链在途时不得提前收尾
        host.result_processor.mark_test_result_completed.assert_not_called()

    def test_rounds_with_existing_trd_skipped_idempotent(self):
        """幂等：已存在逐轮 TRD 记录的轮次不重复提交（E2E 轮次循环/重评链已逐轮提交），
        仅整体维度照常出分。"""
        config = _config([[(72, 'per_round'), (134, 'multi')] for _ in range(3)], [])
        host = _EvalHost(config, existing_round_scores=(0, 1, 2))
        ok = self._evaluate(
            host,
            task_id='t1', result_id=11, test_case_id='c1',
            algorithm_result=_upload_shaped_algo_result(),
            algorithm_type='translation', test_type='api',
        )
        assert ok is True
        assert host.dispatched == [(None, [134])]

    def test_only_per_round_dims_no_overall_dispatch(self):
        """仅有逐轮维度（无任何 multi/顶层维度）：逐轮补提交后整体部分无事可做，
        不提交空整体评估，也不提前收尾（逐轮链负责 TRD 落库与用例收尾）。"""
        config = _config([[(72, 'per_round')] for _ in range(2)], [])
        host = _EvalHost(config)
        ok = self._evaluate(
            host,
            task_id='t1', result_id=11, test_case_id='c1',
            algorithm_result=_upload_shaped_algo_result(2),
            algorithm_type='translation', test_type='api',
        )
        assert ok is True
        assert host.dispatched == [(0, [72]), (1, [72])]
        host.result_processor.mark_test_result_completed.assert_not_called()
        assert host.posted_updates == []

    def test_no_dims_anywhere_falls_back_to_skip_finalization(self):
        """全无维度：不提交任何评估，走既有无维度跳过收尾（标记结果完成+推进用例评估状态）。"""
        config = _config([[] for _ in range(2)], [])
        host = _EvalHost(config)
        ok = self._evaluate(
            host,
            task_id='t1', result_id=11, test_case_id='c1',
            algorithm_result=_upload_shaped_algo_result(2),
            algorithm_type='translation', test_type='api',
        )
        assert ok is False
        assert host.dispatched == []
        host.result_processor.mark_test_result_completed.assert_called_once_with(11)
        assert host.posted_updates == [('t1', 'c1')]

    def test_disabled_round_not_fanned_out(self):
        """evaluation.enabled=False 的轮不补提交逐轮评估。"""
        config = _config([[(72, 'per_round')], [(72, 'per_round')]], [])
        config['rounds'][0]['evaluation']['enabled'] = False
        host = _EvalHost(config)
        ok = self._evaluate(
            host,
            task_id='t1', result_id=11, test_case_id='c1',
            algorithm_result=_upload_shaped_algo_result(2),
            algorithm_type='translation', test_type='api',
        )
        assert ok is True
        assert host.dispatched == [(1, [72])]

    def test_result_rounds_fewer_than_config_rounds_bounded(self):
        """结果轮数少于配置轮数：只补提交实际存在的轮次（下标对齐结果轮次）。"""
        config = _config([[(72, 'per_round')] for _ in range(3)], [])
        host = _EvalHost(config)
        ok = self._evaluate(
            host,
            task_id='t1', result_id=11, test_case_id='c1',
            algorithm_result=_upload_shaped_algo_result(2),
            algorithm_type='translation', test_type='api',
        )
        assert ok is True
        assert host.dispatched == [(0, [72]), (1, [72])]

    def test_legacy_top_dims_case_overall_only(self):
        """传统口径用例（维度在顶层、轮次无维度）：整体入口仅整体出分，无逐轮补提交。"""
        config = _config([[], []], [(9, None)])
        host = _EvalHost(config)
        ok = self._evaluate(
            host,
            task_id='t1', result_id=11, test_case_id='c1',
            algorithm_result=_upload_shaped_algo_result(2),
            algorithm_type='translation', test_type='api',
        )
        assert ok is True
        assert host.dispatched == [(None, [9])]

    def test_per_round_entry_not_affected(self):
        """指定轮次入口（round_number=N）不触发补提交，仍按轮取维度。"""
        config = _config([[(72, 'per_round'), (134, 'multi')] for _ in range(3)], [])
        host = _EvalHost(config)
        ok = self._evaluate(
            host,
            task_id='t1', result_id=11, test_case_id='c1',
            algorithm_result=_upload_shaped_algo_result(),
            algorithm_type='translation', test_type='api', round_number=1,
        )
        assert ok is True
        assert host.dispatched == [(1, [72])]
