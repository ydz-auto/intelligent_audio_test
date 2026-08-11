# -*- coding: utf-8 -*-
"""task_service 防腐层仓储接口（ABC）

Domain 层通过此接口访问 task_service 数据，不直接依赖 infrastructure/acl。
"""
from abc import ABC, abstractmethod
from typing import Dict, List, Optional


class TaskAclRepository(ABC):
    """task_service 防腐层仓储抽象接口"""

    # ========== 读操作 ==========

    @abstractmethod
    def get_test_result_by_id(self, result_id: int) -> Optional[Dict]:
        """按 ID 读取单个 TestResult。返回 dict 或 None。"""
        ...

    @abstractmethod
    def get_task_case_by_ids(
        self, task_id: int, case_ids: Optional[List[str]] = None
    ) -> List[Dict]:
        """批量读取 TaskCase。case_ids 为空时返回该 task 下所有 TaskCase。"""
        ...

    @abstractmethod
    def get_task_by_id(self, task_id: int) -> Optional[Dict]:
        """按 task_id 读取 Task 详情。"""
        ...

    @abstractmethod
    def get_task_devices(self, task_id: int) -> List[Dict]:
        """按 task_id 读取关联设备。"""
        ...

    @abstractmethod
    def get_task_apis(self, task_id: int) -> List[Dict]:
        """按 task_id 读取关联 API。"""
        ...

    @abstractmethod
    def get_test_case_detail(self, tc_id: str) -> Optional[Dict]:
        """按 tc_id 读取测试用例详情。返回 dict 或 None。"""
        ...

    @abstractmethod
    def get_dimension_params(self, dimension_id: int) -> List[Dict]:
        """获取评估维度的参数列表（含 output/input 完整字段）。"""
        ...

    @abstractmethod
    def get_test_results_by_task_and_case(
        self, task_id: int, test_case_id: Optional[str] = None
    ) -> List[Dict]:
        """按 task_id + test_case_id 批量读取 TestResult。"""
        ...

    # ========== 写操作 ==========

    @abstractmethod
    def submit_result(self, task_id: int, result_data: Dict) -> Optional[int]:
        """写入测试结果。返回新 result_id 或 None。"""
        ...

    @abstractmethod
    def update_task_case_status(
        self,
        task_id: int,
        case_id: str,
        status: str = '',
        execution_status: str = '',
        evaluation_status: str = '',
        error_message: str = '',
    ) -> bool:
        """更新 TaskCase 状态。返回是否成功。"""
        ...

    @abstractmethod
    def update_test_result_algorithm_result(
        self, result_id: int, algorithm_result: Dict
    ) -> bool:
        """更新 TestResult.algorithm_result。返回是否成功。"""
        ...

    @abstractmethod
    def update_test_result_status(
        self, result_id: int, execution_status: str
    ) -> bool:
        """更新 TestResult.execution_status。返回是否成功。"""
        ...

    @abstractmethod
    def update_task_status(self, task_id: int, status: str) -> bool:
        """更新 Task.status。返回是否成功。"""
        ...

    @abstractmethod
    def notify_task_progress(self, task_id: int, force: bool = False) -> None:
        """通知 task_service 发送进度更新。"""
        ...

    @abstractmethod
    def notify_case_completed(self, task_id: int) -> None:
        """通知 task_service 唤醒等待线程（某用例评估完成）。"""
        ...
