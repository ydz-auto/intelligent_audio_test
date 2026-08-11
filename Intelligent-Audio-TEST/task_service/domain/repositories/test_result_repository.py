# -*- coding: utf-8 -*-
"""TestResultRepository ABC — 测试结果仓储接口。

infrastructure/persistence/test_result_repository.py 继承此 ABC，实现依赖倒置。
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class TestResultRepositoryABC(ABC):
    """测试结果仓储抽象接口。"""

    @abstractmethod
    def get_by_id(self, result_id: int) -> Optional[Dict[str, Any]]:
        """按 ID 读取单个 TestResult。"""
        ...

    @abstractmethod
    def get_by_task_and_case(self, task_id: int, test_case_id: str = '') -> List[Dict[str, Any]]:
        """按 task_id + test_case_id 批量读取 TestResult。"""
        ...

    @abstractmethod
    def submit(self, task_id: int, data: Dict[str, Any]) -> int:
        """写入测试结果，返回 result_id。"""
        ...

    @abstractmethod
    def update_algorithm_result(self, result_id: int, algorithm_result: Any) -> bool:
        """更新 TestResult 的 algorithm_result。"""
        ...

    @abstractmethod
    def update_status(self, result_id: int, execution_status: str) -> bool:
        """更新 TestResult 的 execution_status。"""
        ...
