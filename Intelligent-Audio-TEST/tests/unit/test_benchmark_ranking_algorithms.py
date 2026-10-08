# -*- coding: utf-8 -*-
"""Benchmark 排行 6 算法 + 指标映射解析单测（INT-27 验收标准 2）

覆盖设计文档《报告Benchmark排行功能设计文档》§5.3 算法规则与边界：
- 空榜（空列表 → 空结果）
- 并列（竞赛排名 rank = 1 + 严格优于数量，并列共享名次）
- 单主体（score100 置空，只给 rank）
- 双向归一化（lower_is_better / higher_is_better）
- 全体并列（无极差 → score100 统一 100）
- 外部基线缺失映射（mapper 返回 None → no_mapping）
"""
import os

import pytest

# BaseConfig 在 import 时校验环境变量（测试环境无 .env），先补齐必需项
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from report_service.domain.entities.benchmark import (
    MetricMapping,
    RankingDirection,
    RankingMetricValues,
)
from report_service.domain.services.benchmark_ranking_calculator import (
    calculate_ranking_metrics,
    compute_gap_best,
    compute_gap_median,
    compute_delta_external,
    compute_percentile,
    compute_ranks,
    compute_score100,
)
from report_service.domain.services.benchmark_metric_mapper import (
    normalize_direction,
    resolve_external_metric,
    resolve_platform_dimension,
)

LOWER = RankingDirection.LOWER_IS_BETTER
HIGHER = RankingDirection.HIGHER_IS_BETTER


# ==================== rank（竞赛排名） ====================

class TestComputeRanks:
    def test_basic_lower_is_better(self):
        assert compute_ranks([5.0, 3.0, 8.0], LOWER) == [2, 1, 3]

    def test_basic_higher_is_better(self):
        assert compute_ranks([5.0, 3.0, 8.0], HIGHER) == [2, 3, 1]

    def test_ties_share_rank(self):
        # 两个 4.0 并列第 1，8.0 排第 3（竞赛排名法，不跳并列但跳名次）
        assert compute_ranks([4.0, 4.0, 8.0], LOWER) == [1, 1, 3]

    def test_ties_higher_direction(self):
        assert compute_ranks([4.0, 4.0, 8.0], HIGHER) == [2, 2, 1]

    def test_empty(self):
        assert compute_ranks([], LOWER) == []

    def test_single(self):
        assert compute_ranks([7.0], LOWER) == [1]


# ==================== percentile ====================

class TestComputePercentile:
    def test_formula(self):
        assert compute_percentile(1, 4) == 25.0
        assert compute_percentile(4, 4) == 100.0

    def test_rounding(self):
        assert compute_percentile(1, 3) == 33.33

    def test_zero_total(self):
        assert compute_percentile(1, 0) is None


# ==================== score100（双向归一化） ====================

class TestComputeScore100:
    def test_lower_is_better(self):
        # best=2 → 100，worst=10 → 0，中点 6 → 50
        assert compute_score100([2.0, 6.0, 10.0], LOWER) == [100.0, 50.0, 0.0]

    def test_higher_is_better(self):
        assert compute_score100([2.0, 6.0, 10.0], HIGHER) == [0.0, 50.0, 100.0]

    def test_single_subject_no_normalize(self):
        # 设计文档 §5.3.4：只有 1 个被测主体时不归一化（score100 置空，只给 rank）
        assert compute_score100([7.0], LOWER) == [None]

    def test_empty(self):
        assert compute_score100([], LOWER) == []

    def test_no_spread_all_tied(self):
        # 全体并列：无极差，统一 100 分（全部位于最优端）
        assert compute_score100([5.0, 5.0, 5.0], LOWER) == [100.0, 100.0, 100.0]

    def test_two_values(self):
        assert compute_score100([1.0, 3.0], LOWER) == [100.0, 0.0]


# ==================== gapBest / gapMedian / deltaExternal ====================

