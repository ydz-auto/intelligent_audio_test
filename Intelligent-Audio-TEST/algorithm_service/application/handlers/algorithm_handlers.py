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

from typing import List, Optional, Tuple

from algorithm_service.domain.entities.algorithm_group import AlgorithmGroupAggregate
from algorithm_service.domain.entities.algorithm_definition import (
    AlgorithmDefinitionAggregate,
    AlgorithmStatus,
)
from algorithm_service.infrastructure.persistence.algorithm_repository import (
    algorithm_group_repository,
    algorithm_definition_repository,
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
)
from algorithm_service.application.queries.algorithm_queries import (
    GetAlgorithmDefinitionByTypeQuery,
    GetAlgorithmDefinitionQuery,
    GetAlgorithmGroupQuery,
    ListActiveAlgorithmDefinitionsQuery,
    ListAlgorithmDefinitionsByGroupQuery,
    ListAlgorithmGroupsQuery,
)


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
            deleted=False,
        )
        return algorithm_group_repository.add(aggregate)

    def handle_update_group(self, cmd: UpdateAlgorithmGroupCommand) -> None:
        """处理更新算法分组命令。

        - 加载已有聚合根
        - 更新可写字段（name / description）
        - 调用 repository.save 持久化
        """
        aggregate = algorithm_group_repository.get_by_id(cmd.id)
        if aggregate is None:
            raise ValueError(f"算法分组 id={cmd.id} 不存在，无法更新")
        aggregate.name = cmd.name
        aggregate.description = cmd.description
        algorithm_group_repository.save(aggregate)

    def handle_delete_group(self, cmd: DeleteAlgorithmGroupCommand) -> bool:
        """处理删除算法分组命令（软删除），返回是否成功。"""
        return algorithm_group_repository.soft_delete(cmd.id)

    # ========== 算法定义命令 ==========

    def handle_create_definition(self, cmd: CreateAlgorithmDefinitionCommand) -> int:
        """处理创建算法定义命令，返回新算法定义ID。

        - 构造 AlgorithmDefinitionAggregate 聚合根
        - 调用 repository.add 持久化
        """
        aggregate = AlgorithmDefinitionAggregate(
            id=0,  # 新建占位，由 repository.add 回填
            group_id=cmd.group_id,
            name=cmd.name,
            algorithm_type=cmd.algorithm_type,
            description=cmd.description,
            status=AlgorithmStatus.DRAFT,
        )
        return algorithm_definition_repository.add(aggregate)

    def handle_update_definition(self, cmd: UpdateAlgorithmDefinitionCommand) -> None:
        """处理更新算法定义命令。

        - 加载已有聚合根
        - 更新可写字段（name / description）
        - 调用 repository.save 持久化
        """
        aggregate = algorithm_definition_repository.get_by_id(cmd.id)
        if aggregate is None:
            raise ValueError(f"算法定义 id={cmd.id} 不存在，无法更新")
        aggregate.name = cmd.name
        aggregate.description = cmd.description
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
