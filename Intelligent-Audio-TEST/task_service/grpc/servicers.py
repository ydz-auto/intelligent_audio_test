# -*- coding: utf-8 -*-
"""
task_service gRPC servicer 实现。

将 gRPC RPC 方法委托给已有业务类：
- ExecutionServiceServicer -> execution_engine

约定：
- 复杂参数通过 JSON string 传递，方法内 json.loads 解析
- 返回结果通过 JSON string 封装到 data 字段
- 所有方法用 try/except 包裹，异常返回 success=False
"""

import json

from shared.proto import task_service_pb2 as task_pb
from shared.proto import task_service_pb2_grpc as task_grpc


def _loads(s, default):
    """安全 JSON 解析，空字符串返回默认值"""
    if not s:
        return default
    if isinstance(s, bytes):
        s = s.decode('utf-8')
    return json.loads(s)


def _dumps(obj):
    """JSON 序列化，None/不可序列化对象返回空字符串"""
    try:
        return json.dumps(obj, ensure_ascii=False, default=str)
    except Exception:
        return ""


class ExecutionServiceServicer(task_grpc.ExecutionServiceServicer):
    """执行引擎服务 gRPC servicer，委托给 execution_engine"""

    def __init__(self):
        self._engine = None

    @property
    def engine(self):
        if self._engine is None:
            from task_service.core.execution_engine import execution_engine
            self._engine = execution_engine
        return self._engine

    def CreateTask(self, request, context=None):
        """创建任务

        execution_engine 本身没有独立的 create_task 方法（任务在 start_task 中按需创建），
        此处保留为占位接口，返回引擎信息。
        """
        try:
            task_id = request.task_id
            task_config = _loads(request.task_config, {})
            result = {
                "task_id": str(task_id),
                "created": True,
                "task_type": task_config.get('type'),
            }
            return task_pb.CreateTaskResponse(success=True, message="ok", data=_dumps(result))
        except Exception as e:
            return task_pb.CreateTaskResponse(success=False, message=str(e), data="")

    def StartTask(self, request, context=None):
        """启动任务"""
        try:
            from flask import current_app
            task_id = request.task_id
            app = current_app._get_current_object()
            success, message = self.engine.start_task(app, task_id)
            return task_pb.StartTaskResponse(
                success=success,
                message=message,
                data=_dumps({"task_id": str(task_id), "started": success, "message": message}),
            )
        except Exception as e:
            return task_pb.StartTaskResponse(success=False, message=str(e), data="")

    def StopTask(self, request, context=None):
        """停止任务"""
        try:
            from flask import current_app
            task_id = request.task_id
            app = current_app._get_current_object()
            success, message = self.engine.control_task(app, task_id, 'stop')
            return task_pb.StopTaskResponse(
                success=success,
                message=message,
                data=_dumps({"task_id": str(task_id), "stopped": success, "message": message}),
            )
        except Exception as e:
            return task_pb.StopTaskResponse(success=False, message=str(e), data="")

    def GetTaskStatus(self, request, context=None):
        """获取任务状态"""
        try:
            from shared.models.database import db
            from shared.models.models import Task
            task_id = request.task_id
            local_db_session = db.session()
            try:
                task = local_db_session.query(Task).get(task_id)
                if not task:
                    return task_pb.TaskStatusResponse(
                        success=False, message=f"任务 {task_id} 不存在", data=""
                    )
                status_info = {
                    "task_id": str(task_id),
                    "status": task.status,
                    "type": task.type,
                    "total_cases": task.total_cases,
                    "completed_cases": task.completed_cases,
                    "failed_cases": task.failed_cases,
                    "started_at": str(task.started_at) if task.started_at else None,
                    "completed_at": str(task.completed_at) if task.completed_at else None,
                    "actual_duration": task.actual_duration,
                    "error_message": task.error_message,
                }
                return task_pb.TaskStatusResponse(
                    success=True, message="ok", data=_dumps(status_info)
                )
            finally:
                local_db_session.close()
        except Exception as e:
            return task_pb.TaskStatusResponse(success=False, message=str(e), data="")

    def Reevaluate(self, request, context=None):
        """重新评估"""
        try:
            reevaluate_config = _loads(request.reevaluate_config, {})
            task_id = request.task_id
            reextract_device_output = reevaluate_config.get('reextract_device_output', True)
            reevaluate_type = reevaluate_config.get('reevaluate_type', 'all')

            from task_service.core.reevaluation_executor import ReevaluationExecutor
            executor = ReevaluationExecutor.get_instance()
            success, message = executor.submit(
                task_id,
                reextract_device_output=reextract_device_output,
                reevaluate_type=reevaluate_type,
            )
            return task_pb.ReevaluateResponse(
                success=success,
                message=message,
                data=_dumps({
                    "task_id": str(task_id),
                    "submitted": success,
                    "message": message,
                }),
            )
        except Exception as e:
            return task_pb.ReevaluateResponse(success=False, message=str(e), data="")

    def GetEngineInfo(self, request, context=None):
        """获取执行引擎实例信息（如线程池状态）"""
        try:
            engine = self.engine
            info = {
                "running_tasks": list(engine.running_tasks.keys()) if hasattr(engine, 'running_tasks') else [],
                "running_e2e": getattr(engine, 'running_e2e', False),
                "running_apis": list(getattr(engine, 'running_apis', set())),
                "queue_size": len(engine.task_queue) if hasattr(engine, 'task_queue') else 0,
                "workers_count": len(engine.workers) if hasattr(engine, 'workers') else 0,
                "api_executors_count": len(engine.api_executors) if hasattr(engine, 'api_executors') else 0,
                "task_completion_events_count": len(engine.task_completion_events) if hasattr(engine, 'task_completion_events') else 0,
            }
            return task_pb.EngineInfoResponse(
                success=True, message="ok", data=_dumps(info)
            )
        except Exception as e:
            return task_pb.EngineInfoResponse(success=False, message=str(e), data="")
