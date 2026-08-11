"""任务执行代理：_ExecutionEngineProxy、_EventManagerProxy 及模块级单例 execution_engine。"""
from shared.clients.grpc_clients import get_execution_service_stub

from ._common import _grpc_call


class _ExecutionEngineProxy:
    """ExecutionEngine 代理：把方法调用转发到 gRPC ExecutionService"""

    @property
    def event_manager(self):
        return _EventManagerProxy()

    def start_task(self, app, task_id):
        from shared.proto import task_service_pb2

        def _call():
            stub = get_execution_service_stub()
            resp = stub.StartTask(task_service_pb2.StartTaskRequest(task_id=str(task_id)))
            return resp.success, resp.message

        return _grpc_call(
            _call,
            default_return=lambda e: (False, f"启动任务失败: {e}"),
            error_msg_prefix="启动任务失败",
        )

    def control_task(self, app, task_id, action):
        from shared.proto import task_service_pb2

        def _call():
            stub = get_execution_service_stub()
            if action == 'stop':
                resp = stub.StopTask(task_service_pb2.StopTaskRequest(task_id=str(task_id)))
            elif action == 'pause':
                resp = stub.PauseTask(task_service_pb2.PauseTaskRequest(task_id=str(task_id)))
            elif action == 'resume':
                resp = stub.ResumeTask(task_service_pb2.ResumeTaskRequest(task_id=str(task_id)))
            else:
                return False, f"不支持的控制操作: {action}"
            return resp.success, resp.message

        return _grpc_call(
            _call,
            default_return=lambda e: (False, f"控制任务失败: {e}"),
            error_msg_prefix="控制任务失败",
        )

    def remove_from_queue(self, task_id):
        from shared.proto import task_service_pb2

        def _call():
            stub = get_execution_service_stub()
            resp = stub.RemoveFromQueue(task_service_pb2.RemoveFromQueueRequest(task_id=str(task_id)))
            return resp.success

        return _grpc_call(_call, default_return=False, error_msg_prefix="移除队列失败")


class _EventManagerProxy:
    """EventManager 代理

    calculate_time_estimate 是 shared 层的算法函数（shared.utils.event_manager），
    非跨服务调用，直接 import 使用，无需 gRPC。
    """

    def calculate_time_estimate(self, task):
        from shared.utils.event_manager import EventManager
        # calculate_time_estimate 是纯算法函数，不依赖 execution_engine 实例状态，
        # 传 None 实例化即可（该方法内只用 self._log 和 db 查询）
        return EventManager(None).calculate_time_estimate(task)


# 模块级单例，供外部直接使用（替代原 execution_engine）
execution_engine = _ExecutionEngineProxy()
