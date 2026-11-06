# -*- coding: utf-8 -*-
"""评估策略配置 gRPC servicer（INT-590）。

委托 task_command_handler / task_query_handler 的评估策略命令/查询。
写操作（create/update/delete）走 CQRS Command；读操作（list/get）走 CQRS Query。
"""
from shared.proto import task_service_pb2 as task_pb
from shared.proto import task_service_pb2_grpc as task_grpc
from shared.utils.grpc_json import loads as _loads, dumps as _dumps


class EvaluationStrategyServiceServicer(task_grpc.EvaluationStrategyServiceServicer):
    """评估策略 CRUD servicer，委托 CQRS Command/Query handler。"""

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
            code=int(result.get('code') or 0),
        )

    # ---- 写操作 ----

    def CreateEvaluationStrategy(self, request, context=None):
        try:
            data = _loads(request.data, {})
            from task_service.application.commands.task_commands import CreateEvaluationStrategyCommand
            return self._resp(self.cmd.handle_create_evaluation_strategy(
                CreateEvaluationStrategyCommand(data=data)
            ))
        except Exception as e:
            return task_pb.TaskConfigResponse(success=False, message=str(e), data="")

    def UpdateEvaluationStrategy(self, request, context=None):
        try:
            data = _loads(request.data, {})
            from task_service.application.commands.task_commands import UpdateEvaluationStrategyCommand
            return self._resp(self.cmd.handle_update_evaluation_strategy(
                UpdateEvaluationStrategyCommand(strategy_id=request.strategy_id, data=data)
            ))
        except Exception as e:
            return task_pb.TaskConfigResponse(success=False, message=str(e), data="")

    def DeleteEvaluationStrategy(self, request, context=None):
        try:
            from task_service.application.commands.task_commands import DeleteEvaluationStrategyCommand
            return self._resp(self.cmd.handle_delete_evaluation_strategy(
                DeleteEvaluationStrategyCommand(strategy_id=request.strategy_id)
            ))
        except Exception as e:
            return task_pb.TaskConfigResponse(success=False, message=str(e), data="")

    # ---- 读操作 ----

    def ListEvaluationStrategies(self, request, context=None):
        try:
            from task_service.application.queries.task_queries import ListEvaluationStrategiesQuery
            query = ListEvaluationStrategiesQuery(
                page=request.page or 1,
                per_page=request.per_page or 10,
                keyword=request.keyword or None,
                algorithm_type=request.algorithm_type or None,
                enabled=request.enabled or None,
            )
            return self._resp(self.qry.handle_list_evaluation_strategies(query))
        except Exception as e:
            return task_pb.TaskConfigResponse(success=False, message=str(e), data="")

    def GetEvaluationStrategy(self, request, context=None):
        try:
            from task_service.application.queries.task_queries import GetEvaluationStrategyQuery
            return self._resp(self.qry.handle_get_evaluation_strategy(
                GetEvaluationStrategyQuery(strategy_id=request.strategy_id)
            ))
        except Exception as e:
            return task_pb.TaskConfigResponse(success=False, message=str(e), data="")
