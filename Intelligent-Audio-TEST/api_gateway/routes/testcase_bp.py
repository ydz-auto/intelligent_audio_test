from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from api_gateway.application.services.testcase.testcase_query_service import TestCaseQueryService
from api_gateway.application.services.testcase.testcase_command_service import TestCaseCommandService
from api_gateway.application.services.testcase.testcase_import_export_service import TestCaseImportExportService
from api_gateway.routes._response import to_response
from api_gateway.application.services.auth.dependencies import require_permission
from api_gateway.application.services.visibility.visibility_service import VisibilityService
from api_gateway.schemas.visibility import VisibilityUpdateRequest

router = APIRouter()

# INT-2241：批量动作 → 所需权限点。路由依赖只看得到 URL，动作在请求体里，
# 故按中间件预解析的 body（request.state._json_body）取 action 细分校验；
# body 缺失/非法时按默认 testcase:update（非法 body 仍由服务层返回 400）。
# 权限点与单资源端点对齐：delete=testcase:delete、copy 系=testcase:copy、
# 其余写动作=testcase:update。破坏性动作（delete/restore/rename_tag）按
# testcase:delete。
_BATCH_ACTION_PERMISSIONS = {
    'delete': 'testcase:delete',
    'restore': 'testcase:delete',
    'rename_tag': 'testcase:delete',
    'copy': 'testcase:copy',
    'copy_to_group': 'testcase:copy',
    'copy_by_group': 'testcase:copy',
    'copy_by_tag': 'testcase:copy',
}
_BATCH_DEFAULT_PERMISSION = 'testcase:update'


def _require_batch_action_permission(request: Request) -> None:
    """批量端点按 action 细分权限（与 require_permission 同 403 语义）。"""
    body = getattr(request.state, '_json_body', None)
    action = body.get('action') if isinstance(body, dict) else None
    required = _BATCH_ACTION_PERMISSIONS.get(action, _BATCH_DEFAULT_PERMISSION)
    user_perms = set(getattr(request.state, 'permissions', None) or [])
    if '*' in user_perms or required in user_perms:
        return
    raise HTTPException(status_code=403, detail=f'缺少权限: {required}')


@router.get('')
def get_all(_: None = require_permission('testcase:read')):
    return to_response(TestCaseQueryService.get_all())


@router.get('/stats')
def get_stats(_: None = require_permission('testcase:read')):
    return to_response(TestCaseQueryService.get_stats())


@router.get('/tags')
def get_tags(_: None = require_permission('testcase:read')):
    return to_response(TestCaseQueryService.get_tags())


# ---- 静态路径导入导出（必须早于 /{tc_id}/preview 等动态路由注册，
# 否则 POST /testcases/import/preview 会被 /{tc_id}/preview 以 tc_id=import 抢先匹配）----
@router.post('/export')
def export_cases(_: None = require_permission('testcase:import_export')):
    """导出用例：format=zip 返回数据包（manifest+testcases.json+参考参数/音频），对齐任务数据导出"""
    return to_response(TestCaseImportExportService.export_cases())


@router.post('/import')
def import_cases(_: None = require_permission('testcase:import_export')):
    """导入用例：支持 JSON/CSV/Excel/ZIP；表单 on_duplicate=skip|overwrite|copy（默认 skip）"""
    return to_response(TestCaseImportExportService.import_cases())


@router.get('/template/download')
def download_template(_: None = require_permission('testcase:import_export')):
    return to_response(TestCaseImportExportService.download_template())


@router.post('/import/preview')
def preview_import(_: None = require_permission('testcase:import_export')):
    return to_response(TestCaseImportExportService.preview_import())


@router.get('/{tc_id}')
def get_one(tc_id: str, _: None = require_permission('testcase:read')):
    return to_response(TestCaseQueryService.get_one(tc_id))

# INT-466：用例可见性切换（资源:share + owner 校验，admin 豁免）
@router.patch('/{tc_id}/visibility')
def update_visibility(tc_id: str, body: VisibilityUpdateRequest,
                      _: None = require_permission('testcase:share')):
    return to_response(VisibilityService.update_testcase_visibility(tc_id, body.visibility))


@router.post('')
def create(_: None = require_permission('testcase:create')):
    return to_response(TestCaseCommandService.create())


@router.put('/{tc_id}')
def update(tc_id: str, _: None = require_permission('testcase:update')):
    return to_response(TestCaseCommandService.update(tc_id))


@router.delete('/{tc_id}')
def delete(tc_id: str, _: None = require_permission('testcase:delete')):
    return to_response(TestCaseCommandService.delete(tc_id))


@router.post('/{tc_id}/copy')
def copy(tc_id: str, _: None = require_permission('testcase:copy')):
    return to_response(TestCaseCommandService.copy(tc_id))


@router.post('/{tc_id}/preview')
def preview(tc_id: str, _: None = require_permission('testcase:preview')):
    return to_response(TestCaseQueryService.preview(tc_id))


# 停止试听：保留下划线/连字符两条别名（历史客户端口径），统一 testcase:preview
# 权限点（与 preview 试听端点一致，INT-2241）
@router.post('/{tc_id}/stop_preview')
def stop_preview(tc_id: str, _: None = require_permission('testcase:preview')):
    return to_response(TestCaseCommandService.stop_preview(tc_id))


@router.post('/{tc_id}/stop-preview')
def stop_preview_hyphen(tc_id: str, _: None = require_permission('testcase:preview')):
    return to_response(TestCaseCommandService.stop_preview(tc_id))


# INT-2241：批量写操作按 action 细分权限（读权限不再可执行批量写）
@router.post('/batch')
def batch_action(_: None = Depends(_require_batch_action_permission)):
    return to_response(TestCaseCommandService.batch_action())


@router.post('/ids')
def fetch_case_ids(_: None = require_permission('testcase:read')):
    """按筛选条件返回全量用例ID（不分页）"""
    return to_response(TestCaseQueryService.fetch_case_ids())


@router.get('/refresh_task/{task_id}')
def get_refresh_task_status(task_id: str, _: None = require_permission('testcase:read')):
    from shared.utils.redis_pubsub import RedisStore
    data = RedisStore().load_task(f'reference_refresh:task:{task_id}')
    if not data:
        return to_response({
            'task_id': task_id,
            'status': 'not_found',
            'message': f'任务 {task_id} 不存在或已过期'
        })
    total = data.get('total', 0)
    updated = data.get('updated', 0)
    failed = data.get('failed', 0)
    progress = 0
    if isinstance(total, int) and total > 0:
        progress = int((updated + failed) / total * 100)
    return to_response({
        'task_id': data.get('task_id', task_id),
        'status': data.get('status', 'unknown'),
        'total': total,
        'updated': updated,
        'failed': failed,
        'progress': progress,
        'started_at': data.get('started_at'),
        'completed_at': data.get('completed_at'),
        'failed_cases': data.get('failed_cases', [])[:10],
        'recovered_count': data.get('recovered_count', 0),
        'error_message': data.get('error_message'),
    })


# ---- reference_params 文件读写 API ----

@router.get('/{tc_id}/rounds/{round_number}/ref-params')
def get_ref_params(tc_id: str, round_number: int, _: None = require_permission('testcase:read')):
    return to_response(TestCaseQueryService.get_ref_params(tc_id, round_number))


@router.put('/{tc_id}/rounds/{round_number}/ref-params')
def update_ref_params(tc_id: str, round_number: int, _: None = require_permission('testcase:update')):
    return to_response(TestCaseCommandService.update_ref_params(tc_id, round_number))
