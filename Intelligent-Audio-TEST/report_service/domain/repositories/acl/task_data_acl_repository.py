# -*- coding: utf-8 -*-
"""task_service.TaskDataService 跨域 ACL 仓储接口。

report_service 通过 gRPC 只读访问 task_service 的 Task / TestResult /
TaskDevice / TaskCase 等数据，接口定义在此 ABC，实现在
infrastructure/acl/task_data_acl_repository.py。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional

from report_service.domain.dto import (
    TaskApiDTO, TaskCaseDTO, TaskDTO, TaskDeviceDTO, TestResultDTO,
)


class TaskDataAclRepository(ABC):
    """task_service.TaskDataService 跨域只读查询接口。"""

    @abstractmethod
    def get_task_devices(self, task_id) -> List[TaskDeviceDTO]:
        """查询 task 关联设备。"""
        ...

    @abstractmethod
    def get_task_apis(self, task_id) -> List[TaskApiDTO]:
        """查询 task 关联 API。"""
        ...

    @abstractmethod
    def get_tasks_by_ids(self, task_ids) -> List[TaskDTO]:
        """批量查询 Task。"""
        ...

    @abstractmethod
    def get_test_results_by_task_ids(self, task_ids) -> List[TestResultDTO]:
        """按 task_id 批量查询 TestResult。"""
        ...

    @abstractmethod
    def get_test_result_by_id(self, result_id) -> Optional[TestResultDTO]:
        """按 ID 查询单个 TestResult。"""
        ...

    @abstractmethod
    def get_task_case_ids(self, task_id) -> List[TaskCaseDTO]:
        """查询 task 关联的 test_case 记录列表。"""
        ...

    @abstractmethod
    def get_task_case_ids_batch(self, task_ids) -> List[TaskCaseDTO]:
        """批量查询多个 task 关联的 test_case 记录。"""
        ...

    @abstractmethod
    def get_test_results_by_task_and_case(
        self, test_case_ids, task_ids=None,
    ) -> List[TestResultDTO]:
        """按 test_case_id + task_id 批量查询 TestResult。"""
        ...
