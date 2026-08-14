# -*- coding: utf-8 -*-
"""algorithm_service 防腐层仓储接口（ABC）。

Domain 层通过此接口访问 algorithm_service 数据，不直接依赖 infrastructure/acl。
infrastructure/acl/algorithm_acl_repository.AlgorithmRepository 继承此 ABC 实现。

返回值约定：
- 读操作（find/get/list）返回 dataclass DTO 或 DTO 列表，不返回 dict。
- 写操作（create/update/delete）返回 DTO（create）或 None（update/delete）。
- 跨域 Dimension 查询返回 DTO（DimensionDTO）。
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from task_service.domain.dto import (
    AlgorithmDefinitionDTO, AlgorithmGroupDTO,
    DeviceParamDTO, ApiParamDTO, CaseParamDTO,
    ReferenceParamDTO, ParamMappingDTO,
    DimensionRelationDTO, DimensionParamDTO,
    DimensionDTO, CreateAckDTO,
)


class AlgorithmAclRepository(ABC):
    """算法参数/映射/维度关联仓储接口（防腐层）。"""

    # ========== 设备参数 / API 参数 CRUD ==========

    @abstractmethod
    def create_device_param(self, data: dict) -> Optional[DeviceParamDTO]:
        ...

    @abstractmethod
    def create_api_param(self, data: dict) -> Optional[ApiParamDTO]:
        ...

    @abstractmethod
    def find_device_param_by_code(self, algorithm_type: str, param_code: str, direction: str) -> Optional[DeviceParamDTO]:
        ...

    @abstractmethod
    def find_api_param_by_code(self, algorithm_type: str, param_code: str, direction: str) -> Optional[ApiParamDTO]:
        ...

    @abstractmethod
    def get_device_param(self, param_id: int) -> Optional[DeviceParamDTO]:
        ...

    @abstractmethod
    def get_api_param(self, param_id: int) -> Optional[ApiParamDTO]:
        ...

    @abstractmethod
    def list_device_params(self, algorithm_type: Optional[str] = None) -> List[DeviceParamDTO]:
        ...

    @abstractmethod
    def list_api_params(self, algorithm_type: Optional[str] = None) -> List[ApiParamDTO]:
        ...

    @abstractmethod
    def update_param_attrs(self, param, fields: Dict[str, Any]) -> None:
        ...

    @abstractmethod
    def soft_delete_param(self, param) -> None:
        ...

    # ========== 用例专属参数 CRUD ==========

    @abstractmethod
    def find_case_param_by_code(self, algorithm_type: str, param_code: str, deleted: bool = False) -> Optional[CaseParamDTO]:
        ...

    @abstractmethod
    def create_case_param(self, data: dict) -> Optional[CaseParamDTO]:
        ...

    @abstractmethod
    def get_case_param(self, param_id: int) -> Optional[CaseParamDTO]:
        ...

    @abstractmethod
    def list_case_params(self, algorithm_type: Optional[str] = None, scope: Optional[str] = None) -> List[CaseParamDTO]:
        ...

    @abstractmethod
    def list_case_params_for_schema(self, algorithm_type: str) -> List[CaseParamDTO]:
        ...

    # ========== 参考参数 CRUD ==========

    @abstractmethod
    def find_reference_param(self, algorithm_type: str, code: str) -> Optional[ReferenceParamDTO]:
        ...

    @abstractmethod
    def create_reference_param(self, data: dict) -> Optional[ReferenceParamDTO]:
        ...

    @abstractmethod
    def get_reference_param(self, param_id: int) -> Optional[ReferenceParamDTO]:
        ...

    @abstractmethod
    def list_reference_params(self, algorithm_type: str) -> List[ReferenceParamDTO]:
        ...

    # ========== 参数映射 CRUD ==========

    @abstractmethod
    def create_mapping(self, data: dict) -> Optional[ParamMappingDTO]:
        ...

    @abstractmethod
    def get_mapping(self, mapping_id: int) -> Optional[ParamMappingDTO]:
        ...

    @abstractmethod
    def list_mappings(self, algorithm_type: Optional[str] = None, source_type: Optional[str] = None, dimension_id: Optional[int] = None) -> List[ParamMappingDTO]:
        ...

    @abstractmethod
    def update_mapping_attrs(self, mapping, data: dict) -> None:
        ...

    @abstractmethod
    def soft_delete_mapping(self, mapping) -> None:
        ...

    # ========== 维度关联 CRUD ==========

    @abstractmethod
    def soft_delete_algorithm_dimension_relations(self, algorithm_type: str) -> None:
        ...

    @abstractmethod
    def create_dimension_relation(self, data: dict) -> Optional[DimensionRelationDTO]:
        ...

    @abstractmethod
    def find_dimension_relation(self, algorithm_type: str, dimension_id: int) -> Optional[DimensionRelationDTO]:
        ...

    @abstractmethod
    def get_dimension_relation(self, relation_id: int) -> Optional[DimensionRelationDTO]:
        ...

    @abstractmethod
    def list_dimension_relations(self, algorithm_type: str = "") -> List[DimensionRelationDTO]:
        ...

    @abstractmethod
    def update_dimension_relation_attrs(self, relation, data: dict) -> None:
        ...

    @abstractmethod
    def soft_delete_dimension_relation(self, relation) -> None:
        ...

    # ========== 评估维度参数 ==========

    @abstractmethod
    def list_dimension_params(self, dimension_id: int) -> List[DimensionParamDTO]:
        ...

    # ========== 算法定义 ==========

    @abstractmethod
    def find_algorithm_by_type(self, algorithm_type: str) -> Optional[AlgorithmDefinitionDTO]:
        ...

    @abstractmethod
    def create_algorithm_definition(self, data: dict) -> Optional[AlgorithmDefinitionDTO]:
        ...

    @abstractmethod
    def update_algorithm_definition_attrs(self, algo_def, data: dict) -> None:
        ...

    @abstractmethod
    def soft_delete_algorithm(self, algo_def) -> None:
        ...

    @abstractmethod
    def list_algorithm_definitions(self, status: Optional[str] = None, group_id: Optional[int] = None) -> List[AlgorithmDefinitionDTO]:
        ...

    @abstractmethod
    def list_online_algorithm_definitions(self) -> List[AlgorithmDefinitionDTO]:
        ...

    @abstractmethod
    def count_algorithms_in_group(self, group_id: int) -> int:
        ...

    @abstractmethod
    def create_import_device_param(self, param_data: dict) -> Optional[DeviceParamDTO]:
        ...

    @abstractmethod
    def list_algorithm_definitions_for_bulk_delete(self, group_id: Optional[int] = None) -> List[AlgorithmDefinitionDTO]:
        ...

    # ========== 算法分组 ==========

    @abstractmethod
    def find_group_by_name(self, name: str) -> Optional[AlgorithmGroupDTO]:
        ...

    @abstractmethod
    def get_group(self, group_id: int) -> Optional[AlgorithmGroupDTO]:
        ...

    @abstractmethod
    def create_group(self, data: dict) -> Optional[AlgorithmGroupDTO]:
        ...

    @abstractmethod
    def update_group_attrs(self, group, data: dict) -> None:
        ...

    @abstractmethod
    def soft_delete_group(self, group) -> None:
        ...

    @abstractmethod
    def list_groups(self) -> List[AlgorithmGroupDTO]:
        ...

    @abstractmethod
    def count_algorithms_in_group_for_group(self, group_id: int) -> int:
        ...

    # ========== 跨域 Dimension 查询（evaluation_service） ==========

    @abstractmethod
    def get_dimension_by_id(self, dim_id) -> Optional[DimensionDTO]:
        ...

    @abstractmethod
    def list_dimensions_by_ids(self, dim_ids: List[int]) -> List[DimensionDTO]:
        ...

    @abstractmethod
    def list_dimensions_map_by_ids(self, dim_ids: List[int]) -> Dict[int, DimensionDTO]:
        ...

    @abstractmethod
    def list_dimension_names_map_by_ids(self, dim_ids: List[int]) -> Dict[int, str]:
        ...

    # ========== 事务控制 no-op 兼容方法 ==========

    @abstractmethod
    def commit(self):
        ...

    @abstractmethod
    def rollback(self):
        ...

    @abstractmethod
    def flush(self):
        ...
