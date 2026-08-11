# -*- coding: utf-8 -*-
"""task_service.TaskDataService 跨域 ACL 仓储接口。

api_test_service 通过 gRPC 只读访问 task_service 的 Task / TaskCase /
TaskApi 等数据，接口定义在此 ABC，实现在
infrastructure/acl/task_data_acl_repository.py。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional

from api_test_service.domain.dto import TaskApiDTO, TaskCaseDTO, TaskDTO


class TaskDataAclRepository(ABC):
    """task_service.TaskDataService 跨域查询/写入接口。"""

    @abstractmethod
    def get_task_case_by_ids(self, task_id, case_ids=None) -> List[TaskCaseDTO]:
        """按 task_id（可选 case_ids）查询 TaskCase 列表。"""
        ...

    @abstractmethod
    def get_task_by_id(self, task_id) -> Optional[TaskDTO]:
        """按 ID 查询 Task。"""
        ...

    @abstractmethod
    def get_task_apis(self, task_id) -> List[TaskApiDTO]:
        """查询 task 关联的 API 列表。"""
        ...

    @abstractmethod
    def update_task_case_status(self, task_id, case_id, status=None,
                                execution_status=None, evaluation_status=None,
                                error_message=None) -> bool:
        """更新 TaskCase 状态（status / execution_status / evaluation_status）。"""
        ...

    @abstractmethod
    def submit_result(self, task_id, result_data) -> Optional[int]:
        """跨服务写入 TestResult，返回新建 result_id。"""
        ...
