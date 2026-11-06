# -*- coding: utf-8 -*-
"""报告查询（Query）对象。

CQRS 读模型入口：查询是 immutable 的读取意图描述，本身不包含业务逻辑。
Handler 接收查询后通过 repository 加载聚合根返回。

所有查询均为 frozen dataclass，保证不可变。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import List, Optional

# 中国标准时区 UTC+8（与 DB 列 utc8now 的写入口径一致；INT-2351）
_CST = timezone(timedelta(hours=8))

_DATE_ONLY_LEN = len('YYYY-MM-DD')


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


def parse_report_date(value, *, end_of_day: bool = False) -> Optional[datetime]:
    """列表时间窗参数（proto start_date/end_date、HTTP start_time/end_time）→ datetime。

    INT-2351 契约（列表筛选口径，gRPC servicer 与 HTTP 路由共用）：

    - 作用列：``test_reports.created_at``（报告入库时间；列表默认排序键）。
      不用 updated_at / 任务执行日：列表展示与排序都以 created_at 为准，
      筛选与展示同列才不会被「改过描述的报告跳进时间窗」误导。
    - 闭区间：``created_at >= start`` 且 ``created_at <= end``（两端都含）。
    - 纯日期 ``YYYY-MM-DD``：start 取当日 00:00:00；end 取当日
      23:59:59.999999（``end_of_day=True``），即「选到某天」包含该天整天。
    - 日期时间 ``YYYY-MM-DD HH:MM[:SS[.ffffff]]`` 或 ISO ``T`` 分隔：按同一时刻。
    - 时区：无时区字符串按东八区（DB 列 utc8now 口径）；带 ``Z`` / ``±HH:MM``
      的按 ISO 解析后换算到东八区再去 tzinfo（与 SQLite 读回的 naive 列可比）。
    - 空串 / 纯空白 / None：不过滤（返回 None）。
    - 非法值：``ValueError``（调用方转 400，绝不静默降级成「不过滤」——
      筛选静默失效正是 INT-2351 要修的缺陷）。

    Args:
        value: 原始参数值（str 或 None）
        end_of_day: True 时把纯日期推到当日最后一刻（用于 end/结束边界）

    Returns:
        naive datetime（东八区）或 None

    Raises:
        ValueError: 非空但无法解析为日期 / 日期时间
    """
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    normalized = text[:-1] + '+00:00' if text.endswith(('Z', 'z')) else text
    try:
        parsed = datetime.fromisoformat(normalized)
    except (TypeError, ValueError):
        raise ValueError(
            f'日期格式非法: {text!r}（支持 YYYY-MM-DD 或 YYYY-MM-DD HH:MM[:SS]）')
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(_CST).replace(tzinfo=None)
    if end_of_day and _is_date_only(text):
        parsed = parsed.replace(hour=23, minute=59, second=59, microsecond=999999)
    return parsed


def _is_date_only(text: str) -> bool:
    """``YYYY-MM-DD`` 形态判定（纯日期没有时刻，end 需覆盖当天整天）。"""
    return (len(text) == _DATE_ONLY_LEN
            and text[4] == '-' and text[7] == '-'
            and text.replace('-', '').isdigit())


@dataclass(frozen=True)
class ListReportsQuery:
    """分页列出报告（未删除）。

    Attributes:
        status: 可选状态过滤（draft / published）
        report_types: 可选类型集合过滤（IN 口径；INT-280 对比视图多类型下发，
            None/空集合不过滤）
        task_id: 可选任务 ID 精确过滤（INT-262：按任务查报告）
        search: 可选关键字（INT-2329：报告名称/描述模糊匹配，忽略大小写）
        start_time: 可选时间窗起点（含，INT-2351：test_reports.created_at；
            由 ``parse_report_date`` 解析，None 不过滤）
        end_time: 可选时间窗终点（含，INT-2351；纯日期已推到当日最后一刻）
        algorithm_type: 可选算法类型（INT-2351：报告主表无该列，按
            report_cases.algorithm_type 存在性归属，与报告统计同口径）
        page: 页码（从 1 开始）
        page_size: 每页数量
        favorite: 可选（INT-141）仅当前用户收藏（user_id 来自 x-user-id metadata）
        deleted: 可选（INT-141）仅回收站软删除项（含删除人/删除时间）
        user_id: 可选，收藏过滤/标记用当前用户
    """
    status: Optional[str] = None
    report_types: Optional[List[str]] = None
    task_id: Optional[int] = None
    search: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    algorithm_type: Optional[str] = None
    page: int = 1
    page_size: int = 20
    favorite: bool = False
    deleted: bool = False
    user_id: Optional[int] = None


@dataclass(frozen=True)
class CountReportsByTabsQuery:
    """Tab / 类型 / 收藏计数（INT-2339：与列表同口径，随筛选收缩）。

    计数入参只有 search / favorite / deleted + 当前用户可见性；
    status / report_type 属 Tab 自身维度，禁止作为计数入参
    （否则「已发布」筛选下草稿 Tab 恒 0）。

    Attributes:
        search: 可选关键字（与 ListReportsQuery.search 同口径）
        favorite: 仅当前用户收藏（与列表 favorite 过滤一致；无 user_id 时全 0）
        deleted: 仅回收站软删除项
        user_id: 可选，收藏过滤/计数用当前用户
    """
    search: Optional[str] = None
    favorite: bool = False
    deleted: bool = False
    user_id: Optional[int] = None


def empty_tab_counts() -> dict:
    """Tab 计数零值（INT-2339：RPC 失败降级口径，保持 200 + 全 0）。"""
    return {
        'all': 0, 'draft': 0, 'published': 0, 'comparison': 0,
        'types': {'task': 0, 'comparison': 0,
                  'secondary_comparison': 0, 'benchmark': 0},
        'favorite': 0,
    }


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
