# -*- coding: utf-8 -*-
"""算法分组/算法定义领域仓储 — 返回领域实体（Aggregate），做 PO ↔ Entity 显式转换。

与 task_service/infrastructure/persistence/algorithm_repository.py 的区别：
- task_service 版本: 旧式仓储，返回 PO（ORM 对象），供 CRUD handler 用
- algorithm_service 版本（本文件）: 新式 DDD 仓储，返回领域聚合根，
  供领域服务用，隔离领域层与 ORM

PO ↔ Entity 转换规则：
- AlgorithmGroup PO → AlgorithmGroupAggregate 聚合根
- AlgorithmDefinition PO → AlgorithmDefinitionAggregate 聚合根
  （含 device_params / api_params / dimension_relations 子实体）
- AlgorithmDeviceParam / AlgorithmApiParam / AlgorithmReferenceParam PO
  → AlgorithmParamEntity（通过 param_kind 区分类别）

字段映射注意事项：
- AlgorithmGroup PO 无 algorithm_type 列，实体该字段加载为 None
- AlgorithmDefinition PO.type ↔ Entity.algorithm_type
- AlgorithmDefinition PO.status（'online'/'offline'）↔ AlgorithmStatus 枚举
  （active→online / deprecated→offline / draft→draft）
- AlgorithmDefinition PO 无 version 列，实体使用默认 '1.0.0'
- 参数 PO 通过 algorithm_type 关联，Entity 用 definition_id；
  转换时由 _definition_po_to_entity 传入聚合根 id 回填
- AlgorithmDefinition PO 无 reference_params 关系，实体该列表加载为空

模块组织（原单文件 854 行，按职责拆分为多个实现模块，本文件保持对外导入路径稳定）：
- _algorithm_converters.py: PO ↔ Entity 转换函数（模块私有，仅内部使用）
- _algorithm_aggregate_repositories.py: 聚合根仓储（分组/定义）
- _algorithm_query_repositories.py: dict 查询仓储（定义/分组）+ _po_to_dict 辅助
- _algorithm_dimension_repositories.py: 维度/映射/设备参数 ACL 仓储

兼容性约定：
- 所有历史导入路径与符号保持不变（类、模块级单例、事务函数）
- 模块私有辅助函数（_po_to_dict 等）随实现模块迁移，仅内部引用，不影响外部
"""
from __future__ import annotations

from algorithm_service.infrastructure.persistence._algorithm_aggregate_repositories import (
    AlgorithmGroupRepository,
    AlgorithmDefinitionRepository,
)
from algorithm_service.infrastructure.persistence._algorithm_query_repositories import (
    AlgorithmDefinitionQueryRepository,
    AlgorithmGroupQueryRepository,
)
from algorithm_service.infrastructure.persistence._algorithm_dimension_repositories import (
    DeviceParamRepository,
    DimensionParamRepository,
    DimensionRelationQueryRepository,
    ParamMappingQueryRepository,
)
from shared.models.database import get_db_session


# ========== 模块级单例 ==========

algorithm_group_repository = AlgorithmGroupRepository()
algorithm_definition_repository = AlgorithmDefinitionRepository()
algorithm_definition_query_repository = AlgorithmDefinitionQueryRepository()
algorithm_group_query_repository = AlgorithmGroupQueryRepository()
device_param_repository = DeviceParamRepository()
dimension_param_repository = DimensionParamRepository()
dimension_relation_query_repository = DimensionRelationQueryRepository()
param_mapping_query_repository = ParamMappingQueryRepository()


# ========== 事务控制包装（供 servicer 委托，不直连 get_db_session） ==========

def commit_transaction():
    """提交当前 DB 事务。"""
    get_db_session().commit()


def rollback_transaction():
    """回滚当前 DB 事务。"""
    get_db_session().rollback()


def flush_transaction():
    """flush 当前 DB session。"""
    get_db_session().flush()
