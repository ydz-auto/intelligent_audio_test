from fastapi import APIRouter
from fastapi.responses import JSONResponse
from api_gateway.controllers.task_controller import TaskController
from api_gateway.routes._response import to_response

router = APIRouter()

@router.get('')
def get_all():
    result = TaskController.get_all()
    if isinstance(result, tuple) and len(result) == 2:
        return to_response(result)
    return result

@router.get('/{task_id}')
def get_one(task_id: int):
    result = TaskController.get_one(task_id)
    if isinstance(result, tuple) and len(result) == 2:
        return to_response(result)
    return result

@router.get('/{task_id}/cases/{case_id}/detail')
def get_case_detail(task_id: int, case_id: str):
    result = TaskController.get_case_detail(task_id, case_id)
    if isinstance(result, tuple) and len(result) == 2:
        return to_response(result)
    return result

@router.get('/{task_id}/cases/{case_id}/results')
def get_case_results(task_id: int, case_id: str):
    result = TaskController.get_case_results(task_id, case_id)
    if isinstance(result, tuple) and len(result) == 2:
        return to_response(result)
    return result

@router.get('/{task_id}/progress')
def get_progress(task_id: int):
    result = TaskController.get_progress(task_id)
    if isinstance(result, tuple) and len(result) == 2:
        return to_response(result)
    return result

@router.post('')
def create():
    result = TaskController.create()
    if isinstance(result, tuple) and len(result) == 2:
        return to_response(result)
    return result

@router.post('/{task_id}/start')
def start(task_id: int):
    result = TaskController.start(task_id)
    if isinstance(result, tuple) and len(result) == 2:
        return to_response(result)
    return result

@router.post('/{task_id}/retry')
def retry(task_id: int):
    result = TaskController.retry(task_id)
    if isinstance(result, tuple) and len(result) == 2:
        return to_response(result)
    return result

@router.post('/{task_id}/control')
def control(task_id: int):
    result = TaskController.control(task_id)
    if isinstance(result, tuple) and len(result) == 2:
        return to_response(result)
    return result

@router.patch('/{task_id}/cases')
def update_cases(task_id: int):
    result = TaskController.update_cases(task_id)
    if isinstance(result, tuple) and len(result) == 2:
        return to_response(result)
    return result

@router.get('/{task_id}/stats')
def stats(task_id: int):
    result = TaskController.stats(task_id)
    if isinstance(result, tuple) and len(result) == 2:
        return to_response(result)
    return result

@router.post('/batch-action')
def batch_action():
    result = TaskController.batch_action()
    if isinstance(result, tuple) and len(result) == 2:
        return to_response(result)
    return result

@router.post('/merge')
def merge():
    result = TaskController.merge()
    if isinstance(result, tuple) and len(result) == 2:
        return to_response(result)
    return result

@router.post('/{task_id}/stop')
def stop(task_id: int):
    result = TaskController.stop(task_id)
    if isinstance(result, tuple) and len(result) == 2:
        return to_response(result)
    return result

@router.post('/{task_id}/reextract')
def reextract(task_id: int):
    result = TaskController.reextract(task_id)
    if isinstance(result, tuple) and len(result) == 2:
        return to_response(result)
    return result

@router.delete('/{task_id}')
def delete(task_id: int):
    result = TaskController.delete(task_id)
    if isinstance(result, tuple) and len(result) == 2:
        return to_response(result)
    return result

@router.put('/{task_id}')
def update(task_id: int):
    result = TaskController.update(task_id)
    if isinstance(result, tuple) and len(result) == 2:
        return to_response(result)
    return result
