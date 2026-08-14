"""任务执行服务"""
from api_gateway.infrastructure.request_adapter import request
from api_gateway.infrastructure.acl import ExecutionAclRepositoryImpl, TaskConfigAclRepositoryImpl
from api_gateway.utils.response import success_response, error_response
from api_gateway.schemas.common import TaskStatusData
from api_gateway.schemas.task import TaskControlRequest
from shared.utils.status_constants import ExecutionStatus

_execution_acl = ExecutionAclRepositoryImpl()
_task_acl = TaskConfigAclRepositoryImpl()


class ExecutionService:
    """任务执行服务（通过 gRPC 调用执行引擎）"""

    @staticmethod
    def start(task_id):
        # 通过 gRPC 获取任务（替代直连 task_service PO）
        result = _task_acl.get_task_detail(task_id)
        if not result.get('success') or not result.get('data'):
            return error_response("未找到任务", 404)

        # 通过 gRPC 获取任务用例（替代直连 task_service PO）
        detail = result.get('data') or {}
        cases = detail.get('cases', [])
        pending_cases = [c for c in cases if c.get('execution_status') == ExecutionStatus.PENDING]
        if not pending_cases:
            return error_response("该任务中没有待运行的用例")

        app = None
        exec_result = _execution_acl.start_task(app, task_id)
        success = exec_result.success
        message = exec_result.message

        if success:
            return success_response(None, message)
        else:
            return error_response(message)

    @staticmethod
    def control(task_id):
        req = TaskControlRequest.model_validate(request.get_json())

        action = req.action
        app = None
        exec_result = _execution_acl.control_task(app, task_id, action)
        success = exec_result.success
        message = exec_result.message

        if success:
            # 通过 ACL 获取任务状态
            result = _task_acl.get_task_detail(task_id)
            task_data = result.get('data') if result.get('success') else None
            status = task_data.get('status') if task_data else None
            return success_response(TaskStatusData(task_id=str(task_id), status=status), message)
        else:
            return error_response(message)
