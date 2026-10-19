"""报告路由 - BFF 路由层

只做 HTTP 接入 + 权限校验，委托给 application/services：
- ReportQueryService（读侧）
- ReportCommandService（写侧）
"""
from fastapi import APIRouter
from fastapi.responses import Response
from api_gateway.routes._response import to_response
from api_gateway.application.services.auth.dependencies import require_permission
from api_gateway.application.services.report.report_query_sevice import ReportQueryService
from api_gateway.application.services.report.report_command_sevice import ReportCommandService
from api_gateway.application.services.visibility.visibility_service import VisibilityService
from api_gateway.schemas.visibility import VisibilityUpdateRequest

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


@router.get('/tab-counts')
def tab_counts(_: None = require_permission('report:read')):
    # INT-280：HistoryReports Tab 全量计数（服务端聚合，客户端不再按当前页统计）
    return _handle(ReportQueryService.get_tab_counts())


@router.get('/export')
def export_get(_: None = require_permission('report:read')):
    return _handle(ReportQueryService.export())


@router.get('/by_task/{task_id}')
def get_by_task(task_id: int, _: None = require_permission('report:read')):
    # INT-262：网关透出按任务查报告（V9.7.10 单体能力，微服务化后丢失）
    return _handle(ReportQueryService.get_by_task(task_id))


# ---- 报告统计分析（INT-791：G04 报告统计分析页）----
# 注意：GET /statistics 必须注册在 GET /{report_id} 之前，否则被 {report_id}
# 捕获返回 422（FEAT 契约审查 INT-754 实施注意事项 #1）

@router.get('/statistics')
def get_statistics(_: None = require_permission('report:read')):
    return _handle(ReportQueryService.get_statistics())


@router.get('/statistics/trend')
def get_statistics_trend(_: None = require_permission('report:read')):
    return _handle(ReportQueryService.get_statistics_trend())


@router.post('/statistics/report')
def generate_statistics_report(_: None = require_permission('report:read')):
    return _handle(ReportQueryService.generate_statistics_report())


# ---- 报告分享公开读取（INT-971）----
# 注意：GET /shared/{token} 必须注册在 GET /{report_id} 之前（同 /statistics
# 注记先例，否则 shared 被 {report_id} int 捕获返回 422）。
# 公开路由：进 AuthMiddleware.PUBLIC_PATHS，handler 内自校验（不走 require_permission）。
@router.get('/shared/{token}')
def get_shared_report(token: str):
    return _handle(ReportQueryService.get_shared_report(token))


@router.get('/{report_id}')
def get_one(report_id: int, _: None = require_permission('report:read')):
    return _handle(ReportQueryService.get_one(report_id))

# INT-466：报告可见性切换（资源:share + owner 校验，admin 豁免）
@router.patch('/{report_id}/visibility')
def update_visibility(report_id: int, body: VisibilityUpdateRequest,
                      _: None = require_permission('report:share')):
    return _handle(VisibilityService.update_report_visibility(report_id, body.visibility))


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
def get_progress(report_id: int, _: None = require_permission('report:read')):
    return _handle(ReportQueryService.get_progress(report_id))


# ---- 报告分享管理（INT-971：生成 / 列表 / 撤销）----
@router.post('/{report_id}/share')
def create_share(report_id: int, _: None = require_permission('report:update')):
    return _handle(ReportCommandService.create_share(report_id))


@router.get('/{report_id}/share')
def list_shares(report_id: int, _: None = require_permission('report:update')):
    return _handle(ReportQueryService.list_shares(report_id))


@router.delete('/{report_id}/share/{token}')
def revoke_share(report_id: int, token: str, _: None = require_permission('report:update')):
    return _handle(ReportCommandService.revoke_share(report_id, token))


@router.post('/compare')
def compare(_: None = require_permission('report:compare')):
    return _handle(ReportCommandService.compare())


@router.post('/secondary-compare')
def secondary_compare():
    return _handle(ReportCommandService.secondary_compare())


@router.post('/generate-task')
def generate_task_report(_: None = require_permission('report:create')):
    return _handle(ReportCommandService.generate_task_report())


@router.post('/{report_id}/regenerate')
def regenerate_report(report_id: int, _: None = require_permission('report:create')):
    return _handle(ReportCommandService.regenerate_report(report_id))


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
