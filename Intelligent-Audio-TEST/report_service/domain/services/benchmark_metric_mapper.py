# -*- coding: utf-8 -*-
"""Benchmark 指标映射解析（纯领域服务，无 IO）

指标映射的单一事实源是 benchmark_metric_mappings 表（配置化，拒绝魔法字符串）：
- 平台实测轨：报告维度名（dimensionValues[].name）→ 排行指标（metric_code + 单位 + 方向）
- 外部基线轨：条目 metric_code 直接对齐映射表的 metric_code，缺失映射的指标跳过（no_mapping）

score100 换算不在映射层做：score100 是排行算法（§5.3.4）对同组值的归一化输出，
映射层只负责指标名/单位/方向的统一，保证双轨同口径入组。
"""
from __future__ import annotations

from typing import Dict, Optional

from report_service.domain.entities.benchmark import (
    MetricMapping,
    RankingDirection,
)


def resolve_platform_dimension(
    mappings: Dict[str, MetricMapping], dimension_name: str,
) -> Optional[MetricMapping]:
    """按系统维度名解析映射（平台实测轨）。

    Args:
        mappings: {dimension_name: MetricMapping}（仅启用项）
        dimension_name: 报告维度名（如 WER / takeover_latency）

    Returns:
        命中的映射；无映射配置时返回 None（调用方跳过该指标并标记 no_mapping）
    """
    return mappings.get(dimension_name)


def resolve_external_metric(
    mappings_by_code: Dict[str, MetricMapping], metric_code: str,
) -> Optional[MetricMapping]:
    """按排行指标代码解析映射（外部基线轨，双向校验用）。

    Args:
        mappings_by_code: {metric_code: MetricMapping}（仅启用项）
        metric_code: 基线条目声明的排行指标代码

    Returns:
        命中的映射；缺失映射返回 None（no_mapping，外部基线缺失映射的边界）
    """
    return mappings_by_code.get(metric_code)


def normalize_direction(value: str) -> Optional[RankingDirection]:
    """方向字符串归一化为枚举；非法值返回 None（校验拦截）。"""
    if not isinstance(value, str):
        return None
    normalized = value.strip().lower()
    for direction in RankingDirection:
        if direction.value == normalized:
            return direction
    return None
