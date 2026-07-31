# -*- coding: utf-8 -*-
"""任务查询定义 (Task Queries) - CQRS 读模型。

查询对象是不可变的读取请求，返回 DTO 字典而非领域聚合根。
查询处理器直接查 DB，不走 ExecutionEngine。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional


@dataclass(frozen=True)
class Query:
    """查询基类。所有查询返回结果数据（dict 或 list）。"""
    pass


@dataclass(frozen=True)
class GetTaskQuery(Query):
    """获取单个任务详情查询。"""
    task_id: int
    include_cases: bool = False  # 是否包含用例列表


@dataclass(frozen=True)
class ListTasksQuery(Query):
    """任务列表查询（支持过滤和分页）。"""
    status: Optional[str] = None
    task_type: Optional[str] = None
    algorithm_type: Optional[str] = None
    created_by: Optional[int] = None
    page: int = 1
    page_size: int = 20
    include_deleted: bool = False


@dataclass(frozen=True)
class GetTaskProgressQuery(Query):
    """获取任务进度查询（轻量级，仅返回进度字段）。"""
    task_id: int


@dataclass(frozen=True)
class GetTaskCasesQuery(Query):
    """获取任务下用例执行状态查询。"""
    task_id: int
    status: Optional[str] = None  # 按用例状态过滤
    page: int = 1
    page_size: int = 50
