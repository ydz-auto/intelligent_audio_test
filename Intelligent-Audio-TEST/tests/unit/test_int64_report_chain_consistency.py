# -*- coding: utf-8 -*-
"""INT-64 守卫：查询链 = 报告主生成链 轮次口径一致性。

原缺陷：查询链（report_aggregation/stats_mixin.py）已实现
agg_denominator / exclude_rounds / round_count / 整体-轮次优先级取值，
但报告主生成链（report_utils/metrics_mixin.py ReportUtils）无轮次优先级取值、
agg item 无 round_count/exclude_rounds——按轮次口径退化为按用例。

修复：两条链共用口径源 report_service/domain/services/round_caliber.py
（collect_dim_items / get_round_value_samples / resolve_exclude_rounds），
ReportUtils.extract_dimension_values 与查询链 ReportHelpers 共用同一实现。

本文件对同一份合成数据分别驱动两条链，断言逐维度结果一致：
- 查询链：_AggregationStatsMixin._compute_weighted_averages（报告页均值）
- 报告链：MetricsMixin.calculate_core_metrics（报告生成落库均值，单资源）
覆盖 average×case / average×round / ratio×round / pass_rate×case /
exclude_rounds 排除轮次 / 无 overall 回退各轮。
"""
import os
from unittest.mock import patch

# BaseConfig 在 import 时校验环境变量（本用例纯单测不触库，与仓库既有测试同款兜底）
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from shared.models.common_enums import TaskStatus
import report_service.application.services.report_aggregation.stats_mixin as stats_mod
from report_service.application.services.report_aggregation.stats_mixin import _AggregationStatsMixin
import report_service.application.services.report_utils.metrics_mixin as metrics_mod
from report_service.application.services.report_utils.metrics_mixin import MetricsMixin
import report_service.application.services.report_utils.resource_mixin as resource_mod


# ---------------- 合成数据 ----------------

def _dims():
    return [
        {'id': 1, 'name': '准确率', 'statistic_method': 'average', 'agg_denominator': 'case', 'exclude_rounds': []},
        {'id': 2, 'name': '时延', 'statistic_method': 'average', 'agg_denominator': 'round', 'exclude_rounds': []},
        {'id': 3, 'name': '打断成功率', 'statistic_method': 'ratio', 'agg_denominator': 'round', 'exclude_rounds': []},
        {'id': 4, 'name': '指令达标率', 'statistic_method': 'pass_rate', 'agg_denominator': 'case', 'exclude_rounds': []},
        {'id': 5, 'name': '恢复时长', 'statistic_method': 'average', 'agg_denominator': 'round', 'exclude_rounds': [0]},
    ]


def _rows(spec):
    """spec: {dim_id: {'overall': v | None, 'rounds': {round: v}}} → TRD 行 dict 列表。"""
    rows = []
    for dim_id, s in spec.items():
        if s.get('overall') is not None:
            rows.append({'dimension_id': dim_id, 'dimension_value': s['overall'], 'round_number': None})
        for rnd, v in sorted(s.get('rounds', {}).items()):
            rows.append({'dimension_id': dim_id, 'dimension_value': v, 'round_number': rnd})
    return rows


def _dim_results_map():
    return {
        1: _rows({
            1: {'overall': 80.0},
            2: {'rounds': {0: 10.0, 1: 30.0}},          # 无整体 → 各轮
            3: {'overall': 2.0, 'rounds': {0: 1.0, 1: 1.0, 2: 1.0}},
            4: {'overall': 1.0},
            5: {'rounds': {0: 100.0, 1: 50.0, 2: 50.0}},
        }),
        2: _rows({
            1: {'rounds': {0: 60.0, 1: 80.0}},          # 无整体 → 各轮算术平均 70
            2: {'overall': 20.0},                        # 仅整体 → 按轮次口径回退整体值
            3: {'rounds': {0: 0.0, 1: 1.0}},
            4: {'rounds': {0: 0.0, 1: 1.0}},             # 无整体 → 每轮独立 item
            5: {'rounds': {0: 30.0, 1: 70.0}},           # 排除第 0 轮 → 只取 70
        }),
    }


def _results():
    return [
        {'id': 1, 'task_id': 7, 'test_case_id': 101, 'execution_status': TaskStatus.COMPLETED.value, 'device_id': 1},
        {'id': 2, 'task_id': 7, 'test_case_id': 102, 'execution_status': TaskStatus.COMPLETED.value, 'device_id': 1},
    ]


_NO_PARAMS: list = []


def _patch_grpc():
    """patch 两条链的 gRPC 协作方（维度参数 / 用例映射 / 设备名）。"""
    test_cases_map = {
        101: {'group': {'id': 1, 'name': 'g1'}, 'tags': []},
        '101': {'group': {'id': 1, 'name': 'g1'}, 'tags': []},
        102: {'group': {'id': 1, 'name': 'g1'}, 'tags': []},
        '102': {'group': {'id': 1, 'name': 'g1'}, 'tags': []},
    }
    device = {'id': 1, 'name': 'DevA', 'app_version': None}
    return [
        patch.object(stats_mod, '_grpc_get_dimension_params', return_value=_NO_PARAMS),
        patch.object(metrics_mod, '_grpc_get_dimension_params', return_value=_NO_PARAMS),
        patch.object(metrics_mod, '_grpc_list_testcases_by_ids', return_value=test_cases_map),
        patch.object(resource_mod, '_grpc_get_device', return_value=device),
    ]


