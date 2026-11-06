from fastapi import APIRouter
from fastapi.responses import JSONResponse
from api_gateway.application.services.execution_service import ExecutionService
from api_gateway.routes._response import to_response
from api_gateway.application.services.auth.dependencies import require_permission

router = APIRouter()


@router.post('/{task_id}/start')
def start(task_id: int, _: None = require_permission('task:execute')):
    return to_response(ExecutionService.start(task_id))


@router.post('/{task_id}/control')
def control(task_id: int, _: None = require_permission('task:execute')):
    return to_response(ExecutionService.control(task_id))
