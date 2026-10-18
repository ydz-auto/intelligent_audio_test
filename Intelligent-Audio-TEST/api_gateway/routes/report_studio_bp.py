"""Report Studio 路由 - BFF 路由层（INT-673）

只做 HTTP 接入 + 权限校验，委托给 application/services：
- ReportStudioQueryService（读侧）
- ReportStudioCommandService（写侧）

契约：设计文档 §15.5，路径前缀 `/api/v1/report-studio`。
权限码：report:studio:create/edit/undo/export；读取复用 report:read。
"""
from fastapi import APIRouter
from fastapi.responses import Response
from api_gateway.routes._response import to_response
from api_gateway.application.services.auth.dependencies import require_permission
from api_gateway.application.services.report.report_studio_service import (
    ReportStudioQueryService,
    ReportStudioCommandService,
)

router = APIRouter()


def _handle(result):
    """统一响应处理：支持普通 JSON / 二进制下载 / error_response"""
    if isinstance(result, dict) and result.get('binary'):
        return Response(
            content=result['content'],
            media_type=result.get('mime_type', 'application/octet-stream'),
            headers={'Content-Disposition': f"attachment; filename=\"{result.get('filename', 'export')}\""})
    if isinstance(result, tuple) and len(result) == 2:
        return to_response(result)
    return result


# ----------------------------------------------------------------------
# 文档
# ----------------------------------------------------------------------

@router.post('/documents')
def create_document(_: None = require_permission('report:studio:create')):
    return _handle(ReportStudioCommandService.create_document())


@router.get('/documents/{doc_id}')
def get_document(doc_id: str, _: None = require_permission('report:read')):
    return _handle(ReportStudioQueryService.get_document(doc_id))


@router.put('/documents/{doc_id}')
def update_document(doc_id: str, _: None = require_permission('report:studio:edit')):
    return _handle(ReportStudioCommandService.update_document(doc_id))


@router.get('/documents/{doc_id}/versions')
def list_versions(doc_id: str, _: None = require_permission('report:read')):
    return _handle(ReportStudioQueryService.list_versions(doc_id))


@router.post('/documents/{doc_id}/restore')
def restore_version(doc_id: str, _: None = require_permission('report:studio:undo')):
    return _handle(ReportStudioCommandService.restore_version(doc_id))


@router.get('/documents/{doc_id}/charts/{chart_id}')
def get_chart_data(doc_id: str, chart_id: str, _: None = require_permission('report:read')):
    return _handle(ReportStudioQueryService.get_chart_data(doc_id, chart_id))


@router.post('/documents/{doc_id}/exports')
def create_export_job(doc_id: str, _: None = require_permission('report:studio:export')):
    return _handle(ReportStudioCommandService.create_export_job(doc_id))


# ----------------------------------------------------------------------
# 导出作业
# ----------------------------------------------------------------------

@router.get('/exports/{export_id}')
def get_export_job(export_id: str, _: None = require_permission('report:studio:export')):
    return _handle(ReportStudioQueryService.get_export_job(export_id))


@router.get('/exports/{export_id}/download')
def download_export(export_id: str, _: None = require_permission('report:studio:export')):
    return _handle(ReportStudioQueryService.download_export(export_id))
