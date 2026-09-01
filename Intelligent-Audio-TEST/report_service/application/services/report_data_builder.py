# -*- coding: utf-8 -*-
"""报告数据构建辅助（report_service 版本）。

从 api_gateway/application/services/report/report_data_builder.py 迁移而来，
保持 ReportDataBuilder 类原有逻辑不变，仅做以下调整：
- 移除 PO / get_db_session 直接数据库访问，改用 report_repository 写入聚合根与子实体
- 移除 api_gateway 专属依赖（response / schemas.report / report_util / report_helpers），
  改从 report_service 对应模块导入
- gRPC helper 统一从 report_service.infrastructure.clients.grpc_clients 导入
- _create_report_record / _create_report_summary / _create_report_detail_data
  改为通过 report_repository 对应方法写入
- 移除 _build_response（Pydantic 响应组装属 api_gateway 职责，不在 report_service 内）
- 报告状态/类型使用字符串字面量 'draft' / 'task'，保持与现有数据模型一致

实现采用 Mixin 组合模式（同 report_utils / report_aggregation 拆分先例）：
- ReportDataTaskMixin: 任务校验 + 维度结果/aux 参数批量查询 + 结果类型提取
- ReportDataAlgorithmMixin: algorithm_results 构建（aux 参数 + 策略化原始结果）
- ReportDataCaseMixin: 用例基本信息 / 指标 / 参考参数组装
- ReportDataResourceMixin: 资源列表 / 任务资源 / 汇总维度与全量指标
- ReportDataPersistMixin: 报告记录 / 摘要 / 明细持久化
"""

from shared.utils.response import success_response, error_response

from report_service.application.services.report_data_builder_task_mixin import ReportDataTaskMixin
from report_service.application.services.report_data_builder_algorithm_mixin import ReportDataAlgorithmMixin
from report_service.application.services.report_data_builder_case_mixin import ReportDataCaseMixin
from report_service.application.services.report_data_builder_resource_mixin import ReportDataResourceMixin
from report_service.application.services.report_data_builder_persist_mixin import ReportDataPersistMixin

# 兼容保留：部分调用方可能从本模块引用这些工具类
from report_service.application.services.report_utils import ReportUtils
from report_service.application.services.report_query_builder import ReportQueryBuilder
from report_service.application.services.report_helpers import ReportHelpers


class ReportDataBuilder(
    ReportDataTaskMixin,
    ReportDataAlgorithmMixin,
    ReportDataCaseMixin,
    ReportDataResourceMixin,
    ReportDataPersistMixin,
):
    """报告数据构建辅助（原 ReportCommandService 中 B 组方法）。

    承载任务报告数据构建相关的静态辅助方法，保持原有逻辑不变。
    """
    pass
