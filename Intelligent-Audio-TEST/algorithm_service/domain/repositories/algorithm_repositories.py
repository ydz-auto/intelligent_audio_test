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

    @abstractmethod
    def save_full(
        self,
        aggregate: Any,
        sub_entities: Dict[str, Any],
        expected_updated_at: Optional[str] = None,
    ) -> str:
        """聚合全量保存（INT-589）。

        同 session 内 upsert 根 + 六类子实体（device/api/case 参数、
        mappings、associated_dimensions、reference_params），单次
        commit/rollback，任一步失败整体回滚。

        - aggregate.id 为 0/None → 新建；否则按 id 更新（CAS 乐观锁）
        - expected_updated_at 提供时做 CAS 条件更新，行数 0 → CONFLICT
        - 子实体按自然键 find-or-upsert，幂等，不产生重复行
        - 返回 AlgorithmSaveCode 字符串（SAVED/OK/CONFLICT/VALIDATION_FAILED）

        Args:
            aggregate: 算法定义聚合根（含基础字段）
            sub_entities: {device_params: [...], api_params: [...],
                case_params: [...], reference_params: [...],
                mappings: [...], associated_dimensions: [...]}
            expected_updated_at: 乐观锁版本（ISO 字符串），更新路径 CAS 用
        """
        ...


class IAlgorithmDefinitionDraftRepository(ABC):
    """算法定义草稿仓储接口（INT-589，JSON 快照表）。"""

    @abstractmethod
    def save_snapshot(self, algorithm_type: str, snapshot: Any) -> None:
        """保存草稿快照（按 algorithm_type upsert，不落正式六表）。"""
        ...

    @abstractmethod
    def get_snapshot(self, algorithm_type: str) -> Optional[Any]:
        """读取草稿快照（dict），不存在返回 None。"""
        ...

    @abstractmethod
    def clear_snapshot(self, algorithm_type: str) -> bool:
        """发布成功后清除草稿快照，返回是否清除。"""
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
