# -*- coding: utf-8 -*-
"""report_service 持久化对象（PO）包。

归属：report_service（报告上下文）
表：test_reports / report_summaries / report_summary_meta / report_raw_data
     / report_cases / report_metric_stats / report_comparison_matrix

P5 改造：从 shared/models/models/report_models.py 真正下沉到本服务。
shared/models/models/report_models.py 改为从这里 re-export。

关键决策：移除 Report.task 跨域 relationship（Task 归属 task_service）。
跨域查询 Task 改通过 task_service gRPC 调用。
Report → ReportSummary/ReportCase 等子表的同域 relationship 全部保留。
"""
from .report_models import (
    Report,
    ReportSummary,
    ReportSummaryMeta,
    ReportRawData,
    ReportCase,
    ReportMetricStats,
    ReportComparisonMatrix,
)

__all__ = [
    'Report', 'ReportSummary', 'ReportSummaryMeta', 'ReportRawData',
    'ReportCase', 'ReportMetricStats', 'ReportComparisonMatrix',
]
