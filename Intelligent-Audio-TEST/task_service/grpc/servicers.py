# -*- coding: utf-8 -*-
"""
task_service gRPC servicer 实现。

将 gRPC RPC 方法委托给已有业务类：
- ExecutionServiceServicer -> execution_engine / reevaluation_executor

约定：
- 复杂参数通过 JSON string 传递，方法内 json.loads 解析
- 返回结果通过 JSON string 封装到 data 字段
- 所有方法用 try/except 包裹，异常返回 success=False
"""

import json

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
            app = self.engine.scheduler_app
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
            task_id = request.task_id
            app = self.engine.scheduler_app
            success, message = self.engine.control_task(app, task_id, 'stop')
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
            app = self.engine.scheduler_app
            success, message = self.engine.control_task(app, task_id, 'pause')
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
            app = self.engine.scheduler_app
            success, message = self.engine.control_task(app, task_id, 'resume')
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
            from shared.models.database import db
            from shared.models.models import Task
            task_id = request.task_id
            app = self.engine.scheduler_app
            with app.app_context():
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
        """重新评估（任务级批量重新评估）"""
        try:
            task_id = request.task_id
            reextract_device_output = request.reextract_device_output
            reevaluate_type = request.reevaluate_type or 'all'

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

    def ReevaluateMultiRound(self, request, context=None):
        """多轮用例重新评估"""
        try:
            task_id = request.task_id
            result = _loads(request.result_json, {})
            test_case_id = request.test_case_id
            algorithm_result = _loads(request.algorithm_result, {})
            test_type = request.test_type or 'api'
            algorithm_type = request.algorithm_type or 'translation'

            from task_service.core.reevaluation_executor import ReevaluationExecutor
            executor = ReevaluationExecutor.get_instance()
            executor._reevaluate_multi_round(
                task_id=task_id,
                result=result,
                test_case_id=test_case_id,
                algorithm_result=algorithm_result,
                test_type=test_type,
                algorithm_type=algorithm_type,
            )
            return task_pb.ReevaluateMultiRoundResponse(
                success=True, message="ok",
                data=_dumps({"task_id": str(task_id), "mode": "multi_round"}),
            )
        except Exception as e:
            return task_pb.ReevaluateMultiRoundResponse(success=False, message=str(e), data="")

    def ReevaluateSingle(self, request, context=None):
        """单轮用例重新评估"""
        try:
            task_id = request.task_id
            result_id = request.result_id
            test_case_id = request.test_case_id
            algorithm_result = _loads(request.algorithm_result, {})
            reference_params = _loads(request.reference_params, {})
            test_type = request.test_type or 'api'
            algorithm_type = request.algorithm_type or 'translation'

            from task_service.core.reevaluation_executor import ReevaluationExecutor
            executor = ReevaluationExecutor.get_instance()
            executor._reevaluate_single(
                task_id=task_id,
                result_id=result_id,
                test_case_id=test_case_id,
                algorithm_result=algorithm_result,
                reference_params=reference_params,
                test_type=test_type,
                algorithm_type=algorithm_type,
            )
            return task_pb.ReevaluateSingleResponse(
                success=True, message="ok",
                data=_dumps({"task_id": str(task_id), "mode": "single"}),
            )
        except Exception as e:
            return task_pb.ReevaluateSingleResponse(success=False, message=str(e), data="")

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

    def EvaluateCase(self, request, context=None):
        """评估单个用例结果（供 e2e_test_service / api_test_service 跨服务调用）"""
        try:
            task_id = request.task_id
            result_id = request.result_id
            test_case_id = request.test_case_id
            algorithm_result = _loads(request.algorithm_result, {})
            eval_params = _loads(request.eval_params, {})

            app = self.engine.scheduler_app
            with app.app_context():
                from task_service.evaluation.evaluation_service import evaluation_service
                evaluation_service.evaluate_case(
                    task_id, result_id, test_case_id, algorithm_result,
                    **eval_params,
                )
            return task_pb.EvaluateCaseResponse(
                success=True, message="ok",
                data=_dumps({"task_id": str(task_id), "result_id": str(result_id), "evaluated": True}),
            )
        except Exception as e:
            return task_pb.EvaluateCaseResponse(success=False, message=str(e), data="")
