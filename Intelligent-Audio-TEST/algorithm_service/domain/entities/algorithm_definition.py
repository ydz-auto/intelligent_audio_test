# -*- coding: utf-8 -*-
"""算法定义聚合根（核心聚合根）。

归属：algorithm_service.domain.entities
对应 PO：AlgorithmDefinition（algorithm_definitions 表）

说明：
- 本模块为纯领域层 dataclass，不依赖 SQLAlchemy / db.Model。
- AlgorithmDefinitionAggregate 为 algorithm_service 的核心聚合根，
  聚合 device_params / api_params / reference_params / dimension_relations
  等同域实体。
- AlgorithmStatus 为算法状态枚举（draft 草稿 / active 上线 / deprecated 废弃）。
- 跨域的 Dimension 关系通过 evaluation_service gRPC 查询，不在本聚合内持有。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional

from .algorithm_param import (
    AlgorithmDimensionRelationEntity,
    AlgorithmParamEntity,
)


class AlgorithmStatus(str, Enum):
    """算法状态枚举。"""

    DRAFT = "draft"        # 草稿
    ACTIVE = "active"      # 上线
    DEPRECATED = "deprecated"  # 废弃


@dataclass
class AlgorithmDefinitionAggregate:
    """算法定义聚合根（核心）。

    聚合同域实体：device_params / api_params / reference_params /
    dimension_relations。
    """

    id: int
    group_id: Optional[int]
    name: str
    algorithm_type: str
    description: Optional[str] = None
    version: str = "1.0.0"
    status: AlgorithmStatus = AlgorithmStatus.DRAFT
    device_params: List[AlgorithmParamEntity] = field(default_factory=list)
    api_params: List[AlgorithmParamEntity] = field(default_factory=list)
    reference_params: List[AlgorithmParamEntity] = field(default_factory=list)
    dimension_relations: List[AlgorithmDimensionRelationEntity] = field(default_factory=list)
    deleted: bool = False

    def is_active(self) -> bool:
        """算法是否处于上线状态。"""
        return self.status == AlgorithmStatus.ACTIVE

    def activate(self) -> None:
        """将算法置为上线状态。"""
        self.status = AlgorithmStatus.ACTIVE

    def deprecate(self) -> None:
        """将算法置为废弃状态。"""
        self.status = AlgorithmStatus.DEPRECATED

    def add_device_param(self, param: AlgorithmParamEntity) -> None:
        """新增设备参数实体。"""
        self.device_params.append(param)

    def add_api_param(self, param: AlgorithmParamEntity) -> None:
        """新增 API 参数实体。"""
        self.api_params.append(param)
