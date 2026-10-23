# -*- coding: utf-8 -*-
"""Task 跨域 ACL 仓储接口。

task_service 域的 TestCase / Task 等数据通过 gRPC 只读访问，
接口定义在此 ABC，实现在 infrastructure/acl/task_acl_repository.py。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict, List, Optional

from audio_service.domain.dto import TestCaseDTO


class TaskACLRepository(ABC):
    """task_service 跨域只读查询接口。"""

    @abstractmethod
    def check_audio_references_batch(self, audio_ids: List[int]) -> Dict[int, Dict[str, int]]:
        """批量检查音频被测试用例/任务引用计数（INT-1306）。

        返回 {audio_id: {'testcase_audio': N, 'testcase_noise': M, 'task': K}}；
        引用状态未知（gRPC 失败）时抛出异常，调用方应 fail-closed 拒绝删除。
        """
        ...

    @abstractmethod
    def check_audio_in_testcases(self, audio_id: int) -> int:
        """检查音频是否被测试用例引用"""
        ...

    @abstractmethod
    def check_audio_in_testcase_noise(self, audio_id: int) -> int:
        """检查音频是否被测试用例作为背景噪音引用"""
        ...

    @abstractmethod
    def check_audio_in_tasks(self, audio_id: int) -> int:
        """检查音频是否被任务引用"""
        ...

    @abstractmethod
    def get_testcase_by_id(self, testcase_id) -> Optional[TestCaseDTO]:
        """按 ID 查询 TestCase（返回 TestCaseDTO）"""
        ...

    @abstractmethod
    def get_testcase_config_audios(self, testcase_id) -> List[dict]:
        """查询 TestCase config 中 audios 配置列表（只读）"""
        ...

    @abstractmethod
    def has_running_e2e_tasks(self) -> bool:
        """查询 task_service 是否有运行中的 e2e 任务"""
        ...
