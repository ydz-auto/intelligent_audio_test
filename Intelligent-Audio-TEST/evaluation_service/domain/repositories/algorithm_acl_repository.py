# -*- coding: utf-8 -*-
"""algorithm_service 防腐层仓储接口（ABC）

Domain 层通过此接口访问 algorithm_service 数据，不直接依赖 infrastructure/acl。

返回值约定：
- 读操作返回 dataclass DTO 或 DTO 列表，不返回 dict。
- 写操作返回 bool/Optional[int]。
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from evaluation_service.domain.dto import (
    DimensionParamDTO,
    DimensionRelationDTO,
    ParamMappingDTO,
)


class AlgorithmAclRepository(ABC):
    """algorithm_service 防腐层仓储抽象接口"""

    # ========== 维度关系管理 ==========

    @abstractmethod
    def sync_dimension_relations(
        self, dimension_id: int, relations: List[Dict[str, Any]]
    ) -> bool:
        """同步算法-维度关联（先清空旧关联再插入新关联）。"""
        ...

    @abstractmethod
    def get_relations_by_dimension(self, dimension_id: int) -> List[DimensionRelationDTO]:
        """按 dimension_id 查询未删除的算法-维度关联列表。"""
        ...

    # ========== 评估维度参数管理 ==========

    @abstractmethod
    def create_dimension_param(self, param_data: Dict[str, Any]) -> Optional[int]:
        """创建单条评估维度参数。返回新 param_id 或 None。"""
        ...

    @abstractmethod
    def delete_dimension_params_by_direction(
        self, dimension_id: int, param_direction: str
    ) -> bool:
        """按 dimension_id + param_direction 物理删除评估维度参数。"""
        ...

    @abstractmethod
    def get_dimension_params(self, dimension_id: int) -> List[DimensionParamDTO]:
        """获取评估维度的参数列表（含 output/input 完整字段）。"""
        ...

    @abstractmethod
    def find_audio_dimension_ids(self, dim_ids: List[int]) -> set:
        """查询需要音频文件参数的维度 ID 集合。"""
        ...

    # ========== 参数映射同步 ==========

    @abstractmethod
    def list_param_mappings_for_dimension(self, dimension_id: int) -> List[ParamMappingDTO]:
        """查询某维度所有 ParamMapping（含软删除项，用于同步逻辑）。"""
        ...

    @abstractmethod
    def sync_param_mappings(
        self,
        dimension_id: int,
        params: Any,
        direction: str = 'output',
        algorithm_type: str = 'voice_llm',
    ) -> bool:
        """同步 ParamMapping。"""
        ...
