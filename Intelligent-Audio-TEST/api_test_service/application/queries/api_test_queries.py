# -*- coding: utf-8 -*-
"""查询对象 — 应用层只读用例输入，纯数据载体。"""
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class GetAPITestStatusQuery:
    """查询 API 测试任务状态"""

    task_id: int


@dataclass(frozen=True)
class GetAPIQuery:
    """查询单个 API 配置详情

    通过 repository 加载 APIAggregate 聚合根。
    """

    api_id: int


@dataclass(frozen=True)
class ListAPIsQuery:
    """分页查询 API 配置列表

    通过 repository 分页查询 APIAggregate 聚合根列表。
    """

    page: int = 1
    per_page: int = 10
    keyword: Optional[str] = None
    status: Optional[str] = None
    algorithm_type: Optional[str] = None
