from flask import request, current_app
from shared.models.models import Task, TaskCase
from shared.models.database import db
from shared.utils.response import success_response, error_response
# TODO: 跨服务依赖，应改为 HTTP 调用
from task_service.core.execution_engine import execution_engine
from api_gateway.schemas.common import TaskStatusData
from api_gateway.schemas.task import TaskControlRequest

class ExecutionController:
    # 开始执行任务
    @staticmethod
    def start(task_id):
        task = db.session.get(Task, task_id)
        if not task:
            return error_response("未找到任务", 404)
        
        # 检查是否有待运行的用例
        cases = TaskCase.query.filter_by(task_id=task_id, execution_status='pending').all()
        if not cases:
            return error_response("该任务中没有待运行的用例")

        # 开始异步执行
        # 需要获取应用实例以供 context 使用
        app = current_app._get_current_object()
        print(app)
        success, message = execution_engine.start_task(app, task_id)
        
        if success:
            return success_response(None, message)
        else:
            return error_response(message)

    # 控制任务状态（暂停、恢复、停止）
    @staticmethod
    def control(task_id):
        req = TaskControlRequest.model_validate(request.get_json())
        
        action = req.action
        app = current_app._get_current_object()
        success, message = execution_engine.control_task(app, task_id, action)
        
        if success:
            task = db.session.get(Task, task_id)
            return success_response(TaskStatusData(task_id=str(task_id), status=task.status if task else None), message)
        else:
            return error_response(message)
