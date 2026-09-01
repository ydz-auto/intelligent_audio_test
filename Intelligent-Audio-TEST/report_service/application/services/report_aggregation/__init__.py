# -*- coding: utf-8 -*-
"""报告聚合统计子包。

将原 services/ 下扁平存放的报告聚合拆分文件（common/stats/resource/cases/export/service）
收拢为一个独立子包，遵循 report_utils/ 子包组织模式。

对外入口：
- ReportAggregationService：组合各 Mixin 的门面服务类
- 各 Mixin 与 _r_get 辅助函数：供内部或潜在外部按需引用
"""
from report_service.application.services.report_aggregation.common import _r_get
from report_service.application.services.report_aggregation.stats_mixin import _AggregationStatsMixin
from report_service.application.services.report_aggregation.resource_mixin import _AggregationResourceMixin
from report_service.application.services.report_aggregation.cases_mixin import _AggregationCasesMixin
from report_service.application.services.report_aggregation.export_mixin import _AggregationExportMixin
from report_service.application.services.report_aggregation.service import ReportAggregationService

__all__ = [
    'ReportAggregationService',
    '_AggregationStatsMixin',
    '_AggregationResourceMixin',
    '_AggregationCasesMixin',
    '_AggregationExportMixin',
    '_r_get',
]
