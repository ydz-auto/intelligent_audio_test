"""任务执行服务"""
from api_gateway.infrastructure.request_adapter import request
from api_gateway.infrastructure.acl import ExecutionAclRepositoryImpl, TaskConfigAclRepositoryImpl
from api_gateway.utils.response import success_response, error_response
from api_gateway.schemas.common import TaskStatusData
from api_gateway.schemas.task import TaskControlRequest
from shared.utils.status_constants import ExecutionStatus

_execution_acl = ExecutionAclRepositoryImpl()
_task_acl = TaskConfigAclRepositoryImpl()


def _check_execution_visible(detail):
    """私有任务执行/控制 owner 校验（INT-573）。

    legacy `/api/v1/execution/` 直连执行引擎路径（不经过 task_lifecycle_service），
    私有任务非 owner 在此拦截 403，防旁路绕过；共享任务回落 RBAC 既有语义。
    返回 403 (body, http_code) 或 None（放行）。
    """
    from api_gateway.application.services.visibility.visibility_audit import _request_identity
    from shared.infrastructure.visibility_filter import check_visible
    user_id, is_admin = _request_identity()
    owner = (detail or {}).get('created_by_user_id')
    vis = (detail or {}).get('visibility') or 'shared'
    try:
        check_visible(owner, vis, user_id, is_admin)
    except PermissionError as e:
        return error_response(str(e), code=403, http_code=403)
    return None


class ExecutionService:
    """任务执行服务（通过 gRPC 调用执行引擎）"""

    @staticmethod
    def start(task_id):
        # 通过 gRPC 获取任务（替代直连 task_service PO）
        result = _task_acl.get_task_detail(task_id)
        if not result.get('success') or not result.get('data'):
            return error_response("未找到任务", 404)

        # INT-573：私有任务非 owner 不可执行（legacy 直连路径防旁路）
        denied = _check_execution_visible(result.get('data'))
        if denied:
            return denied

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

        # INT-573：私有任务非 owner 不可控制（legacy 直连路径防旁路）
        result = _task_acl.get_task_detail(task_id)
        detail = result.get('data') if result.get('success') else None
        if not detail:
            return error_response("未找到任务", 404)
        denied = _check_execution_visible(detail)
        if denied:
            return denied

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
