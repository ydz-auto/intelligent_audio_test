# -*- coding: utf-8 -*-
"""algorithm_service gRPC servicers.

继承 proto 生成的 servicer 基类：
- AlgorithmGroupServicer → algorithm_service_pb2_grpc.AlgorithmGroupServiceServicer
- AlgorithmDefinitionServicer → algorithm_service_pb2_grpc.AlgorithmDefinitionServiceServicer

每个 RPC 方法通过 application 层 handler 或 infrastructure 层仓储处理，
不直接 import PO 或 db.session，返回
algorithm_service_pb2.AlgorithmResponse(success/message/data)。

说明：
- AlgorithmGroupServicer: 算法分组 CRUD，委托 AlgorithmCommandHandler / AlgorithmQueryHandler
- AlgorithmDefinitionServicer: 算法定义 CRUD + 参数/映射/维度关联查询/写操作
  参数/映射/维度关系/分组/事务方法从 _param_mixin.py 继承
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from shared.proto import algorithm_service_pb2 as _pb
from shared.proto import algorithm_service_pb2_grpc as _pb_grpc
from shared.utils.grpc_base import (
    grpc_rpc_handler,
    build_response,
    parse_request_data,
)
from shared.utils.grpc_json import loads as _loads, dumps as _dumps

from algorithm_service.interfaces.grpc._param_mixin import (
    _ParamMethodsMixin,
    _success,
    _failure,
)


def _definition_to_dict(aggregate) -> Dict[str, Any]:
    """将 AlgorithmDefinitionAggregate 序列化为 dict（供 servicer 响应使用）。"""
    return {
        "id": aggregate.id,
        "group_id": aggregate.group_id,
        "name": aggregate.name,
        "algorithm_type": aggregate.algorithm_type,
        "description": aggregate.description,
        "version": aggregate.version,
        "status": str(aggregate.status) if aggregate.status else None,
    }


class AlgorithmGroupServicer(_pb_grpc.AlgorithmGroupServiceServicer):
    """算法分组 gRPC servicer。

    委托 AlgorithmCommandHandler / AlgorithmQueryHandler 完成分组 CRUD。
    """

    def __init__(self) -> None:
        # 延迟导入，避免循环依赖与启动期开销
        self._command_handler = None
        self._query_handler = None

    # ---- handler 懒加载 ----

    @property
    def command_handler(self):
        """命令处理器（写操作）"""
        if self._command_handler is None:
            from algorithm_service.application.handlers.algorithm_handlers import (
                AlgorithmCommandHandler,
            )
            self._command_handler = AlgorithmCommandHandler()
        return self._command_handler

    @property
    def query_handler(self):
        """查询处理器（读操作）"""
        if self._query_handler is None:
            from algorithm_service.application.handlers.algorithm_handlers import (
                AlgorithmQueryHandler,
            )
            self._query_handler = AlgorithmQueryHandler()
        return self._query_handler

    # ---- 分组 CRUD ----

    @grpc_rpc_handler(response_cls=_pb.AlgorithmResponse)
    def CreateAlgorithmGroup(self, request, context=None):
        """创建算法分组。

        请求字段（CreateAlgorithmGroupRequest.data JSON）：
        name / description / algorithm_type
        """
        from algorithm_service.application.commands.algorithm_commands import (
            CreateAlgorithmGroupCommand,
        )
        data = parse_request_data(request)
        cmd = CreateAlgorithmGroupCommand(
            name=data.get("name", ""),
            description=data.get("description"),
            algorithm_type=data.get("algorithm_type"),
        )
        new_id = self.command_handler.handle_create_group(cmd)
        return {"id": new_id, "name": cmd.name}

    @grpc_rpc_handler(response_cls=_pb.AlgorithmResponse)
    def UpdateAlgorithmGroup(self, request, context=None):
        """更新算法分组可变字段。

        请求字段（UpdateAlgorithmGroupRequest）：group_id / data
        """
        from algorithm_service.application.commands.algorithm_commands import (
            UpdateAlgorithmGroupCommand,
        )
        data = parse_request_data(request)
        cmd = UpdateAlgorithmGroupCommand(
            id=int(request.group_id),
            name=data.get("name", ""),
            description=data.get("description"),
        )
        self.command_handler.handle_update_group(cmd)
        return {"id": cmd.id, "updated": True}

    @grpc_rpc_handler(response_cls=_pb.AlgorithmResponse)
    def DeleteAlgorithmGroup(self, request, context=None):
        """软删除算法分组。

        请求字段（DeleteAlgorithmGroupRequest）：group_id
        """
        from algorithm_service.application.commands.algorithm_commands import (
            DeleteAlgorithmGroupCommand,
        )
        cmd = DeleteAlgorithmGroupCommand(id=int(request.group_id))
        ok = self.command_handler.handle_delete_group(cmd)
        return {"id": cmd.id, "deleted": ok}

    @grpc_rpc_handler(response_cls=_pb.AlgorithmResponse)
    def GetAlgorithmGroup(self, request, context=None):
        """按 ID 查询算法分组。

        请求字段（GetAlgorithmGroupRequest）：group_id
        """
        from algorithm_service.application.queries.algorithm_queries import (
            GetGroupQuery,
        )
        query = GetGroupQuery(group_id=request.group_id)
        result = self.query_handler.handle_get_group(query)
        if result is None:
            return build_response(
                _pb.AlgorithmResponse, success=False, message="Group not found"
            )
        return result

    @grpc_rpc_handler(response_cls=_pb.AlgorithmResponse)
    def ListAlgorithmGroups(self, request, context=None):
        """查询算法分组列表（按 display_order、id 排序）。"""
        from algorithm_service.application.queries.algorithm_queries import (
            ListGroupsQuery,
        )
        query = ListGroupsQuery()
        result = self.query_handler.handle_list_groups(query)
        return {"items": result}


class AlgorithmDefinitionServicer(_ParamMethodsMixin, _pb_grpc.AlgorithmDefinitionServiceServicer):
    """算法定义 gRPC servicer。

    算法定义 CRUD 委托 AlgorithmCommandHandler / AlgorithmQueryHandler；
    参数/映射/维度关联查询通过 AlgorithmParamCommandHandler /
    AlgorithmParamQueryHandler 处理，返回 AlgorithmResponse。

    参数/映射/维度关系/分组/事务方法从 _ParamMethodsMixin 继承。
    """

    def __init__(self) -> None:
        # 延迟导入，避免循环依赖与启动期开销
        self._command_handler = None
        self._query_handler = None
        self._param_command_handler = None
        self._param_query_handler = None

    # ---- handler 懒加载 ----

    @property
    def command_handler(self):
        """命令处理器（写操作）"""
        if self._command_handler is None:
            from algorithm_service.application.handlers.algorithm_handlers import (
                AlgorithmCommandHandler,
            )
            self._command_handler = AlgorithmCommandHandler()
        return self._command_handler

    @property
    def query_handler(self):
        """查询处理器（读操作）"""
        if self._query_handler is None:
            from algorithm_service.application.handlers.algorithm_handlers import (
                AlgorithmQueryHandler,
            )
            self._query_handler = AlgorithmQueryHandler()
        return self._query_handler

    @property
    def param_command_handler(self):
        """参数/映射/维度关联命令处理器（写操作）"""
        if self._param_command_handler is None:
            from algorithm_service.application.handlers.algorithm_param_handlers import (
                AlgorithmParamCommandHandler,
            )
            self._param_command_handler = AlgorithmParamCommandHandler()
        return self._param_command_handler

    @property
    def param_query_handler(self):
        """参数/映射/维度关联查询处理器（读操作）"""
        if self._param_query_handler is None:
            from algorithm_service.application.handlers.algorithm_param_handlers import (
                AlgorithmParamQueryHandler,
            )
            self._param_query_handler = AlgorithmParamQueryHandler()
        return self._param_query_handler

    # ---- 算法定义 CRUD ----

    @grpc_rpc_handler(response_cls=_pb.AlgorithmResponse)
    def CreateAlgorithm(self, request, context=None):
        """创建算法定义。

        请求字段（CreateAlgorithmRequest.data JSON）：
        type / name / group_id / description / status / icon / display_order
        """
        from algorithm_service.application.commands.algorithm_commands import (
            CreateAlgorithmDefinitionCommand,
        )
        data = parse_request_data(request)
        cmd = CreateAlgorithmDefinitionCommand(
            group_id=data.get("group_id"),
            name=data.get("name", ""),
            algorithm_type=data.get("algorithm_type") or data.get("type") or "",
            description=data.get("description"),
        )
        new_id = self.command_handler.handle_create_definition(cmd)
        return {"id": new_id, "name": cmd.name}

    @grpc_rpc_handler(response_cls=_pb.AlgorithmResponse)
    def UpdateAlgorithm(self, request, context=None):
        """更新算法定义可变字段。

        请求字段（UpdateAlgorithmRequest）：algorithm_id / data
        """
        from algorithm_service.application.commands.algorithm_commands import (
            UpdateAlgorithmDefinitionCommand,
        )
        data = parse_request_data(request)
        cmd = UpdateAlgorithmDefinitionCommand(
            id=int(request.algorithm_id),
            name=data.get("name", ""),
            description=data.get("description"),
        )
        self.command_handler.handle_update_definition(cmd)
        return {"id": cmd.id, "updated": True}

    @grpc_rpc_handler(response_cls=_pb.AlgorithmResponse)
    def DeleteAlgorithm(self, request, context=None):
        """软删除算法定义。

        请求字段（DeleteAlgorithmRequest）：algorithm_id
        """
        from algorithm_service.application.commands.algorithm_commands import (
            DeleteAlgorithmDefinitionCommand,
        )
        cmd = DeleteAlgorithmDefinitionCommand(id=int(request.algorithm_id))
        ok = self.command_handler.handle_delete_definition(cmd)
        return {"id": cmd.id, "deleted": ok}

    @grpc_rpc_handler(response_cls=_pb.AlgorithmResponse)
    def GetAlgorithm(self, request, context=None):
        """按 ID 查询算法定义详情。

        请求字段（GetAlgorithmRequest）：algorithm_id
        """
        from algorithm_service.application.queries.algorithm_queries import (
            GetAlgorithmDefinitionQuery,
        )
        query = GetAlgorithmDefinitionQuery(id=request.algorithm_id)
        result = self.query_handler.handle_get_definition(query)
        if result is None:
            return build_response(
                _pb.AlgorithmResponse, success=False, message="Algorithm not found"
            )
        return _definition_to_dict(result)

    @grpc_rpc_handler(response_cls=_pb.AlgorithmResponse)
    def ListAlgorithms(self, request, context=None):
        """查询算法定义列表（可按 group_id / status 过滤）。

        请求字段（ListAlgorithmsRequest）：group_id / status
        """
        from algorithm_service.application.queries.algorithm_queries import (
            ListAlgorithmDefinitionsQuery,
        )
        group_id = request.group_id or None
        status = request.status or None
        query = ListAlgorithmDefinitionsQuery(group_id=group_id, status=status)
        result = self.query_handler.handle_list_definitions(query)
        return {"items": [_definition_to_dict(d) for d in result]}

    @grpc_rpc_handler(response_cls=_pb.AlgorithmResponse)
    def GetAlgorithmOptions(self, request, context=None):
        """查询算法定义选项列表（下拉框，按 group_id 过滤）。

        请求字段（GetAlgorithmOptionsRequest）：group_id
        """
        from algorithm_service.application.queries.algorithm_queries import (
            ListAlgorithmDefinitionsQuery,
        )
        query = ListAlgorithmDefinitionsQuery(
            group_id=request.group_id or None, status="online"
        )
        result = self.query_handler.handle_list_definitions(query)
        return {
            "options": [
                {"id": d.id, "name": d.name, "type": d.algorithm_type}
                for d in result
            ]
        }
