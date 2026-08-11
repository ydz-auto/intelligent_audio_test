# -*- coding: utf-8 -*-
"""report_service gRPC servicer

ReportServicer: 报告 CRUD / 生成 / 查询（CreateReport / UpdateReport /
DeleteReport / BatchActionReports / ListReports / GetReportDetail /
GetReportByTask / GenerateReport / UpdateReportStatus）

继承 report_service_pb2_grpc.ReportConfigServiceServicer，
每个方法委托 application 层 handler。
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from shared.proto import report_service_pb2 as report_pb
from shared.proto import report_service_pb2_grpc as report_grpc
from shared.utils.grpc_json import loads as _loads, dumps as _dumps

from report_service.application.commands.report_commands import (
    CreateReportCommand,
    DeleteReportCommand,
    GenerateReportCommand,
    UpdateReportStatusCommand,
)
from report_service.application.handlers.report_handlers import (
    ReportCommandHandler,
    ReportQueryHandler,
)
from report_service.application.queries.report_queries import (
    GetReportByTaskQuery,
    GetReportQuery,
    GetReportSummaryQuery,
    ListReportsQuery,
)
from report_service.domain.entities import ReportAggregate

logger = logging.getLogger(__name__)


def _aggregate_to_dict(aggregate: Optional[ReportAggregate]) -> Optional[Dict[str, Any]]:
    """将 ReportAggregate 聚合根序列化为字典。

    Args:
        aggregate: 报告聚合根（可能为 None）

    Returns:
        包含报告元数据的字典；aggregate 为 None 时返回 None
    """
    if aggregate is None:
        return None
    return {
        'id': aggregate.id,
        'task_id': aggregate.task_id,
        'report_type': aggregate.report_type,
        'status': aggregate.status,
        'config': dict(aggregate.config) if aggregate.config else {},
        'created_at': str(aggregate.created_at) if aggregate.created_at is not None else None,
        # 子实体集合（仅 summary 查询时填充）
        'summaries': [
            {
                'id': s.id,
                'report_id': s.report_id,
                'metric_name': s.metric_name,
                'metric_value': s.metric_value,
                'metadata': dict(s.metadata) if s.metadata else {},
            }
            for s in aggregate.summaries
        ],
        'cases': [
            {
                'id': c.id,
                'report_id': c.report_id,
                'test_case_id': c.test_case_id,
                'result_summary': dict(c.result_summary) if c.result_summary else {},
                'score': c.score,
            }
            for c in aggregate.cases
        ],
        'metric_stats': [
            {
                'id': m.id,
                'report_id': m.report_id,
                'metric_name': m.metric_name,
                'avg': m.avg,
                'min': m.min,
                'max': m.max,
                'std_dev': m.std_dev,
                'sample_count': m.sample_count,
            }
            for m in aggregate.metric_stats
        ],
        'raw_data': [
            {
                'id': r.id,
                'report_id': r.report_id,
                'data_type': r.data_type,
                'data': dict(r.data) if r.data else {},
            }
            for r in aggregate.raw_data
        ],
    }


class ReportServicer(report_grpc.ReportConfigServiceServicer):
    """报告服务 gRPC servicer

    继承 report_service_pb2_grpc.ReportConfigServiceServicer，
    每个 RPC 方法委托 application 层：
    - 写操作 -> ReportCommandHandler
    - 读操作 -> ReportQueryHandler
    """

    def __init__(self) -> None:
        """初始化 servicer，延迟创建 command/query handler。"""
        self._command_handler: Optional[ReportCommandHandler] = None
        self._query_handler: Optional[ReportQueryHandler] = None

    @property
    def command_handler(self) -> ReportCommandHandler:
        """延迟初始化命令处理器。"""
        if self._command_handler is None:
            self._command_handler = ReportCommandHandler()
        return self._command_handler

    @property
    def query_handler(self) -> ReportQueryHandler:
        """延迟初始化查询处理器。"""
        if self._query_handler is None:
            self._query_handler = ReportQueryHandler()
        return self._query_handler

    @staticmethod
    def _resp(success: bool, message: str = '', data: Any = None) -> report_pb.ReportConfigResponse:
        """构造统一响应。"""
        return report_pb.ReportConfigResponse(
            success=success,
            message=message,
            data=_dumps(data) if data is not None else '',
        )

    # ---- 写操作 ----

    def CreateReport(self, request, context=None):
        """创建报告（pending 状态）。

        请求字段（proto CreateReportRequest）：
            data: str  JSON：{task_id, report_type, config, name, ...}

        Returns:
            ReportConfigResponse
        """
        try:
            data = _loads(getattr(request, 'data', ''), {}) or {}
            command = CreateReportCommand(
                task_id=data.get('task_id'),
                report_type=data.get('report_type') or 'standard',
                config=data.get('config') or {},
            )
            report_id = self.command_handler.handle_create(command)
            return self._resp(True, 'ok', {'report_id': report_id})
        except Exception as e:
            logger.exception("CreateReport failed")
            return self._resp(False, str(e), {})

    def UpdateReport(self, request, context=None):
        """更新报告字段。

        请求字段（proto UpdateReportRequest）：
            report_id: int  报告 ID
            data: str      JSON：更新字段
        """
        try:
            data = _loads(getattr(request, 'data', ''), {}) or {}
            # application 层无独立 update 命令，通过 update_status 间接处理。
            # 若 data 含 status 则更新状态，否则返回 ok。
            status = data.get('status')
            if status:
                command = UpdateReportStatusCommand(
                    report_id=getattr(request, 'report_id'),
                    status=status,
                )
                self.command_handler.handle_update_status(command)
            return self._resp(True, 'ok', {
                'report_id': getattr(request, 'report_id'),
                'updated': True,
            })
        except Exception as e:
            logger.exception("UpdateReport failed")
            return self._resp(False, str(e), {})

    def DeleteReport(self, request, context=None):
        """删除报告（软删除）。

        请求字段（proto DeleteReportRequest）：
            report_id: int   报告 ID
            hard_delete: bool 是否硬删除
        """
        try:
            command = DeleteReportCommand(
                report_id=getattr(request, 'report_id'),
            )
            deleted = self.command_handler.handle_delete(command)
            return self._resp(
                deleted,
                'ok' if deleted else 'report not found',
                {'report_id': command.report_id, 'deleted': deleted},
            )
        except Exception as e:
            logger.exception("DeleteReport failed")
            return self._resp(False, str(e), {})

    def BatchActionReports(self, request, context=None):
        """批量操作报告。

        请求字段（proto BatchActionReportsRequest）：
            data: str  JSON：批量操作参数
        """
        try:
            data = _loads(getattr(request, 'data', ''), {}) or {}
            action = data.get('action') or 'delete'
            report_ids = data.get('report_ids') or []
            results = []
            for rid in report_ids:
                command = DeleteReportCommand(report_id=rid)
                ok = self.command_handler.handle_delete(command)
                results.append({'report_id': rid, 'deleted': ok})
            return self._resp(True, 'ok', {'items': results})
        except Exception as e:
            logger.exception("BatchActionReports failed")
            return self._resp(False, str(e), {})

    def GenerateReport(self, request, context=None):
        """生成报告（pending -> generating -> completed/failed）。

        请求字段（proto GenerateReportRequest）：
            task_id: int      关联任务 ID
            report_type: str  报告类型
            data: str         JSON：额外参数
        """
        try:
            command = GenerateReportCommand(
                task_id=getattr(request, 'task_id'),
                report_type=getattr(request, 'report_type', None) or 'standard',
            )
            report_id = self.command_handler.handle_generate(command)
            return self._resp(
                report_id is not None,
                'ok' if report_id is not None else 'generate failed',
                {'report_id': report_id},
            )
        except Exception as e:
            logger.exception("GenerateReport failed")
            return self._resp(False, str(e), {})

    def GenerateTaskReport(self, request, context=None):
        """生成任务报告。"""
        try:
            result = self.command_handler.handle_generate_task_report(
                task_id=getattr(request, 'task_id'),
                name=getattr(request, 'name', None) or None,
                description=getattr(request, 'description', None) or None,
            )
            return self._resp(
                result.get('success', False),
                result.get('message', ''),
                result.get('data'),
            )
        except Exception as e:
            logger.exception("GenerateTaskReport failed")
            return self._resp(False, str(e), {})

    def GenerateCompareReport(self, request, context=None):
        """生成对比报告。"""
        try:
            data = _loads(getattr(request, 'data', ''), {}) or {}
            result = self.command_handler.handle_generate_compare_report(
                task_ids=data.get('task_ids', []),
                name=data.get('name'),
                description=data.get('description'),
            )
            return self._resp(
                result.get('success', False),
                result.get('message', ''),
                result.get('data'),
            )
        except Exception as e:
            logger.exception("GenerateCompareReport failed")
            return self._resp(False, str(e), {})

    def GenerateSecondaryCompareReport(self, request, context=None):
        """生成二次对比报告。"""
        try:
            data = _loads(getattr(request, 'data', ''), {}) or {}
            result = self.command_handler.handle_generate_secondary_compare_report(
                report_ids=data.get('report_ids', []),
                description=data.get('description'),
            )
            return self._resp(
                result.get('success', False),
                result.get('message', ''),
                result.get('data'),
            )
        except Exception as e:
            logger.exception("GenerateSecondaryCompareReport failed")
            return self._resp(False, str(e), {})

    def UpdateReportStatus(self, request, context=None):
        """更新报告状态（状态流转）。

        请求字段（proto UpdateReportStatusRequest）：
            report_id: int  报告 ID
            status: str     目标状态
        """
        try:
            command = UpdateReportStatusCommand(
                report_id=getattr(request, 'report_id'),
                status=getattr(request, 'status', None) or 'pending',
            )
            self.command_handler.handle_update_status(command)
            return self._resp(True, 'ok', {
                'report_id': command.report_id,
                'status': command.status,
            })
        except Exception as e:
            logger.exception("UpdateReportStatus failed")
            return self._resp(False, str(e), {})

    # ---- 读操作 ----

    def GetReportDetail(self, request, context=None):
        """按 ID 查询报告详情（不含子实体集合）。

        请求字段（proto GetReportDetailRequest）：
            report_id: int  报告 ID
        """
        try:
            query = GetReportQuery(
                report_id=getattr(request, 'report_id'),
            )
            aggregate = self.query_handler.handle_get(query)
            return self._resp(
                aggregate is not None,
                'ok' if aggregate is not None else 'report not found',
                _aggregate_to_dict(aggregate),
            )
        except Exception as e:
            logger.exception("GetReportDetail failed")
            return self._resp(False, str(e), None)

    def GetReportByTask(self, request, context=None):
        """按任务 ID 查询最新报告。

        请求字段（proto GetReportByTaskRequest）：
            task_id: int  任务 ID
        """
        try:
            query = GetReportByTaskQuery(
                task_id=getattr(request, 'task_id'),
            )
            aggregate = self.query_handler.handle_get_by_task(query)
            return self._resp(
                aggregate is not None,
                'ok' if aggregate is not None else 'report not found',
                _aggregate_to_dict(aggregate),
            )
        except Exception as e:
            logger.exception("GetReportByTask failed")
            return self._resp(False, str(e), None)

    def ListReports(self, request, context=None):
        """分页列出报告。

        请求字段（proto ListReportsRequest）：
            report_type: str    可选类型过滤
            status: str         可选状态过滤
            task_id: int        可选任务过滤
            algorithm_type: str 可选算法类型过滤
            page: int           页码（从 1 开始）
            per_page: int       每页数量
            search: str         可选搜索关键字
            start_date: str     可选开始日期
            end_date: str       可选结束日期
        """
        try:
            query = ListReportsQuery(
                status=getattr(request, 'status', None) or None,
                page=getattr(request, 'page', None) or 1,
                page_size=getattr(request, 'per_page', None) or 20,
            )
            aggregates: List[ReportAggregate] = self.query_handler.handle_list(query)
            return self._resp(True, 'ok', {
                'items': [_aggregate_to_dict(a) for a in aggregates],
                'page': query.page,
                'page_size': query.page_size,
            })
        except Exception as e:
            logger.exception("ListReports failed")
            return self._resp(False, str(e), {'items': []})

    # ---- 报告用例查询 / 搜索 / 导出 / 平均值 / 日志下载 ----

    def GetReportCases(self, request, context=None):
        """查询报告用例列表。

        请求字段（proto GetReportCasesRequest）：
            report_id: int   报告 ID
            data: str        JSON: 查询参数（keyword/category/tags/page/per_page 等）
        """
        try:
            report_id = getattr(request, 'report_id', 0)
            params_dict = _loads(getattr(request, 'data', ''), {}) or {}
            data = self.query_handler.handle_get_report_cases(report_id, params_dict)
            return self._resp(True, 'ok', data)
        except Exception as e:
            logger.exception("GetReportCases failed")
            return self._resp(False, str(e), {'items': []})

    def SearchReportCases(self, request, context=None):
        """搜索报告用例。

        请求字段（proto SearchReportCasesRequest）：
            report_id: int   报告 ID
            data: str        JSON: 搜索参数（keyword/category/tags/include_untagged 等）
        """
        try:
            report_id = getattr(request, 'report_id', 0)
            params_dict = _loads(getattr(request, 'data', ''), {}) or {}
            data = self.query_handler.handle_search_report_cases(report_id, params_dict)
            return self._resp(True, 'ok', data)
        except Exception as e:
            logger.exception("SearchReportCases failed")
            return self._resp(False, str(e), {'items': []})

    def ExportReports(self, request, context=None):
        """导出报告（Excel/PDF/CSV）。

        请求字段（proto ExportReportsRequest）：
            data: str  JSON: {ids: [int], format: str}
        """
        try:
            data_in = _loads(getattr(request, 'data', ''), {}) or {}
            report_ids = data_in.get('ids') or []
            format_type = data_in.get('format') or 'csv'
            data = self.query_handler.handle_export_reports(report_ids, format_type)
            if not data.get('content_base64'):
                return self._resp(False, data.get('message', 'export failed'), data)
            return self._resp(True, 'ok', data)
        except Exception as e:
            logger.exception("ExportReports failed")
            return self._resp(False, str(e), {})

    def GetCaseAverages(self, request, context=None):
        """查询用例平均值（按分组和标签）。

        请求字段（proto GetCaseAveragesRequest）：
            data: str  JSON: {task_id, category, tags, categories, include_untagged}
        """
        try:
            params_dict = _loads(getattr(request, 'data', ''), {}) or {}
            data = self.query_handler.handle_get_case_averages(params_dict)
            if data.get('success') is False:
                return self._resp(False, data.get('message', 'failed'), data)
            return self._resp(True, 'ok', data)
        except Exception as e:
            logger.exception("GetCaseAverages failed")
            return self._resp(False, str(e), {})

    def DownloadCaseLogs(self, request, context=None):
        """下载用例日志（ZIP）。

        请求字段（proto DownloadCaseLogsRequest）：
            report_id: int   报告 ID
            case_id: str     用例 ID
        """
        try:
            report_id = getattr(request, 'report_id', 0)
            case_id = getattr(request, 'case_id', '')
            data = self.query_handler.handle_download_case_logs(report_id, case_id)
            if not data.get('content_base64'):
                return self._resp(False, data.get('message', 'download failed'), data)
            return self._resp(True, 'ok', data)
        except Exception as e:
            logger.exception("DownloadCaseLogs failed")
            return self._resp(False, str(e), {})

    def BuildReferenceParams(self, request, context=None):
        """构建参考参数（供 api_gateway task_query_service 调用）。

        请求字段（proto BuildReferenceParamsRequest）：
            data: str  JSON: {case_info: dict, case_results: list, test_type: str}
        """
        try:
            params = _loads(request.data, {}) or {}
            case_info = params.get('case_info', {})
            case_results = params.get('case_results', [])
            test_type = params.get('test_type', 'api')
            ref_params = self.query_handler.handle_build_reference_params(
                case_info, case_results, test_type
            )
            return self._resp(True, 'ok', ref_params)
        except Exception as e:
            logger.exception("BuildReferenceParams failed")
            return self._resp(False, str(e), {})
