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
)
from api_gateway.infrastructure.grpc_proxies import report_config_service
from shared.proto import report_service_pb2 as report_pb
from shared.utils.grpc_json import loads as _loads, dumps as _dumps

logger = logging.getLogger(__name__)


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
                algorithm_type=query.algorithm_type or '',
                page=query.page,
                per_page=query.per_page or 20,
                search=query.keyword or '',
                start_date=query.start_time or '',
                end_date=query.end_time or '',
            ))
            if not resp.success:
                return error_response(resp.message or '查询失败')
            data = _loads(resp.data, {}) or {}
            return success_response(data)
        except Exception as e:
            return error_response(f'查询报告列表失败: {str(e)}')

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
            return success_response(data)
        except Exception as e:
            return error_response(f'查询报告失败: {str(e)}')

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
                    'tags': req.tags or [],
                    'include_untagged': req.include_untagged or False,
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
                ids_str = request.args.get('ids', '')
                if not ids_str:
                    return error_response('缺少必要参数: ids', 400)
                report_ids = [int(rid.strip()) for rid in str(ids_str).split(',') if rid.strip()]
                if not report_ids:
                    return error_response('无效的报告 ID 列表', 400)
                format_type = request.args.get('format', 'csv')
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