class TestGapsAndDelta:
    def test_gap_best_lower(self):
        # lower_is_better 最佳 = min = 2
        assert compute_gap_best(5.0, [2.0, 5.0, 8.0], LOWER) == 3.0
        assert compute_gap_best(2.0, [2.0, 5.0, 8.0], LOWER) == 0.0

    def test_gap_best_higher(self):
        # higher_is_better 最佳 = max = 8
        assert compute_gap_best(5.0, [2.0, 5.0, 8.0], HIGHER) == -3.0

    def test_gap_median(self):
        # 中位数与方向无关
        assert compute_gap_median(5.0, [2.0, 5.0, 8.0]) == 0.0
        assert compute_gap_median(8.0, [2.0, 5.0, 8.0]) == 3.0

    def test_gap_median_even_count(self):
        # 偶数个取中间两值平均：(5+7)/2 = 6
        assert compute_gap_median(5.0, [3.0, 5.0, 7.0, 9.0]) == -1.0

    def test_gap_empty(self):
        assert compute_gap_best(5.0, [], LOWER) == 0.0
        assert compute_gap_median(5.0, []) == 0.0

    def test_delta_external(self):
        # delta = 实测值 - 导入值
        assert compute_delta_external(4.2, 3.9) == pytest.approx(0.3)


# ==================== 全流程 calculate_ranking_metrics ====================

class TestCalculateRankingMetrics:
    def test_empty_board(self):
        # 边界：空榜 → 空结果
        assert calculate_ranking_metrics([], LOWER) == []

    def test_single_subject(self):
        # 边界：单主体 → rank=1/total=1，score100 置空
        results = calculate_ranking_metrics([3.5], LOWER)
        assert len(results) == 1
        assert results[0].rank == 1
        assert results[0].total == 1
        assert results[0].percentile == 100.0
        assert results[0].score100 is None

    def test_ties(self):
        # 边界：并列 → 共享名次，percentile 按 rank 计算
        results = calculate_ranking_metrics([4.0, 4.0, 8.0], LOWER)
        assert [m.rank for m in results] == [1, 1, 3]
        assert [m.percentile for m in results] == [33.33, 33.33, 100.0]
        # 并列者同分
        assert results[0].score100 == results[1].score100 == 100.0
        assert results[2].score100 == 0.0

    def test_full_metrics_lower(self):
        results = calculate_ranking_metrics([10.0, 2.0], LOWER)
        best, worst = results[1], results[0]
        assert best.rank == 1 and worst.rank == 2
        assert best.score100 == 100.0 and worst.score100 == 0.0
        assert best.gap_best == 0.0 and worst.gap_best == 8.0
        assert best.gap_median == -4.0 and worst.gap_median == 4.0

    def test_delta_external_when_both_tracks(self):
        # 双轨并存：实测 4.0 vs 导入 3.0 → delta = 1.0
        results = calculate_ranking_metrics([4.0], LOWER, {0: 3.0})
        assert results[0].delta_external == pytest.approx(1.0)

    def test_no_delta_without_external(self):
        results = calculate_ranking_metrics([4.0, 5.0], LOWER)
        assert all(m.delta_external is None for m in results)

    def test_result_type(self):
        results = calculate_ranking_metrics([1.0], HIGHER)
        assert isinstance(results[0], RankingMetricValues)


# ==================== 指标映射解析 ====================

class TestMetricMapper:
    def _mapping(self, dim='WER', code='WER', direction=LOWER):
        return MetricMapping(
            id=1, dimension_name=dim, metric_code=code, metric_name='Word Error Rate',
            unit='%', direction=direction, scenario_tags=['普通话通用'],
        )

    def test_resolve_platform_dimension_hit(self):
        mappings = {'WER': self._mapping()}
        assert resolve_platform_dimension(mappings, 'WER').metric_code == 'WER'

    def test_resolve_platform_dimension_miss(self):
        # 边界：外部基线/维度缺失映射 → None（no_mapping，排行跳过该指标）
        assert resolve_platform_dimension({'WER': self._mapping()}, 'MOS') is None

    def test_resolve_external_metric_hit(self):
        mappings = {'WER': self._mapping()}
        assert resolve_external_metric(mappings, 'WER').dimension_name == 'WER'

    def test_resolve_external_metric_missing_mapping(self):
        assert resolve_external_metric({}, 'UNKNOWN') is None

    def test_normalize_direction_valid(self):
        assert normalize_direction('lower_is_better') == LOWER
        assert normalize_direction('HIGHER_IS_BETTER') == HIGHER
        assert normalize_direction(' higher_is_better ') == HIGHER

    def test_normalize_direction_invalid(self):
        assert normalize_direction('up_is_better') is None
        assert normalize_direction('') is None
        assert normalize_direction(None) is None
