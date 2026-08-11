# -*- coding: utf-8 -*-
"""报告命令 Service（BFF Application 层 - CQRS Command Side）

职责：参数校验 + gRPC 调用 report_service，不含业务逻辑。
"""
import logging

from api_gateway.infrastructure.request_adapter import request
from api_gateway.utils.response import success_response, error_response
from api_gateway.schemas.report import (
    ReportUpdateRequest,
    GenerateTaskReportRequest,
    CompareReportsRequest,
    SecondaryCompareRequest,
)
from shared.clients.grpc_clients import get_report_config_service_stub
from shared.proto import report_service_pb2 as report_pb
from shared.utils.grpc_json import loads as _loads, dumps as _dumps

logger = logging.getLogger(__name__)


class ReportCommandService:
    """报告命令 BFF Service：参数校验 → gRPC 调用 → 响应组装"""

    # ------------------------------------------------------------------
    # 删除报告
    # ------------------------------------------------------------------

    @staticmethod
    def delete(report_id):
        try:
            stub = get_report_config_service_stub()
            resp = stub.DeleteReport(report_pb.DeleteReportRequest(
                report_id=int(report_id)))
            if not resp.success:
                return error_response(resp.message or '删除失败')
            data = _loads(resp.data, {}) or {}
            return success_response(data)
        except Exception as e:
            return error_response(f'删除报告失败: {str(e)}')

    # ------------------------------------------------------------------
    # 更新报告
    # ------------------------------------------------------------------

    @staticmethod
    def update(report_id):
        try:
            body = request.get_json() or {}
            req = ReportUpdateRequest.model_validate(body)
        except Exception as e:
            return error_response(f'参数错误: {str(e)}', 400)

        try:
            stub = get_report_config_service_stub()
            resp = stub.UpdateReport(report_pb.UpdateReportRequest(
                report_id=int(report_id),
                data=_dumps(req.model_dump(by_alias=True, exclude_none=True))))
            if not resp.success:
                return error_response(resp.message or '更新失败')
            data = _loads(resp.data, {}) or {}
            return success_response(data)
        except Exception as e:
            return error_response(f'更新报告失败: {str(e)}')

    # ------------------------------------------------------------------
    # 发布报告
    # ------------------------------------------------------------------

    @staticmethod
    def publish(report_id):
        try:
            stub = get_report_config_service_stub()
            resp = stub.UpdateReportStatus(report_pb.UpdateReportStatusRequest(
                report_id=int(report_id),
                status='published'))
            if not resp.success:
                return error_response(resp.message or '发布失败')
            data = _loads(resp.data, {}) or {}
            return success_response(data)
        except Exception as e:
            return error_response(f'发布报告失败: {str(e)}')

    # ------------------------------------------------------------------
    # 批量删除
    # ------------------------------------------------------------------

    @staticmethod
    def batch_delete():
        try:
            body = request.get_json() or {}
            ids = body.get('ids', [])
            if not ids or not isinstance(ids, list):
                return error_response('ids 列表不能为空', 400)
        except Exception as e:
            return error_response(f'参数错误: {str(e)}', 400)

        try:
            stub = get_report_config_service_stub()
            resp = stub.BatchActionReports(report_pb.BatchActionReportsRequest(
                data=_dumps({
                    'ids': [int(i) for i in ids],
                    'action': 'delete',
                    'hard_delete': bool(body.get('hard_delete', False)),
                })))
            if not resp.success:
                return error_response(resp.message or '批量删除失败')
            data = _loads(resp.data, {}) or {}
            return success_response(data)
        except Exception as e:
            return error_response(f'批量删除报告失败: {str(e)}')

    # ------------------------------------------------------------------
    # 对比报告
    # ------------------------------------------------------------------

    @staticmethod
    def compare():
        try:
            body = request.get_json() or {}
            req = CompareReportsRequest.model_validate(body)
            if not req.task_ids:
                return error_response('taskIds 不能为空', 400)
        except Exception as e:
            return error_response(f'参数错误: {str(e)}', 400)

        try:
            stub = get_report_config_service_stub()
            resp = stub.GenerateCompareReport(report_pb.GenerateCompareReportRequest(
                data=_dumps({
                    'task_ids': req.task_ids,
                    'name': req.name or '',
                    'description': req.description or '',
                })))
            if not resp.success:
                return error_response(resp.message or '生成对比报告失败')
            data = _loads(resp.data, {}) or {}
            return success_response(data)
        except Exception as e:
            return error_response(f'生成对比报告失败: {str(e)}')

    # ------------------------------------------------------------------
    # 二次对比报告
    # ------------------------------------------------------------------

    @staticmethod
    def secondary_compare():
        try:
            body = request.get_json() or {}
            req = SecondaryCompareRequest.model_validate(body)
            if not req.report_ids:
                return error_response('reportIds 不能为空', 400)
        except Exception as e:
            return error_response(f'参数错误: {str(e)}', 400)

        try:
            stub = get_report_config_service_stub()
            resp = stub.GenerateSecondaryCompareReport(report_pb.GenerateSecondaryCompareReportRequest(
                data=_dumps({
                    'report_ids': req.report_ids,
                    'description': req.description or '',
                })))
            if not resp.success:
                return error_response(resp.message or '生成二次对比报告失败')
            data = _loads(resp.data, {}) or {}
            return success_response(data)
        except Exception as e:
            return error_response(f'生成二次对比报告失败: {str(e)}')

    # ------------------------------------------------------------------
    # 生成任务报告
    # ------------------------------------------------------------------

    @staticmethod
    def generate_task_report():
        try:
            body = request.get_json() or {}
            req = GenerateTaskReportRequest.model_validate(body)
            if not req.task_id:
                return error_response('taskId 不能为空', 400)
        except Exception as e:
            return error_response(f'参数错误: {str(e)}', 400)

        try:
            stub = get_report_config_service_stub()
            resp = stub.GenerateTaskReport(report_pb.GenerateTaskReportRequest(
                task_id=int(req.task_id),
                name=req.name or '',
                description=req.description or ''))
            if not resp.success:
                return error_response(resp.message or '生成任务报告失败')
            data = _loads(resp.data, {}) or {}
            return success_response(data)
        except Exception as e:
            return error_response(f'生成任务报告失败: {str(e)}')
