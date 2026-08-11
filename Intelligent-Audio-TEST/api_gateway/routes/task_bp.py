from fastapi import APIRouter
from fastapi.responses import JSONResponse
from api_gateway.application.services.task.task_query_service import TaskQueryService
from api_gateway.application.services.task.task_command_service import TaskCommandService
from api_gateway.application.services.task.task_lifecycle_service import TaskLifecycleService
from api_gateway.routes._response import to_response
from api_gateway.application.services.auth.dependencies import require_permission

router = APIRouter()

@router.get('')
def get_all(_: None = require_permission('task:read')):
    result = TaskQueryService.get_all()
    if isinstance(result, tuple) and len(result) == 2:
        return to_response(result)
    return result

@router.get('/{task_id}')
def get_one(task_id: int, _: None = require_permission('task:read')):
    result = TaskQueryService.get_one(task_id)
    if isinstance(result, tuple) and len(result) == 2:
        return to_response(result)
    return result

@router.get('/{task_id}/cases/{case_id}/detail')
def get_case_detail(task_id: int, case_id: str, _: None = require_permission('task:read')):
    result = TaskQueryService.get_case_detail(task_id, case_id)
    if isinstance(result, tuple) and len(result) == 2:
        return to_response(result)
    return result

@router.get('/{task_id}/cases/{case_id}/results')
def get_case_results(task_id: int, case_id: str, _: None = require_permission('task:read')):
    result = TaskQueryService.get_case_results(task_id, case_id)
    if isinstance(result, tuple) and len(result) == 2:
        return to_response(result)
    return result

@router.get('/{task_id}/progress')
def get_progress(task_id: int, _: None = require_permission('task:read')):
    result = TaskQueryService.get_progress(task_id)
    if isinstance(result, tuple) and len(result) == 2:
        return to_response(result)
    return result

@router.post('')
def create(_: None = require_permission('task:create')):
    result = TaskCommandService.create()
    if isinstance(result, tuple) and len(result) == 2:
        return to_response(result)
    return result

@router.post('/{task_id}/start')
def start(task_id: int, _: None = require_permission('task:execute')):
    result = TaskLifecycleService.start(task_id)
    if isinstance(result, tuple) and len(result) == 2:
        return to_response(result)
    return result

@router.post('/{task_id}/retry')
def retry(task_id: int, _: None = require_permission('task:execute')):
    result = TaskLifecycleService.retry(task_id)
    if isinstance(result, tuple) and len(result) == 2:
        return to_response(result)
    return result

@router.post('/{task_id}/control')
def control(task_id: int, _: None = require_permission('task:execute')):
    result = TaskLifecycleService.control(task_id)
    if isinstance(result, tuple) and len(result) == 2:
        return to_response(result)
    return result

@router.patch('/{task_id}/cases')
def update_cases(task_id: int, _: None = require_permission('task:update')):
    result = TaskCommandService.update_cases(task_id)
    if isinstance(result, tuple) and len(result) == 2:
        return to_response(result)
    return result

@router.get('/{task_id}/stats')
def stats(task_id: int, _: None = require_permission('task:read')):
    result = TaskQueryService.stats(task_id)
    if isinstance(result, tuple) and len(result) == 2:
        return to_response(result)
    return result

@router.post('/batch-action')
def batch_action(_: None = require_permission('task:batch')):
    result = TaskCommandService.batch_action()
    if isinstance(result, tuple) and len(result) == 2:
        return to_response(result)
    return result

@router.post('/merge')
def merge(_: None = require_permission('task:merge')):
    result = TaskLifecycleService.merge()
    if isinstance(result, tuple) and len(result) == 2:
        return to_response(result)
    return result

@router.post('/{task_id}/stop')
def stop(task_id: int):
    result = TaskLifecycleService.stop(task_id)
    if isinstance(result, tuple) and len(result) == 2:
        return to_response(result)
    return result

@router.post('/{task_id}/reextract')
def reextract(task_id: int, _: None = require_permission('task:reextract')):
    result = TaskLifecycleService.reextract(task_id)
    if isinstance(result, tuple) and len(result) == 2:
        return to_response(result)
    return result

@router.delete('/{task_id}')
def delete(task_id: int, _: None = require_permission('task:delete')):
    result = TaskCommandService.delete(task_id)
    if isinstance(result, tuple) and len(result) == 2:
        return to_response(result)
    return result

@router.put('/{task_id}')
def update(task_id: int, _: None = require_permission('task:update')):
    result = TaskCommandService.update(task_id)
    if isinstance(result, tuple) and len(result) == 2:
        return to_response(result)
    return result
