# -*- coding: utf-8 -*-
"""TaskRepository ABC — 任务聚合根仓储接口。

infrastructure/persistence/task_repository.py 继承此 ABC，实现依赖倒置。
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple


class TaskRepositoryABC(ABC):
    """任务仓储抽象接口。"""

    @abstractmethod
    def get_by_id(self, task_id: int) -> Optional[Any]:
        ...

    @abstractmethod
    def get_task_dict_by_id(self, task_id: int) -> Optional[Dict[str, Any]]:
        """按 ID 读取 Task 详情（返回 dict 序列化格式）。"""
        ...

    @abstractmethod
    def update_status(self, task_id: int, status: str) -> Optional[Dict[str, Any]]:
        """更新 Task 的 status，返回 {task_id, old_status, new_status} 或 None。"""
        ...

    @abstractmethod
    def get_task_device_ids(self, task_id: int) -> List[Dict[str, Any]]:
        """获取任务关联设备列表。"""
        ...

    @abstractmethod
    def get_task_api_ids(self, task_id: int) -> List[Dict[str, Any]]:
        """获取任务关联 API 列表。"""
        ...

    @abstractmethod
    def get_task_stats(self, status: str = '', algorithm_type: str = '',
                       group_by: str = '') -> Dict[str, Any]:
        """聚合统计 Task — count / group_by。"""
        ...
