import logging

from api_gateway.infrastructure.request_adapter import request
from api_gateway.utils.response import success_response, error_response
from api_gateway.utils.error_codes import ErrorCode
from api_gateway.infrastructure.grpc_proxies import task_config_service
from api_gateway.schemas.task import (
    TaskControlRequest,
    TaskMergeRequest,
    TaskStartData,
)
from api_gateway.schemas.common import TaskStatusData

logger = logging.getLogger(__name__)


class TaskLifecycleService:
    """任务生命周期 Service（CQRS Lifecycle Side）。

    按 DDD 原则，网关不再直接操作 DB，而是通过 gRPC 调用 task_service。
    保留对路由层的签名不变（静态方法 + success_response/error_response 包装）。
    """

    # 启动任务
    @staticmethod
    def start(task_id):
        result = task_config_service.start(task_id)

        if not result.get('success'):
            code = result.get('code', 500)
            if code == 404:
                return error_response("任务 ID 不存在", code=ErrorCode.NOT_FOUND, http_code=404)
            return error_response(result.get('message', '启动失败'), code=code)

        data = result.get('data') or {}
        return success_response(
            TaskStartData(
                task_id=str(data.get('task_id', task_id)),
                start_time=data.get('start_time', 0),
                status=data.get('status', 'running'),
                expected_total_time=data.get('expected_total_time'),
                expected_complete_time=data.get('expected_complete_time'),
            ),
            result.get('message', '任务已启动'),
        )

    # 重新执行失败或未完成的用例
    @staticmethod
    def retry(task_id):
        result = task_config_service.retry(task_id)

        if not result.get('success'):
            code = result.get('code', 500)
            if code == 404:
                return error_response("未找到任务", code=ErrorCode.NOT_FOUND, http_code=404)
            return error_response(result.get('message', '重试失败'), code=code)

        data = result.get('data') or {}
        return success_response(
            TaskStatusData(task_id=str(data.get('task_id', task_id)), status=data.get('status', 'running')),
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

        result = task_config_service.control(task_id, data_dict)

        if not result.get('success'):
            code = result.get('code', 500)
            if code == 404:
                return error_response("未找到任务", code=ErrorCode.NOT_FOUND, http_code=404)
            return error_response(result.get('message', '控制失败'), code=code)

        data = result.get('data') or {}
        return success_response(
            TaskStatusData(task_id=str(data.get('task_id', task_id)), status=data.get('status')),
            result.get('message', "Action executed successfully"),
        )

    # 停止正在运行的任务
    @staticmethod
    def stop(task_id):
        result = task_config_service.stop(task_id)

        if not result.get('success'):
            code = result.get('code', 500)
            if code == 404:
                return error_response("未找到任务", 404)
            return error_response(result.get('message', '停止失败'), code=code)

        return success_response(None, result.get('message', '任务已停止'))

    # 重新提取设备输出
    @staticmethod
    def reextract(task_id):
        from pydantic import BaseModel, Field

        class TaskReextractInput(BaseModel):
            task_id: int = Field(..., validation_alias='task_id')
            execution_status: str = Field('completed', validation_alias='executionStatus')
            evaluation_status: str = Field(None, validation_alias='evaluationStatus')

        try:
            req = TaskReextractInput.model_validate(request.get_json())
        except Exception as e:
            return error_response(f"数据验证失败: {str(e)}")

        data_dict = {
            'execution_status': req.execution_status,
            'evaluation_status': req.evaluation_status,
        }

        result = task_config_service.reextract(task_id, data_dict)

        if not result.get('success'):
            code = result.get('code', 500)
            if code == 404:
                return error_response("未找到任务", 404)
            return error_response(result.get('message', '重新提取失败'), code=code)

        data = result.get('data') or {}
        return success_response({
            'task_id': data.get('task_id', task_id),
            'reextracted_count': data.get('reextracted_count', 0),
            'reextracted_cases': data.get('reextracted_cases', []),
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

        result = task_config_service.merge(data_dict)

        if not result.get('success'):
            code = result.get('code', 500)
            if code == 404:
                return error_response("部分任务未找到", code=ErrorCode.NOT_FOUND)
            return error_response(result.get('message', '合并失败'), code=code)

        data = result.get('data') or {}
        return success_response(
            {"merged_task_id": data.get('merged_task_id'), "merged_task_name": data.get('merged_task_name', '')},
            result.get('message', '合并成功'),
            http_code=201,
        )
