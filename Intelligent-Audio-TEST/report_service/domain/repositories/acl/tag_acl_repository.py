# -*- coding: utf-8 -*-
"""task_service.TagConfigService 跨域 ACL 仓储接口。"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from report_service.domain.dto import TagCategoryDTO


class TagConfigAclRepository(ABC):
    """task_service.TagConfigService 跨域只读查询接口。"""

    @abstractmethod
    def get_tag_category(self, category_id) -> Optional[TagCategoryDTO]:
        """查询单个 TagCategory。"""
        ...
