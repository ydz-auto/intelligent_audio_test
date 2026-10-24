"""Report Studio 路由 - BFF 路由层（INT-673）

只做 HTTP 接入 + 权限校验，委托给 application/services：
- ReportStudioQueryService（读侧）
- ReportStudioCommandService（写侧）

契约：设计文档 §15.5，路径前缀 `/api/v1/report-studio`。
权限码：report:studio:create/edit/undo/export；读取复用 report:read。
"""
from fastapi import APIRouter, Form, UploadFile
from fastapi.responses import Response
from api_gateway.routes._response import to_response, content_disposition
from api_gateway.application.services.auth.dependencies import require_permission
from api_gateway.application.services.report.report_studio_service import (
    ReportStudioQueryService,
    ReportStudioCommandService,
)

router = APIRouter()


def _handle(result):
    """统一响应处理：支持普通 JSON / 二进制下载 / error_response"""
    if isinstance(result, dict) and result.get('binary'):
        headers = {
            'Content-Disposition':
                content_disposition(result.get('filename', 'export'))}
        # 调用方可覆盖（上传件下载带 nosniff / 沙箱 CSP，D0 A11-3）
        headers.update(result.get('headers') or {})
        return Response(
            content=result['content'],
            media_type=result.get('mime_type', 'application/octet-stream'),
            headers=headers)
    if isinstance(result, tuple) and len(result) == 2:
        return to_response(result)
    return result


# ----------------------------------------------------------------------
# 文档
# ----------------------------------------------------------------------

@router.post('/documents')
def create_document(_: None = require_permission('report:studio:create')):
    return _handle(ReportStudioCommandService.create_document())


@router.get('/documents')
def list_documents(report_id: int = None, source_type: str = None,
                   parent_doc_id: str = None, limit: int = None, offset: int = None,
                   _: None = require_permission('report:read')):
    """文档列表（INT-1763 §6.4）。

    过滤条件显式传入：平台报告详情页文档列表带 ``source_type=platform_report``
    （与迁移前一致，不混入导入文档）；独立文档库带 ``source_type=uploaded_file``；
    ``parent_doc_id`` 反查 Agent 总结子文档。
    """
    return _handle(ReportStudioQueryService.list_documents({
        'report_id': report_id, 'source_type': source_type,
        'parent_doc_id': parent_doc_id, 'limit': limit, 'offset': offset,
    }))


@router.post('/import')
def import_document(file: UploadFile, title: str = Form(None),
                    task_id: str = Form(None), format: str = Form(None),
                    _: None = require_permission('report:studio:create')):
    """文件型独立报告导入（3b，设计文档 §6.2 / D0 A11）。

    multipart：file（md/html/pptx）+ title + 可选 task_id + format。
    白名单不符 415、超限 413、上传件下载带沙箱 CSP。
    """
    return _handle(ReportStudioCommandService.import_document(
        file, title=title, task_id=task_id, fmt=format))


@router.get('/documents/{doc_id}')
def get_document(doc_id: str, _: None = require_permission('report:read')):
    return _handle(ReportStudioQueryService.get_document(doc_id))


@router.put('/documents/{doc_id}')
def update_document(doc_id: str, _: None = require_permission('report:studio:edit')):
    return _handle(ReportStudioCommandService.update_document(doc_id))


@router.get('/documents/{doc_id}/versions')
def list_versions(doc_id: str, _: None = require_permission('report:read')):
    return _handle(ReportStudioQueryService.list_versions(doc_id))


@router.get('/documents/{doc_id}/source')
def download_source(doc_id: str, _: None = require_permission('report:read')):
    """上传件（html/pptx）下载/预览：附件语义 + nosniff + 沙箱 CSP（D0 A11-3）。"""
    return _handle(ReportStudioQueryService.download_source(doc_id))


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
