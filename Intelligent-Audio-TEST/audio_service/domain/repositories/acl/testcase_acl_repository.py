# -*- coding: utf-8 -*-
"""TestCaseConfig 跨域 ACL 仓储接口。

task_service 域的测试用例 CRUD 通过 gRPC 访问，
接口定义在此 ABC，实现在 infrastructure/acl/testcase_acl_repository.py。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional


class TestCaseConfigACLRepository(ABC):
    """task_service 测试用例跨域读写接口。"""

    @abstractmethod
    def list_testcases(self, page: int = 1, per_page: int = 50,
                       keyword: str = '', include_deleted: bool = False) -> dict:
        """分页查询测试用例列表（ListTestCases）

        返回分页 dict，包含 items/total/pages 等字段。
        gRPC 不可用时返回空 dict。
        """
        ...

    @abstractmethod
    def create_testcase_config(self, data: dict) -> Optional[dict]:
        """创建测试用例（CreateTestCaseConfig）

        返回创建结果 dict（含 id），失败返回 None。
        """
        ...

    @abstractmethod
    def update_testcase_config(self, tc_id: str, data: dict) -> Optional[dict]:
        """更新测试用例（UpdateTestCaseConfig）

        返回更新结果 dict，失败返回 None。
        """
        ...

    @abstractmethod
    def list_all_testcases(self, include_deleted: bool = False) -> List[dict]:
        """分页获取所有测试用例（自动翻页）

        返回完整的用例 dict 列表。
        """
        ...
