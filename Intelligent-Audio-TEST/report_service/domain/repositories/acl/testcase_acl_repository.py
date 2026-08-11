# -*- coding: utf-8 -*-
"""task_service.TestCaseConfigService 跨域 ACL 仓储接口。"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict

from report_service.domain.dto import TestCaseDTO


class TestCaseConfigAclRepository(ABC):
    """task_service.TestCaseConfigService 跨域只读查询接口。"""

    @abstractmethod
    def list_testcases_by_ids(self, test_case_ids) -> Dict[int, TestCaseDTO]:
        """按 ID 批量查询测试用例，返回 {id: TestCaseDTO}。"""
        ...
