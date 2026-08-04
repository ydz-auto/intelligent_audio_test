"""任务执行服务"""
from api_gateway.infrastructure.request_adapter import request
from shared.models.models import Task, TaskCase
from shared.models.database import db
from shared.utils.response import success_response, error_response
from api_gateway.infrastructure.grpc_proxies import execution_engine
from api_gateway.schemas.common import TaskStatusData
from api_gateway.schemas.task import TaskControlRequest


class ExecutionService:
    """任务执行服务（通过 gRPC 调用执行引擎）"""

    @staticmethod
    def start(task_id):
        task = db.session.get(Task, task_id)
        if not task:
            return error_response("未找到任务", 404)

        cases = TaskCase.query.filter_by(task_id=task_id, execution_status='pending').all()
        if not cases:
            return error_response("该任务中没有待运行的用例")

        app = None
        success, message = execution_engine.start_task(app, task_id)

        if success:
            return success_response(None, message)
        else:
            return error_response(message)

    @staticmethod
    def control(task_id):
        req = TaskControlRequest.model_validate(request.get_json())

        action = req.action
        app = None
        success, message = execution_engine.control_task(app, task_id, action)

        if success:
            task = db.session.get(Task, task_id)
            return success_response(TaskStatusData(task_id=str(task_id), status=task.status if task else None), message)
        else:
            return error_response(message)
