import logging

from api_gateway.infrastructure.request_adapter import request
from api_gateway.utils.response import success_response, error_response
from api_gateway.utils.error_codes import ErrorCode
from api_gateway.infrastructure.acl import TaskConfigAclRepositoryImpl
from api_gateway.schemas.task import (
    TaskControlRequest,
    TaskMergeRequest,
    TaskStartData,
)
from api_gateway.schemas.common import TaskStatusData
from shared.utils.status_constants import TaskStatus, ExecutionStatus

logger = logging.getLogger(__name__)

_task_acl = TaskConfigAclRepositoryImpl()


def _lifecycle_http_code(result):
    """生命周期路径下游错误码 → HTTP 状态映射（INT-573）：403/404 原样透出。

    下游 task_service 命令侧已做私有任务 owner/启动人校验（非 owner 403），
    网关须把 code=403 映射为 HTTP 403，避免统一落 400（镜像 INT-564 写路径
    映射口径）。
    """
    code = result.get('code', 400)
    return code if code in (403, 404) else 400


def _audit_task_private_operation(task_id, action, result, pre_data):
    """admin 操作私有任务落 PRIVATE_RESOURCE_ACCESS 审计（INT-573，旁路）。

    pre_data 为 preload_private_state 预取的资源 data（含 visibility，仅 admin
    取数）；操作成功且为 admin 且资源 private 时由 maybe_audit_private_write
    落审计。旁路失败不影响业务结果。
    """
    if not result.get('success'):
        return
    try:
        from api_gateway.application.services.visibility.visibility_audit import (
            maybe_audit_private_write,
        )
        maybe_audit_private_write('task', task_id, action, pre_data)
    except Exception:
        pass


