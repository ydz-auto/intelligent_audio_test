"""报告路由 - BFF 路由层

只做 HTTP 接入 + 权限校验，委托给 application/services：
- ReportQueryService（读侧）
- ReportCommandService（写侧）
"""
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from api_gateway.routes._response import to_response
from api_gateway.application.services.auth.dependencies import require_permission
from api_gateway.application.services.report.report_query_sevice import ReportQueryService
from api_gateway.application.services.report.report_command_sevice import ReportCommandService

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


@router.get('')
def get_all(_: None = require_permission('report:read')):
    return _handle(ReportQueryService.get_all())


@router.get('/{report_id}')
def get_one(report_id: int, _: None = require_permission('report:read')):
    return _handle(ReportQueryService.get_one(report_id))


@router.delete('/{report_id}')
def delete(report_id: int, _: None = require_permission('report:delete')):
    return _handle(ReportCommandService.delete(report_id))


@router.put('/{report_id}')
def update(report_id: int, _: None = require_permission('report:update')):
    return _handle(ReportCommandService.update(report_id))


@router.post('/{report_id}/publish')
def publish(report_id: int, _: None = require_permission('report:publish')):
    return _handle(ReportCommandService.publish(report_id))


@router.post('/batch-delete')
def batch_delete(_: None = require_permission('report:delete')):
    return _handle(ReportCommandService.batch_delete())


@router.get('/{report_id}/progress')
def get_progress(report_id: int):
    raise HTTPException(status_code=404, detail="report progress 端点未实现")


@router.post('/compare')
def compare(_: None = require_permission('report:compare')):
    return _handle(ReportCommandService.compare())


@router.post('/secondary-compare')
def secondary_compare():
    return _handle(ReportCommandService.secondary_compare())


@router.post('/generate-task')
def generate_task_report(_: None = require_permission('report:create')):
    return _handle(ReportCommandService.generate_task_report())


@router.post('/export')
def export(_: None = require_permission('report:read')):
    return _handle(ReportQueryService.export())


@router.post('/case-averages')
def get_case_averages_by_filters(_: None = require_permission('report:read')):
    return _handle(ReportQueryService.get_case_averages_by_filters())


@router.get('/{report_id}/cases')
def get_report_cases(report_id: int, _: None = require_permission('report:read')):
    return _handle(ReportQueryService.get_report_cases(report_id))


@router.post('/{report_id}/cases/search')
def search_report_cases(report_id: int):
    return _handle(ReportQueryService.search_report_cases(report_id))


@router.get('/{report_id}/cases/{case_id}/logs/download')
def download_case_logs(report_id: int, case_id: str):
    return _handle(ReportQueryService.download_case_logs(report_id, case_id))
