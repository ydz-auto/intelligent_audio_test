# -*- coding: utf-8 -*-
"""报告查询（Query）对象。

CQRS 读模型入口：查询是 immutable 的读取意图描述，本身不包含业务逻辑。
Handler 接收查询后通过 repository 加载聚合根返回。

所有查询均为 frozen dataclass，保证不可变。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class GetReportQuery:
    """按 ID 查询单个报告（不含子实体集合）。

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


@dataclass(frozen=True)
class ListReportsQuery:
    """分页列出报告（未删除）。

    Attributes:
        status: 可选状态过滤（pending/generating/completed/failed）
        page: 页码（从 1 开始）
        page_size: 每页数量
    """
    status: Optional[str] = None
    page: int = 1
    page_size: int = 20


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
