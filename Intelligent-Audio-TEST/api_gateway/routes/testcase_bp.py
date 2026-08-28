from fastapi import APIRouter
from fastapi.responses import JSONResponse
from api_gateway.application.services.testcase.testcase_query_service import TestCaseQueryService
from api_gateway.application.services.testcase.testcase_command_service import TestCaseCommandService
from api_gateway.application.services.testcase.testcase_import_export_service import TestCaseImportExportService
from api_gateway.routes._response import to_response
from api_gateway.application.services.auth.dependencies import require_permission

router = APIRouter()


@router.get('')
def get_all(_: None = require_permission('testcase:read')):
    return to_response(TestCaseQueryService.get_all())


@router.get('/stats')
def get_stats(_: None = require_permission('testcase:read')):
    return to_response(TestCaseQueryService.get_stats())


@router.get('/tags')
def get_tags(_: None = require_permission('testcase:read')):
    return to_response(TestCaseQueryService.get_tags())


@router.get('/{tc_id}')
def get_one(tc_id: str):
    return to_response(TestCaseQueryService.get_one(tc_id))


@router.post('')
def create():
    return to_response(TestCaseCommandService.create())


@router.put('/{tc_id}')
def update(tc_id: str, _: None = require_permission('testcase:update')):
    return to_response(TestCaseCommandService.update(tc_id))


@router.delete('/{tc_id}')
def delete(tc_id: str):
    return to_response(TestCaseCommandService.delete(tc_id))


@router.post('/{tc_id}/copy')
def copy(tc_id: str, _: None = require_permission('testcase:copy')):
    return to_response(TestCaseCommandService.copy(tc_id))


@router.post('/{tc_id}/preview')
def preview(tc_id: str, _: None = require_permission('testcase:preview')):
    return to_response(TestCaseQueryService.preview(tc_id))


@router.post('/{tc_id}/stop_preview')
def stop_preview(tc_id: str):
    return to_response(TestCaseCommandService.stop_preview(tc_id))


@router.post('/{tc_id}/stop-preview')
def stop_preview_hyphen(tc_id: str, _: None = require_permission('testcase:preview')):
    return to_response(TestCaseCommandService.stop_preview(tc_id))


@router.post('/batch')
def batch_action(_: None = require_permission('testcase:read')):
    return to_response(TestCaseCommandService.batch_action())


@router.post('/ids')
def fetch_case_ids(_: None = require_permission('testcase:read')):
    """按筛选条件返回全量用例ID（不分页）"""
    return to_response(TestCaseQueryService.fetch_case_ids())


@router.post('/export')
def export_cases():
    return to_response(TestCaseImportExportService.export_cases())


@router.post('/import')
def import_cases(_: None = require_permission('testcase:import_export')):
    return to_response(TestCaseImportExportService.import_cases())


@router.get('/template/download')
def download_template(_: None = require_permission('testcase:import_export')):
    return to_response(TestCaseImportExportService.download_template())


@router.post('/import/preview')
def preview_import(_: None = require_permission('testcase:import_export')):
    return to_response(TestCaseImportExportService.preview_import())


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
    })


# ---- reference_params 文件读写 API ----

@router.get('/{tc_id}/rounds/{round_number}/ref-params')
def get_ref_params(tc_id: str, round_number: int, _: None = require_permission('testcase:read')):
    return to_response(TestCaseQueryService.get_ref_params(tc_id, round_number))


@router.put('/{tc_id}/rounds/{round_number}/ref-params')
def update_ref_params(tc_id: str, round_number: int, _: None = require_permission('testcase:update')):
    return to_response(TestCaseCommandService.update_ref_params(tc_id, round_number))
