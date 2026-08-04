from fastapi import APIRouter
from fastapi.responses import JSONResponse
from api_gateway.application.services.execution_service import ExecutionService
from api_gateway.routes._response import to_response

router = APIRouter()


@router.post('/{task_id}/start')
def start(task_id: int):
    return to_response(ExecutionService.start(task_id))


@router.post('/{task_id}/control')
def control(task_id: int):
    return to_response(ExecutionService.control(task_id))
