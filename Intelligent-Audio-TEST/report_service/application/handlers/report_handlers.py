# -*- coding: utf-8 -*-
"""报告命令/查询处理器（CQRS Handler，聚合模块，P4-5 大文件拆分）。

原单文件 831 行，按职责拆分为 3 个内部模块，本文件保持
`from report_service.application.handlers.report_handlers import ...`
的全部导入路径不变：

- _report_case_filters.py：TestResult / TestCase 客户端过滤公共函数
- _report_cases_query_mixin.py：ReportCasesQueryMixin — 用例列表/搜索/导出
- _report_stats_query_mixin.py：ReportStatsQueryMixin — 平均值统计/日志下载

职责：
- 接收 Command/Query 对象
- 通过 report_repository 操作聚合根（不直接 import PO）
- 返回聚合根或聚合根列表

遵循 DDD 分层：application 层只依赖 domain 与 repository，
不感知 ORM/PO，保持领域层与基础设施解耦。
"""
from __future__ import annotations

from typing import List, Optional
import logging

from report_service.domain.entities import ReportAggregate, ReportStatus
from report_service.infrastructure.persistence.report_repository import report_repository
from report_service.application.commands.report_commands import (
    CreateReportCommand,
    DeleteReportCommand,
    GenerateReportCommand,
    UpdateReportStatusCommand,
)
from report_service.application.queries.report_queries import (
    GetReportByTaskQuery,
    GetReportQuery,
    GetReportSummaryQuery,
    GetTrendDataQuery,
    ListReportsQuery,
)
from report_service.application.handlers._report_cases_query_mixin import (
    ReportCasesQueryMixin,
)
from report_service.application.handlers._report_stats_query_mixin import (
    ReportStatsQueryMixin,
)

logger = logging.getLogger(__name__)


class ReportCommandHandler:
    """报告命令处理器。

    处理所有写操作命令，通过 report_repository 操作聚合根。
    支持注入自定义仓储实例以便单元测试。
    """

    def __init__(self, repository=report_repository) -> None:
        """初始化命令处理器。

        Args:
            repository: 报告仓储实例，默认使用模块级单例 report_repository
        """
        self.repository = repository

    def handle_create(self, command: CreateReportCommand) -> int:
        """处理创建报告命令。

        构造一个处于 pending 状态的聚合根并持久化。

        Args:
            command: CreateReportCommand

        Returns:
            新创建的报告 ID
        """
        aggregate = ReportAggregate(
            id=0,
            task_id=command.task_id,
            report_type=command.report_type,
            status=ReportStatus.PENDING.value,
            config=dict(command.config),
        )
        return self.repository.add(aggregate)

    def handle_generate(self, command: GenerateReportCommand) -> Optional[int]:
        """处理生成报告命令。

        流程：查找任务最新报告 -> 标记为 generating；
        若报告不存在则创建新报告并直接标记为 generating。

        Args:
            command: GenerateReportCommand

        Returns:
            报告 ID；若无法处理返回 None
        """
        aggregate = self.repository.get_by_task(command.task_id)
        if aggregate is None:
            # 任务尚无报告，新建并直接进入 generating
            aggregate = ReportAggregate(
                id=0,
                task_id=command.task_id,
                report_type=command.report_type,
                status=ReportStatus.GENERATING.value,
                config={},
            )
            return self.repository.add(aggregate)
        # 已存在报告：更新类型并标记为 generating
        aggregate.report_type = command.report_type
        aggregate.mark_generating()
        self.repository.save(aggregate)
        return aggregate.id

    def handle_generate_task_report(self, task_id: int, name: str = None, description: str = None) -> dict:
        """处理生成任务报告命令。

        委托 ReportTaskGenerator 执行异步生成。
        """
        from report_service.application.services.report_task_generator import ReportTaskGenerator
        return ReportTaskGenerator.generate_task_report(task_id, name, description)

    def handle_generate_compare_report(self, task_ids: list, name: str = None, description: str = None) -> dict:
        """处理生成对比报告命令。"""
        from report_service.application.services.report_compare_generator import ReportCompareGenerator
        return ReportCompareGenerator.compare(task_ids, name, description)

    def handle_generate_secondary_compare_report(self, report_ids: list, description: str = None) -> dict:
        """处理生成二次对比报告命令。"""
        from report_service.application.services.report_compare_generator import ReportCompareGenerator
        return ReportCompareGenerator.secondary_compare(report_ids, description)

    def handle_update_status(self, command: UpdateReportStatusCommand) -> None:
        """处理更新报告状态命令。

        Args:
            command: UpdateReportStatusCommand
        """
        self.repository.update_status(command.report_id, command.status)

    def handle_delete(self, command: DeleteReportCommand) -> bool:
        """处理删除报告命令（软删除）。

        Args:
            command: DeleteReportCommand

        Returns:
            True 表示删除成功，False 表示报告不存在
        """
        return self.repository.soft_delete(command.report_id)