class TaskLifecycleService:
    """任务生命周期 Service（CQRS Lifecycle Side）。

    按 DDD 原则，网关不再直接操作 DB，而是通过 gRPC 调用 task_service。
    保留对路由层的签名不变（静态方法 + success_response/error_response 包装）。
    """

    # 启动任务
    @staticmethod
    def start(task_id):
        # INT-573：admin 操作私有任务落 PRIVATE_RESOURCE_ACCESS 审计（旁路预取，仅 admin 取数）
        from api_gateway.application.services.visibility.visibility_audit import preload_private_state
        pre_data = preload_private_state(lambda: _task_acl.get_task_detail(task_id).get('data') or {})

        result = _task_acl.start(task_id)

        if not result.get('success'):
            code = result.get('code', 500)
            if code == 404:
                return error_response("任务 ID 不存在", code=ErrorCode.NOT_FOUND, http_code=404)
            return error_response(result.get('message', '启动失败'), code=code,
                                  http_code=_lifecycle_http_code(result))

        _audit_task_private_operation(task_id, 'start', result, pre_data)

        data = result.get('data') or {}
        return success_response(
            TaskStartData(
                task_id=str(data.get('task_id', task_id)),
                start_time=data.get('start_time', 0),
                status=data.get('status', TaskStatus.RUNNING),
                expected_total_time=data.get('expected_total_time'),
                expected_complete_time=data.get('expected_complete_time'),
            ),
            result.get('message', '任务已启动'),
        )

    # 重新执行失败或未完成的用例
    @staticmethod
    def retry(task_id):
        # INT-302：可选 body {case_ids, mode} 承载按用例选择重执行；缺省整任务语义
        retry_data = None
        try:
            body = request.get_json(silent=True) or {}
        except Exception:
            body = {}
        if isinstance(body, dict) and (body.get('case_ids') or body.get('mode')):
            retry_data = {
                'case_ids': body.get('case_ids') or [],
                'mode': body.get('mode') or 'all',
            }

        # INT-573：admin 操作私有任务落 PRIVATE_RESOURCE_ACCESS 审计（旁路预取，仅 admin 取数）
        from api_gateway.application.services.visibility.visibility_audit import preload_private_state
        pre_data = preload_private_state(lambda: _task_acl.get_task_detail(task_id).get('data') or {})

        result = _task_acl.retry(task_id, retry_data)

        if not result.get('success'):
            code = result.get('code', 500)
            if code == 404:
                return error_response("未找到任务", code=ErrorCode.NOT_FOUND, http_code=404)
            return error_response(result.get('message', '重试失败'), code=code,
                                  http_code=_lifecycle_http_code(result))

        _audit_task_private_operation(task_id, 'retry', result, pre_data)

        data = result.get('data') or {}
        return success_response(
            TaskStatusData(task_id=str(data.get('task_id', task_id)), status=data.get('status', TaskStatus.RUNNING)),
            result.get('message', '重试任务已启动'),
        )

    # 任务运行时控制
    @staticmethod
    def control(task_id):
        try:
            req = TaskControlRequest.model_validate(request.get_json())
        except Exception as e:
            return error_response(f"数据验证失败: {str(e)}")

        data_dict = req.model_dump(by_alias=False, exclude_none=True)

        # INT-573：admin 操作私有任务落 PRIVATE_RESOURCE_ACCESS 审计（旁路预取，仅 admin 取数）
        from api_gateway.application.services.visibility.visibility_audit import preload_private_state
        pre_data = preload_private_state(lambda: _task_acl.get_task_detail(task_id).get('data') or {})

        result = _task_acl.control(task_id, data_dict)

        if not result.get('success'):
            code = result.get('code', 500)
            if code == 404:
                return error_response("未找到任务", code=ErrorCode.NOT_FOUND, http_code=404)
            return error_response(result.get('message', '控制失败'), code=code,
                                  http_code=_lifecycle_http_code(result))

        _audit_task_private_operation(task_id, 'control', result, pre_data)

        data = result.get('data') or {}
        return success_response(
            TaskStatusData(task_id=str(data.get('task_id', task_id)), status=data.get('status')),
            result.get('message', "Action executed successfully"),
        )

    # 停止正在运行的任务
    @staticmethod
    def stop(task_id):
        # INT-573：admin 操作私有任务落 PRIVATE_RESOURCE_ACCESS 审计（旁路预取，仅 admin 取数）
        from api_gateway.application.services.visibility.visibility_audit import preload_private_state
        pre_data = preload_private_state(lambda: _task_acl.get_task_detail(task_id).get('data') or {})

        result = _task_acl.stop(task_id)

        if not result.get('success'):
            code = result.get('code', 500)
            if code == 404:
                return error_response("未找到任务", 404)
            return error_response(result.get('message', '停止失败'), code=code,
                                  http_code=_lifecycle_http_code(result))

        _audit_task_private_operation(task_id, 'stop', result, pre_data)

        return success_response(None, result.get('message', '任务已停止'))

    # 重新提取设备输出
    @staticmethod
    def reextract(task_id):
        from pydantic import BaseModel, Field

        class TaskReextractInput(BaseModel):
            task_id: int = Field(..., validation_alias='task_id')
            execution_status: str = Field(ExecutionStatus.COMPLETED, validation_alias='executionStatus')
            evaluation_status: str = Field(None, validation_alias='evaluationStatus')

        try:
            req = TaskReextractInput.model_validate(request.get_json())
        except Exception as e:
            return error_response(f"数据验证失败: {str(e)}")

        data_dict = {
            'execution_status': req.execution_status,
            'evaluation_status': req.evaluation_status,
        }

        # INT-573：admin 操作私有任务落 PRIVATE_RESOURCE_ACCESS 审计（旁路预取，仅 admin 取数）
        from api_gateway.application.services.visibility.visibility_audit import preload_private_state
        pre_data = preload_private_state(lambda: _task_acl.get_task_detail(task_id).get('data') or {})

        result = _task_acl.reextract(task_id, data_dict)

        if not result.get('success'):
            code = result.get('code', 500)
            if code == 404:
                return error_response("未找到任务", 404)
            return error_response(result.get('message', '重新提取失败'), code=code,
                                  http_code=_lifecycle_http_code(result))

        _audit_task_private_operation(task_id, 'rextract', result, pre_data)

        data = result.get('data') or {}
        return success_response({
            'taskId': data.get('task_id', task_id),
            'reextractedCount': data.get('reextracted_count', 0),
            'reextractedCases': data.get('reextracted_cases', []),
            'message': result.get('message', '重新提取成功'),
        }, result.get('message', '重新提取成功'))

    # 合并多个已完成任务
    @staticmethod
    def merge():
        try:
            req = TaskMergeRequest.model_validate(request.get_json())
        except Exception as e:
            return error_response(f"数据验证失败: {str(e)}")

        data_dict = req.model_dump(by_alias=False, exclude_none=True)

        result = _task_acl.merge(data_dict)

        if not result.get('success'):
            code = result.get('code', 500)
            if code == 404:
                return error_response("部分任务未找到", code=ErrorCode.NOT_FOUND)
            return error_response(result.get('message', '合并失败'), code=code)

        data = result.get('data') or {}
        return success_response(
            {
                'merged_task_id': data.get('merged_task_id'),
                'merged_task_name': data.get('merged_task_name', ''),
            },
            result.get('message', '合并成功'),
            http_code=201,
        )

    # 移除任务用例（INT-305：执行详情模态窗删除用例，四阶段全允许）
    @staticmethod
    def remove_case(task_id, case_id):
        # INT-573：admin 操作私有任务落 PRIVATE_RESOURCE_ACCESS 审计（旁路预取，仅 admin 取数）
        from api_gateway.application.services.visibility.visibility_audit import preload_private_state
        pre_data = preload_private_state(lambda: _task_acl.get_task_detail(task_id).get('data') or {})

        result = _task_acl.remove_case(task_id, case_id)

        if not result.get('success'):
            code = result.get('code', 500)
            if code == 404:
                return error_response(result.get('message', '未找到任务或用例'),
                                      code=ErrorCode.NOT_FOUND, http_code=404)
            return error_response(result.get('message', '移除失败'), code=code,
                                  http_code=_lifecycle_http_code(result))

        _audit_task_private_operation(task_id, 'remove_case', result, pre_data)

        data = result.get('data') or {}
        return success_response(
            {
                'taskId': str(data.get('task_id', task_id)),
                'caseId': str(data.get('case_id', case_id)),
                # removed/idempotent 透传（INT-305 P4：幂等重复删除可与新删除区分）
                'removed': bool(data.get('removed', True)),
                'idempotent': bool(data.get('idempotent', False)),
                'purged': bool(data.get('purged', False)),
                'reportRequeued': bool(data.get('report_requeued', False)),
            },
            result.get('message', '用例已移除'),
        )
