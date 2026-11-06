# -*- coding: utf-8 -*-
"""task_service.TestCaseConfigService 跨域 ACL 仓储接口。"""
from __future__ import annotations

from abc import ABC, abstractmethod

from report_service.domain.dto import TestCaseLookupResult


class TestCaseConfigAclRepository(ABC):
    """task_service.TestCaseConfigService 跨域只读查询接口。"""

    @abstractmethod
    def list_testcases_by_ids(self, test_case_ids) -> TestCaseLookupResult:
        """按 ID 批量查询测试用例。

        Returns:
            TestCaseLookupResult：items 为 {str(id): TestCaseDTO}（id 主键为 varchar，
            统一字符串 key）；missing_ids / incomplete_ids 给出完整性口径，
            调用方据此区分「用例不存在」与「查询没做完」。
        """
        ...
