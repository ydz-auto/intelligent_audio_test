# -*- coding: utf-8 -*-
"""算法参数/映射/维度关联仓储 — gRPC ACL 适配层。

本模块原为直接访问 algorithm_service PO 的仓储，现已改为通过
algorithm_service gRPC 接口访问，彻底消除跨服务 PO / DB 耦合。

- 写操作（Create/Update/Delete/SoftDelete/Revive/...）通过
  AlgorithmDefinitionService / AlgorithmGroupService 的 RPC 完成，
  每个 RPC 自动提交事务。
- 读操作（Find/Get/List/Count）同样通过 gRPC，返回 dict（不再返回 ORM 对象）。
- 事务控制方法 commit/rollback/flush 保留向后兼容，现已为 gRPC 等价 RPC
  的 no-op 形式（每条写 RPC 均自动提交，无法跨调用回滚）。
- 跨域 Dimension 查询保持原有 evaluation_service gRPC 调用不变。

相关 stub：shared.clients.grpc_clients.get_algorithm_definition_service_stub /
get_algorithm_group_service_stub
proto：shared/proto/algorithm_service.proto

按职责拆分为 Mixin 组合（对外 API 不变，导入路径保持本模块）：
- algorithm_acl_param_mixin.AlgorithmParamMixin: 设备/API/用例专属/参考参数 CRUD
- algorithm_acl_mapping_dimension_mixin.AlgorithmMappingDimensionMixin: 参数映射/维度关联/维度参数
- algorithm_acl_definition_group_mixin.AlgorithmDefinitionGroupMixin: 算法定义/算法分组
- algorithm_acl_dimension_query_tx_mixin.AlgorithmDimensionQueryTxMixin: 跨域维度查询/事务兼容/查询服务封装
- 本文件保留 gRPC 响应解析辅助函数与类组合定义。
"""
import logging

from task_service.domain.repositories.algorithm_acl_repository import AlgorithmAclRepository

from task_service.infrastructure.acl.algorithm_acl_grpc_helpers import (
    _get_stub, _group_stub, _items, _one, _raise_on_failure,
)
from task_service.infrastructure.acl.algorithm_acl_param_mixin import AlgorithmParamMixin
from task_service.infrastructure.acl.algorithm_acl_mapping_dimension_mixin import AlgorithmMappingDimensionMixin
from task_service.infrastructure.acl.algorithm_acl_definition_group_mixin import AlgorithmDefinitionGroupMixin
from task_service.infrastructure.acl.algorithm_acl_dimension_query_tx_mixin import AlgorithmDimensionQueryTxMixin

_logger = logging.getLogger(__name__)


class AlgorithmRepository(
    AlgorithmParamMixin,
    AlgorithmMappingDimensionMixin,
    AlgorithmDefinitionGroupMixin,
    AlgorithmDimensionQueryTxMixin,
    AlgorithmAclRepository,
):
    """算法参数/映射/维度关联仓储（gRPC ACL 适配层）。

    继承 domain ABC 实现依赖倒置。

    职责拆分为四个 Mixin 组合：
    - AlgorithmParamMixin: 设备/API/用例专属/参考参数 CRUD
    - AlgorithmMappingDimensionMixin: 参数映射/维度关联/维度参数
    - AlgorithmDefinitionGroupMixin: 算法定义/算法分组
    - AlgorithmDimensionQueryTxMixin: 跨域维度查询/事务兼容/查询服务封装
    """

    # 所有方法实现分布于上方 Mixin；本类仅负责组合与依赖倒置继承。
