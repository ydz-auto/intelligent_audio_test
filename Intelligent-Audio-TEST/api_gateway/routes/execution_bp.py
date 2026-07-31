from fastapi import APIRouter
from fastapi.responses import JSONResponse
from api_gateway.controllers.execution_controller import ExecutionController
from api_gateway.routes._response import to_response

router = APIRouter()


@router.post('/{task_id}/start')
def start(task_id: int):
    return to_response(ExecutionController.start(task_id))


@router.post('/{task_id}/control')
def control(task_id: int):
    return to_response(ExecutionController.control(task_id))
