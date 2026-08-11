# -*- coding: utf-8 -*-
"""算法参数/映射/维度关联领域仓储接口（ACL 抽象层）。

归属：algorithm_service.domain.repositories

说明：
- 本模块为纯领域层抽象基类（ABC），不依赖 SQLAlchemy / PO。
- 每个接口定义一组数据访问契约，返回 dict（PO 隔离后的 ACL DTO），
  不向调用方暴露 ORM 对象，隔离领域层与 ORM。
- 具体实现位于 infrastructure.persistence.param_repository.py，
  通过 get_db_session() 的 scoped_session 访问数据。
- 接口方法遵循现有 servicers.py 的字段映射约定，确保切换后行为一致。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any


class IAlgorithmParamRepository(ABC):
    """设备/API 参数仓储接口。

    覆盖 AlgorithmDeviceParam / AlgorithmApiParam 两张结构相同的表，
    通过 param_type_source（device/api）区分目标 PO。
    """

    @abstractmethod
    def find_by_code(
        self,
        algorithm_type: str,
        param_code: str,
        direction: str,
        param_type_source: str,
    ) -> Optional[Dict[str, Any]]:
        """按 算法/参数代码/方向 查找未删除的设备或 API 参数。"""

    @abstractmethod
    def get_by_id(
        self, param_id: int, param_type_source: str
    ) -> Optional[Dict[str, Any]]:
        """按 ID 获取未删除的设备或 API 参数。

        当 param_type_source 未指定时，实现可先查 device 再查 api。
        """

    @abstractmethod
    def list_by_algorithm(
        self, algorithm_type: str, param_type: str
    ) -> List[Dict[str, Any]]:
        """按算法类型查询参数列表（param_type 为 device/api）。"""

    @abstractmethod
    def create(
        self, data: Dict[str, Any], param_type_source: str
    ) -> Dict[str, Any]:
        """创建设备或 API 参数，返回新参数 dict。"""

    @abstractmethod
    def update_attrs(
        self, param_id: int, fields: Dict[str, Any], param_type_source: str
    ) -> Dict[str, Any]:
        """按 ID 更新设备或 API 参数可写字段，返回更新后的 dict。"""

    @abstractmethod
    def soft_delete(
        self, param_id: int, param_type_source: str
    ) -> bool:
        """按 ID 软删除设备或 API 参数，返回是否成功。"""


class ICaseParamRepository(ABC):
    """用例参数仓储接口（CaseAlgorithmParam PO）。"""

    @abstractmethod
    def find_by_code(
        self,
        algorithm_type: str,
        param_code: str,
        include_deleted: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """按 算法/参数代码 查找用例参数（可包含软删项）。"""

    @abstractmethod
    def get_by_id(self, param_id: int) -> Optional[Dict[str, Any]]:
        """按 ID 获取未删除的用例参数。"""

    @abstractmethod
    def list_by_algorithm(
        self, algorithm_type: str, scope: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """按算法查询用例参数列表（可按 scope 过滤）。"""

    @abstractmethod
    def create(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """创建用例参数，返回新参数 dict。"""

    @abstractmethod
    def update_attrs(
        self, param_id: int, fields: Dict[str, Any]
    ) -> Dict[str, Any]:
        """按 ID 更新用例参数可写字段，返回更新后的 dict。"""

    @abstractmethod
    def soft_delete(self, param_id: int) -> bool:
        """按 ID 软删除用例参数，返回是否成功。"""

    @abstractmethod
    def revive(
        self, param_id: int, data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """恢复软删除的用例参数并更新字段，返回更新后的 dict。"""


class IReferenceParamRepository(ABC):
    """参考参数仓储接口（AlgorithmReferenceParam PO）。"""

    @abstractmethod
    def find_by_code(
        self, algorithm_type: str, code: str
    ) -> Optional[Dict[str, Any]]:
        """按 算法/code 查找未删除的参考参数。"""

    @abstractmethod
    def get_by_id(self, param_id: int) -> Optional[Dict[str, Any]]:
        """按 ID 获取未删除的参考参数。"""

    @abstractmethod
    def list_by_algorithm(
        self, algorithm_type: str
    ) -> List[Dict[str, Any]]:
        """按算法查询参考参数列表。"""

    @abstractmethod
    def create(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """创建参考参数，返回新参数 dict。"""

    @abstractmethod
    def update_attrs(
        self, param_id: int, fields: Dict[str, Any]
    ) -> Dict[str, Any]:
        """按 ID 更新参考参数可写字段，返回更新后的 dict。"""

    @abstractmethod
    def soft_delete(self, param_id: int) -> bool:
        """按 ID 软删除参考参数，返回是否成功。"""


class IMappingRepository(ABC):
    """参数映射仓储接口（ParamMapping PO）。"""

    @abstractmethod
    def get_by_id(self, mapping_id: int) -> Optional[Dict[str, Any]]:
        """按 ID 获取未删除的参数映射。"""

    @abstractmethod
    def list_by_algorithm(
        self,
        algorithm_type: str,
        source_type: Optional[str] = None,
        dimension_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """按算法查询参数映射列表（可按 source_type / dimension_id 过滤）。"""

    @abstractmethod
    def create(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """创建参数映射，返回新映射 dict。"""

    @abstractmethod
    def update_attrs(
        self, mapping_id: int, fields: Dict[str, Any]
    ) -> Dict[str, Any]:
        """按 ID 更新参数映射可写字段，返回更新后的 dict。"""

    @abstractmethod
    def soft_delete(self, mapping_id: int) -> bool:
        """按 ID 软删除参数映射，返回是否成功。"""


class IDimensionRelationRepository(ABC):
    """维度关联仓储接口（AlgorithmDimensionRelation PO）。"""

    @abstractmethod
    def find(
        self, algorithm_type: str, dimension_id: int
    ) -> Optional[Dict[str, Any]]:
        """按 算法/维度 查找未删除的维度关联。"""

    @abstractmethod
    def get_by_id(self, relation_id: int) -> Optional[Dict[str, Any]]:
        """按 ID 获取维度关联（含软删项）。"""

    @abstractmethod
    def list_by_algorithm(
        self, algorithm_type: str
    ) -> List[Dict[str, Any]]:
        """按算法查询未删除的维度关联列表。"""

    @abstractmethod
    def create(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """创建维度关联，返回新关联 dict。"""

    @abstractmethod
    def update_attrs(
        self, relation_id: int, fields: Dict[str, Any]
    ) -> Dict[str, Any]:
        """按 ID 更新维度关联可写字段，返回更新后的 dict。"""

    @abstractmethod
    def soft_delete(self, relation_id: int) -> bool:
        """按 ID 软删除维度关联，返回是否成功。"""

    @abstractmethod
    def soft_delete_by_algorithm(self, algorithm_type: str) -> bool:
        """按算法批量软删除维度关联，返回是否成功。"""
