# -*- coding: utf-8 -*-
from shared.proto import task_service_pb2 as task_pb
from shared.proto import task_service_pb2_grpc as task_grpc
from shared.utils.grpc_json import loads as _loads, dumps as _dumps


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
            task_id = request.task_id
            success, message = self.engine.start_task(task_id)
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
            task_id = request.task_id
            success, message = self.engine.control_task(task_id, 'stop')
            return task_pb.StopTaskResponse(
                success=success,
                message=message,
                data=_dumps({"task_id": str(task_id), "stopped": success, "message": message}),
            )
        except Exception as e:
            return task_pb.StopTaskResponse(success=False, message=str(e), data="")

    def PauseTask(self, request, context=None):
        """暂停任务"""
        try:
            task_id = request.task_id
            success, message = self.engine.control_task(task_id, 'pause')
            return task_pb.PauseTaskResponse(
                success=success,
                message=message,
                data=_dumps({"task_id": str(task_id), "paused": success, "message": message}),
            )
        except Exception as e:
            return task_pb.PauseTaskResponse(success=False, message=str(e), data="")

    def ResumeTask(self, request, context=None):
        """恢复任务"""
        try:
            task_id = request.task_id
            success, message = self.engine.control_task(task_id, 'resume')
            return task_pb.ResumeTaskResponse(
                success=success,
                message=message,
                data=_dumps({"task_id": str(task_id), "resumed": success, "message": message}),
            )
        except Exception as e:
            return task_pb.ResumeTaskResponse(success=False, message=str(e), data="")

    def RemoveFromQueue(self, request, context=None):
        """从队列中移除任务"""
        try:
            task_id = request.task_id
            self.engine.remove_from_queue(task_id)
            return task_pb.RemoveFromQueueResponse(
                success=True, message="ok",
                data=_dumps({"task_id": str(task_id), "removed": True}),
            )
        except Exception as e:
            return task_pb.RemoveFromQueueResponse(success=False, message=str(e), data="")

    def GetTaskStatus(self, request, context=None):
        """获取任务状态"""
        try:
            from task_service.infrastructure.persistence.task_repository import task_repository
            task_id = request.task_id
            task = task_repository.get_task_dict_by_id(task_id)
            if not task:
                return task_pb.TaskStatusResponse(
                    success=False, message=f"任务 {task_id} 不存在", data=""
                )
            status_info = {
                "task_id": str(task_id),
                "status": task.get('status'),
                "type": task.get('type'),
                "total_cases": task.get('total_cases'),
                "completed_cases": task.get('completed_cases'),
                "failed_cases": task.get('failed_cases'),
                "started_at": task.get('started_at'),
                "completed_at": task.get('completed_at'),
                "actual_duration": task.get('actual_duration'),
                "error_message": None,
            }
            return task_pb.TaskStatusResponse(
                success=True, message="ok", data=_dumps(status_info)
            )
        except Exception as e:
            return task_pb.TaskStatusResponse(success=False, message=str(e), data="")

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

    # 注：EvaluateCase / Reevaluate / ReevaluateMultiRound / ReevaluateSingle
    # 已迁移至 evaluation_service.EvaluationService，不再在此 servicer 中实现。

    def NotifyProgress(self, request, context=None):
        """通知进度更新（evaluation_service 评估完成后调用）"""
        try:
            task_id = request.task_id
            force = request.force
            self.engine._emit_progress(task_id, force=force)
            return task_pb.NotifyProgressResponse(success=True, message="ok")
        except Exception as e:
            return task_pb.NotifyProgressResponse(success=False, message=str(e))

    def NotifyCaseCompleted(self, request, context=None):
        """通知用例已完成（唤醒等待线程）"""
        try:
            task_id = request.task_id
            self.engine.notify_case_completed(task_id)
            return task_pb.NotifyCaseCompletedResponse(success=True, message="ok")
        except Exception as e:
            return task_pb.NotifyCaseCompletedResponse(success=False, message=str(e))
