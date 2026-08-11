# -*- coding: utf-8 -*-
"""TaskCaseRepository ABC — 任务用例关联仓储接口。

infrastructure/persistence/task_repository.py 继承此 ABC，实现依赖倒置。
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class TaskCaseRepositoryABC(ABC):
    """任务用例关联仓储抽象接口。"""

    @abstractmethod
    def get_by_task_and_case_ids(self, task_id: int, case_ids: List[str] = None) -> List[Dict[str, Any]]:
        """按 task_id + case_ids 批量读取 TaskCase。case_ids 为空时返回该 task 下所有 TaskCase。"""
        ...

    @abstractmethod
    def update_status(self, task_id: int, case_id: str, status: str = '',
                      execution_status: str = '', evaluation_status: str = '',
                      error_message: str = '') -> bool:
        """更新 TaskCase 状态。"""
        ...

    @abstractmethod
    def get_stats(self, algorithm_type: str = '', group_id: str = '',
                  group_by: str = '') -> Dict[str, Any]:
        """聚合统计 TestCase — count / group_by。"""
        ...
