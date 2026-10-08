# -*- coding: utf-8 -*-
"""Benchmark 查询对象（CQRS 读侧，frozen dataclass）

查询是 immutable 的读取意图描述：Handler 只读 ReadModel / 配置表，
不产生任何写副作用。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class GetBenchmarkRankingQuery:
    """排行查询（读 benchmark_rankings ReadModel）。

    Attributes:
        suite: 测试集筛选
        category: 被测类别筛选
        metric_code: 排行指标代码筛选
        source: 数据来源筛选（platform_test / external_import）
        published_task_id: 已发布任务筛选（查指定版本引用的排行行）
        subject_name: 被测对象名筛选
    """
    suite: Optional[str] = None
    category: Optional[str] = None
    metric_code: Optional[str] = None
    source: Optional[str] = None
    published_task_id: Optional[int] = None
    subject_name: Optional[str] = None


@dataclass(frozen=True)
class GetBenchmarkRankingSubjectsQuery:
    """参与排行的被测主体列表查询。"""
    suite: Optional[str] = None


@dataclass(frozen=True)
class ListBenchmarkSourcesQuery:
    """外部基线数据源分页查询。"""
    page: int = 1
    per_page: int = 10
    source_type: Optional[str] = None


@dataclass(frozen=True)
class ListBenchmarkBaselinesQuery:
    """外部基线条目分页查询（仅当前生效版本 is_current=True）。"""
    category: Optional[str] = None
    metric_code: Optional[str] = None
    source_id: Optional[int] = None
    page: int = 1
    per_page: int = 20


@dataclass(frozen=True)
class ListBenchmarkMetricMappingsQuery:
    """指标映射查询。"""
    active_only: bool = False
