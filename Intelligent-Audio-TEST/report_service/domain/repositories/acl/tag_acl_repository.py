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

    @abstractmethod
    def get_tags_by_category(self) -> Optional[TagCategoryDTO]:
        """查询按分类分组的标签全量（GetTagsByCategory）。

        返回 data 信封（{items: [{category, tags}, ...], total, ...}）挂 DTO.result_data；
        查询失败返回 None（调用方按「无分类」兜底，不抛异常）。
        """
        ...
