from fastapi import APIRouter
from fastapi.responses import JSONResponse
from api_gateway.application.services.task.task_query_service import TaskQueryService
from api_gateway.application.services.task.task_command_service import TaskCommandService
from api_gateway.application.services.task.task_lifecycle_service import TaskLifecycleService
from api_gateway.routes._response import to_response
from api_gateway.application.services.auth.dependencies import require_permission
from api_gateway.application.services.visibility.visibility_service import VisibilityService
from api_gateway.schemas.visibility import VisibilityUpdateRequest

router = APIRouter()

@router.get('')
def get_all(_: None = require_permission('task:read')):
    result = TaskQueryService.get_all()
    if isinstance(result, tuple) and len(result) == 2:
        return to_response(result)
    return result

# INT-200：任务域全量聚合统计（须先于 /{task_id} 注册，避免 int 路径参数抢先匹配）
@router.get('/stats')
def domain_stats(_: None = require_permission('task:read')):
    return to_response(TaskQueryService.domain_stats())

# INT-540：任务资源归属校验（实验室扩展 §5.4.4）——须先于 /{task_id} 注册，
# 同 /stats 先例，否则被 int 路径参数抢先匹配 422
@router.post('/validate')
def validate_task(_: None = require_permission('task:create')):
    return to_response(TaskCommandService.validate())

# INT-540：任务关联实验室查询（实验室扩展 §5.3，多实验室 N:M）
@router.get('/{task_id}/labs')
def get_task_labs(task_id: int, _: None = require_permission('task:read')):
    result = TaskQueryService.get_task_labs(task_id)
    if isinstance(result, tuple) and len(result) == 2:
        return to_response(result)
    return result


@router.get('/{task_id}')
def get_one(task_id: int, _: None = require_permission('task:read')):
    result = TaskQueryService.get_one(task_id)
    if isinstance(result, tuple) and len(result) == 2:
        return to_response(result)
    return result

# INT-466：任务可见性切换（资源:share + owner 校验，admin 豁免）
@router.patch('/{task_id}/visibility')
def update_visibility(task_id: int, body: VisibilityUpdateRequest,
                      _: None = require_permission('task:share')):
    return to_response(VisibilityService.update_task_visibility(task_id, body.visibility))

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

# INT-305：执行详情模态窗删除用例（待执行/执行中/已完成/评估完成四阶段全允许）
@router.delete('/{task_id}/cases/{case_id}')
def remove_case(task_id: int, case_id: str, _: None = require_permission('task:execute')):
    result = TaskLifecycleService.remove_case(task_id, case_id)
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
def stop(task_id: int, _: None = require_permission('task:execute')):
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
