# -*- coding: utf-8 -*-
"""EvaluationStrategyRepository ABC — 评估策略仓储接口（INT-590）。

infrastructure/persistence/evaluation_strategy_repository.py 继承此 ABC，
实现依赖倒置。策略实体归 task_service（用例域），引用/删保护/列表计数
全部本地化。
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class EvaluationStrategyRepositoryABC(ABC):
    """评估策略仓储抽象接口。"""

    @abstractmethod
    def create_strategy(self, data: Dict[str, Any]):
        """创建评估策略（含 flush，未 commit）。返回 PO。"""
        ...

    @abstractmethod
    def get_strategy(self, strategy_id: str, include_deleted: bool = False):
        """按 ID 查询单个未删除评估策略。"""
        ...

    @abstractmethod
    def get_strategy_by_name(self, name: str) -> Optional[Any]:
        """按名称查询未删除评估策略（用于重名校验）。"""
        ...

    @abstractmethod
    def list_strategies(self, page: int = 1, per_page: int = 10,
                        keyword: Optional[str] = None,
                        algorithm_type: Optional[str] = None,
                        enabled: Optional[bool] = None) -> Dict[str, Any]:
        """分页查询未删除评估策略（含 referenced_case_count）。"""
        ...

    @abstractmethod
    def count_referenced_cases(self, strategy_id: str) -> int:
        """统计引用该策略的未删除用例数（删保护 + 列表计数同源）。"""
        ...

    @abstractmethod
    def soft_delete_strategy(self, strategy_id: str) -> bool:
        """软删除评估策略（未 commit；被引用时由应用层先校验）。"""
        ...

    @abstractmethod
    def commit(self) -> None:
        """提交事务。"""
        ...

    @abstractmethod
    def rollback(self) -> None:
        """回滚事务。"""
        ...