def _query_chain_averages():
    """查询链：报告页统计均值（stats_mixin._compute_weighted_averages）。"""
    all_dimensions = _dims()
    dim_results_map = _dim_results_map()
    dim_strategy_info = _AggregationStatsMixin._build_dim_strategy_info(all_dimensions)
    metric_name_to_id = {str(d['name']): int(d['id']) for d in all_dimensions}
    averages_map, _overall = _AggregationStatsMixin._compute_weighted_averages(
        _results(), all_dimensions, metric_name_to_id, dim_strategy_info, dim_results_map
    )
    return averages_map


def _report_chain_metric_data():
    """报告主生成链：报告生成落库均值（metrics_mixin.calculate_core_metrics）。"""
    all_dimensions = _dims()
    dim_results_map = _dim_results_map()
    resources = []
    core = MetricsMixin.calculate_core_metrics(
        results=_results(), all_dimensions=all_dimensions, resources=resources,
        dim_results_map=dim_results_map, tasks_map=None, use_time_prefix=False,
    )
    assert len(resources) == 1, f"fixture 应收敛到单资源，实际 {resources}"
    return core['metric_data'][resources[0]]


class TestQueryChainEqualsReportChain:
    """同一数据两条链逐维度一致。"""

    def test_all_dims_consistent(self):
        patches = _patch_grpc()
        with patches[0], patches[1], patches[2], patches[3]:
            query = _query_chain_averages()
            report = _report_chain_metric_data()

        for dim in _dims():
            name = dim['name']
            assert name in query, f"查询链缺少维度 {name}: {query}"
            assert name in report, f"报告链缺少维度 {name}: {report}"
            assert report[name] == query[name], (
                f"维度[{name}] 口径不一致: 查询链={query[name]} 报告链={report[name]}"
            )

    def test_average_case_mode_value(self):
        """average×case：有 overall 取 overall，无 overall 取各轮均值，再按用例平均。"""
        patches = _patch_grpc()
        with patches[0], patches[1], patches[2], patches[3]:
            query = _query_chain_averages()
        # R1=80(overall)，R2=(60+80)/2=70 → 75
        assert query['准确率'] == 75.0

    def test_average_round_mode_value(self):
        """average×round：各轮独立样本；仅整体回退整体值。"""
        patches = _patch_grpc()
        with patches[0], patches[1], patches[2], patches[3]:
            query = _query_chain_averages()
        # R1=[10,30]，R2=[20](回退) → (10+30+20)/3 = 20
        assert query['时延'] == 20.0

    def test_ratio_round_mode_value(self):
        """ratio×round：Σ数量/Σ有值轮次数。"""
        patches = _patch_grpc()
        with patches[0], patches[1], patches[2], patches[3]:
            query = _query_chain_averages()
        # R1 overall=2 (round_count=3)，R2 各轮 [0,1] (round_count=2) → (2+0+1)/(3+2)*100 = 60
        assert query['打断成功率'] == 60.0

    def test_pass_rate_case_mode_value(self):
        """pass_rate×case：达标用例数/用例数（无 overall 时按轮 item、按用例去重）。"""
        patches = _patch_grpc()
        with patches[0], patches[1], patches[2], patches[3]:
            query = _query_chain_averages()
        # R1=1(达标)，R2 轮 [0,1] → 用例级视为有值用例；达标计数 2 / 2 用例 = 100
        assert query['指令达标率'] == 100.0

    def test_exclude_rounds_value(self):
        """average×round + exclude_rounds=[0]：被排除轮次不进样本。"""
        patches = _patch_grpc()
        with patches[0], patches[1], patches[2], patches[3]:
            query = _query_chain_averages()
        # R1 排除轮 0 → [50,50]；R2 排除轮 0 → [70] → (50+50+70)/3
        assert abs(query['恢复时长'] - (50.0 + 50.0 + 70.0) / 3) < 1e-9

    def test_round_mode_report_chain_not_case_degraded(self):
        """回归锁定：报告链按轮次口径不再退化为按用例。

        修复前报告链对 average×round 维度直接累加用例级值：
        (R1 轮均值 20 + R2 overall 20) / 2 = 20（巧合相等），
        改用 R1=[10,30] 时按用例口径为 20、按轮次口径同为 20 无法区分——
        故本用例以 ratio×round 维度做退化判定：按轮次=60，按用例退化值=150。
        """
        patches = _patch_grpc()
        with patches[0], patches[1], patches[2], patches[3]:
            report = _report_chain_metric_data()
        assert report['打断成功率'] == 60.0
        assert report['打断成功率'] != 150.0
