# -*- coding: utf-8 -*-
"""api_test_service.APITestService 跨域 ACL 仓储接口。"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict, Optional

from report_service.domain.dto import ApiConfigDTO


class ApiTestAclRepository(ABC):
    """api_test_service.APITestService 跨域只读查询接口。"""

    @abstractmethod
    def get_api(self, api_id) -> Optional[ApiConfigDTO]:
        """查询单个 API 配置。"""
        ...

    @abstractmethod
    def get_apis_by_ids(self, api_ids) -> Dict[int, ApiConfigDTO]:
        """批量查询 API 配置，返回 {id: ApiConfigDTO}。"""
        ...
