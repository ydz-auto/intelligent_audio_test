# -*- coding: utf-8 -*-
"""TaskMergeRelationRepository ABC — 任务合并关系仓储接口。

infrastructure/persistence/task_merge_repository.py 继承此 ABC，实现依赖倒置。
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, List


class TaskMergeRelationRepositoryABC(ABC):
    """任务合并关系仓储抽象接口。"""

    @abstractmethod
    def get_by_task_id(self, task_id: int) -> List[Dict[str, Any]]:
        """查询 TaskMergeRelation（task_id 同时匹配 merged_task_id 与 source_task_id）。"""
        ...
