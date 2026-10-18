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
            from shared.infrastructure.user_context import user_id_from_context
            from task_service.application.queries.task_queries import ListTasksConfigQuery
            query = ListTasksConfigQuery(
                page=request.page,
                per_page=request.per_page,
                status=request.status or None,
                # 差异#2 收尾：proto ListTasksRequest.type 字段改承载 device_type 过滤值
                device_type=request.type or None,
                algorithm_type=request.algorithm_type or None,
                search=request.search or None,
                start_date=request.start_date or None,
                end_date=request.end_date or None,
                # INT-141：收藏/回收站过滤（user_id 从 x-user-id metadata 取）
                favorite=request.favorite,
                deleted=request.deleted,
                user_id=user_id_from_context(context),
                # INT-301：评估状态过滤（与执行状态并列）
                evaluation_status=request.evaluation_status or None,
                # INT-301 F1：执行状态过滤（复用派生表达式，徽章与筛选同口径）
                execution_status=request.execution_status or None,
                # INT-298：仅合并容器任务（对齐 V9.7.10 合并页签数据源）
                merged=request.merged,
                # INT-339：仅挑选合并容器任务（专有关系表存在性判定，§5.4）
                cherry_pick=getattr(request, 'cherry_pick', False),
                # INT-273：按派生任务类型过滤（api/e2e/mixed）
                task_type=getattr(request, 'task_type', '') or None,
                # INT-577：仅「挑选合并」页签计算合并容器统计块（stats=true 才执行
                # 3 次 COUNT；日常/已发布/收藏页签恒 None——审计 P2 门控全链透传）
                stats=getattr(request, 'stats', False),
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
            # INT-302：data JSON 承载按用例选择（case_ids/mode），缺省空对象整任务语义
            # （getattr 兼容旧测试替身无 data 属性）
            raw_options = getattr(request, 'data', '') or ''
            options = _loads(raw_options, {}) if raw_options else {}
            from task_service.application.commands.task_commands import RetryTaskCommand
            return self._resp(self.cmd.handle_retry_task(
                RetryTaskCommand(task_id=request.task_id, options=options)))
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

    def RemoveTaskCaseLifecycle(self, request, context=None):
        """移除任务用例（INT-305）：操作人经 x-user-id metadata 透传（命令 handler 内 get_current_user_id）"""
        try:
            from task_service.application.commands.task_commands import RemoveTaskCaseCommand
            return self._resp(self.cmd.handle_remove_task_case(
                RemoveTaskCaseCommand(task_id=request.task_id, case_id=request.case_id)
            ))
        except Exception as e:
            return task_pb.TaskConfigResponse(success=False, message=str(e), data="")

    # ---- 收藏 / 回收站（INT-141）----

    def FavoriteTask(self, request, context=None):
        try:
            from task_service.application.commands.task_commands import FavoriteEntityCommand
            return self._resp(self.cmd.handle_favorite_entity(
                FavoriteEntityCommand(entity_type=request.entity_type,
                                      entity_id=request.entity_id)))
        except Exception as e:
            return task_pb.TaskConfigResponse(success=False, message=str(e), data="")

    def UnfavoriteTask(self, request, context=None):
        try:
            from task_service.application.commands.task_commands import FavoriteEntityCommand
            return self._resp(self.cmd.handle_unfavorite_entity(
                FavoriteEntityCommand(entity_type=request.entity_type,
                                      entity_id=request.entity_id)))
        except Exception as e:
            return task_pb.TaskConfigResponse(success=False, message=str(e), data="")

    def ListFavoriteIds(self, request, context=None):
        try:
            from shared.infrastructure.user_context import user_id_from_context, normalize_user_id
            from task_service.application.queries.task_queries import ListFavoriteIdsQuery
            user_id = normalize_user_id(request.user_id) or user_id_from_context(context)
            if not user_id:
                return task_pb.TaskConfigResponse(success=False, message='未认证用户', data="")
            return self._resp(self.qry.handle_list_favorite_ids(
                ListFavoriteIdsQuery(user_id=user_id,
                                     entity_type=request.entity_type or None)))
        except Exception as e:
            return task_pb.TaskConfigResponse(success=False, message=str(e), data="")

    def ListDeletedTasks(self, request, context=None):
        try:
            from task_service.application.queries.task_queries import ListDeletedTasksQuery
            return self._resp(self.qry.handle_list_deleted_tasks(
                ListDeletedTasksQuery(page=request.page, per_page=request.per_page,
                                      search=request.search or None)))
        except Exception as e:
            return task_pb.TaskConfigResponse(success=False, message=str(e), data="")

    def RestoreTasks(self, request, context=None):
        try:
            from task_service.application.commands.task_commands import RestoreTasksCommand
            return self._resp(self.cmd.handle_restore_tasks(
                RestoreTasksCommand(task_ids=list(request.task_ids))))
        except Exception as e:
            return task_pb.TaskConfigResponse(success=False, message=str(e), data="")

    def PurgeTasks(self, request, context=None):
        try:
            from task_service.application.commands.task_commands import PurgeTasksCommand
            return self._resp(self.cmd.handle_purge_tasks(
                PurgeTasksCommand(task_ids=list(request.task_ids))))
        except Exception as e:
            return task_pb.TaskConfigResponse(success=False, message=str(e), data="")
