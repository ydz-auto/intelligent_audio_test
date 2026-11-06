# -*- coding: utf-8 -*-
"""报告聚合统计服务 — 兼容性重导出（Facade Shim）。

实现已迁移至 report_service/application/services/report_aggregation/ 子包，
本文件仅保留旧导入路径 `report_service.application.services.report_aggregation_service`
的向后兼容，供既有 handler（_report_stats_query_mixin / _report_cases_query_mixin）继续使用。
"""
from report_service.application.services.report_aggregation.service import ReportAggregationService

__all__ = ['ReportAggregationService']
