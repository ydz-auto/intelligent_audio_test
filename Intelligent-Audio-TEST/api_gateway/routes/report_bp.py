from fastapi import APIRouter
from fastapi.responses import JSONResponse
from api_gateway.controllers.report_controller import ReportController
from shared.utils.log_handler import log_and_emit
from api_gateway.routes._response import to_response

router = APIRouter()

@router.get('')
def get_all():
    result = ReportController.get_all()
    if isinstance(result, tuple) and len(result) == 2:
        return to_response(result)
    return result

@router.get('/{report_id}')
def get_one(report_id: int):
    result = ReportController.get_one(report_id)
    if isinstance(result, tuple) and len(result) == 2:
        return to_response(result)
    return result

@router.delete('/{report_id}')
def delete(report_id: int):
    result = ReportController.delete(report_id)
    if isinstance(result, tuple) and len(result) == 2:
        return to_response(result)
    return result

@router.put('/{report_id}')
def update(report_id: int):
    result = ReportController.update(report_id)
    if isinstance(result, tuple) and len(result) == 2:
        return to_response(result)
    return result

@router.post('/{report_id}/publish')
def publish(report_id: int):
    result = ReportController.publish(report_id)
    if isinstance(result, tuple) and len(result) == 2:
        return to_response(result)
    return result

@router.post('/batch-delete')
def batch_delete():
    result = ReportController.batch_delete()
    if isinstance(result, tuple) and len(result) == 2:
        return to_response(result)
    return result

@router.get('/{report_id}/progress')
def get_progress(report_id: int):
    result = ReportController.get_progress(report_id)
    if isinstance(result, tuple) and len(result) == 2:
        return to_response(result)
    return result

@router.post('/compare')
def compare():
    result = ReportController.compare()
    if isinstance(result, tuple) and len(result) == 2:
        return to_response(result)
    return result

@router.post('/secondary-compare')
def secondary_compare():
    result = ReportController.secondary_compare()
    if isinstance(result, tuple) and len(result) == 2:
        return to_response(result)
    return result

@router.post('/generate-task')
def generate_task_report():
    result = ReportController.generate_task_report()
    if isinstance(result, tuple) and len(result) == 2:
        return to_response(result)
    return result

@router.post('/export')
def export():
    result = ReportController.export()
    if isinstance(result, tuple) and len(result) == 2:
        return to_response(result)
    return result

@router.post('/case-averages')
def get_case_averages_by_filters():
    result = ReportController.get_case_averages_by_filters()
    if isinstance(result, tuple) and len(result) == 2:
        return to_response(result)
    return result

@router.get('/{report_id}/cases')
def get_report_cases(report_id: int):
    result = ReportController.get_report_cases(report_id)
    if isinstance(result, tuple) and len(result) == 2:
        return to_response(result)
    return result

@router.post('/{report_id}/cases/search')
def search_report_cases(report_id: int):
    result = ReportController.search_report_cases(report_id)
    if isinstance(result, tuple) and len(result) == 2:
        return to_response(result)
    return result

@router.get('/{report_id}/cases/{case_id}/logs/download')
def download_case_logs(report_id: int, case_id: str):
    log_and_emit(
        level='INFO',
        module='report',
        content=f'收到下载日志请求 - report_id: {report_id}, case_id: {case_id}'
    )
    result = ReportController.download_case_logs(report_id, case_id)
    if isinstance(result, tuple) and len(result) == 2:
        return to_response(result)
    return result