class ReportQueryHandler(ReportCasesQueryMixin, ReportStatsQueryMixin):
    """报告查询处理器（组合用例/统计查询 Mixin）。

    处理所有读操作查询，通过 report_repository 加载聚合根。
    支持注入自定义仓储实例以便单元测试。
    """

    def __init__(self, repository=report_repository) -> None:
        """初始化查询处理器。

        Args:
            repository: 报告仓储实例，默认使用模块级单例 report_repository
        """
        self.repository = repository

    def handle_get(self, query: GetReportQuery) -> Optional[ReportAggregate]:
        """处理按 ID 查询报告详情（附完整摘要统计，不含 cases 等大体积子实体）。

        Args:
            query: GetReportQuery

        Returns:
            ReportAggregate 或 None（报告不存在或已软删除）
        """
        aggregate = self.repository.get_by_id(query.report_id)
        if aggregate is None:
            return None
        # 加载摘要统计，供序列化层派生出对外契约 summary 字段
        aggregate.summaries = self.repository.load_summaries(query.report_id)
        # 详情接口补充完整摘要视图（all_metrics/case_categories/all_case_tags/
        # metric_data/tag_metric_data 等），序列化层优先输出到 summary 字段
        aggregate.full_summary = self.repository.load_full_report_data(query.report_id)
        return aggregate

    def handle_get_by_task(self, query: GetReportByTaskQuery) -> Optional[ReportAggregate]:
        """处理按任务 ID 查询最新报告。

        Args:
            query: GetReportByTaskQuery

        Returns:
            ReportAggregate 或 None
        """
        aggregate = self.repository.get_by_task(query.task_id)
        if aggregate is None:
            return None
        aggregate.summaries = self.repository.load_summaries(aggregate.id)
        return aggregate

    def handle_list(self, query: ListReportsQuery) -> List[ReportAggregate]:
        """处理分页列出报告（各条附摘要统计）。

        Args:
            query: ListReportsQuery

        Returns:
            聚合根列表（不含 cases 等大体积子实体）
        """
        aggregates = self.repository.list_reports(
            status=query.status,
            page=query.page,
            page_size=query.page_size,
        )
        # 逐条加载摘要统计（列表场景每页数据量小，避免默认空 summary）
        for aggregate in aggregates:
            if aggregate is None:
                continue
            aggregate.summaries = self.repository.load_summaries(aggregate.id)
        return aggregates

    def handle_get_summary(self, query: GetReportSummaryQuery) -> Optional[ReportAggregate]:
        """处理查询报告摘要（含子实体集合）。

        加载主聚合根后，附加 summaries/cases/metric_stats/raw_data 等子实体。

        Args:
            query: GetReportSummaryQuery

        Returns:
            填充了子实体的 ReportAggregate，或 None（报告不存在）
        """
        aggregate = self.repository.get_by_id(query.report_id)
        if aggregate is None:
            return None
        # 加载子实体集合并填充到聚合根
        aggregate.summaries = self.repository.load_summaries(query.report_id)
        aggregate.cases = self.repository.load_cases(query.report_id)
        aggregate.metric_stats = self.repository.load_metric_stats(query.report_id)
        aggregate.raw_data = self.repository.load_raw_data(query.report_id)
        return aggregate

    def handle_get_trend(self, query: GetTrendDataQuery) -> list:
        """处理查询报告趋势数据。

        返回按 created_at 升序排列的报告列表，每条含成功率/时长，
        并计算与前一条相比的变化量。

        Args:
            query: GetTrendDataQuery

        Returns:
            list[dict]: 趋势数据列表
        """
        rows = self.repository.get_trend_data(
            report_type=query.report_type,
            task_id=query.task_id,
            limit=query.limit,
        )
        trend_data = []
        prev_rate = None
        prev_duration = None
        for row in rows:
            rate = row.get('pass_rate', 0) or 0
            duration = row.get('duration', 0) or 0
            delta_rate = round(rate - prev_rate, 2) if prev_rate is not None else 0
            delta_dur_pct = round((duration - prev_duration) / prev_duration * 100, 2) if prev_duration else 0
            trend_data.append({
                'report_id': row.get('report_id'),
                'name': row.get('name'),
                'created_at': row.get('created_at').isoformat() if row.get('created_at') else None,
                'success_rate': rate,
                'avg_duration': duration,
                'delta_success_rate': delta_rate,
                'delta_duration_percent': delta_dur_pct,
            })
            prev_rate = rate
            prev_duration = duration
        return trend_data

    # ---- 参考参数构建（供 api_gateway task_query_service 通过 gRPC 调用）----

    def handle_build_reference_params(self, case_info: dict, case_results: list, test_type: str = 'api') -> dict:
        """构建参考参数和音频列表。

        从 case_results 中提取 adjusted_reference_params，或回退到 case_info.reference_params / config，
        再通过 algorithm_service gRPC 获取标准化的参考参数格式。
        同时构建音频列表。

        Args:
            case_info: TestCase 信息 dict
            case_results: 测试结果列表
            test_type: 测试类型

        Returns:
            dict: {reference_params, audios_list}
        """
        from report_service.application.services.report_data_builder import ReportDataBuilder
        from report_service.application.services.report_helpers import ReportHelpers
        from types import SimpleNamespace

        case = SimpleNamespace(**case_info) if isinstance(case_info, dict) else case_info
        results = case_results or []

        ref_params = ReportDataBuilder._get_reference_params(case, results, test_type)
        audios_list = ReportHelpers._build_audios_list(case)

        return {'reference_params': ref_params, 'audios_list': audios_list}
