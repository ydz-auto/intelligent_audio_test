# -*- coding: utf-8 -*-
"""report_service 领域实体（re-export 入口）

纯领域对象，不依赖 SQLAlchemy / db.Model。
Repository 负责 PO ↔ Entity 转换。
"""
from report_service.domain.entities.report import (
    ReportAggregate,
    ReportCaseEntity,
    ReportComparisonMatrixEntity,
    ReportMetricStatsEntity,
    ReportRawDataEntity,
    ReportStatus,
    ReportSummaryEntity,
    ReportSummaryMetaEntity,
    ReportType,
)
from report_service.domain.entities.benchmark import (
    BaselineDraftEntry,
    BenchmarkCategory,
    BenchmarkSourceType,
    MetricMapping,
    RankingDirection,
    RankingEntry,
    RankingMetricValues,
    RankingNote,
    RankingSource,
    SubjectType,
)

__all__ = [
    'ReportAggregate',
    'ReportStatus',
    'ReportType',
    'ReportSummaryEntity',
    'ReportSummaryMetaEntity',
    'ReportCaseEntity',
    'ReportMetricStatsEntity',
    'ReportRawDataEntity',
    'ReportComparisonMatrixEntity',
    'BaselineDraftEntry',
    'BenchmarkCategory',
    'BenchmarkSourceType',
    'MetricMapping',
    'RankingDirection',
    'RankingEntry',
    'RankingMetricValues',
    'RankingNote',
    'RankingSource',
    'SubjectType',
]
