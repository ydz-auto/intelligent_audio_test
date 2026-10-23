# -*- coding: utf-8 -*-
"""报告查询（Query）对象。

CQRS 读模型入口：查询是 immutable 的读取意图描述，本身不包含业务逻辑。
Handler 接收查询后通过 repository 加载聚合根返回。

所有查询均为 frozen dataclass，保证不可变。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional


@dataclass(frozen=True)
class GetReportQuery:
    """按 ID 查询单个报告（不含子实体集合）。

    Attributes:
        report_id: 报告 ID
    """
    report_id: int


@dataclass(frozen=True)
class GetReportProgressQuery:
    """查询报告生成进度（按报告 ID 推导生成状态）。

    Attributes:
        report_id: 报告 ID
    """
    report_id: int


@dataclass(frozen=True)
class GetReportByTaskQuery:
    """按任务 ID 查询最新一条报告。

    一个任务可能存在多个报告版本，取最新创建的一条。

    Attributes:
        task_id: 任务 ID
    """
    task_id: int


def split_report_types(report_type: Optional[str]) -> Optional[List[str]]:
    """proto/HTTP report_type 单值字段 → 类型集合（INT-280 多类型 IN 过滤）。

    多类型以逗号分隔下发（如 comparison,secondary_comparison）；
    空串/纯逗号归一为 None（不过滤）。
    gRPC servicer 与 HTTP 路由共用，避免两端口径漂移。
    """
    if not report_type:
        return None
    types = [t.strip() for t in report_type.split(',') if t.strip()]
    return types or None


@dataclass(frozen=True)
class ListReportsQuery:
    """分页列出报告（未删除）。

    Attributes:
        status: 可选状态过滤（pending/generating/completed/failed）
        report_types: 可选类型集合过滤（IN 口径；INT-280 对比视图多类型下发，
            None/空集合不过滤）
        task_id: 可选任务 ID 精确过滤（INT-262：按任务查报告）
        page: 页码（从 1 开始）
        page_size: 每页数量
        favorite: 可选（INT-141）仅当前用户收藏（user_id 来自 x-user-id metadata）
        deleted: 可选（INT-141）仅回收站软删除项（含删除人/删除时间）
        user_id: 可选，收藏过滤/标记用当前用户
    """
    status: Optional[str] = None
    report_types: Optional[List[str]] = None
    task_id: Optional[int] = None
    page: int = 1
    page_size: int = 20
    favorite: bool = False
    deleted: bool = False
    user_id: Optional[int] = None


@dataclass(frozen=True)
class ListReportBriefsByTaskIdsQuery:
    """页级批量列出多个任务的报告摘要（INT-1462）。

    Attributes:
        task_ids: 页面任务 ID 集合（一次查询取回，消除列表逐任务串行 RPC）
        per_task_limit: 每个任务最多返回的摘要条数（与列表页历史上限一致）
    """
    task_ids: List[int]
    per_task_limit: int = 100


@dataclass(frozen=True)
class GetReportSummaryQuery:
    """查询报告摘要（含子实体集合）。

    返回的聚合根将填充 summaries/cases/metric_stats/raw_data 等子实体。

    Attributes:
        report_id: 报告 ID
    """
    report_id: int


@dataclass(frozen=True)
class GetTrendDataQuery:
    """查询报告趋势数据。

    按 created_at 升序返回报告及其摘要，用于计算成功率/时长趋势。

    Attributes:
        report_type: 可选报告类型过滤
        task_id: 可选任务 ID 过滤
        limit: 最多返回条数
    """
    report_type: Optional[str] = None
    task_id: Optional[int] = None
    limit: int = 50
