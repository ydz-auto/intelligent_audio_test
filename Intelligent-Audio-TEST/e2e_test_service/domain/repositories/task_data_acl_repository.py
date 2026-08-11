# -*- coding: utf-8 -*-
"""TaskDataService ACL 仓储接口

e2e_test_service 通过此接口访问 task_service 的任务统计数据、
TestResult / TaskCase 的读写、维度评估结果等。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from e2e_test_service.domain.dto import (
    DimensionResultDTO,
    TaskCaseDTO,
    TaskDeviceDTO,
    TestResultDTO,
)


class TaskDataAclRepository(ABC):
    """任务数据服务 ACL 仓储接口"""

    @abstractmethod
    def has_running_e2e_tasks(self) -> bool:
        """检查是否有运行中的 E2E 任务"""

    @abstractmethod
    def get_task_devices(self, task_id: str) -> List[TaskDeviceDTO]:
        """查询任务关联的设备记录"""

    @abstractmethod
    def get_test_result_by_id(self, result_id: int) -> Optional[TestResultDTO]:
        """按 ID 查询 TestResult"""

    @abstractmethod
    def update_test_result_algorithm_result(self, result_id: int,
                                             algorithm_result: str) -> bool:
        """更新 TestResult.algorithm_result"""

    @abstractmethod
    def update_test_result_status(self, result_id: int,
                                  execution_status: str) -> bool:
        """更新 TestResult.execution_status"""

    @abstractmethod
    def get_task_case_by_ids(self, task_id: str,
                             case_ids: List[str]) -> List[TaskCaseDTO]:
        """按 task_id 和 case_ids 查询 TaskCase"""

    @abstractmethod
    def update_task_case_status(self, task_id: str, case_id: str,
                                status: str, execution_status: str = '',
                                evaluation_status: str = '',
                                error_message: str = '') -> bool:
        """更新 TaskCase 状态"""

    @abstractmethod
    def get_dimension_results_by_result_ids(self,
                                            result_ids: List[int]) -> List[DimensionResultDTO]:
        """按 result_ids 查询维度评估结果"""
