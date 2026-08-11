# -*- coding: utf-8 -*-
"""algorithm_service domain 仓储接口（ABC）。

infrastructure/persistence/algorithm_repository.py 继承此处的 ABC，
实现依赖倒置。
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class IAlgorithmGroupRepository(ABC):
    """算法分组聚合根仓储接口。"""

    @abstractmethod
    def get_by_id(self, group_id: int) -> Optional[Any]:
        ...

    @abstractmethod
    def save(self, aggregate: Any) -> None:
        ...

    @abstractmethod
    def add(self, aggregate: Any) -> int:
        ...

    @abstractmethod
    def soft_delete(self, group_id: int) -> bool:
        ...


class IAlgorithmDefinitionRepository(ABC):
    """算法定义聚合根仓储接口。"""

    @abstractmethod
    def get_by_id(self, definition_id: int) -> Optional[Any]:
        ...

    @abstractmethod
    def save(self, aggregate: Any) -> None:
        ...

    @abstractmethod
    def add(self, aggregate: Any) -> int:
        ...

    @abstractmethod
    def soft_delete(self, definition_id: int) -> bool:
        ...


class IAlgorithmDefinitionQueryRepository(ABC):
    """算法定义查询仓储接口（返回 dict）。"""

    @abstractmethod
    def list_definitions(self, status: Optional[str] = None,
                         group_id: Optional[int] = None) -> List[Dict[str, Any]]:
        ...


class IAlgorithmGroupQueryRepository(ABC):
    """算法分组查询仓储接口（返回 dict）。"""

    @abstractmethod
    def find_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        ...


class IDeviceParamRepository(ABC):
    """设备参数仓储接口（返回 dict）。"""

    @abstractmethod
    def create_import_device_param(self, data: Dict[str, Any]) -> Dict[str, Any]:
        ...


class IDimensionParamRepository(ABC):
    """评估维度参数仓储接口（返回 dict）。"""

    @abstractmethod
    def list_by_dimension(self, dimension_id: int) -> List[Dict[str, Any]]:
        ...


class IDimensionRelationQueryRepository(ABC):
    """算法-维度关联查询仓储接口（返回 dict）。"""

    @abstractmethod
    def list_by_algorithm_definition(self, definition_id: int) -> List[Dict[str, Any]]:
        ...


class IParamMappingQueryRepository(ABC):
    """参数映射查询仓储接口（返回 dict）。"""

    @abstractmethod
    def list_by_dimension(self, dimension_id: int) -> List[Dict[str, Any]]:
        ...
