# -*- coding: utf-8 -*-
"""task_service.TestCaseConfigService 跨域 ACL 仓储接口。"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from api_test_service.domain.dto import TestCaseDetailDTO


class TestCaseConfigAclRepository(ABC):
    """task_service.TestCaseConfigService 跨域只读查询接口。"""

    @abstractmethod
    def get_test_case_detail(self, test_case_id) -> Optional[TestCaseDetailDTO]:
        """按 ID 查询测试用例详情。"""
        ...
