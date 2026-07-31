"""api_gateway 领域层 —— 值对象"""
from dataclasses import dataclass
from typing import Optional, List
from datetime import datetime


@dataclass(frozen=True)
class CaseId:
    """测试用例 ID 值对象"""
    value: str

    def __str__(self):
        return self.value


@dataclass(frozen=True)
class ReportId:
    """报告 ID 值对象"""
    value: str

    def __str__(self):
        return self.value


@dataclass(frozen=True)
class GroupId:
    """分组 ID 值对象"""
    value: str

    def __str__(self):
        return self.value


@dataclass(frozen=True)
class TagFilter:
    """标签过滤条件"""
    tags: List[str]

    def is_empty(self) -> bool:
        return len(self.tags) == 0


@dataclass(frozen=True)
class Pagination:
    """分页参数"""
    page: int = 1
    page_size: int = 20

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size

    @property
    def limit(self) -> int:
        return self.page_size
