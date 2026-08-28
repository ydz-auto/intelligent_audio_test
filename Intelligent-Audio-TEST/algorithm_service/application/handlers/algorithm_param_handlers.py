# -*- coding: utf-8 -*-
"""参数/映射/维度关联命令/查询处理器（CQRS - Handler 侧）。

归属：algorithm_service.application.handlers

说明：
- AlgorithmParamCommandHandler: 处理参数/映射/维度关联的写命令，
  通过 param_repository 的 5 个仓储实现操作 PO，不直接 import PO，
  返回 dict（ACL DTO）。
- AlgorithmParamQueryHandler: 处理参数/映射/维度关联的读查询，
  通过 param_repository 的 5 个仓储实现查询，返回 dict / dict 列表。
- 对于算法定义/分组的查询/写操作（servicer 复用），handler 通过
  algorithm_definition_query_repository / algorithm_group_query_repository
  等专用仓储查询，不直接 import PO。
- Handler 不持有业务规则，业务规则由 domain 层聚合根/领域服务承载；
  Handler 仅负责：构造命令/查询 → 调用 repository → 返回结果。
- 命令处理失败时抛出 ValueError，由上层统一捕获转换为 gRPC 响应。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from algorithm_service.infrastructure.persistence.param_repository import (
    algorithm_param_repository,
    case_param_repository,
    reference_param_repository,
    mapping_repository,
    dimension_relation_repository,
)
from algorithm_service.infrastructure.persistence.algorithm_repository import (
    algorithm_definition_query_repository,
    algorithm_group_query_repository,
    device_param_repository,
    dimension_param_repository,
)
from algorithm_service.application.commands.algorithm_param_commands import (
    CreateParamCommand,
    UpdateParamCommand,
    DeleteParamCommand,
    FindParamByCodeCommand,
    CreateCaseParamCommand,
    UpdateCaseParamCommand,
    DeleteCaseParamCommand,
    FindCaseParamByCodeCommand,
    CreateReferenceParamCommand,
    UpdateReferenceParamCommand,
    DeleteReferenceParamCommand,
    FindReferenceParamCommand,
    CreateMappingCommand,
    UpdateMappingCommand,
    DeleteMappingCommand,
    CreateDimensionRelationCommand,
    UpdateDimensionRelationAttrsCommand,
    DeleteDimensionRelationCommand,
    SoftDeleteAlgorithmDimensionRelationsCommand,
    CreateImportDeviceParamCommand,
    BulkDeleteAlgorithmsCommand,
)
from algorithm_service.application.queries.algorithm_param_queries import (
    GetParamQuery,
    ListParamsQuery,
    FindParamByCodeQuery,
    GetCaseParamQuery,
    ListCaseParamsQuery,
    FindCaseParamByCodeQuery,
    GetReferenceParamQuery,
    ListReferenceParamsQuery,
    FindReferenceParamQuery,
    GetMappingQuery,
    ListMappingsQuery,
    GetDimensionRelationQuery,
    ListDimensionRelationsQuery,
    FindDimensionRelationQuery,
    ListAlgorithmDefinitionsQuery,
    ListOnlineAlgorithmDefinitionsQuery,
    FindAlgorithmByTypeQuery,
    CountAlgorithmsInGroupQuery,
    ListAlgorithmDefinitionsForBulkDeleteQuery,
    FindGroupByNameQuery,
    GetGroupQuery,
    ListGroupsQuery,
    CountAlgorithmsInGroupForGroupQuery,
    ListDimensionParamsQuery,
)


class AlgorithmParamCommandHandler:
    """参数/映射/维度关联命令处理器。

    处理 param/mapping/relation 的增删改命令。
    通过仓储实现操作 PO，不直接 import PO。
    """

    def __init__(
        self,
        param_repo=None,
        case_repo=None,
        reference_repo=None,
        mapping_repo=None,
        relation_repo=None,
    ) -> None:
        """注入仓储实例（默认使用模块级单例）。"""
        self._param_repo = param_repo or algorithm_param_repository
        self._case_repo = case_repo or case_param_repository
        self._reference_repo = reference_repo or reference_param_repository
        self._mapping_repo = mapping_repo or mapping_repository
        self._relation_repo = relation_repo or dimension_relation_repository

    # ========== 设备/API 参数命令 ==========

    def handle_create_param(self, cmd: CreateParamCommand) -> Dict[str, Any]:
        """处理创建设备/API 参数命令，返回新参数 dict。"""
        return self._param_repo.create(cmd.data, cmd.param_type_source)

    def handle_update_param(self, cmd: UpdateParamCommand) -> Dict[str, Any]:
        """处理更新设备/API 参数命令，返回更新后的 dict。"""
        return self._param_repo.update_attrs(
            cmd.param_id, cmd.data, cmd.param_type_source
        )

    def handle_delete_param(self, cmd: DeleteParamCommand) -> bool:
        """处理软删除设备/API 参数命令，返回是否成功。"""
        return self._param_repo.soft_delete(
            cmd.param_id, cmd.param_type_source
        )

    def handle_find_param_by_code(
        self, cmd: FindParamByCodeCommand
    ) -> Optional[Dict[str, Any]]:
        """处理按 算法/参数代码/方向 查找设备/API 参数命令，返回 dict 或 None。"""
        return self._param_repo.find_by_code(
            cmd.algorithm_type,
            cmd.param_code,
            cmd.direction,
            cmd.param_type_source,
        )

    # ========== 用例参数命令 ==========

    def handle_create_case_param(
        self, cmd: CreateCaseParamCommand
    ) -> Dict[str, Any]:
        """处理创建用例参数命令，返回新参数 dict。"""
        return self._case_repo.create(cmd.data)

    def handle_update_case_param(
        self, cmd: UpdateCaseParamCommand
    ) -> Dict[str, Any]:
        """处理更新用例参数命令，返回更新后的 dict。"""
        return self._case_repo.update_attrs(cmd.param_id, cmd.data)

    def handle_delete_case_param(self, cmd: DeleteCaseParamCommand) -> bool:
        """处理软删除用例参数命令，返回是否成功。"""
        return self._case_repo.soft_delete(cmd.param_id)

    def handle_find_case_param_by_code(
        self, cmd: FindCaseParamByCodeCommand
    ) -> Optional[Dict[str, Any]]:
        """处理按 算法/参数代码 查找用例参数命令，返回 dict 或 None。"""
        return self._case_repo.find_by_code(
            cmd.algorithm_type,
            cmd.param_code,
            cmd.include_deleted,
        )

    # ========== 参考参数命令 ==========

    def handle_create_reference_param(
        self, cmd: CreateReferenceParamCommand
    ) -> Dict[str, Any]:
        """处理创建参考参数命令，返回新参数 dict。"""
        return self._reference_repo.create(cmd.data)

    def handle_update_reference_param(
        self, cmd: UpdateReferenceParamCommand
    ) -> Dict[str, Any]:
        """处理更新参考参数命令，返回更新后的 dict。"""
        return self._reference_repo.update_attrs(cmd.param_id, cmd.data)

    def handle_delete_reference_param(
        self, cmd: DeleteReferenceParamCommand
    ) -> bool:
        """处理软删除参考参数命令，返回是否成功。"""
        return self._reference_repo.soft_delete(cmd.param_id)

    def handle_find_reference_param(
        self, cmd: FindReferenceParamCommand
    ) -> Optional[Dict[str, Any]]:
        """处理按 算法/code 查找参考参数命令，返回 dict 或 None。"""
        return self._reference_repo.find_by_code(
            cmd.algorithm_type, cmd.code
        )

    # ========== 参数映射命令 ==========

    def handle_create_mapping(
        self, cmd: CreateMappingCommand
    ) -> Dict[str, Any]:
        """处理创建参数映射命令，返回新映射 dict。"""
        # source 必须是合法值，防止 'evaluation' 等非法值写入
        source_val = cmd.data.get('source_type') or cmd.data.get('source')
        if source_val and source_val not in ('case', 'reference', 'device', 'api'):
            raise ValueError(
                f"source 必须是 case/reference/device/api，当前值: {source_val}"
            )
        return self._mapping_repo.create(cmd.data)

    def handle_update_mapping(
        self, cmd: UpdateMappingCommand
    ) -> Dict[str, Any]:
        """处理更新参数映射命令，返回更新后的 dict。"""
        return self._mapping_repo.update_attrs(cmd.mapping_id, cmd.data)

    def handle_delete_mapping(self, cmd: DeleteMappingCommand) -> bool:
        """处理软删除参数映射命令，返回是否成功。"""
        return self._mapping_repo.soft_delete(cmd.mapping_id)

    # ========== 维度关联命令 ==========

    def handle_create_dimension_relation(
        self, cmd: CreateDimensionRelationCommand
    ) -> Dict[str, Any]:
        """处理创建维度关联命令，返回新关联 dict。"""
        return self._relation_repo.create(cmd.data)

    def handle_update_dimension_relation_attrs(
        self, cmd: UpdateDimensionRelationAttrsCommand
    ) -> Dict[str, Any]:
        """处理更新维度关联属性命令，返回更新后的 dict。"""
        return self._relation_repo.update_attrs(cmd.relation_id, cmd.data)

    def handle_delete_dimension_relation(
        self, cmd: DeleteDimensionRelationCommand
    ) -> bool:
        """处理软删除维度关联命令，返回是否成功。"""
        return self._relation_repo.soft_delete(cmd.relation_id)

    def handle_soft_delete_algorithm_dimension_relations(
        self, cmd: SoftDeleteAlgorithmDimensionRelationsCommand
    ) -> bool:
        """处理按算法批量软删除维度关联命令，返回是否成功。"""
        return self._relation_repo.soft_delete_by_algorithm(
            cmd.algorithm_type
        )

    # ========== 导入/批量命令 ==========

    def handle_create_import_device_param(
        self, cmd: CreateImportDeviceParamCommand
    ) -> Dict[str, Any]:
        """处理导入场景创建设备参数命令（仅 add，不 flush/commit）。

        与 servicers.py CreateImportDeviceParam 一致：
        - 字段映射：code → param_code, name → param_name, type → param_type
        - 不 flush/commit，由调用方统一控制事务
        """
        return device_param_repository.create_import_device_param(cmd.data)

    def handle_bulk_delete_algorithms(
        self, cmd: BulkDeleteAlgorithmsCommand
    ) -> Dict[str, Any]:
        """处理批量软删除算法定义命令，返回已删除类型列表。

        与 servicers.py BulkDeleteAlgorithms 一致：
        - 按 type.in_(algorithm_types) 查询未删除算法定义
        - 批量置 deleted=True
        - 返回 {"deleted_types": [...]}
        """
        deleted_types = algorithm_definition_query_repository.bulk_soft_delete(
            cmd.algorithm_types
        )
        return {"deleted_types": deleted_types}


class AlgorithmParamQueryHandler:
    """参数/映射/维度关联查询处理器。

    处理 param/mapping/relation 的读查询，返回 dict / dict 列表。
    通过仓储实现查询，不直接 import PO。
    """

    def __init__(
        self,
        param_repo=None,
        case_repo=None,
        reference_repo=None,
        mapping_repo=None,
        relation_repo=None,
    ) -> None:
        """注入仓储实例（默认使用模块级单例）。"""
        self._param_repo = param_repo or algorithm_param_repository
        self._case_repo = case_repo or case_param_repository
        self._reference_repo = reference_repo or reference_param_repository
        self._mapping_repo = mapping_repo or mapping_repository
        self._relation_repo = relation_repo or dimension_relation_repository

    # ========== 设备/API 参数查询 ==========

    def handle_get_param(
        self, query: GetParamQuery
    ) -> Optional[Dict[str, Any]]:
        """按 ID 获取设备或 API 参数，返回 dict 或 None。"""
        return self._param_repo.get_by_id(
            query.param_id, query.param_type_source
        )

    def handle_list_params(
        self, query: ListParamsQuery
    ) -> List[Dict[str, Any]]:
        """查询设备/API 参数列表，返回 dict 列表。"""
        return self._param_repo.list_by_algorithm(
            query.algorithm_type, query.param_type
        )

    def handle_find_param_by_code(
        self, query: FindParamByCodeQuery
    ) -> Optional[Dict[str, Any]]:
        """按 算法/参数代码/方向 查找设备/API 参数，返回 dict 或 None。"""
        return self._param_repo.find_by_code(
            query.algorithm_type,
            query.param_code,
            query.direction,
            query.param_type_source,
        )

    # ========== 用例参数查询 ==========

    def handle_get_case_param(
        self, query: GetCaseParamQuery
    ) -> Optional[Dict[str, Any]]:
        """按 ID 获取用例参数，返回 dict 或 None。"""
        return self._case_repo.get_by_id(query.param_id)

    def handle_list_case_params(
        self, query: ListCaseParamsQuery
    ) -> List[Dict[str, Any]]:
        """查询用例参数列表，返回 dict 列表。"""
        return self._case_repo.list_by_algorithm(
            query.algorithm_type, query.scope
        )

    def handle_find_case_param_by_code(
        self, query: FindCaseParamByCodeQuery
    ) -> Optional[Dict[str, Any]]:
        """按 算法/参数代码 查找用例参数，返回 dict 或 None。"""
        return self._case_repo.find_by_code(
            query.algorithm_type,
            query.param_code,
            query.include_deleted,
        )

    # ========== 参考参数查询 ==========

    def handle_get_reference_param(
        self, query: GetReferenceParamQuery
    ) -> Optional[Dict[str, Any]]:
        """按 ID 获取参考参数，返回 dict 或 None。"""
        return self._reference_repo.get_by_id(query.param_id)

    def handle_list_reference_params(
        self, query: ListReferenceParamsQuery
    ) -> List[Dict[str, Any]]:
        """查询参考参数列表，返回 dict 列表。"""
        return self._reference_repo.list_by_algorithm(
            query.algorithm_type
        )

    def handle_find_reference_param(
        self, query: FindReferenceParamQuery
    ) -> Optional[Dict[str, Any]]:
        """按 算法/code 查找参考参数，返回 dict 或 None。

        此方法复用 IReferenceParamRepository.find_by_code。
        """
        return self._reference_repo.find_by_code(
            query.algorithm_type, query.code
        )

    # ========== 参数映射查询 ==========

    def handle_get_mapping(
        self, query: GetMappingQuery
    ) -> Optional[Dict[str, Any]]:
        """按 ID 获取参数映射，返回 dict 或 None。"""
        return self._mapping_repo.get_by_id(query.mapping_id)

    def handle_list_mappings(
        self, query: ListMappingsQuery
    ) -> List[Dict[str, Any]]:
        """查询参数映射列表，返回 dict 列表。"""
        return self._mapping_repo.list_by_algorithm(
            query.algorithm_type,
            source_type=query.source_type,
            dimension_id=query.dimension_id,
        )

    # ========== 维度关联查询 ==========

    def handle_get_dimension_relation(
        self, query: GetDimensionRelationQuery
    ) -> Optional[Dict[str, Any]]:
        """按 ID 获取维度关联（含软删项），返回 dict 或 None。"""
        return self._relation_repo.get_by_id(query.relation_id)

    def handle_list_dimension_relations(
        self, query: ListDimensionRelationsQuery
    ) -> List[Dict[str, Any]]:
        """查询算法关联的维度关联列表，返回 dict 列表。"""
        return self._relation_repo.list_by_algorithm(query.algorithm_type)

    def handle_find_dimension_relation(
        self, query: FindDimensionRelationQuery
    ) -> Optional[Dict[str, Any]]:
        """按 算法/维度 查找维度关联，返回 dict 或 None。"""
        return self._relation_repo.find(
            query.algorithm_type, query.dimension_id
        )

    # ========== 算法定义/分组查询（servicer 复用） ==========

    def handle_list_algorithm_definitions(
        self, query: ListAlgorithmDefinitionsQuery
    ) -> List[Dict[str, Any]]:
        """查询未删除的算法定义列表（可按 status / group_id 过滤）。

        与 servicers.py ListAlgorithmDefinitions 一致：
        - 按 display_order、id 排序
        - 返回 dict 列表
        """
        return algorithm_definition_query_repository.list_definitions(
            status=query.status,
            group_id=query.group_id,
        )

    def handle_list_online_algorithm_definitions(
        self, query: ListOnlineAlgorithmDefinitionsQuery
    ) -> List[Dict[str, Any]]:
        """查询在线算法定义列表（按 display_order 排序）。"""
        return algorithm_definition_query_repository.list_online_definitions()

    def handle_find_algorithm_by_type(
        self, query: FindAlgorithmByTypeQuery
    ) -> Optional[Dict[str, Any]]:
        """按 type 查询未删除的算法定义，返回 dict 或 None。"""
        return algorithm_definition_query_repository.find_by_type(
            query.algorithm_type
        )

    def handle_count_algorithms_in_group(
        self, query: CountAlgorithmsInGroupQuery
    ) -> int:
        """统计分组下未删除的算法定义数量。"""
        return algorithm_definition_query_repository.count_in_group(
            query.group_id
        )

    def handle_list_algorithm_definitions_for_bulk_delete(
        self, query: ListAlgorithmDefinitionsForBulkDeleteQuery
    ) -> List[Dict[str, Any]]:
        """按 type 列表查询未删除的算法定义（供批量删除）。

        与 servicers.py ListAlgorithmDefinitionsForBulkDelete 一致：
        - query.algorithm_types 为 JSON 文本，解析为 list
        - 返回 dict 列表
        """
        import json
        try:
            algorithm_types = json.loads(query.algorithm_types) if query.algorithm_types else []
        except (json.JSONDecodeError, TypeError):
            algorithm_types = []
        if not isinstance(algorithm_types, list):
            algorithm_types = []
        return algorithm_definition_query_repository.list_for_bulk_delete(
            algorithm_types
        )

    def handle_find_group_by_name(
        self, query: FindGroupByNameQuery
    ) -> Optional[Dict[str, Any]]:
        """按 name 查询未删除的算法分组，返回 dict 或 None。"""
        return algorithm_group_query_repository.find_by_name(query.name)

    def handle_get_group(
        self, query: GetGroupQuery
    ) -> Optional[Dict[str, Any]]:
        """按 ID 查询未删除的算法分组，返回 dict 或 None。"""
        return algorithm_group_query_repository.get_by_id(query.group_id)

    def handle_list_groups(
        self, query: ListGroupsQuery
    ) -> List[Dict[str, Any]]:
        """查询未删除的算法分组列表（按 display_order、id 排序）。"""
        return algorithm_group_query_repository.list_all()

    def handle_count_algorithms_in_group_for_group(
        self, query: CountAlgorithmsInGroupForGroupQuery
    ) -> int:
        """统计指定分组下未删除的算法定义数量。

        与 servicers.py CountAlgorithmsInGroupForGroup 一致：
        - 先确认分组存在，再统计其下算法定义数量
        - 分组不存在时抛出 ValueError
        """
        return algorithm_group_query_repository.count_algorithms_in_group(
            query.group_id
        )

    # ========== 评估维度参数查询 ==========

    def handle_list_dimension_params(
        self, query: ListDimensionParamsQuery
    ) -> List[Dict[str, Any]]:
        """查询评估维度的参数列表（按 ui_order 排序）。

        与 servicers.py ListDimensionParams 一致：
        - 按 dimension_id 查询未删除的 EvaluationDimensionParam
        - 返回 dict 列表
        """
        return dimension_param_repository.list_by_dimension(query.dimension_id)
