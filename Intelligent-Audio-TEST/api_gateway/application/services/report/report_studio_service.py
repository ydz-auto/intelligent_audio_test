# -*- coding: utf-8 -*-
"""Report Studio BFF Service（api_gateway Application 层）

职责：参数校验 → gRPC 调用 report_service.ReportStudioService → 响应组装。
不含业务逻辑（乐观锁/权限/版本快照由 report_service 领域层强制）。
"""
import base64
import logging

from api_gateway.infrastructure.request_adapter import request
from api_gateway.utils.response import success_response, error_response
from api_gateway.infrastructure.grpc_proxies.report_studio_proxies import (
    report_studio_service,
)
from shared.proto import report_service_pb2 as report_pb
from shared.utils.grpc_json import loads as _loads, dumps as _dumps

logger = logging.getLogger(__name__)


def _parse_json_body(default=None):
    """读取请求体 JSON（FastAPI request_adapter 兼容）。"""
    try:
        body = request.get_json()
    except Exception:
        body = None
    return body if isinstance(body, dict) else (default or {})


def _call(stub_method, payload: dict):
    """统一 gRPC 调用 + 响应映射。

    Report Studio 响应带 HTTP 语义业务码（StudioResponse.code：
    404/403/409/400/500，0 = 200），网关据此还原 HTTP 状态。
    """
    resp = stub_method(report_pb.StudioDocumentRequest(data=_dumps(payload)))
    data = _loads(resp.data, {}) or {}
    if resp.success:
        return success_response(data)
    return error_response(resp.message or '操作失败', http_code=resp.code or 400, detail=data)


class ReportStudioQueryService:
    """Report Studio 读侧 BFF Service。"""

    # ------------------------------------------------------------------
    # 文档
    # ------------------------------------------------------------------

    @staticmethod
    def get_document(doc_id):
        if not doc_id:
            return error_response('缺少 doc_id', http_code=400)
        return _call(report_studio_service.stub.GetStudioDocument, {'doc_id': doc_id})

    @staticmethod
    def list_versions(doc_id):
        if not doc_id:
            return error_response('缺少 doc_id', http_code=400)
        return _call(report_studio_service.stub.ListStudioDocumentVersions,
                     {'doc_id': doc_id})

    # ------------------------------------------------------------------
    # 图表
    # ------------------------------------------------------------------

    @staticmethod
    def get_chart_data(doc_id, chart_id):
        if not doc_id or not chart_id:
            return error_response('缺少 doc_id 或 chart_id', http_code=400)
        return _call(report_studio_service.stub.GetStudioChartData,
                     {'doc_id': doc_id, 'chart_id': chart_id})

    # ------------------------------------------------------------------
    # 导出作业
    # ------------------------------------------------------------------

    @staticmethod
    def get_export_job(export_id):
        if not export_id:
            return error_response('缺少 export_id', http_code=400)
        return _call(report_studio_service.stub.GetStudioExportJob,
                     {'export_id': export_id})

    @staticmethod
    def download_export(export_id):
        if not export_id:
            return error_response('缺少 export_id', http_code=400)
        resp = report_studio_service.stub.DownloadStudioExport(
            report_pb.StudioExportJobRequest(data=_dumps({'export_id': export_id})))
        data = _loads(resp.data, {}) or {}
        if not resp.success:
            return error_response(resp.message or '下载失败', http_code=resp.code or 400, detail=data)
        if data.get('content_base64'):
            return {
                'binary': True,
                'content': base64.b64decode(data['content_base64']),
                'mime_type': data.get('mime_type', 'application/octet-stream'),
                'filename': data.get('filename', 'export'),
            }
        return success_response(data)


class ReportStudioCommandService:
    """Report Studio 写侧 BFF Service。"""

    # ------------------------------------------------------------------
    # 文档
    # ------------------------------------------------------------------

    @staticmethod
    def create_document():
        body = _parse_json_body()
        report_id = body.get('report_id')
        if not report_id:
            return error_response('缺少 report_id', http_code=400)
        payload = {
            'report_id': report_id,
            'agent_session_id': body.get('agent_session_id'),
            'title': body.get('title'),
            'markdown_content': body.get('markdown_content'),
            'chart_refs': body.get('chart_refs'),
            'style_prefs': body.get('style_prefs'),
        }
        return _call(report_studio_service.stub.CreateStudioDocument, payload)

    @staticmethod
    def update_document(doc_id):
        body = _parse_json_body()
        if not doc_id:
            return error_response('缺少 doc_id', http_code=400)
        expected_version = body.get('expected_version')
        if expected_version is None:
            return error_response('缺少 expected_version', http_code=400)
        payload = {
            'doc_id': doc_id,
            'expected_version': expected_version,
            'idempotency_key': body.get('idempotency_key'),
            'markdown_content': body.get('markdown_content'),
            'chart_refs': body.get('chart_refs'),
            'style_prefs': body.get('style_prefs'),
        }
        return _call(report_studio_service.stub.UpdateStudioDocument, payload)

    @staticmethod
    def restore_version(doc_id):
        body = _parse_json_body()
        if not doc_id:
            return error_response('缺少 doc_id', http_code=400)
        version = body.get('version')
        expected_version = body.get('expected_version')
        if version is None or expected_version is None:
            return error_response('缺少 version 或 expected_version', http_code=400)
        return _call(report_studio_service.stub.RestoreStudioDocumentVersion,
                     {'doc_id': doc_id, 'version': version, 'expected_version': expected_version})

    # ------------------------------------------------------------------
    # 导出
    # ------------------------------------------------------------------

    @staticmethod
    def create_export_job(doc_id):
        body = _parse_json_body()
        if not doc_id:
            return error_response('缺少 doc_id', http_code=400)
        version = body.get('version')
        fmt = body.get('format')
        if version is None or not fmt:
            return error_response('缺少 version 或 format', http_code=400)
        return _call(report_studio_service.stub.CreateStudioExportJob,
                     {'doc_id': doc_id, 'version': version, 'format': fmt,
                      'theme': body.get('theme')})
