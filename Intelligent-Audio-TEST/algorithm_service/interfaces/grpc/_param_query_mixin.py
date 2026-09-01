# -*- coding: utf-8 -*-
"""AlgorithmDefinitionServicer 的参数/映射/维度查询方法 mixin（读操作）。

从 _param_mixin.py 拆分，包含以下只读 RPC 方法：
- 参数查询（device / api / case / reference）
- 映射查询
- 维度关系查询
- 算法定义查询
- 算法分组查询
- 评估维度参数查询
"""
from __future__ import annotations

from shared.utils.grpc_json import loads as _loads

from algorithm_service.interfaces.grpc._param_helpers import _success, _failure, _ParamBaseMixin


class _ParamQueryMixin(_ParamBaseMixin):
    """参数/映射/维度关系/算法定义/分组的只读查询方法 mixin。"""

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

    # ---- 维度关系查询 ----

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

    # ---- 算法定义查询 ----

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

    # ---- 算法分组查询 ----

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

    # ---- 评估维度参数查询 ----

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
