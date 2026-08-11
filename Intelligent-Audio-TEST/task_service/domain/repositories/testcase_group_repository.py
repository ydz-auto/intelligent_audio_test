# -*- coding: utf-8 -*-
"""TestCaseGroupRepository ABC — 用例分组仓储接口。

infrastructure/persistence/testcase_repository.py 继承此 ABC，实现依赖倒置。
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class TestCaseGroupRepositoryABC(ABC):
    """用例分组仓储抽象接口。"""

    @abstractmethod
    def list_groups(self, algorithm_type: str = '', search: str = '') -> List[Dict[str, Any]]:
        """查询 TestCaseGroup 列表（过滤逻辑删除）。"""
        ...

    @abstractmethod
    def get_groups_by_ids(self, group_ids: List[str]) -> List[Dict[str, Any]]:
        """按 ID 列表批量查询 TestCaseGroup。"""
        ...

    @abstractmethod
    def get_groups_by_names(self, names: List[str]) -> List[Dict[str, Any]]:
        """按名称列表批量查询 TestCaseGroup。"""
        ...

    @abstractmethod
    def get_group_by_id(self, group_id: str) -> Optional[Dict[str, Any]]:
        """按 ID 查询单个 TestCaseGroup。"""
        ...

    @abstractmethod
    def get_group_by_name(self, group_name: str) -> Optional[Dict[str, Any]]:
        """按名称查询单个 TestCaseGroup。"""
        ...

    @abstractmethod
    def create_group(self, group_id: str, name: str, description: str = '',
                     algorithm_type: str = '') -> Dict[str, Any]:
        """创建 TestCaseGroup。"""
        ...

    @abstractmethod
    def update_group(self, group_id: str, name: str = '', description: str = '',
                     algorithm_type: str = '') -> Dict[str, Any]:
        """更新 TestCaseGroup（名称/描述/算法类型）。返回更新后的 dict 或 raise。"""
        ...

    @abstractmethod
    def delete_group(self, group_id: str, cascade: bool = False) -> Dict[str, Any]:
        """软删除 TestCaseGroup（cascade=True 时同时软删该分组下所有 TestCase）。"""
        ...
