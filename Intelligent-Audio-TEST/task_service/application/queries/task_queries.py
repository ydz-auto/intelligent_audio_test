# -*- coding: utf-8 -*-
"""任务查询定义 (Task Queries) - CQRS 读模型。

查询对象是不可变的读取请求，返回 DTO 字典而非领域聚合根。
查询处理器直接查 DB，不走 ExecutionEngine。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional


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


# ==================== task 域查询（gRPC servicer 用） ====================
# 以下查询委托 task_query_service 旧服务作为过渡，
# 返回 dict: {success, message, data, code?}（与旧 service 返回格式一致）。


@dataclass(frozen=True)
class ListTasksConfigQuery(Query):
    """任务列表查询（gRPC servicer 用，参数与 task_query_service.list_tasks 对齐）。"""
    page: int = 1
    per_page: int = 10
    status: Optional[str] = None
    task_type: Optional[str] = None
    algorithm_type: Optional[str] = None
    search: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None


@dataclass(frozen=True)
class GetTaskDetailQuery(Query):
    """任务详情查询（含时间预估）。委托 task_query_service.get_task_detail。"""
    task_id: int


@dataclass(frozen=True)
class GetTaskProgressDetailedQuery(Query):
    """任务实时进度查询（详细版）。委托 task_query_service.get_task_progress。"""
    task_id: int


@dataclass(frozen=True)
class GetTaskStatsQuery(Query):
    """任务统计信息查询。委托 task_query_service.get_task_stats。"""
    task_id: int


@dataclass(frozen=True)
class GetCaseDetailQuery(Query):
    """任务用例执行详情查询。委托 task_query_service.get_case_detail。"""
    task_id: int
    case_id: str = ''


@dataclass(frozen=True)
class GetCaseResultsQuery(Query):
    """任务用例执行结果查询。委托 task_query_service.get_case_results。"""
    task_id: int
    case_id: str = ''


# ==================== testcase 域查询（gRPC servicer 用） ====================


@dataclass(frozen=True)
class ListTestCasesQuery(Query):
    """测试用例列表查询。委托 testcase_query_service.list_testcases。"""
    page: int = 1
    per_page: int = 10
    keyword: Optional[str] = None
    tag: Optional[str] = None
    group_id: Optional[str] = None
    test_type: Optional[str] = None
    algorithm_type: Optional[str] = None
    view: Optional[str] = None
    include_deleted: bool = False


@dataclass(frozen=True)
class GetTestCaseDetailQuery(Query):
    """测试用例详情查询。委托 testcase_query_service.get_testcase_detail。"""
    tc_id: str = ''


@dataclass(frozen=True)
class GetTestCaseStatsQuery(Query):
    """测试用例统计信息查询。委托 testcase_query_service.get_testcase_stats。"""
    pass


@dataclass(frozen=True)
class GetTestCaseTagsQuery(Query):
    """获取所有标签名列表查询。委托 testcase_query_service.get_testcase_tags。"""
    pass


@dataclass(frozen=True)
class GetTestCaseRefParamsQuery(Query):
    """获取用例参考参数查询。委托 testcase_query_service.get_testcase_ref_params。"""
    tc_id: str = ''
    round_number: int = 1


@dataclass(frozen=True)
class FetchCaseIdsQuery(Query):
    """按筛选条件返回全量用例ID查询（不分页）。委托 testcase_query_service.fetch_case_ids。"""
    data: dict = None


# ==================== tag 域查询（gRPC servicer 用） ====================


@dataclass(frozen=True)
class ListTagCategoriesQuery(Query):
    """标签分类列表查询。委托 tag_crud_service.list_categories。"""
    page: int = 1
    per_page: int = 20
    keyword: Optional[str] = None


@dataclass(frozen=True)
class GetTagCategoryQuery(Query):
    """获取单个标签分类查询。委托 tag_crud_service.get_category。"""
    category_id: int = 0


@dataclass(frozen=True)
class ListTagsQuery(Query):
    """标签列表查询（带分类过滤）。委托 tag_crud_service.list_tags。"""
    page: int = 1
    per_page: int = 20
    category_id: Optional[int] = None
    keyword: Optional[str] = None


@dataclass(frozen=True)
class ListTagNamesQuery(Query):
    """标签名称列表查询。委托 tag_crud_service.list_tag_names。"""
    page: int = 1
    per_page: int = 100
    keyword: Optional[str] = None


@dataclass(frozen=True)
class GetTagQuery(Query):
    """获取单个标签查询。委托 tag_crud_service.get_tag。"""
    tag_id: int = 0


@dataclass(frozen=True)
class GetTagsByCategoryQuery(Query):
    """获取按分类分组的标签查询。委托 tag_crud_service.get_tags_by_category。"""
    pass
