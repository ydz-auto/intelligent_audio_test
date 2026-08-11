# -*- coding: utf-8 -*-
from report_service.application.services.report_utils.resource_mixin import ResourceMixin
from report_service.application.services.report_utils.metrics_mixin import MetricsMixin
from report_service.application.services.report_utils.flatten_mixin import FlattenMixin


class ReportUtils(ResourceMixin, MetricsMixin, FlattenMixin):
    """报告工具类，聚合资源命名、指标计算和数据扁平化方法。"""
    pass


# 将 ReportUtils 注入各 mixin 模块的全局命名空间，
# 使 mixin 内部以 ReportUtils.xxx 形式调用的跨模块方法引用在运行时正确解析
import report_service.application.services.report_utils.resource_mixin as _resource_mixin_module
import report_service.application.services.report_utils.metrics_mixin as _metrics_mixin_module
import report_service.application.services.report_utils.flatten_mixin as _flatten_mixin_module

_resource_mixin_module.ReportUtils = ReportUtils
_metrics_mixin_module.ReportUtils = ReportUtils
_flatten_mixin_module.ReportUtils = ReportUtils
