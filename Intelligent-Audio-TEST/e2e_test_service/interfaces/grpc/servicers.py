# -*- coding: utf-8 -*-
"""e2e_test_service gRPC servicer 实现（interfaces 层）。

P2.5.7 拆分后仅保留 E2E 执行相关 servicer：
- ExecutionServiceServicer -> e2e_service（application/core 层编排）

Audio / Device / SPL 相关 servicer 已迁出至：
- audio_service/interfaces/grpc/servicers.py
- device_service/interfaces/grpc/servicers.py

约定：
- 复杂参数通过 JSON string 传递，方法内 _loads 解析
- 返回结果通过 JSON string 封装到 data 字段
- 所有方法用 try/except 包裹，异常返回 success=False
"""

from shared.proto import e2e_test_service_pb2 as e2e_pb
from shared.proto import e2e_test_service_pb2_grpc as e2e_grpc
from shared.utils.grpc_json import loads as _loads, dumps as _dumps


# ==================== ExecutionServiceServicer ====================

class ExecutionServiceServicer(e2e_grpc.ExecutionServiceServicer):
    """E2E 执行服务 gRPC servicer，委托给 e2e_service"""

    def __init__(self):
        self._e2e_service = None

    @property
    def e2e_service(self):
        if self._e2e_service is None:
            from e2e_test_service.application.services.e2e_service import e2e_service
            self._e2e_service = e2e_service
        return self._e2e_service

    def StartE2ETask(self, request, context=None):
        """启动 E2E 任务（执行单个 E2E 用例）"""
        try:
            task_id = request.task_id
            tc_rel_id = request.tc_rel_id
            result = self.e2e_service.start_e2e_case(task_id, tc_rel_id)
            return e2e_pb.StartE2ETaskResponse(
                success=result.get('success', False),
                message=result.get('message', ''),
                data=_dumps(result),
            )
        except Exception as e:
            return e2e_pb.StartE2ETaskResponse(success=False, message=str(e), data="")

    def StopE2ETask(self, request, context=None):
        """停止 E2E 任务"""
        try:
            task_id = request.task_id
            result = self.e2e_service.stop_e2e_case(task_id)
            return e2e_pb.StopE2ETaskResponse(
                success=result.get('success', False),
                message=result.get('message', ''),
                data=_dumps(result),
            )
        except Exception as e:
            return e2e_pb.StopE2ETaskResponse(success=False, message=str(e), data="")

    def GetE2ETaskStatus(self, request, context=None):
        """获取 E2E 任务状态"""
        try:
            task_id = request.task_id
            result = self.e2e_service.get_e2e_task_status(task_id)
            return e2e_pb.GetE2ETaskStatusResponse(
                success=True, message="ok", data=_dumps(result)
            )
        except Exception as e:
            return e2e_pb.GetE2ETaskStatusResponse(success=False, message=str(e), data="")


__all__ = [
    "ExecutionServiceServicer",
]
