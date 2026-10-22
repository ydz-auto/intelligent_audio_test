# -*- coding: utf-8 -*-
"""算法命令/查询处理器（CQRS - Handler 侧）。

归属：algorithm_service.application.handlers

说明：
- AlgorithmCommandHandler: 处理所有写命令，通过 repository 操作领域聚合根，
  不直接 import PO，隔离领域层与 ORM。
- AlgorithmQueryHandler: 处理所有读查询，返回领域聚合根/聚合根列表。
- Handler 不持有业务规则，业务规则由 domain 层聚合根/领域服务承载；
  Handler 仅负责：构造聚合根 → 调用 repository → 返回结果。
- 命令处理失败时抛出 ValueError，由上层统一捕获转换为 HTTP 响应。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from algorithm_service.domain.entities.algorithm_group import AlgorithmGroupAggregate
from algorithm_service.domain.entities.algorithm_definition import (
    AlgorithmDefinitionAggregate,
    AlgorithmStatus,
)
from algorithm_service.infrastructure.persistence.algorithm_repository import (
    algorithm_group_repository,
    algorithm_definition_repository,
    algorithm_definition_draft_repository,
)
from algorithm_service.application.commands.algorithm_commands import (
    CreateAlgorithmDefinitionCommand,
    CreateAlgorithmGroupCommand,
    DeleteAlgorithmDefinitionCommand,
    DeleteAlgorithmGroupCommand,
    DeprecateAlgorithmCommand,
    UpdateAlgorithmDefinitionCommand,
    UpdateAlgorithmGroupCommand,
    ActivateAlgorithmCommand,
    SaveAlgorithmDefinitionCommand,
)
from algorithm_service.application.queries.algorithm_queries import (
    GetAlgorithmDefinitionByTypeQuery,
    GetAlgorithmDefinitionQuery,
    GetAlgorithmGroupQuery,
    ListActiveAlgorithmDefinitionsQuery,
    ListAlgorithmDefinitionsByGroupQuery,
    ListAlgorithmGroupsQuery,
)
from algorithm_service.domain.value_objects.algorithm_save_code import AlgorithmSaveCode
from algorithm_service.infrastructure.acl.algorithm_acl_gateway import (
    validate_dimension_ids_exist,
)


# PO 口径状态字符串 → AlgorithmStatus（与持久层 _status_from_po 转换口径一致，未知值按 draft）
_STATUS_STR_TO_ENUM = {
    'online': AlgorithmStatus.ACTIVE,
    'offline': AlgorithmStatus.DEPRECATED,
    'draft': AlgorithmStatus.DRAFT,
}


def _status_str_to_enum(status: str) -> AlgorithmStatus:
    return _STATUS_STR_TO_ENUM.get(status, AlgorithmStatus.DRAFT)


def _normalize_mappings(mappings: Any) -> List[Dict[str, Any]]:
    """映射 payload 归一为平铺列表。

    兼容两种形态（与旧 Vue 保存路径 payload 口径一致）：
    - dict 按 source 分组：{"device": [{...}, ...], "api": [...]} →
      展开为 item 自带 source 的列表
    - list 平铺：[{"source": "device", ...}, ...] 原样返回
    """
    if not mappings:
        return []
    if isinstance(mappings, dict):
        result = []
        for source, items in mappings.items():
            for item in items or []:
                if not isinstance(item, dict):
                    continue
                row = dict(item)
                row.setdefault('source', source)
                result.append(row)
        return result
    if isinstance(mappings, list):
        return [dict(item) for item in mappings if isinstance(item, dict)]
    return []


class AlgorithmCommandHandler:
    """算法命令处理器。

    处理算法分组/算法定义的增删改及状态变更命令。
    通过 algorithm_group_repository / algorithm_definition_repository
    操作领域聚合根，不直接 import PO。
    """

    # ========== 算法分组命令 ==========

    def handle_create_group(self, cmd: CreateAlgorithmGroupCommand) -> int:
        """处理创建算法分组命令，返回新分组ID。

        - 构造 AlgorithmGroupAggregate 聚合根
        - 调用 repository.add 持久化
        """
        aggregate = AlgorithmGroupAggregate(
            id=0,  # 新建占位，由 repository.add 回填
            name=cmd.name,
            description=cmd.description,
            algorithm_type=cmd.algorithm_type,
            icon=cmd.icon,
            display_order=cmd.display_order if cmd.display_order is not None else 0,
            deleted=False,
        )
        return algorithm_group_repository.add(aggregate)

    def handle_update_group(self, cmd: UpdateAlgorithmGroupCommand) -> None:
        """处理更新算法分组命令（PATCH 语义：icon/display_order 为 None 不改现值）。

        - 加载已有聚合根
        - 更新可写字段（name / description，icon/display_order 仅非 None 覆盖）
        - 调用 repository.save 持久化
        """
        aggregate = algorithm_group_repository.get_by_id(cmd.id)
        if aggregate is None:
            raise ValueError(f"算法分组 id={cmd.id} 不存在，无法更新")
        aggregate.name = cmd.name
        aggregate.description = cmd.description
        if cmd.icon is not None:
            aggregate.icon = cmd.icon
        if cmd.display_order is not None:
            aggregate.display_order = cmd.display_order
        algorithm_group_repository.save(aggregate)

    def handle_delete_group(self, cmd: DeleteAlgorithmGroupCommand) -> bool:
        """处理删除算法分组命令（软删除），返回是否成功。"""
        return algorithm_group_repository.soft_delete(cmd.id)

    # ========== 算法定义命令 ==========

    def handle_create_definition(self, cmd: CreateAlgorithmDefinitionCommand) -> int:
        """处理创建算法定义命令，返回新算法定义ID。

        - 构造 AlgorithmDefinitionAggregate 聚合根
        - 应用命令提交的 status（online/offline/draft；缺省按 draft）
        - 调用 repository.add 持久化
        """
        aggregate = AlgorithmDefinitionAggregate(
            id=0,  # 新建占位，由 repository.add 回填
            group_id=cmd.group_id,
            name=cmd.name,
            algorithm_type=cmd.algorithm_type,
            description=cmd.description,
            status=_status_str_to_enum(cmd.status) if cmd.status else AlgorithmStatus.DRAFT,
            icon=cmd.icon,
            display_order=cmd.display_order or 0,
        )
        return algorithm_definition_repository.add(aggregate)

    def handle_update_definition(self, cmd: UpdateAlgorithmDefinitionCommand) -> None:
        """处理更新算法定义命令（PATCH 语义：仅覆盖命令携带的非 None 字段）。

        - 加载已有聚合根
        - 更新可写字段（name / description / group_id / status / icon / display_order）
        - 调用 repository.save 持久化

        PATCH 语义的动机：部分更新（如算法列表启用/禁用仅携带 status）此前会
        把 name 强制覆盖为 ""、description 覆盖为 None；分组/状态/图标/排序
        亦被静默丢弃（模态窗假成功）。字段为 None 一律不改动现值。
        """
        aggregate = algorithm_definition_repository.get_by_id(cmd.id)
        if aggregate is None:
            raise ValueError(f"算法定义 id={cmd.id} 不存在，无法更新")
        if cmd.name is not None:
            aggregate.name = cmd.name
        if cmd.description is not None:
            aggregate.description = cmd.description
        if cmd.group_id is not None:
            aggregate.group_id = cmd.group_id
        if cmd.status is not None:
            aggregate.status = _status_str_to_enum(cmd.status)
        if cmd.icon is not None:
            aggregate.icon = cmd.icon
        if cmd.display_order is not None:
            aggregate.display_order = cmd.display_order
        algorithm_definition_repository.save(aggregate)

    def handle_delete_definition(self, cmd: DeleteAlgorithmDefinitionCommand) -> bool:
        """处理删除算法定义命令（软删除），返回是否成功。"""
        return algorithm_definition_repository.soft_delete(cmd.id)

    # ========== 算法状态变更命令 ==========

    def handle_activate_algorithm(self, cmd: ActivateAlgorithmCommand) -> None:
        """处理上线算法命令。

        - 加载已有聚合根
        - 调用聚合根 activate 方法变更状态
        - 调用 repository.save 持久化
        """
        aggregate = algorithm_definition_repository.get_by_id(cmd.id)
        if aggregate is None:
            raise ValueError(f"算法定义 id={cmd.id} 不存在，无法上线")
        aggregate.activate()
        algorithm_definition_repository.save(aggregate)

    def handle_deprecate_algorithm(self, cmd: DeprecateAlgorithmCommand) -> None:
        """处理废弃算法命令。

        - 加载已有聚合根
        - 调用聚合根 deprecate 方法变更状态
        - 调用 repository.save 持久化
        """
        aggregate = algorithm_definition_repository.get_by_id(cmd.id)
        if aggregate is None:
            raise ValueError(f"算法定义 id={cmd.id} 不存在，无法废弃")
        aggregate.deprecate()
        algorithm_definition_repository.save(aggregate)

    # ========== 算法定义全量保存（INT-589） ==========

    def handle_save_definition(
        self, cmd: SaveAlgorithmDefinitionCommand
    ) -> Dict[str, Any]:
        """处理算法定义全量保存命令（聚合事务 + 乐观锁）。

        一次提交完整定义 + 六类子实体，原子落库。发布路径校验
        associated_dimensions 维度存在性（草稿保存不做）。

        - 校验失败（algorithm_type/name 缺失、维度不存在、type 已存在）
          抛 ValueError → 上层映射 VALIDATION_FAILED
        - 乐观锁冲突返回 {"code": "CONFLICT"}（不抛异常）
        - 成功返回 {"code": "SAVED"/"OK", "id": ..., "algorithm_type": ...}
        - 发布成功后清除草稿快照（清除失败不阻断发布结果）
        """
        if not cmd.algorithm_type:
            raise ValueError('algorithm_type 必填')
        if not cmd.name:
            raise ValueError('name 必填')
        if cmd.id and not cmd.expected_updated_at:
            raise ValueError('更新算法定义必须携带 expected_updated_at（乐观锁版本）')

        mappings = _normalize_mappings(cmd.mappings)
        sub_entities = {
            'device_params': cmd.device_params or [],
            'api_params': cmd.api_params or [],
            'case_params': cmd.case_params or [],
            'reference_params': cmd.reference_params or [],
            'mappings': mappings,
            'associated_dimensions': cmd.associated_dimensions or [],
        }

        # 发布校验：associated_dimensions 的 dimension_id 存在性
        dimension_ids = _as_dimension_ids(cmd.associated_dimensions)
        missing = validate_dimension_ids_exist(dimension_ids)
        if missing:
            raise ValueError(f'关联评估维度不存在，请先创建: {missing}')

        aggregate = AlgorithmDefinitionAggregate(
            id=cmd.id or 0,
            group_id=cmd.group_id,
            name=cmd.name,
            algorithm_type=cmd.algorithm_type,
            description=cmd.description,
            status=(
                _status_str_to_enum(cmd.status)
                if cmd.status else AlgorithmStatus.ACTIVE
            ),
            icon=cmd.icon,
            display_order=cmd.display_order or 0,
        )
        code = algorithm_definition_repository.save_full(
            aggregate,
            sub_entities,
            expected_updated_at=cmd.expected_updated_at,
        )

        if code in (AlgorithmSaveCode.SAVED.value, AlgorithmSaveCode.OK.value):
            try:
                algorithm_definition_draft_repository.clear_snapshot(
                    cmd.algorithm_type
                )
            except Exception:
                # 草稿清除失败不阻断发布结果（快照残留可下次发布覆盖）
                pass
            return {
                'code': code,
                'id': aggregate.id,
                'algorithm_type': cmd.algorithm_type,
            }
        # CONFLICT
        return {'code': code, 'id': cmd.id or 0, 'algorithm_type': cmd.algorithm_type}

    def handle_save_draft(self, algorithm_type: str, snapshot: Any) -> Optional[Any]:
        """处理草稿自动保存（30s 快照，不落正式六表）。

        Returns:
            服务端最后保存时间（draft PO.updated_at，datetime），供草稿
            保存响应补 saved_at（INT-683）；无则返回 None。
        """
        if not algorithm_type:
            raise ValueError('algorithm_type 必填')
        if snapshot is None:
            raise ValueError('草稿快照不能为空')
        return algorithm_definition_draft_repository.save_snapshot(algorithm_type, snapshot)

    def handle_clear_draft(self, algorithm_type: str) -> bool:
        """发布成功后清除草稿快照，返回是否清除。"""
        if not algorithm_type:
            return False
        return algorithm_definition_draft_repository.clear_snapshot(algorithm_type)


def _as_dimension_ids(associated_dimensions: Any) -> List[int]:
    """从 associated_dimensions payload 提取维度 ID 整数列表。"""
    result = []
    for item in associated_dimensions or []:
        dim_id = item.get('dimension_id') if isinstance(item, dict) else None
        if dim_id is None:
            continue
        try:
            result.append(int(dim_id))
        except (TypeError, ValueError):
            continue
    return result


class AlgorithmQueryHandler:
    """算法查询处理器。

    处理算法分组/算法定义的查询请求，返回领域聚合根/聚合根列表。
    通过 algorithm_group_repository / algorithm_definition_repository 查询，
    不直接 import PO。
    """

    # ========== 算法分组查询 ==========

    def handle_get_group(self, query: GetAlgorithmGroupQuery) -> Optional[AlgorithmGroupAggregate]:
        """按 ID 查询算法分组聚合根。"""
        return algorithm_group_repository.get_by_id(query.id)

    def handle_list_groups(
        self, query: ListAlgorithmGroupsQuery
    ) -> Tuple[List[AlgorithmGroupAggregate], int]:
        """分页查询算法分组列表，返回 (当前页数据, 总数)。

        - repository.get_all 返回全部未删除分组，在此做内存分页
        - 适用于分组数量较少的场景；如分组量大，后续可下沉分页到 SQL
        """
        all_groups = algorithm_group_repository.get_all()
        total = len(all_groups)
        # 页码从 1 开始，计算起止索引
        start = (query.page - 1) * query.page_size
        if start < 0:
            start = 0
        end = start + query.page_size
        return all_groups[start:end], total

    # ========== 算法定义查询 ==========

    def handle_get_definition(
        self, query: GetAlgorithmDefinitionQuery
    ) -> Optional[AlgorithmDefinitionAggregate]:
        """按 ID 查询算法定义聚合根。"""
        return algorithm_definition_repository.get_by_id(query.id)

    def handle_list_definitions_by_group(
        self, query: ListAlgorithmDefinitionsByGroupQuery
    ) -> List[AlgorithmDefinitionAggregate]:
        """按分组 ID 查询算法定义聚合根列表。"""
        return algorithm_definition_repository.get_by_group(query.group_id)

    def handle_get_definition_by_type(
        self, query: GetAlgorithmDefinitionByTypeQuery
    ) -> Optional[AlgorithmDefinitionAggregate]:
        """按算法类型代码查询算法定义聚合根。"""
        return algorithm_definition_repository.get_by_type(query.algorithm_type)

    def handle_list_active_definitions(
        self, query: ListActiveAlgorithmDefinitionsQuery
    ) -> List[AlgorithmDefinitionAggregate]:
        """查询全部上线状态的算法定义聚合根列表。"""
        return algorithm_definition_repository.list_all_active()

    def handle_get_definition_draft(
        self, algorithm_type: str
    ) -> Optional[Dict[str, Any]]:
        """读取算法定义草稿快照（前端编辑恢复），不存在返回 None。"""
        if not algorithm_type:
            return None
        return algorithm_definition_draft_repository.get_snapshot(algorithm_type)
