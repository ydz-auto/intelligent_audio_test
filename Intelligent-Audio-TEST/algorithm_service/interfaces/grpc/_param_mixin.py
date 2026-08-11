# -*- coding: utf-8 -*-
"""AlgorithmDefinitionServicer 的参数/映射/维度关系/分组/事务方法 mixin。

从 servicers.py 拆分，减少主文件体积。本 mixin 提供 AlgorithmDefinitionServicer
的参数 CRUD、映射 CRUD、维度关联 CRUD、算法分组 CRUD、算法定义写操作、
评估维度参数管理、参数映射同步、事务控制等方法。

使用方式：AlgorithmDefinitionServicer(AlgorithmDefinitionServiceServicer, _ParamMethodsMixin)
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from shared.proto import algorithm_service_pb2 as _pb
from shared.utils.grpc_json import loads as _loads, dumps as _dumps


def _success(data: Any = None, message: str = "ok"):
    """构造成功响应（AlgorithmResponse）。"""
    return _pb.AlgorithmResponse(
        success=True,
        message=message,
        data=_dumps(data) if data is not None else "",
    )


def _failure(message: str, data: Any = None):
    """构造失败响应（AlgorithmResponse）。"""
    return _pb.AlgorithmResponse(
        success=False,
        message=message,
        data=_dumps(data) if data is not None else "",
    )


class _ParamMethodsMixin:
    """参数/映射/维度关系/分组/事务方法 mixin。

    被 AlgorithmDefinitionServicer 继承，提供以下方法组：
    - 参数查询（device/api/case/reference）
    - 映射查询
    - 维度关系 CRUD + 批量管理
    - 导入/重载
    - 评估维度参数管理
    - 参数映射同步
    - 设备/API/用例/参考参数写操作
    - 参数映射写操作
    - 算法定义写操作
    - 算法分组写操作
    - 维度关联写操作
    - 事务控制
    """

    # ---- 参数查询（device / api / case / reference）----

    def ListParams(self, request, context=None):
        """查询参数列表（设备参数 / API 参数）。"""
        try:
            from algorithm_service.application.queries.algorithm_param_queries import (
                ListParamsQuery,
            )
            query = ListParamsQuery(
                algorithm_type=request.algorithm_type or None,
                param_type=request.param_type or None,
            )
            result = self.param_query_handler.handle_list_params(query)
            return _success({"parameters": result, "total": len(result)})
        except Exception as e:
            return _failure(str(e))

    def GetParam(self, request, context=None):
        """按 ID 获取参数详情（设备参数或 API 参数）。"""
        try:
            from algorithm_service.application.queries.algorithm_param_queries import (
                GetParamQuery,
            )
            query = GetParamQuery(param_id=request.param_id, param_type_source="device")
            result = self.param_query_handler.handle_get_param(query)
            if result is None:
                query = GetParamQuery(param_id=request.param_id, param_type_source="api")
                result = self.param_query_handler.handle_get_param(query)
            if result is None:
                return _failure("Parameter not found")
            return _success(result)
        except Exception as e:
            return _failure(str(e))

    def ListCaseParams(self, request, context=None):
        """查询用例专属参数列表。"""
        try:
            from algorithm_service.application.queries.algorithm_param_queries import (
                ListCaseParamsQuery,
            )
            query = ListCaseParamsQuery(
                algorithm_type=request.algorithm_type or None,
            )
            result = self.param_query_handler.handle_list_case_params(query)
            return _success({"parameters": result, "total": len(result)})
        except Exception as e:
            return _failure(str(e))

    def ListReferenceParams(self, request, context=None):
        """查询参考参数列表。"""
        try:
            from algorithm_service.application.queries.algorithm_param_queries import (
                ListReferenceParamsQuery,
            )
            query = ListReferenceParamsQuery(
                algorithm_type=request.algorithm_type or None,
            )
            result = self.param_query_handler.handle_list_reference_params(query)
            return _success({"parameters": result, "total": len(result)})
        except Exception as e:
            return _failure(str(e))

    # ---- 映射查询 ----

    def ListMappings(self, request, context=None):
        """查询参数映射列表。"""
        try:
            from algorithm_service.application.queries.algorithm_param_queries import (
                ListMappingsQuery,
            )
            query = ListMappingsQuery(
                algorithm_type=request.algorithm_type or None,
            )
            result = self.param_query_handler.handle_list_mappings(query)
            return _success({"mappings": result, "total": len(result)})
        except Exception as e:
            return _failure(str(e))

    def GetDimensionParams(self, request, context=None):
        """查询评估维度的参数列表（含 output/input 完整字段）。"""
        try:
            from algorithm_service.infrastructure.persistence.algorithm_repository import (
                dimension_param_repository,
            )
            params = dimension_param_repository.list_with_code_name(
                int(request.dimension_id)
            )
            return _success({"params": params})
        except Exception as e:
            return _failure(str(e))

    def GetAlgorithmDimensions(self, request, context=None):
        """查询算法关联的评估维度。"""
        try:
            from algorithm_service.application.queries.algorithm_param_queries import (
                ListDimensionRelationsQuery,
            )
            query = ListDimensionRelationsQuery(algorithm_type=request.algorithm_type)
            relations = self.param_query_handler.handle_list_dimension_relations(query)
            dimension_ids = [r.get("dimension_id") for r in relations]
            default_relation = next((r for r in relations if r.get("is_default")), None)
            weights_map = {r.get("dimension_id"): r.get("weight") for r in relations}
            is_default_map = {r.get("dimension_id"): r.get("is_default") for r in relations}
            return _success({
                "dimensions": [
                    {
                        "id": r.get("dimension_id"),
                        "weight": weights_map.get(r.get("dimension_id"), 1.0),
                        "is_default": is_default_map.get(r.get("dimension_id"), False),
                    }
                    for r in relations
                ],
                "dimension_ids": dimension_ids,
                "default_dimension_id": default_relation.get("dimension_id") if default_relation else None,
                "weights": weights_map,
            })
        except Exception as e:
            return _failure(str(e))

    # ---- 维度关系 CRUD ----

    def CreateDimensionRelation(self, request, context=None):
        """创建算法-维度关联。"""
        try:
            from algorithm_service.application.commands.algorithm_param_commands import (
                CreateDimensionRelationCommand,
            )
            data = _loads(request.data, {}) if not isinstance(request, dict) else request
            cmd = CreateDimensionRelationCommand(data=data)
            result = self.param_command_handler.handle_create_dimension_relation(cmd)
            return _success({"id": result.get("id"), "created": True})
        except Exception as e:
            return _failure(str(e))

    def UpdateDimensionRelation(self, request, context=None):
        """更新算法-维度关联。"""
        try:
            from algorithm_service.application.commands.algorithm_param_commands import (
                UpdateDimensionRelationAttrsCommand,
            )
            data = _loads(request.data, {}) if not isinstance(request, dict) else request
            cmd = UpdateDimensionRelationAttrsCommand(
                relation_id=request.relation_id,
                data=data,
            )
            self.param_command_handler.handle_update_dimension_relation_attrs(cmd)
            return _success({"id": request.relation_id, "updated": True})
        except Exception as e:
            return _failure(str(e))

    def DeleteDimensionRelation(self, request, context=None):
        """删除算法-维度关联（软删除）。"""
        try:
            from algorithm_service.application.commands.algorithm_param_commands import (
                DeleteDimensionRelationCommand,
            )
            cmd = DeleteDimensionRelationCommand(relation_id=request.relation_id)
            result = self.param_command_handler.handle_delete_dimension_relation(cmd)
            return _success({"id": request.relation_id, "deleted": result})
        except Exception as e:
            return _failure(str(e))

    # ---- 导入/重载 ----

    def ImportAlgorithms(self, request, context=None):
        """导入算法定义（批量）。"""
        try:
            data = _loads(request.data, {}) if not isinstance(request, dict) else request
            return _failure("ImportAlgorithms 暂未实现", {"received_keys": list(data.keys())})
        except Exception as e:
            return _failure(str(e))

    def ReloadAlgorithmConfig(self, request, context=None):
        """重新加载算法配置（热更新）。"""
        try:
            from algorithm_service.infrastructure.persistence.config_cache import get_config_cache
            cache = get_config_cache()
            reloaded = cache.reload()
            return _success({
                "success": True,
                "message": f"Config reloaded: {reloaded}",
                "reload_time": cache.get_last_reload_time(),
            })
        except Exception as e:
            return _failure(str(e))

    # ---- 维度关系批量管理 ----

    def DeleteRelationsByDimension(self, request, context=None):
        """按 dimension_id 物理删除所有算法-维度关联。"""
        try:
            from algorithm_service.infrastructure.persistence.algorithm_repository import (
                dimension_relation_query_repository,
            )
            dimension_relation_query_repository.delete_by_dimension(
                int(request.dimension_id)
            )
            return _success({"dimension_id": int(request.dimension_id), "deleted": True})
        except Exception as e:
            return _failure(str(e))

    def GetRelationsByDimension(self, request, context=None):
        """按 dimension_id 查询未删除的算法-维度关联列表。"""
        try:
            from algorithm_service.infrastructure.persistence.algorithm_repository import (
                dimension_relation_query_repository,
            )
            result = dimension_relation_query_repository.list_by_dimension(
                int(request.dimension_id)
            )
            return _success({"relations": result})
        except Exception as e:
            return _failure(str(e))

    def SyncDimensionRelations(self, request, context=None):
        """按 dimension_id 同步算法-维度关联。"""
        try:
            from algorithm_service.infrastructure.persistence.algorithm_repository import (
                dimension_relation_query_repository,
            )
            data = _loads(request.data, []) if not isinstance(request, dict) else request
            dimension_id = int(request.dimension_id)
            dimension_relation_query_repository.sync_by_dimension(dimension_id, data)
            return _success({"dimension_id": dimension_id, "synced": True})
        except Exception as e:
            return _failure(str(e))

    # ---- 评估维度参数管理 ----

    def CreateDimensionParam(self, request, context=None):
        """创建单条评估维度参数。"""
        try:
            from algorithm_service.infrastructure.persistence.algorithm_repository import (
                dimension_param_repository,
            )
            data = _loads(request.data, {}) if not isinstance(request, dict) else request
            result = dimension_param_repository.create(data)
            return _success({"id": result.get("id"), "created": True})
        except Exception as e:
            return _failure(str(e))

    def DeleteDimensionParamsByDirection(self, request, context=None):
        """按 dimension_id + param_direction 物理删除评估维度参数。"""
        try:
            from algorithm_service.infrastructure.persistence.algorithm_repository import (
                dimension_param_repository,
            )
            dimension_param_repository.delete_by_dimension_and_direction(
                int(request.dimension_id), request.param_direction
            )
            return _success({
                "dimension_id": int(request.dimension_id),
                "param_direction": request.param_direction,
                "deleted": True,
            })
        except Exception as e:
            return _failure(str(e))

    def FindAudioDimensionIds(self, request, context=None):
        """查询需要音频文件参数的维度 ID 集合。"""
        try:
            from algorithm_service.infrastructure.persistence.algorithm_repository import (
                dimension_param_repository,
            )
            dim_ids = _loads(request.dimension_ids, []) if not isinstance(request, dict) else request
            if not dim_ids:
                return _success({"audio_dimension_ids": []})
            result = dimension_param_repository.find_audio_dimension_ids(dim_ids)
            return _success({"audio_dimension_ids": result})
        except Exception as e:
            return _failure(str(e))

    # ---- 参数映射同步 ----

    def ListParamMappingsForDimension(self, request, context=None):
        """查询某维度所有 ParamMapping（含软删除项）。"""
        try:
            from algorithm_service.infrastructure.persistence.algorithm_repository import (
                param_mapping_query_repository,
            )
            result = param_mapping_query_repository.list_for_dimension(
                int(request.dimension_id)
            )
            return _success({"mappings": result})
        except Exception as e:
            return _failure(str(e))

    def SyncParamMappings(self, request, context=None):
        """同步 ParamMapping。"""
        try:
            from algorithm_service.infrastructure.persistence.algorithm_repository import (
                param_mapping_query_repository,
            )
            dimension_id = int(request.dimension_id)
            data = _loads(request.data, {}) if not isinstance(request, dict) else request
            params = data.get("params", [])
            direction = data.get("direction", "output")
            algorithm_type = data.get("algorithm_type", "voice_llm")

            if params is None:
                return _success({"dimension_id": dimension_id, "synced": True})

            import json as _json
            if isinstance(params, str):
                try:
                    params = _json.loads(params)
                except _json.JSONDecodeError:
                    params = []
            if not isinstance(params, list):
                params = []

            param_mapping_query_repository.sync_for_dimension(
                dimension_id, params, direction, algorithm_type
            )
            return _success({"dimension_id": dimension_id, "synced": True})
        except Exception as e:
            return _failure(str(e))

    # ---- 设备/API 参数写操作 ----

    def CreateParam(self, request, context=None):
        """创建设备参数或 API 参数。"""
        try:
            from algorithm_service.application.commands.algorithm_param_commands import (
                CreateParamCommand,
            )
            data = _loads(request.data, {}) if not isinstance(request, dict) else request
            cmd = CreateParamCommand(
                data=data,
                param_type_source=data.get("param_type_source") or "device",
            )
            result = self.param_command_handler.handle_create_param(cmd)
            return _success(result)
        except Exception as e:
            return _failure(str(e))

    def UpdateParam(self, request, context=None):
        """更新设备参数或 API 参数。"""
        try:
            from algorithm_service.application.commands.algorithm_param_commands import (
                UpdateParamCommand,
            )
            data = _loads(request.data, {}) if not isinstance(request, dict) else request
            cmd = UpdateParamCommand(
                param_id=request.param_id,
                data=data,
                param_type_source="",
            )
            result = self.param_command_handler.handle_update_param(cmd)
            return _success(result)
        except Exception as e:
            return _failure(str(e))

    def DeleteParam(self, request, context=None):
        """软删除设备参数或 API 参数。"""
        try:
            from algorithm_service.application.commands.algorithm_param_commands import (
                DeleteParamCommand,
            )
            cmd = DeleteParamCommand(
                param_id=request.param_id,
                param_type_source="",
            )
            result = self.param_command_handler.handle_delete_param(cmd)
            return _success({"id": request.param_id, "deleted": result})
        except Exception as e:
            return _failure(str(e))

    def FindParamByCode(self, request, context=None):
        """按算法/参数代码/方向查找未删除的设备参数或 API 参数。"""
        try:
            from algorithm_service.application.queries.algorithm_param_queries import (
                FindParamByCodeQuery,
            )
            query = FindParamByCodeQuery(
                algorithm_type=request.algorithm_type,
                param_code=request.param_code,
                direction=request.direction,
                param_type_source=request.param_type_source or "device",
            )
            result = self.param_query_handler.handle_find_param_by_code(query)
            return _success(result)
        except Exception as e:
            return _failure(str(e))

    # ---- 用例参数写操作 ----

    def CreateCaseParam(self, request, context=None):
        """创建用例专属参数。"""
        try:
            from algorithm_service.application.commands.algorithm_param_commands import (
                CreateCaseParamCommand,
            )
            data = _loads(request.data, {}) if not isinstance(request, dict) else request
            cmd = CreateCaseParamCommand(data=data)
            result = self.param_command_handler.handle_create_case_param(cmd)
            return _success(result)
        except Exception as e:
            return _failure(str(e))

    def UpdateCaseParam(self, request, context=None):
        """更新用例专属参数。"""
        try:
            from algorithm_service.application.commands.algorithm_param_commands import (
                UpdateCaseParamCommand,
            )
            data = _loads(request.data, {}) if not isinstance(request, dict) else request
            cmd = UpdateCaseParamCommand(
                param_id=request.param_id,
                data=data,
            )
            result = self.param_command_handler.handle_update_case_param(cmd)
            return _success(result)
        except Exception as e:
            return _failure(str(e))

    def DeleteCaseParam(self, request, context=None):
        """软删除用例专属参数。"""
        try:
            from algorithm_service.application.commands.algorithm_param_commands import (
                DeleteCaseParamCommand,
            )
            cmd = DeleteCaseParamCommand(param_id=request.param_id)
            result = self.param_command_handler.handle_delete_case_param(cmd)
            return _success({"id": request.param_id, "deleted": result})
        except Exception as e:
            return _failure(str(e))

    def FindCaseParamByCode(self, request, context=None):
        """按算法/参数代码查找用例专属参数（可包含软删项）。"""
        try:
            from algorithm_service.application.queries.algorithm_param_queries import (
                FindCaseParamByCodeQuery,
            )
            query = FindCaseParamByCodeQuery(
                algorithm_type=request.algorithm_type,
                param_code=request.param_code,
                include_deleted=bool(request.include_deleted),
            )
            result = self.param_query_handler.handle_find_case_param_by_code(query)
            return _success(result)
        except Exception as e:
            return _failure(str(e))

    def ReviveCaseParam(self, request, context=None):
        """恢复软删除的用例专属参数并更新字段。"""
        try:
            from algorithm_service.application.commands.algorithm_param_commands import (
                ReviveCaseParamCommand,
            )
            data = _loads(request.data, {}) if not isinstance(request, dict) else request
            cmd = ReviveCaseParamCommand(
                param_id=request.param_id,
                data=data,
            )
            result = self.param_command_handler.handle_revive_case_param(cmd)
            return _success(result)
        except Exception as e:
            return _failure(str(e))

    # ---- 参考参数写操作 ----

    def CreateReferenceParam(self, request, context=None):
        """创建参考参数。"""
        try:
            from algorithm_service.application.commands.algorithm_param_commands import (
                CreateReferenceParamCommand,
            )
            data = _loads(request.data, {}) if not isinstance(request, dict) else request
            cmd = CreateReferenceParamCommand(data=data)
            result = self.param_command_handler.handle_create_reference_param(cmd)
            return _success(result)
        except Exception as e:
            return _failure(str(e))

    def UpdateReferenceParam(self, request, context=None):
        """更新参考参数。"""
        try:
            from algorithm_service.application.commands.algorithm_param_commands import (
                UpdateReferenceParamCommand,
            )
            data = _loads(request.data, {}) if not isinstance(request, dict) else request
            cmd = UpdateReferenceParamCommand(
                param_id=request.param_id,
                data=data,
            )
            result = self.param_command_handler.handle_update_reference_param(cmd)
            return _success(result)
        except Exception as e:
            return _failure(str(e))

    def DeleteReferenceParam(self, request, context=None):
        """软删除参考参数。"""
        try:
            from algorithm_service.application.commands.algorithm_param_commands import (
                DeleteReferenceParamCommand,
            )
            cmd = DeleteReferenceParamCommand(param_id=request.param_id)
            result = self.param_command_handler.handle_delete_reference_param(cmd)
            return _success({"id": request.param_id, "deleted": result})
        except Exception as e:
            return _failure(str(e))

    def FindReferenceParam(self, request, context=None):
        """按算法/代码查找未删除的参考参数。"""
        try:
            from algorithm_service.application.queries.algorithm_param_queries import (
                FindReferenceParamQuery,
            )
            query = FindReferenceParamQuery(
                algorithm_type=request.algorithm_type,
                code=request.code,
            )
            result = self.param_query_handler.handle_find_reference_param(query)
            return _success(result)
        except Exception as e:
            return _failure(str(e))

    # ---- 参数映射写操作 ----

    def CreateMapping(self, request, context=None):
        """创建参数映射。"""
        try:
            from algorithm_service.application.commands.algorithm_param_commands import (
                CreateMappingCommand,
            )
            data = _loads(request.data, {}) if not isinstance(request, dict) else request
            cmd = CreateMappingCommand(data=data)
            result = self.param_command_handler.handle_create_mapping(cmd)
            return _success(result)
        except Exception as e:
            return _failure(str(e))

    def UpdateMapping(self, request, context=None):
        """更新参数映射。"""
        try:
            from algorithm_service.application.commands.algorithm_param_commands import (
                UpdateMappingCommand,
            )
            data = _loads(request.data, {}) if not isinstance(request, dict) else request
            cmd = UpdateMappingCommand(
                mapping_id=request.mapping_id,
                data=data,
            )
            result = self.param_command_handler.handle_update_mapping(cmd)
            return _success(result)
        except Exception as e:
            return _failure(str(e))

    def DeleteMapping(self, request, context=None):
        """软删除参数映射。"""
        try:
            from algorithm_service.application.commands.algorithm_param_commands import (
                DeleteMappingCommand,
            )
            cmd = DeleteMappingCommand(mapping_id=request.mapping_id)
            result = self.param_command_handler.handle_delete_mapping(cmd)
            return _success({"id": request.mapping_id, "deleted": result})
        except Exception as e:
            return _failure(str(e))

    def GetMapping(self, request, context=None):
        """按 ID 获取未删除的参数映射。"""
        try:
            from algorithm_service.application.queries.algorithm_param_queries import (
                GetMappingQuery,
            )
            query = GetMappingQuery(mapping_id=request.mapping_id)
            result = self.param_query_handler.handle_get_mapping(query)
            return _success(result)
        except Exception as e:
            return _failure(str(e))

    # ---- 算法定义写操作 ----

    def CreateAlgorithmDefinition(self, request, context=None):
        """创建算法定义。"""
        try:
            from algorithm_service.application.commands.algorithm_commands import (
                CreateAlgorithmDefinitionCommand,
            )
            data = _loads(request.data, {}) if not isinstance(request, dict) else request
            cmd = CreateAlgorithmDefinitionCommand(
                group_id=data.get("group_id"),
                name=data.get("name", ""),
                algorithm_type=data.get("algorithm_type") or data.get("type") or "",
                description=data.get("description"),
            )
            new_id = self.command_handler.handle_create_definition(cmd)
            return _success({"id": new_id, "name": cmd.name})
        except Exception as e:
            return _failure(str(e))

    def UpdateAlgorithmDefinitionAttrs(self, request, context=None):
        """更新算法定义可变字段。"""
        try:
            from algorithm_service.application.commands.algorithm_commands import (
                UpdateAlgorithmDefinitionCommand,
            )
            data = _loads(request.data, {}) if not isinstance(request, dict) else request
            cmd = UpdateAlgorithmDefinitionCommand(
                id=int(request.algorithm_id),
                name=data.get("name", ""),
                description=data.get("description"),
            )
            self.command_handler.handle_update_definition(cmd)
            return _success({"id": cmd.id, "updated": True})
        except Exception as e:
            return _failure(str(e))

    def SoftDeleteAlgorithm(self, request, context=None):
        """软删除算法定义。"""
        try:
            from algorithm_service.application.commands.algorithm_commands import (
                DeleteAlgorithmDefinitionCommand,
            )
            cmd = DeleteAlgorithmDefinitionCommand(id=int(request.algorithm_id))
            ok = self.command_handler.handle_delete_definition(cmd)
            return _success({"id": cmd.id, "deleted": ok})
        except Exception as e:
            return _failure(str(e))

    def FindAlgorithmByType(self, request, context=None):
        """按 type 查询未删除的算法定义。"""
        try:
            from algorithm_service.application.queries.algorithm_param_queries import (
                FindAlgorithmByTypeQuery,
            )
            query = FindAlgorithmByTypeQuery(algorithm_type=request.algorithm_type)
            result = self.param_query_handler.handle_find_algorithm_by_type(query)
            return _success(result)
        except Exception as e:
            return _failure(str(e))

    def ListAlgorithmDefinitions(self, request, context=None):
        """查询未删除的算法定义列表。"""
        try:
            from algorithm_service.application.queries.algorithm_param_queries import (
                ListAlgorithmDefinitionsQuery,
            )
            status = request.status or None
            group_id = request.group_id or None
            query = ListAlgorithmDefinitionsQuery(status=status, group_id=group_id)
            result = self.param_query_handler.handle_list_algorithm_definitions(query)
            return _success({"items": result})
        except Exception as e:
            return _failure(str(e))

    def ListOnlineAlgorithmDefinitions(self, request, context=None):
        """查询在线算法定义列表（按 display_order 排序）。"""
        try:
            from algorithm_service.application.queries.algorithm_param_queries import (
                ListOnlineAlgorithmDefinitionsQuery,
            )
            query = ListOnlineAlgorithmDefinitionsQuery()
            result = self.param_query_handler.handle_list_online_algorithm_definitions(query)
            return _success({"items": result})
        except Exception as e:
            return _failure(str(e))

    def CountAlgorithmsInGroup(self, request, context=None):
        """统计分组下未删除的算法定义数量。"""
        try:
            from algorithm_service.application.queries.algorithm_param_queries import (
                CountAlgorithmsInGroupQuery,
            )
            query = CountAlgorithmsInGroupQuery(group_id=request.group_id)
            count = self.param_query_handler.handle_count_algorithms_in_group(query)
            return _success({"count": count})
        except Exception as e:
            return _failure(str(e))

    def CreateImportDeviceParam(self, request, context=None):
        """导入场景下创建设备参数。"""
        try:
            from algorithm_service.application.commands.algorithm_param_commands import (
                CreateImportDeviceParamCommand,
            )
            data = _loads(request.data, {}) if not isinstance(request, dict) else request
            cmd = CreateImportDeviceParamCommand(data=data)
            result = self.param_command_handler.handle_create_import_device_param(cmd)
            return _success(result)
        except Exception as e:
            return _failure(str(e))

    def ListAlgorithmDefinitionsForBulkDelete(self, request, context=None):
        """按 type 列表查询未删除的算法定义（供批量删除）。"""
        try:
            from algorithm_service.application.queries.algorithm_param_queries import (
                ListAlgorithmDefinitionsForBulkDeleteQuery,
            )
            query = ListAlgorithmDefinitionsForBulkDeleteQuery(
                algorithm_types=request.algorithm_types or ""
            )
            result = self.param_query_handler.handle_list_algorithm_definitions_for_bulk_delete(query)
            return _success({"items": result})
        except Exception as e:
            return _failure(str(e))

    def BulkDeleteAlgorithms(self, request, context=None):
        """批量软删除算法定义。"""
        try:
            from algorithm_service.application.commands.algorithm_param_commands import (
                BulkDeleteAlgorithmsCommand,
            )
            algorithm_types = _loads(request.algorithm_types, [])
            if not isinstance(algorithm_types, list):
                algorithm_types = []
            cmd = BulkDeleteAlgorithmsCommand(algorithm_types=algorithm_types)
            result = self.param_command_handler.handle_bulk_delete_algorithms(cmd)
            return _success(result)
        except Exception as e:
            return _failure(str(e))

    # ---- 算法分组写操作 ----

    def FindGroupByName(self, request, context=None):
        """按 name 查询未删除的算法分组。"""
        try:
            from algorithm_service.application.queries.algorithm_param_queries import (
                FindGroupByNameQuery,
            )
            query = FindGroupByNameQuery(name=request.name)
            result = self.param_query_handler.handle_find_group_by_name(query)
            return _success(result)
        except Exception as e:
            return _failure(str(e))

    def GetGroup(self, request, context=None):
        """按 ID 查询未删除的算法分组。"""
        try:
            from algorithm_service.application.queries.algorithm_param_queries import (
                GetGroupQuery,
            )
            query = GetGroupQuery(group_id=request.group_id)
            result = self.param_query_handler.handle_get_group(query)
            return _success(result)
        except Exception as e:
            return _failure(str(e))

    def CreateGroup(self, request, context=None):
        """创建算法分组。"""
        try:
            from algorithm_service.application.commands.algorithm_commands import (
                CreateAlgorithmGroupCommand,
            )
            data = _loads(request.data, {}) if not isinstance(request, dict) else request
            cmd = CreateAlgorithmGroupCommand(
                name=data.get("name", ""),
                description=data.get("description"),
                algorithm_type=data.get("algorithm_type"),
            )
            new_id = self.command_handler.handle_create_group(cmd)
            return _success({"id": new_id, "name": cmd.name})
        except Exception as e:
            return _failure(str(e))

    def UpdateGroupAttrs(self, request, context=None):
        """更新算法分组可变字段。"""
        try:
            from algorithm_service.application.commands.algorithm_commands import (
                UpdateAlgorithmGroupCommand,
            )
            data = _loads(request.data, {}) if not isinstance(request, dict) else request
            group_id = request.group_id or data.get("group_id") or data.get("id")
            cmd = UpdateAlgorithmGroupCommand(
                id=int(group_id),
                name=data.get("name", ""),
                description=data.get("description"),
            )
            self.command_handler.handle_update_group(cmd)
            return _success({"id": cmd.id, "updated": True})
        except Exception as e:
            return _failure(str(e))

    def SoftDeleteGroup(self, request, context=None):
        """软删除算法分组。"""
        try:
            from algorithm_service.application.commands.algorithm_commands import (
                DeleteAlgorithmGroupCommand,
            )
            cmd = DeleteAlgorithmGroupCommand(id=int(request.group_id))
            ok = self.command_handler.handle_delete_group(cmd)
            return _success({"id": cmd.id, "deleted": ok})
        except Exception as e:
            return _failure(str(e))

    def ListGroups(self, request, context=None):
        """查询未删除的算法分组列表。"""
        try:
            from algorithm_service.application.queries.algorithm_param_queries import (
                ListGroupsQuery,
            )
            query = ListGroupsQuery()
            result = self.param_query_handler.handle_list_groups(query)
            return _success({"items": result})
        except Exception as e:
            return _failure(str(e))

    def CountAlgorithmsInGroupForGroup(self, request, context=None):
        """统计指定分组下未删除的算法定义数量。"""
        try:
            from algorithm_service.application.queries.algorithm_param_queries import (
                CountAlgorithmsInGroupForGroupQuery,
            )
            query = CountAlgorithmsInGroupForGroupQuery(group_id=request.group_id)
            count = self.param_query_handler.handle_count_algorithms_in_group_for_group(query)
            return _success({"count": count})
        except Exception as e:
            return _failure(str(e))

    # ---- 维度关联写操作 ----

    def SoftDeleteAlgorithmDimensionRelations(self, request, context=None):
        """按算法批量软删除维度关联。"""
        try:
            from algorithm_service.application.commands.algorithm_param_commands import (
                SoftDeleteAlgorithmDimensionRelationsCommand,
            )
            cmd = SoftDeleteAlgorithmDimensionRelationsCommand(
                algorithm_type=request.algorithm_type
            )
            result = self.param_command_handler.handle_soft_delete_algorithm_dimension_relations(cmd)
            return _success({"algorithm_type": request.algorithm_type, "deleted": result})
        except Exception as e:
            return _failure(str(e))

    def FindDimensionRelation(self, request, context=None):
        """按算法/维度查找未删除的维度关联。"""
        try:
            from algorithm_service.application.queries.algorithm_param_queries import (
                FindDimensionRelationQuery,
            )
            query = FindDimensionRelationQuery(
                algorithm_type=request.algorithm_type,
                dimension_id=request.dimension_id,
            )
            result = self.param_query_handler.handle_find_dimension_relation(query)
            return _success(result)
        except Exception as e:
            return _failure(str(e))

    def GetDimensionRelation(self, request, context=None):
        """按 ID 查询维度关联（含软删项）。"""
        try:
            from algorithm_service.application.queries.algorithm_param_queries import (
                GetDimensionRelationQuery,
            )
            query = GetDimensionRelationQuery(relation_id=request.relation_id)
            result = self.param_query_handler.handle_get_dimension_relation(query)
            return _success(result)
        except Exception as e:
            return _failure(str(e))

    def ListDimensionRelations(self, request, context=None):
        """查询算法关联的未删除维度关联列表。"""
        try:
            from algorithm_service.application.queries.algorithm_param_queries import (
                ListDimensionRelationsQuery,
            )
            query = ListDimensionRelationsQuery(algorithm_type=request.algorithm_type)
            result = self.param_query_handler.handle_list_dimension_relations(query)
            return _success({"items": result})
        except Exception as e:
            return _failure(str(e))

    def UpdateDimensionRelationAttrs(self, request, context=None):
        """更新维度关联属性。"""
        try:
            from algorithm_service.application.commands.algorithm_param_commands import (
                UpdateDimensionRelationAttrsCommand,
            )
            data = _loads(request.data, {}) if not isinstance(request, dict) else request
            cmd = UpdateDimensionRelationAttrsCommand(
                relation_id=request.relation_id,
                data=data,
            )
            result = self.param_command_handler.handle_update_dimension_relation_attrs(cmd)
            return _success(result)
        except Exception as e:
            return _failure(str(e))

    def SoftDeleteDimensionRelation(self, request, context=None):
        """软删除维度关联。"""
        try:
            from algorithm_service.application.commands.algorithm_param_commands import (
                DeleteDimensionRelationCommand,
            )
            cmd = DeleteDimensionRelationCommand(relation_id=request.relation_id)
            result = self.param_command_handler.handle_delete_dimension_relation(cmd)
            return _success({"id": request.relation_id, "deleted": result})
        except Exception as e:
            return _failure(str(e))

    # ---- 评估维度参数读 ----

    def ListDimensionParams(self, request, context=None):
        """查询评估维度的参数列表（按 ui_order 排序）。"""
        try:
            from algorithm_service.application.queries.algorithm_param_queries import (
                ListDimensionParamsQuery,
            )
            query = ListDimensionParamsQuery(dimension_id=request.dimension_id)
            result = self.param_query_handler.handle_list_dimension_params(query)
            return _success({"params": result})
        except Exception as e:
            return _failure(str(e))

    # ---- 事务控制 ----

    def CommitTransaction(self, request, context=None):
        """提交当前事务。"""
        try:
            from algorithm_service.infrastructure.persistence.algorithm_repository import commit_transaction
            commit_transaction()
            return _success({"committed": True})
        except Exception as e:
            return _failure(str(e))

    def RollbackTransaction(self, request, context=None):
        """回滚当前事务。"""
        try:
            from algorithm_service.infrastructure.persistence.algorithm_repository import rollback_transaction
            rollback_transaction()
            return _success({"rolled_back": True})
        except Exception as e:
            return _failure(str(e))

    def FlushTransaction(self, request, context=None):
        """flush 当前 session。"""
        try:
            from algorithm_service.infrastructure.persistence.algorithm_repository import flush_transaction
            flush_transaction()
            return _success({"flushed": True})
        except Exception as e:
            return _failure(str(e))
