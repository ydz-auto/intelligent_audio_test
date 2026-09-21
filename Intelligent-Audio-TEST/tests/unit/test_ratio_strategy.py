# -*- coding: utf-8 -*-
"""比率统计策略（RatioStrategy）回归测试（从 V9.7.10 移植，适配 V9.7.31 模块路径）。

覆盖：多轮/单轮 × 有整体/无整体 × 按轮次/按用例；排除轮次（含 -1 最后一轮解析）。
"""
from report_service.domain.services.aggregation_strategies import (
    RatioStrategy,
    PassRateStrategy,
    SimpleAverageStrategy,
)
from report_service.application.services.report_aggregation.stats_mixin import _AggregationStatsMixin


def _overall_item(value, case_id, round_count):
    """有整体结果时每用例 1 个 item：值为该用例总数，round_count 为该用例有值轮次数。"""
    return {'dimension_value': value, 'api_raw_response': {}, 'test_result_id': case_id, 'round_count': round_count}


def _round_items(values, case_id):
    """无整体结果时每轮 1 个 item：round_count = 该用例有值轮次数。"""
    n = len(values)
    return [{'dimension_value': v, 'api_raw_response': {}, 'test_result_id': case_id, 'round_count': n}
            for v in values]


# ---------- 按轮次（agg_denominator='round'，打断数量类默认） ----------

def test_round_mode_with_overall():
    """有整体结果、按轮次：Σ数量 / Σ各用例有值轮次数。"""
    items = [
        _overall_item(1, case_id=1, round_count=2),
        _overall_item(2, case_id=2, round_count=3),
    ]
    assert RatioStrategy().aggregate(items, denominator_mode='round') == round((1 + 2) / (2 + 3) * 100, 2)  # 60.0


def test_round_mode_without_overall():
    """无整体结果（每轮独立 item）、按轮次：轮次数按用例去重，不重复计数。"""
    items = (
        _round_items([1, 0], case_id=1) +   # 该用例 2 轮
        _round_items([1, 1, 1], case_id=2)  # 该用例 3 轮
    )
    assert RatioStrategy().aggregate(items, denominator_mode='round') == round((1 + 0 + 1 + 1 + 1) / (2 + 3) * 100, 2)  # 80.0


def test_round_mode_null_value_excluded():
    """值为 None 的 item 不计入分子也不计入分母。"""
    items = [
        _overall_item(None, case_id=1, round_count=3),
        _overall_item(1, case_id=2, round_count=2),
    ]
    assert RatioStrategy().aggregate(items, denominator_mode='round') == round(1 / 2 * 100, 2)  # 50.0


def test_round_mode_pure_overall_no_round_records_fallback_to_cases():
    """纯 overall 无轮次记录时，按轮次口径回退为用例数。"""
    items = [
        {'dimension_value': 1, 'api_raw_response': None, 'test_result_id': 1, 'round_count': 0},
        {'dimension_value': 2, 'api_raw_response': None, 'test_result_id': 2, 'round_count': 0},
    ]
    assert RatioStrategy().aggregate(items, denominator_mode='round') == round((1 + 2) / 2 * 100, 2)  # 150.0


# ---------- 按用例（agg_denominator='case'） ----------

def test_case_mode_with_overall():
    """有整体结果、按用例：Σ数量 / 配置该维度的用例数。"""
    items = [
        _overall_item(0, case_id=1, round_count=2),
        _overall_item(2, case_id=2, round_count=3),
    ]
    assert RatioStrategy().aggregate(items, denominator_mode='case') == round((0 + 2) / 2 * 100, 2)  # 100.0


def test_case_mode_without_overall_dedupe_by_case():
    """无整体结果、按用例：用例数按 test_result_id 去重，多轮不重复计。"""
    items = (
        _round_items([1, 0], case_id=1) +
        _round_items([1], case_id=2)
    )
    assert RatioStrategy().aggregate(items, denominator_mode='case') == round((1 + 0 + 1) / 2 * 100, 2)  # 100.0


def test_default_mode_is_case():
    """未传 denominator_mode 时默认按用例。"""
    items = [_overall_item(1, case_id=1, round_count=2)]
    assert RatioStrategy().aggregate(items) == 100.0


def test_all_zero_denominator_returns_none():
    """分母为 0（无任何有效 item）返回 None。"""
    assert RatioStrategy().aggregate([], denominator_mode='round') is None
    assert RatioStrategy().aggregate([{'dimension_value': None, 'test_result_id': 1}], denominator_mode='case') is None


