# -*- coding: utf-8 -*-
"""Benchmark 排行领域对象（纯领域对象，不依赖 SQLAlchemy / HTTP）

归属：report_service（报告上下文，D1 Benchmark 双轨排行）
对应 PO：BenchmarkRanking / BenchmarkMetricMapping / BenchmarkSource / BenchmarkBaseline

双轨数据来源（设计文档《报告Benchmark排行功能设计文档》§2.3）：
- platform_test   平台实测（主）：正式发布任务（published_tasks.benchmark=true）的执行得分
- external_import 外部基线导入（辅）：人工导入的业界公开榜单数据（不可变版本快照）
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class RankingSource(str, Enum):
    """排行数据来源枚举（双轨制）。"""
    PLATFORM_TEST = 'platform_test'
    EXTERNAL_IMPORT = 'external_import'


class RankingDirection(str, Enum):
    """指标方向枚举：排名与 score100 归一化的语义依据。"""
    LOWER_IS_BETTER = 'lower_is_better'
    HIGHER_IS_BETTER = 'higher_is_better'


class BenchmarkCategory(str, Enum):
    """被测类别枚举（published_tasks.snapshot_config.benchmarkCategory / 基线条目 category）。"""
    ASR = 'asr'
    VOICE_LLM = 'voice_llm'
    TTS = 'tts'
    TRANSLATION = 'translation'


class SubjectType(str, Enum):
    """被测主体类型枚举。"""
    OPEN_SOURCE = 'open_source'
    CLOSED_SOURCE = 'closed_source'
    APP = 'app'


class BenchmarkSourceType(str, Enum):
    """外部基线数据源类型枚举。"""
    OFFICIAL = 'official'
    THIRD_PARTY = 'third_party'
    SELF_TEST = 'self_test'
    MANUAL = 'manual'


class RankingNote(str, Enum):
    """排行参与情况备注枚举（设计文档 §10 异常处理）。"""
    NO_REPORT = 'no_report'
    NO_MAPPING = 'no_mapping'
    SUBJECT_OFFLINE = 'subject_offline'


@dataclass(frozen=True)
class MetricMapping:
    """指标映射值对象：系统维度 ↔ 排行指标的单一事实源条目。"""
    id: Optional[int]
    dimension_name: str
    metric_code: str
    metric_name: str
    unit: str
    direction: RankingDirection
    scenario_tags: List[str] = field(default_factory=list)
    active: bool = True


@dataclass(frozen=True)
class RankingMetricValues:
    """单条排行计算结果（6 算法输出：rank/percentile/score100/gapBest/gapMedian/deltaExternal）。

    delta_external 仅当同模型平台实测与外部基线并存时有值，否则 None。
    """
    rank: int
    total: int
    percentile: Optional[float]
    score100: Optional[float]
    gap_best: Optional[float]
    gap_median: Optional[float]
    delta_external: Optional[float] = None


@dataclass(frozen=True)
class RankingEntry:
    """参与排行的一条被测数据（双轨统一形态，经指标映射后入组）。"""
    source: RankingSource
    subject_name: str
    metric_code: str
    metric_name: str
    metric_value: float
    unit: str
    direction: RankingDirection
    suite: str = ''
    category: str = ''
    scenario_key: str = ''
    subject_type: str = SubjectType.CLOSED_SOURCE.value
    device_type: str = ''
    published_task_id: Optional[int] = None
    published_task_version: Optional[int] = None
    report_id: Optional[int] = None
    baseline_id: Optional[int] = None


@dataclass(frozen=True)
class BaselineDraftEntry:
    """外部基线导入草稿行（逐行校验的输入形态）。"""
    model_name: str
    metric_code: str
    value: float
    vendor: str = ''
    metric_name: str = ''
    unit: str = ''
    direction: str = ''
    category: str = ''
    scenario_tags: List[str] = field(default_factory=list)
    sample_size: Optional[int] = None
    metric_date: str = ''
