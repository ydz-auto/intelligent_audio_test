# -*- coding: utf-8 -*-
from shared.proto import task_service_pb2 as task_pb
from shared.proto import task_service_pb2_grpc as task_grpc
from shared.utils.grpc_json import loads as _loads, dumps as _dumps


class TaskConfigServiceServicer(task_grpc.TaskConfigServiceServicer):
    """任务配置 CRUD servicer，委托给 TaskCommandHandler / TaskQueryHandler。

    写操作（create/update/delete/update_cases/batch_action/merge/生命周期）
    通过 CQRS Command 委托 task_command_handler；读操作通过 CQRS Query
    委托 task_query_handler。handler 内部过渡期仍委托旧 service。
    """

    def __init__(self):
        self._cmd = None
        self._qry = None

    @property
    def cmd(self):
        """延迟加载命令处理器（CQRS 写侧入口）。"""
        if self._cmd is None:
            from task_service.application.handlers import task_command_handler
            self._cmd = task_command_handler
        return self._cmd

    @property
    def qry(self):
        """延迟加载查询处理器（CQRS 读侧入口）。"""
        if self._qry is None:
            from task_service.application.handlers import task_query_handler
            self._qry = task_query_handler
        return self._qry

    @staticmethod
    def _resp(result):
        """统一包装返回结果为 TaskConfigResponse"""
        return task_pb.TaskConfigResponse(
            success=result.get('success', False),
            message=result.get('message', ''),
            data=_dumps(result.get('data')) if result.get('data') is not None else "",
        )

    # ---- 写操作 ----

    def CreateTaskConfig(self, request, context=None):
        try:
            data = _loads(request.data, {})
            from task_service.application.commands.task_commands import CreateTaskConfigCommand
            return self._resp(self.cmd.handle_create_task_config(CreateTaskConfigCommand(data=data)))
        except Exception as e:
            return task_pb.TaskConfigResponse(success=False, message=str(e), data="")

    def UpdateTaskConfig(self, request, context=None):
        try:
            data = _loads(request.data, {})
            from task_service.application.commands.task_commands import UpdateTaskCommand
            return self._resp(self.cmd.handle_update_task(UpdateTaskCommand(task_id=request.task_id, data=data)))
        except Exception as e:
            return task_pb.TaskConfigResponse(success=False, message=str(e), data="")

    def DeleteTaskConfig(self, request, context=None):
        try:
            from task_service.application.commands.task_commands import DeleteTaskCommand
            return self._resp(self.cmd.handle_delete_task(DeleteTaskCommand(task_id=request.task_id)))
        except Exception as e:
            return task_pb.TaskConfigResponse(success=False, message=str(e), data="")

    def UpdateTaskCases(self, request, context=None):
        try:
            data = _loads(request.data, {})
            from task_service.application.commands.task_commands import UpdateTaskCasesCommand
            return self._resp(self.cmd.handle_update_task_cases(
                UpdateTaskCasesCommand(task_id=request.task_id, data=data)
            ))
        except Exception as e:
            return task_pb.TaskConfigResponse(success=False, message=str(e), data="")

    def BatchActionTasks(self, request, context=None):
        try:
            data = _loads(request.data, {})
            from task_service.application.commands.task_commands import BatchActionTaskCommand
            return self._resp(self.cmd.handle_batch_action_task(BatchActionTaskCommand(data=data)))
        except Exception as e:
            return task_pb.TaskConfigResponse(success=False, message=str(e), data="")

    def MergeTasks(self, request, context=None):
        try:
            data = _loads(request.data, {})
            from task_service.application.commands.task_commands import MergeTasksConfigCommand
            return self._resp(self.cmd.handle_merge_tasks_config(MergeTasksConfigCommand(data=data)))
        except Exception as e:
            return task_pb.TaskConfigResponse(success=False, message=str(e), data="")

    # ---- 读操作 ----

    def ListTasks(self, request, context=None):
        try:
            from task_service.application.queries.task_queries import ListTasksConfigQuery
            query = ListTasksConfigQuery(
                page=request.page,
                per_page=request.per_page,
                status=request.status or None,
                task_type=request.type or None,
                algorithm_type=request.algorithm_type or None,
                search=request.search or None,
                start_date=request.start_date or None,
                end_date=request.end_date or None,
            )
            return self._resp(self.qry.handle_list_tasks_config(query))
        except Exception as e:
            return task_pb.TaskConfigResponse(success=False, message=str(e), data="")

    def GetTaskDetail(self, request, context=None):
        try:
            from task_service.application.queries.task_queries import GetTaskDetailQuery
            return self._resp(self.qry.handle_get_task_detail(GetTaskDetailQuery(task_id=request.task_id)))
        except Exception as e:
            return task_pb.TaskConfigResponse(success=False, message=str(e), data="")

    def GetTaskProgress(self, request, context=None):
        try:
            from task_service.application.queries.task_queries import GetTaskProgressDetailedQuery
            return self._resp(self.qry.handle_get_task_progress_detailed(
                GetTaskProgressDetailedQuery(task_id=request.task_id)
            ))
        except Exception as e:
            return task_pb.TaskConfigResponse(success=False, message=str(e), data="")

    def GetTaskStats(self, request, context=None):
        try:
            from task_service.application.queries.task_queries import GetTaskStatsQuery
            return self._resp(self.qry.handle_get_task_stats(GetTaskStatsQuery(task_id=request.task_id)))
        except Exception as e:
            return task_pb.TaskConfigResponse(success=False, message=str(e), data="")

    def GetCaseDetail(self, request, context=None):
        try:
            from task_service.application.queries.task_queries import GetCaseDetailQuery
            return self._resp(self.qry.handle_get_case_detail(
                GetCaseDetailQuery(task_id=request.task_id, case_id=request.case_id)
            ))
        except Exception as e:
            return task_pb.TaskConfigResponse(success=False, message=str(e), data="")

    def GetCaseResults(self, request, context=None):
        try:
            from task_service.application.queries.task_queries import GetCaseResultsQuery
            return self._resp(self.qry.handle_get_case_results(
                GetCaseResultsQuery(task_id=request.task_id, case_id=request.case_id)
            ))
        except Exception as e:
            return task_pb.TaskConfigResponse(success=False, message=str(e), data="")

    # ---- 生命周期操作 ----

    def StartTaskLifecycle(self, request, context=None):
        try:
            from task_service.application.commands.task_commands import StartTaskLifecycleCommand
            return self._resp(self.cmd.handle_start_task_lifecycle(
                StartTaskLifecycleCommand(task_id=request.task_id)
            ))
        except Exception as e:
            return task_pb.TaskConfigResponse(success=False, message=str(e), data="")

    def RetryTaskLifecycle(self, request, context=None):
        try:
            from task_service.application.commands.task_commands import RetryTaskCommand
            return self._resp(self.cmd.handle_retry_task(RetryTaskCommand(task_id=request.task_id)))
        except Exception as e:
            return task_pb.TaskConfigResponse(success=False, message=str(e), data="")

    def ControlTaskLifecycle(self, request, context=None):
        try:
            data = _loads(request.data, {})
            from task_service.application.commands.task_commands import ControlTaskCommand
            return self._resp(self.cmd.handle_control_task(
                ControlTaskCommand(task_id=request.task_id, data=data)
            ))
        except Exception as e:
            return task_pb.TaskConfigResponse(success=False, message=str(e), data="")

    def StopTaskLifecycle(self, request, context=None):
        try:
            from task_service.application.commands.task_commands import StopTaskLifecycleCommand
            return self._resp(self.cmd.handle_stop_task_lifecycle(
                StopTaskLifecycleCommand(task_id=request.task_id)
            ))
        except Exception as e:
            return task_pb.TaskConfigResponse(success=False, message=str(e), data="")

    def RextractTaskLifecycle(self, request, context=None):
        try:
            data = _loads(request.data, {})
            from task_service.application.commands.task_commands import RextractTaskCommand
            return self._resp(self.cmd.handle_reextract_task(
                RextractTaskCommand(task_id=request.task_id, data=data)
            ))
        except Exception as e:
            return task_pb.TaskConfigResponse(success=False, message=str(e), data="")
