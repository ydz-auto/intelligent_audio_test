from fastapi import APIRouter
from fastapi.responses import JSONResponse
from api_gateway.application.services.testcase_query_service import TestCaseQueryService
from api_gateway.application.services.testcase_command_service import TestCaseCommandService
from api_gateway.application.services.testcase_import_export_service import TestCaseImportExportService
from api_gateway.routes._response import to_response

router = APIRouter()


@router.get('')
def get_all():
    return to_response(TestCaseQueryService.get_all())


@router.get('/{tc_id}')
def get_one(tc_id: str):
    return to_response(TestCaseQueryService.get_one(tc_id))


@router.post('')
def create():
    return to_response(TestCaseCommandService.create())


@router.put('/{tc_id}')
def update(tc_id: str):
    return to_response(TestCaseCommandService.update(tc_id))


@router.delete('/{tc_id}')
def delete(tc_id: str):
    return to_response(TestCaseCommandService.delete(tc_id))


@router.post('/{tc_id}/copy')
def copy(tc_id: str):
    return to_response(TestCaseCommandService.copy(tc_id))


@router.post('/{tc_id}/preview')
def preview(tc_id: str):
    return to_response(TestCaseQueryService.preview(tc_id))


@router.post('/{tc_id}/stop_preview')
def stop_preview(tc_id: str):
    return to_response(TestCaseCommandService.stop_preview(tc_id))


@router.post('/{tc_id}/stop-preview')
def stop_preview_hyphen(tc_id: str):
    return to_response(TestCaseCommandService.stop_preview(tc_id))


@router.post('/batch')
def batch_action():
    return to_response(TestCaseCommandService.batch_action())


@router.get('/stats')
def get_stats():
    return to_response(TestCaseQueryService.get_stats())


@router.get('/tags')
def get_tags():
    return to_response(TestCaseQueryService.get_tags())


@router.post('/export')
def export_cases():
    return to_response(TestCaseImportExportService.export_cases())


@router.post('/import')
def import_cases():
    return to_response(TestCaseImportExportService.import_cases())


@router.get('/template/download')
def download_template():
    return to_response(TestCaseImportExportService.download_template())


@router.post('/import/preview')
def preview_import():
    return to_response(TestCaseImportExportService.preview_import())


@router.get('/refresh_task/{task_id}')
def get_refresh_task_status(task_id: str):
    from shared.utils.reference_refresh_task import get_reference_refresh_task_status
    return to_response(get_reference_refresh_task_status(task_id))


# ---- reference_params 文件读写 API ----

@router.get('/{tc_id}/rounds/{round_number}/ref-params')
def get_ref_params(tc_id: str, round_number: int):
    return to_response(TestCaseQueryService.get_ref_params(tc_id, round_number))


@router.put('/{tc_id}/rounds/{round_number}/ref-params')
def update_ref_params(tc_id: str, round_number: int):
    return to_response(TestCaseCommandService.update_ref_params(tc_id, round_number))
