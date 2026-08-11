# -*- coding: utf-8 -*-
"""评估维度 CRUD 仓储接口（ABC）

Domain 层通过此接口访问 Category / Dimension 等自有 PO 的 CRUD 操作，
不直接依赖 infrastructure/persistence。

注意：
- Category/Dimension 返回 ORM PO 对象（用 Any 标注，避免 domain → infrastructure 依赖）。
- gRPC 委托方法返回 dataclass DTO 列表（DimensionRelationDTO / DimensionParamDTO / ParamMappingDTO）。
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Set

from evaluation_service.domain.dto import (
    DimensionParamDTO,
    DimensionRelationDTO,
    ParamMappingDTO,
)


class EvaluationRepositoryABC(ABC):
    """评估维度 CRUD 仓储抽象接口

    涵盖 Category / Dimension 的本地 CRUD，以及通过 gRPC 访问
    algorithm_service 的 AlgorithmDimensionRelation / EvaluationDimensionParam /
    ParamMapping 的委托方法。
    """

    # ========== Category CRUD ==========

    @abstractmethod
    def get_category_by_name(self, name: str) -> Optional[Any]:
        """按名称查询未删除的分类。"""
        ...

    @abstractmethod
    def get_category_by_id(self, cat_id: int) -> Optional[Any]:
        """按 ID 查询分类（含已删除）。"""
        ...

    @abstractmethod
    def create_category(self, data: Dict[str, Any]) -> Any:
        """创建分类（含 flush，未 commit）。"""
        ...

    @abstractmethod
    def list_categories(self) -> List[Any]:
        """查询所有未删除分类。"""
        ...

    # ========== Dimension CRUD ==========

    @abstractmethod
    def get_dimension(self, dim_id: int) -> Optional[Any]:
        """按 ID 查询单个维度（含已删除）。"""
        ...

    @abstractmethod
    def create_dimension(self, create_data: Dict[str, Any]) -> Any:
        """创建维度记录（含 flush，未 commit）。"""
        ...

    @abstractmethod
    def soft_delete_dimension(self, dim: Any) -> None:
        """软删除维度（含 flush，未 commit）。"""
        ...

    @abstractmethod
    def batch_update_dimensions(
        self, ids: List[int], update_data: Dict[str, Any]
    ) -> int:
        """按 ID 列表批量更新维度（含 flush，未 commit）。返回受影响行数。"""
        ...

    @abstractmethod
    def list_dimensions_by_ids(self, ids: List[int]) -> List[Any]:
        """按 ID 列表查询维度。"""
        ...

    @abstractmethod
    def list_sub_dimensions(self, parent_id: int) -> List[Any]:
        """查询某主维度下未删除的子维度。"""
        ...

    @abstractmethod
    def query_dimensions_paginated(
        self,
        category_id: Optional[int] = None,
        page: int = 1,
        per_page: int = 10,
        search: str = '',
    ) -> Any:
        """分页查询维度（带搜索）。"""
        ...

    @abstractmethod
    def list_dimension_options(self, algorithm_type: str = '') -> List[Any]:
        """查询维度选项列表（可按 algorithm_type 过滤）。"""
        ...

    @abstractmethod
    def update_dimension_attrs(self, dim: Any, data: Dict[str, Any]) -> None:
        """更新维度可赋值字段（含 flush，未 commit）。"""
        ...

    # ========== AlgorithmDimensionRelation 管理（gRPC） ==========

    @abstractmethod
    def delete_relations_by_dimension(self, dim_id: int) -> bool:
        """按维度 ID 删除所有算法-维度关联（gRPC）。"""
        ...

    @abstractmethod
    def add_relation(self, data: Dict[str, Any]) -> bool:
        """创建单条算法-维度关联（gRPC）。"""
        ...

    @abstractmethod
    def sync_relations(
        self, dim_id: int, relations: List[Dict[str, Any]]
    ) -> bool:
        """同步算法-维度关联（先清空旧关联再插入新关联，gRPC）。"""
        ...

    @abstractmethod
    def list_relations_by_dimension(
        self, dim_id: int
    ) -> List[DimensionRelationDTO]:
        """查询维度关联的未删除算法-维度关联列表（gRPC，返回 DTO 列表）。"""
        ...

    # ========== EvaluationDimensionParam 管理（gRPC） ==========

    @abstractmethod
    def delete_input_params_by_dimension(self, dim_id: int) -> bool:
        """按维度 ID 删除所有 input 方向参数（gRPC）。"""
        ...

    @abstractmethod
    def delete_output_params_by_dimension(self, dim_id: int) -> bool:
        """按维度 ID 删除所有 output 方向参数（gRPC）。"""
        ...

    @abstractmethod
    def add_dimension_param(self, data: Dict[str, Any]) -> Optional[int]:
        """创建单条评估维度参数（gRPC）。返回新 param_id 或 None。"""
        ...

    @abstractmethod
    def list_dimension_params(
        self, dim_id: int
    ) -> List[DimensionParamDTO]:
        """查询评估维度的参数列表（gRPC，返回 DTO 列表）。"""
        ...

    @abstractmethod
    def find_audio_dimension_ids(self, dim_ids: List[int]) -> Set[int]:
        """查询需要音频文件参数的维度 ID 集合（gRPC）。"""
        ...

    # ========== ParamMapping 同步（gRPC） ==========

    @abstractmethod
    def list_param_mappings_for_dimension(
        self, dimension_id: int
    ) -> List[ParamMappingDTO]:
        """查询某维度所有 ParamMapping（含软删除项，用于同步逻辑，gRPC，返回 DTO 列表）。"""
        ...

    @abstractmethod
    def sync_param_mappings(
        self,
        dimension_id: int,
        params: Any,
        direction: str = 'output',
        algorithm_type: str = 'voice_llm',
    ) -> bool:
        """同步 ParamMapping（gRPC 委托）。"""
        ...

    # ========== 事务控制（仅限本服务自有 PO） ==========

    @abstractmethod
    def commit(self) -> None:
        """提交事务。"""
        ...

    @abstractmethod
    def rollback(self) -> None:
        """回滚事务。"""
        ...

    @abstractmethod
    def flush(self) -> None:
        """flush session。"""
        ...
