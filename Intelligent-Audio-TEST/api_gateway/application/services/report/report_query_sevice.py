# -*- coding: utf-8 -*-
"""报告查询 Service（BFF Application 层 - CQRS Query Side）

职责：参数校验 + gRPC 调用 report_service，不含业务逻辑。
"""
import base64
import logging

from api_gateway.infrastructure.request_adapter import request
from api_gateway.utils.response import success_response, error_response
from api_gateway.schemas.report import (
    ReportListQuery,
    ReportCaseListQuery,
    ReportSearchCasesRequest,
    ReportExportRequest,
    GetCaseAveragesRequest,
    ReportExportQuery,
    ReportStatisticsQuery,
    ReportStatisticsTrendQuery,
    GenerateStatisticsReportRequest,
)
from api_gateway.infrastructure.grpc_proxies import report_config_service
from shared.models.common_enums import ReportStatus, ReportType
from shared.proto import report_service_pb2 as report_pb
from shared.utils.grpc_json import loads as _loads, dumps as _dumps

logger = logging.getLogger(__name__)


def _parse_query_params(model_cls):
    params = {k: v[0] if isinstance(v, list) else v for k, v in request.args.to_dict().items()}
    return model_cls.model_validate(params)


class ReportQueryService:
    """报告查询 BFF Service：参数校验 → gRPC 调用 → 响应组装"""

    # ------------------------------------------------------------------
    # 报告列表
    # ------------------------------------------------------------------

    @staticmethod
    def get_all():
        try:
            params = {k: v[0] if isinstance(v, list) else v
                      for k, v in request.args.to_dict().items()}
            query = ReportListQuery.model_validate(params)
        except Exception as e:
            return error_response(f'参数错误: {str(e)}', 400)

        try:
            stub = report_config_service.stub
            resp = stub.ListReports(report_pb.ListReportsRequest(
                report_type=query.report_type or '',
                status=query.status or '',
                task_id=query.task_id or 0,
                algorithm_type=query.algorithm_type or '',
                page=query.page,
                per_page=query.per_page or 20,
                search=query.keyword or '',
                start_date=query.start_time or '',
                end_date=query.end_time or '',
                # INT-141：收藏 / 回收站过滤
                favorite=getattr(query, 'favorite', False),
                deleted=getattr(query, 'deleted', False),
            ))
            if not resp.success:
                return error_response(resp.message or '查询失败')
            data = _loads(resp.data, {}) or {}
            return success_response(data)
        except Exception as e:
            return error_response(f'查询报告列表失败: {str(e)}')

    # ------------------------------------------------------------------
    # Tab 计数聚合（INT-280：HistoryReports Tab 计数服务端化）
    # ------------------------------------------------------------------

    @staticmethod
    def get_tab_counts():
        """四个视图 Tab 的全量计数（每 Tab 一次 CountReports RPC，page/per_page 忽略）。

        Tab → 过滤映射与 report_service ReportStatus/ReportType 枚举一致：
        - all:         无过滤
        - draft:       status=draft
        - published:   status=published
        - comparison:  report_type=comparison,secondary_comparison
        单 Tab 失败时该 Tab 计数 0 并降级继续（列表仍可用，计数不阻塞主视图）。
        """
        tab_filters = {
            'all': {},
            'draft': {'status': ReportStatus.DRAFT.value},
            'published': {'status': ReportStatus.PUBLISHED.value},
            'comparison': {'report_type': ','.join([
                ReportType.COMPARISON.value,
                ReportType.SECONDARY_COMPARISON.value,
            ])},
        }
        counts = {}
        try:
            stub = report_config_service.stub
            for tab, filters in tab_filters.items():
                try:
                    resp = stub.CountReports(report_pb.ListReportsRequest(**filters))
                    data = _loads(resp.data, {}) or {}
                    counts[tab] = int(data.get('total', 0)) if resp.success else 0
                except Exception:
                    logger.exception('报告 Tab 计数失败: %s', tab)
                    counts[tab] = 0
            return success_response(counts)
        except Exception as e:
            return error_response(f'查询报告 Tab 计数失败: {str(e)}')

    # ------------------------------------------------------------------
    # 报告详情
    # ------------------------------------------------------------------

    @staticmethod
    def get_one(report_id):
        try:
            stub = report_config_service.stub
            resp = stub.GetReportDetail(report_pb.GetReportDetailRequest(
                report_id=int(report_id)))
            if not resp.success:
                return error_response(resp.message or '查询失败', 404)
            data = _loads(resp.data, {}) or {}
            # INT-466：admin 访问私有报告详情落 PRIVATE_RESOURCE_ACCESS 审计（旁路）
            from api_gateway.application.services.visibility.visibility_audit import (
                maybe_audit_private_detail,
            )
            maybe_audit_private_detail('report', report_id, data)
            return success_response(data)
        except Exception as e:
            return error_response(f'查询报告失败: {str(e)}')

    @staticmethod
    def get_by_task(task_id):
        """按任务查询最新报告（INT-262：对齐 report_service 直连 /by_task 路由）。

        任务无报告时 404，与 get_one 口径一致。
        """
        try:
            stub = report_config_service.stub
            resp = stub.GetReportByTask(report_pb.GetReportByTaskRequest(
                task_id=int(task_id)))
            if not resp.success:
                return error_response(resp.message or '未找到测试报告',
                                      code=404, http_code=404)
            data = _loads(resp.data, {}) or {}
            return success_response(data)
        except Exception as e:
            return error_response(f'查询报告失败: {str(e)}')

    @staticmethod
    def get_progress(report_id):
        """报告生成进度查询（从任务/报告生成状态推导，report_service 读侧）。"""
        try:
            stub = report_config_service.stub
            resp = stub.GetReportProgress(report_pb.GetReportProgressRequest(
                report_id=int(report_id)))
            if not resp.success:
                return error_response(resp.message or '未找到测试报告', code=404, http_code=404)
            data = _loads(resp.data, {}) or {}
            return success_response(data)
        except Exception as e:
            return error_response(f'查询报告进度失败: {str(e)}')

    # ------------------------------------------------------------------
    # 报告用例列表
    # ------------------------------------------------------------------

    @staticmethod
    def get_report_cases(report_id):
        try:
            params = {k: v[0] if isinstance(v, list) else v
                      for k, v in request.args.to_dict().items()}
            query = ReportCaseListQuery.model_validate(params)
        except Exception as e:
            return error_response(f'参数错误: {str(e)}', 400)

        try:
            stub = report_config_service.stub
            resp = stub.GetReportCases(report_pb.GetReportCasesRequest(
                report_id=int(report_id),
                data=_dumps({
                    'keyword': query.keyword or '',
                    'category': query.category or '',
                    'tags': query.tags or [],
                    'page': query.page,
                    'per_page': query.per_page,
                })))
            if not resp.success:
                return error_response(resp.message or '查询失败')
            data = _loads(resp.data, {}) or {}
            return success_response(data)
        except Exception as e:
            return error_response(f'查询报告用例失败: {str(e)}')

    # ------------------------------------------------------------------
    # 搜索报告用例
    # ------------------------------------------------------------------

    @staticmethod
    def search_report_cases(report_id):
        try:
            body = request.get_json() or {}
            req = ReportSearchCasesRequest.model_validate(body)
        except Exception as e:
            return error_response(f'参数错误: {str(e)}', 400)

        try:
            stub = report_config_service.stub
            resp = stub.SearchReportCases(report_pb.SearchReportCasesRequest(
                report_id=int(report_id),
                data=_dumps({
                    'keyword': req.keyword or '',
                    'category': req.category or '',
                    'categories': req.categories or [],
                    'tags': req.tags or [],
                    'include_untagged': req.include_untagged or False,
                    'metrics': req.metrics or [],
                    'sort_by': req.sort_by or 'name',
                    'sort_metric': req.sort_metric or '',
                    'sort_resource': req.sort_resource or '',
                    'sort_order': req.sort_order or 'asc',
                    'page': req.page,
                    'per_page': req.per_page,
                })))
            if not resp.success:
                return error_response(resp.message or '搜索失败')
            data = _loads(resp.data, {}) or {}
            return success_response(data)
        except Exception as e:
            return error_response(f'搜索报告用例失败: {str(e)}')

    # ------------------------------------------------------------------
    # 导出报告
    # ------------------------------------------------------------------

    @staticmethod
    def export():
        try:
            body = request.get_json()
            if body:
                req = ReportExportRequest.model_validate(body)
                report_ids = req.ids
                format_type = req.format
            else:
                query = _parse_query_params(ReportExportQuery)
                ids_str = query.ids
                if not ids_str:
                    return error_response('缺少必要参数: ids', 400)
                report_ids = [int(rid.strip()) for rid in str(ids_str).split(',') if rid.strip()]
                if not report_ids:
                    return error_response('无效的报告 ID 列表', 400)
                format_type = query.format
        except Exception as e:
            return error_response(f'参数错误: {str(e)}', 400)

        try:
            stub = report_config_service.stub
            resp = stub.ExportReports(report_pb.ExportReportsRequest(
                data=_dumps({'ids': report_ids, 'format': format_type})))
            if not resp.success:
                return error_response(resp.message or '导出失败')
            data = _loads(resp.data, {}) or {}
            # 如果返回 base64 文件内容，返回特殊结构供路由层转换为二进制响应
            if data.get('content_base64'):
                return {
                    'binary': True,
                    'content': base64.b64decode(data['content_base64']),
                    'mime_type': data.get('mime_type', 'application/octet-stream'),
                    'filename': data.get('filename', 'export'),
                }
            return success_response(data)
        except Exception as e:
            return error_response(f'导出报告失败: {str(e)}')

    # ------------------------------------------------------------------
    # 用例平均值
    # ------------------------------------------------------------------

    @staticmethod
    def get_case_averages_by_filters():
        try:
            body = request.get_json() or {}
            req = GetCaseAveragesRequest.model_validate(body)
            if not req.task_id:
                return error_response('taskId 不能为空', 400)
        except Exception as e:
            return error_response(f'参数错误: {str(e)}', 400)

        try:
            stub = report_config_service.stub
            resp = stub.GetCaseAverages(report_pb.GetCaseAveragesRequest(
                data=_dumps({
                    'task_id': req.task_id,
                    'category': req.category or '',
                    'tags': req.tags or [],
                    'categories': req.categories or [],
                    'include_untagged': req.include_untagged or False,
                })))
            if not resp.success:
                return error_response(resp.message or '查询失败')
            data = _loads(resp.data, {}) or {}
            return success_response(data)
        except Exception as e:
            return error_response(f'获取用例平均值失败: {str(e)}')

    # ------------------------------------------------------------------
    # 报告统计分析（INT-791：/reports/statistics*，供 G04 报告统计分析页）
    # ------------------------------------------------------------------

    @staticmethod
    def get_statistics():
        try:
            params = {k: v[0] if isinstance(v, list) else v
                      for k, v in request.args.to_dict().items()}
            query = ReportStatisticsQuery.model_validate(params)
        except Exception as e:
            return error_response(f'参数错误: {str(e)}', 400)

        try:
            stub = report_config_service.stub
            resp = stub.GetStatistics(report_pb.GetStatisticsRequest(
                data=_dumps(query.model_dump(by_alias=False, exclude_none=True))))
            if not resp.success:
                return error_response(resp.message or '统计分析失败')
            data = _loads(resp.data, {}) or {}
            return success_response(data)
        except Exception as e:
            return error_response(f'统计分析失败: {str(e)}')

    @staticmethod
    def get_statistics_trend():
        try:
            params = {k: v[0] if isinstance(v, list) else v
                      for k, v in request.args.to_dict().items()}
            query = ReportStatisticsTrendQuery.model_validate(params)
        except Exception as e:
            return error_response(f'参数错误: {str(e)}', 400)

        try:
            stub = report_config_service.stub
            resp = stub.GetStatisticsTrend(report_pb.GetStatisticsTrendRequest(
                data=_dumps(query.model_dump(by_alias=False, exclude_none=True))))
            if not resp.success:
                return error_response(resp.message or '趋势分析失败')
            data = _loads(resp.data, {}) or {}
            return success_response(data)
        except Exception as e:
            return error_response(f'趋势分析失败: {str(e)}')

    @staticmethod
    def generate_statistics_report():
        try:
            body = request.get_json() or {}
            req = GenerateStatisticsReportRequest.model_validate(body)
        except Exception as e:
            return error_response(f'参数错误: {str(e)}', 400)

        try:
            stub = report_config_service.stub
            resp = stub.GenerateStatisticsReport(report_pb.GenerateStatisticsReportRequest(
                data=_dumps(req.model_dump(by_alias=False, exclude_none=True))))
            if not resp.success:
                return error_response(resp.message or '报表生成失败')
            data = _loads(resp.data, {}) or {}
            # 复用 binary 下载链路：zip_base64 → Blob 下载（对齐 export 链路）
            if data.get('content_base64'):
                return {
                    'binary': True,
                    'content': base64.b64decode(data['content_base64']),
                    'mime_type': data.get('mime_type', 'application/octet-stream'),
                    'filename': data.get('filename', 'statistics_report'),
                }
            return success_response(data)
        except Exception as e:
            return error_response(f'报表生成失败: {str(e)}')

    # ------------------------------------------------------------------
    # 下载用例日志
    # ------------------------------------------------------------------

    @staticmethod
    def download_case_logs(report_id, case_id):
        if not case_id:
            return error_response('case_id 不能为空', 400)

        try:
            stub = report_config_service.stub
            resp = stub.DownloadCaseLogs(report_pb.DownloadCaseLogsRequest(
                report_id=int(report_id),
                case_id=str(case_id)))
            if not resp.success:
                return error_response(resp.message or '下载失败')
            data = _loads(resp.data, {}) or {}
            if data.get('content_base64'):
                return {
                    'binary': True,
                    'content': base64.b64decode(data['content_base64']),
                    'mime_type': data.get('mime_type', 'application/octet-stream'),
                    'filename': data.get('filename', 'logs.zip'),
                }
            return success_response(data)
        except Exception as e:
            return error_response(f'下载用例日志失败: {str(e)}')
