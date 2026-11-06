# -*- coding: utf-8 -*-
"""Benchmark 排行算法（6 种，纯领域服务，无 IO）

实现设计文档《报告Benchmark排行功能设计文档》§5.3：
1. rank         名次：rank = 1 + count(严格优于本主体的被测主体)，并列共享名次（竞赛排名法）
2. total        参与对比的被测主体数
3. percentile   百分位 = rank / total * 100（越低越靠前）
4. score100     归一化 0-100 分：全部被测主体极值线性映射，方向取反；
                只有 1 个被测主体时不归一化（score100 置空，只给 rank）
5. gapBest      本主体值 - 排行最佳（原始差值，符号随方向语义化展示）
6. gapMedian    本主体值 - 排行中位数
7. deltaExternal 平台实测值 - 外部基线值（仅同模型双轨并存时有值）

方向判定：direction = lower_is_better | higher_is_better。
- lower_is_better（如 WER%、时延 ms）：值越小名次越前
- higher_is_better（如 接话率%、MOS 分）：值越大名次越前

边界约定：
- 空榜：返回空列表
- 单主体：rank=1/total=1/percentile=100，score100 置空（不归一化），gap 取 0
- 全体并列（无极差）：score100 统一为 100（全部位于最优端），gap 为 0
"""
from __future__ import annotations

import statistics
from typing import Dict, List, Optional, Sequence

from report_service.domain.entities.benchmark import (
    RankingDirection,
    RankingMetricValues,
)


def _is_better(value, benchmark, direction: RankingDirection) -> bool:
    """value 是否严格优于 benchmark（不含并列）。"""
    if direction == RankingDirection.LOWER_IS_BETTER:
        return value < benchmark
    return value > benchmark


def compute_ranks(values: Sequence[float], direction: RankingDirection) -> List[int]:
    """竞赛排名：rank = 1 + 严格优于本主体的数量（并列共享名次）。

    Args:
        values: 参与排行的指标值列表（与方向语义一致）
        direction: 方向枚举

    Returns:
        与 values 等长的名次列表（从 1 开始）
    """
    if not values:
        return []
    ranks = []
    for v in values:
        ranks.append(1 + sum(1 for other in values if _is_better(other, v, direction)))
    return ranks


def compute_percentile(rank: int, total: int) -> Optional[float]:
    """百分位 = rank / total * 100（越低越靠前），保留 2 位小数。"""
    if total <= 0:
        return None
    return round(rank / total * 100, 2)


def compute_score100(
    values: Sequence[float], direction: RankingDirection,
) -> List[Optional[float]]:
    """归一化 0-100 分（极值线性映射，方向取反）。

    - lower_is_better：score100 = (worst - v) / (worst - best) * 100
    - higher_is_better：score100 = (v - worst) / (best - worst) * 100
    - 单主体：不归一化，全部置空（只给 rank）
    - 无极差（best == worst，全体并列）：统一 100 分（全部位于最优端）
    """
    n = len(values)
    if n == 0:
        return []
    if n == 1:
        return [None]
    lo, hi = min(values), max(values)
    spread = hi - lo
    if spread == 0:
        return [100.0 for _ in values]
    scores: List[Optional[float]] = []
    for v in values:
        if direction == RankingDirection.LOWER_IS_BETTER:
            raw = (hi - v) / spread
        else:
            raw = (v - lo) / spread
        scores.append(round(raw * 100, 2))
    return scores


def compute_gap_best(value: float, values: Sequence[float], direction: RankingDirection) -> float:
    """与排行最佳的差距：本主体值 - 排行最佳。

    lower_is_better 时最佳 = min；higher_is_better 时最佳 = max。
    """
    if not values:
        return 0.0
    best = min(values) if direction == RankingDirection.LOWER_IS_BETTER else max(values)
    return round(value - best, 6)


def compute_gap_median(value: float, values: Sequence[float]) -> float:
    """与排行中位数的差距：本主体值 - 排行中位数（中位数与方向无关）。"""
    if not values:
        return 0.0
    return round(value - statistics.median(values), 6)


def compute_delta_external(platform_value: float, external_value: float) -> float:
    """双轨并存差异：delta = 平台实测值 - 外部基线值。"""
    return round(platform_value - external_value, 6)


def calculate_ranking_metrics(
    values: Sequence[float],
    direction: RankingDirection,
    external_values: Optional[Dict[int, float]] = None,
) -> List[RankingMetricValues]:
    """对同组（同测试集 + 同类别 + 同指标）的值序列计算全部排行指标。

    Args:
        values: 参与排行的指标值列表（顺序与调用方条目一致）
        direction: 方向枚举
        external_values: {下标: 外部基线值}，双轨并存时计算 delta_external

    Returns:
        与 values 等长的 RankingMetricValues 列表；空榜返回空列表
    """
    if not values:
        return []
    values = list(values)
    total = len(values)
    ranks = compute_ranks(values, direction)
    percentiles = [compute_percentile(r, total) for r in ranks]
    score100s = compute_score100(values, direction)
    results: List[RankingMetricValues] = []
    for i, v in enumerate(values):
        delta = None
        if external_values and i in external_values:
            delta = compute_delta_external(v, external_values[i])
        results.append(RankingMetricValues(
            rank=ranks[i],
            total=total,
            percentile=percentiles[i],
            score100=score100s[i],
            gap_best=compute_gap_best(v, values, direction),
            gap_median=compute_gap_median(v, values),
            delta_external=delta,
        ))
    return results