# ---------- 按用例/按轮次 下沉到 pass_rate / average ----------

def test_pass_rate_round_mode():
    """pass_rate 按轮次：达标轮次数 / 有值轮次数。"""
    items = (
        _round_items([1, 0], case_id=1) +   # 1 轮达标
        _round_items([1, 1], case_id=2)     # 2 轮达标
    )
    # 阈值默认 value>0：3 轮达标 / 4 轮
    assert PassRateStrategy().aggregate(items, denominator_mode='round') == 75.0


def test_pass_rate_case_mode():
    """pass_rate 按用例：达标用例数 / 用例数。"""
    items = [
        _overall_item(1, case_id=1, round_count=2),
        _overall_item(0, case_id=2, round_count=3),
        _overall_item(1, case_id=3, round_count=2),
    ]
    assert PassRateStrategy().aggregate(items, denominator_mode='case') == round(2 / 3 * 100, 2)  # 66.67


def test_average_round_mode():
    """average 按轮次：Σ轮值 / 轮次数（多轮用例权重更大）。"""
    items = (
        _round_items([2, 4], case_id=1) +  # 轮均 3
        _round_items([10], case_id=2)      # 单值 10
    )
    # 按轮次：(2+4+10)/3 = 5.333...
    assert SimpleAverageStrategy().aggregate(items, denominator_mode='round') == (2 + 4 + 10) / 3


def test_average_case_mode():
    """average 按用例：Σ用例值 / 用例数（每用例等权）。"""
    items = [
        _overall_item(2, case_id=1, round_count=2),
        _overall_item(10, case_id=2, round_count=1),
    ]
    assert SimpleAverageStrategy().aggregate(items, denominator_mode='case') == 6.0


# ---------- 排除轮次（exclude_rounds，V9.7.31 stats_mixin 实现） ----------

_DIM_ID = 10


def _result_map(rows):
    """构造 dim_results_map: {result_id: [dimension 行 dict, ...]}（V9.7.31 契约：dimension_id/dimension_value）。"""
    return {1: rows}


def _rows(values_rounds):
    """values_rounds: [(value, round_number), ...] → TRD 行 dict。"""
    return [{'dimension_id': _DIM_ID, 'dimension_value': v, 'round_number': rn} for v, rn in values_rounds]


def test_get_round_value_samples_excludes_rounds():
    """_get_round_value_samples 跳过被排除的轮次；全部排除时回退整体值。"""
    dim_results_map = _result_map(_rows([(1.0, 0), (2.0, 1), (3.0, 2)]))
    assert _AggregationStatsMixin._get_round_value_samples(1, _DIM_ID, dim_results_map, {1}, 0.0) == [1.0, 3.0]
    # 全部排除 → 回退整体值 1 个样本
    assert _AggregationStatsMixin._get_round_value_samples(1, _DIM_ID, dim_results_map, {0, 1, 2}, 7.0) == [7.0]
    # 无排除 → 全部轮值
    assert _AggregationStatsMixin._get_round_value_samples(1, _DIM_ID, dim_results_map, set(), 0.0) == [1.0, 2.0, 3.0]


def test_resolve_exclude_rounds_minus_one():
    """排除轮次 -1（最后一轮）解析为该用例该维度最大轮次。"""
    dim_results_map = _result_map(_rows([(1.0, 0), (2.0, 1), (3.0, 2)]))
    # -1 → 最大轮次 2
    assert _AggregationStatsMixin._resolve_exclude_rounds(1, _DIM_ID, dim_results_map, {-1}) == {2}
    # -1 与具体轮次并存
    assert _AggregationStatsMixin._resolve_exclude_rounds(1, _DIM_ID, dim_results_map, {-1, 0}) == {2, 0}
    # 无轮次记录时 -1 无效 → 空集
    assert _AggregationStatsMixin._resolve_exclude_rounds(1, _DIM_ID, {}, {-1}) == set()


def test_get_round_value_samples_minus_one_flow():
    """-1 经 _resolve_exclude_rounds 后正确排除最后一轮。"""
    dim_results_map = _result_map(_rows([(1.0, 0), (2.0, 1), (3.0, 2)]))
    assert _AggregationStatsMixin._get_round_value_samples(1, _DIM_ID, dim_results_map, {-1}, 0.0) == [1.0, 2.0]
