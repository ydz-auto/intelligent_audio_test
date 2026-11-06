# -*- coding: utf-8 -*-
"""报告聚合统计服务（门面）。

职责：组合各 Mixin，对外提供统一的 ReportAggregationService 门面类，
对外接口与拆分前完全一致（调用方仅依赖本模块的类导入路径）。

各 Mixin 职责划分：
- _AggregationStatsMixin：统计计算（平均值、维度过滤、算法结果展开等）
- _AggregationResourceMixin：资源聚合（设备/API 资源列表、用例映射）
- _AggregationCasesMixin：用例列表（构建/过滤/分页/排序）
- _AggregationExportMixin：导出（Excel/PDF/CSV 载荷构建）
"""
from __future__ import annotations

from report_service.application.services.report_aggregation.common import _r_get
from report_service.application.services.report_aggregation.stats_mixin import _AggregationStatsMixin
from report_service.application.services.report_aggregation.resource_mixin import _AggregationResourceMixin
from report_service.application.services.report_aggregation.cases_mixin import _AggregationCasesMixin
from report_service.application.services.report_aggregation.export_mixin import _AggregationExportMixin

__all__ = ['ReportAggregationService', '_r_get']


class ReportAggregationService(_AggregationStatsMixin, _AggregationResourceMixin, _AggregationCasesMixin, _AggregationExportMixin):
    """报告聚合统计服务（门面，组合各 Mixin，对外接口不变）。

    将原 ReportQueryHandler._calculate_averages 中的业务逻辑拆分至此，
    handler 仅负责请求解析和响应格式化。
    """
    pass
