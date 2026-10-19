# -*- coding: utf-8 -*-
"""Report 主表查询 Mixin（从 report_repository.py 拆分，P4-5 大文件拆分）。

职责：Report 主表的聚合根查询（按 ID / 按任务 / 分页列表 / 趋势数据）
与原始 PO 查询（供报告生成引擎直接使用 PO）。

依赖 self.PO_CLASS（= Report），由 ReportRepository 组合时提供。
"""
from __future__ import annotations

from typing import List, Optional

from shared.models.database import get_db_session
from shared.utils.db_session import with_session

from report_service.infrastructure.persistence._report_converters import (
    _report_po_to_entity,
)


class ReportQueryMixin:
    """Report 主表查询（依赖 PO_CLASS 与 _report_po_to_entity）。"""

    PO_CLASS = None  # 由 ReportRepository 提供（Report）

    @with_session
    def get_by_id(self, report_id: int) -> Optional[object]:
        """按 ID 加载报告聚合根（不含子实体集合）。

        Returns:
            ReportAggregate 或 None（报告不存在或已软删除）。
        """
        session = get_db_session()
        po = session.get(self.PO_CLASS, report_id)
        if po is None or po.deleted:
            return None
        return _report_po_to_entity(po)

    @with_session
    def get_by_task(self, task_id: int) -> Optional[object]:
        """按任务 ID 加载报告聚合根（取最新一条未删除报告）。

        一个任务可能对应多个报告版本，取最新创建的一条。
        """
        session = get_db_session()
        po = (
            session.query(self.PO_CLASS)
            .filter(self.PO_CLASS.task_id == task_id, self.PO_CLASS.deleted == False)  # noqa: E712
            .order_by(self.PO_CLASS.created_at.desc())
            .first()
        )
        if po is None:
            return None
        return _report_po_to_entity(po)

    @with_session
    def list_reports(
        self,
        status: Optional[str] = None,
        report_types: Optional[List[str]] = None,
        task_id: Optional[int] = None,
        page: int = 1,
        page_size: int = 20,
        favorite: bool = False,
        deleted: bool = False,
        user_id: Optional[int] = None,
    ) -> List[object]:
        """分页列出报告聚合根。

        Args:
            status: 可选状态过滤（pending/generating/completed/failed）
            report_types: 可选类型集合过滤（IN 口径，INT-280 对比视图多类型；
                空集合或 None 不过滤）
            task_id: 可选任务 ID 精确过滤（INT-262）
            page: 页码（从 1 开始）
            page_size: 每页数量
            favorite: 可选（INT-141）仅当前用户收藏
            deleted: 可选（INT-141）仅回收站软删除项
            user_id: 可选，收藏过滤/标记用当前用户

        Returns:
            聚合根列表（不含子实体集合）。
        """
        from sqlalchemy import select as sa_select, cast as sa_cast, String
        from shared.models.common_enums import EntityType

        session = get_db_session()
        query = session.query(self.PO_CLASS).filter(
            self.PO_CLASS.deleted == (True if deleted else False))  # noqa: E712
        if status:
            query = query.filter(self.PO_CLASS.status == status)
        if report_types:
            query = query.filter(self.PO_CLASS.type.in_(report_types))
        if task_id:
            query = query.filter(self.PO_CLASS.task_id == task_id)
        if favorite:
            from report_service.infrastructure.persistence.models import ReportFavorite
            if not user_id:
                return []
            query = query.filter(sa_select(ReportFavorite.id)
                                 .where(ReportFavorite.user_id == user_id,
                                        ReportFavorite.entity_type == EntityType.REPORT.value,
                                        ReportFavorite.entity_id == sa_cast(self.PO_CLASS.id, String))
                                 .correlate(self.PO_CLASS)
                                 .exists())
        query = query.order_by(self.PO_CLASS.created_at.desc())
        # 分页：limit/offset（避免依赖 Flask-SQLAlchemy paginate）
        page = max(page, 1)
        page_size = max(page_size, 1)
        rows = query.limit(page_size).offset((page - 1) * page_size).all()
        return [_report_po_to_entity(po) for po in rows]

    @with_session
    def count_reports(
        self,
        status: Optional[str] = None,
        report_types: Optional[List[str]] = None,
        task_id: Optional[int] = None,
        favorite: bool = False,
        deleted: bool = False,
        user_id: Optional[int] = None,
    ) -> int:
        """按 list_reports 同一套过滤条件计数（INT-297：分页信封补 total/pages）。

        Args:
            status/report_types/task_id/favorite/deleted/user_id: 与 list_reports 口径一致。

        Returns:
            满足过滤条件的报告总数。
        """
        from sqlalchemy import select as sa_select, cast as sa_cast, String
        from shared.models.common_enums import EntityType

        session = get_db_session()
        query = session.query(self.PO_CLASS).filter(
            self.PO_CLASS.deleted == (True if deleted else False))  # noqa: E712
        if status:
            query = query.filter(self.PO_CLASS.status == status)
        if report_types:
            query = query.filter(self.PO_CLASS.type.in_(report_types))
        if task_id:
            query = query.filter(self.PO_CLASS.task_id == task_id)
        if favorite:
            from report_service.infrastructure.persistence.models import ReportFavorite
            if not user_id:
                return 0
            query = query.filter(sa_select(ReportFavorite.id)
                                 .where(ReportFavorite.user_id == user_id,
                                        ReportFavorite.entity_type == EntityType.REPORT.value,
                                        ReportFavorite.entity_id == sa_cast(self.PO_CLASS.id, String))
                                 .correlate(self.PO_CLASS)
                                 .exists())
        return query.count()

    # ---- 原始 PO 查询（供报告生成引擎直接使用 PO） ----

    @with_session
    def get_report_by_id_raw(self, report_id: int):
        """按 ID 查询原始 Report PO（不转换为实体）。

        供报告生成引擎检查已存在报告使用，返回 PO 或 None。
        """
        session = get_db_session()
        return session.get(self.PO_CLASS, report_id)

    @with_session
    def get_report_by_task_id_raw(self, task_id: int):
        """按 task_id 查询原始 Report PO（不转换为实体）。

        取最新一条未删除报告，返回 PO 或 None。
        """
        session = get_db_session()
        return (
            session.query(self.PO_CLASS)
            .filter(self.PO_CLASS.task_id == task_id, self.PO_CLASS.deleted == False)  # noqa: E712
            .order_by(self.PO_CLASS.created_at.desc())
            .first()
        )

    @with_session
    def get_cases_by_report_id(self, report_id: int) -> list:
        """按 report_id 查询原始 ReportCase PO 列表。

        供报告生成引擎读取已存用例数据使用，返回 PO 列表。
        """
        from report_service.infrastructure.persistence.models import ReportCase

        session = get_db_session()
        return (
            session.query(ReportCase)
            .filter(ReportCase.report_id == report_id)
            .all()
        )

    @with_session
    def get_trend_data(
        self,
        report_type: Optional[str] = None,
        task_id: Optional[int] = None,
        limit: int = 50,
    ) -> list:
        """查询报告趋势数据。

        按 created_at 升序返回已完成报告及其摘要，用于计算成功率/时长趋势。

        Args:
            report_type: 可选报告类型过滤（如 'task'）
            task_id: 可选任务 ID 过滤
            limit: 最多返回条数

        Returns:
            list[dict]: 每条含 report_id/name/created_at/pass_rate/duration
        """
        from report_service.infrastructure.persistence.models import ReportSummary

        session = get_db_session()
        query = (
            session.query(self.PO_CLASS, ReportSummary)
            .outerjoin(ReportSummary, self.PO_CLASS.id == ReportSummary.report_id)
            .filter(self.PO_CLASS.deleted == False)  # noqa: E712
        )
        if report_type:
            query = query.filter(self.PO_CLASS.type == report_type)
        if task_id:
            query = query.filter(self.PO_CLASS.task_id == task_id)
        query = query.order_by(self.PO_CLASS.created_at.asc()).limit(limit)
        rows = query.all()
        return [
            {
                'report_id': r.id,
                'name': r.name,
                'created_at': r.created_at,
                'pass_rate': s.pass_rate if s else 0,
                'duration': s.duration if s else 0,
            }
            for r, s in rows
        ]

    # ---- 统计分析基础行（INT-791：/reports/statistics*） ----

    @with_session
    def get_statistics_rows(self, start_time=None, end_time=None, algorithm_type=None):
        """查询统计用报告基础行（主表 + 摘要 + 元数据，外连接）。

        Args:
            start_time: datetime 或 None，created_at >= start_time
            end_time: datetime 或 None，created_at <= end_time
            algorithm_type: str 或 None，按 report_cases.algorithm_type 存在性过滤
                （报告无 algorithm_type 列，以用例级算法类型归属）

        Returns:
            list[tuple(Report, ReportSummary|None, ReportSummaryMeta|None)]，
            按 created_at 升序。
        """
        from sqlalchemy import select as sa_select

        from report_service.infrastructure.persistence.models import (
            ReportCase,
            ReportSummary,
            ReportSummaryMeta,
        )

        session = get_db_session()
        query = (
            session.query(self.PO_CLASS, ReportSummary, ReportSummaryMeta)
            .outerjoin(ReportSummary, self.PO_CLASS.id == ReportSummary.report_id)
            .outerjoin(ReportSummaryMeta, self.PO_CLASS.id == ReportSummaryMeta.report_id)
            .filter(self.PO_CLASS.deleted == False)  # noqa: E712
        )
        if start_time is not None:
            query = query.filter(self.PO_CLASS.created_at >= start_time)
        if end_time is not None:
            query = query.filter(self.PO_CLASS.created_at <= end_time)
        if algorithm_type:
            query = query.filter(
                sa_select(ReportCase.id)
                .where(ReportCase.report_id == self.PO_CLASS.id,
                       ReportCase.algorithm_type == algorithm_type)
                .correlate(self.PO_CLASS)
                .exists()
            )
        query = query.order_by(self.PO_CLASS.created_at.asc())
        return query.all()

    @with_session
    def get_metric_stats_for_report_ids(self, report_ids):
        """按 report_id 批量加载 ReportMetricStats，返回 {report_id: po}。

        供统计分析报表生成（device_performance 类型）读取设备/API 统计快照。
        """
        if not report_ids:
            return {}
        from report_service.infrastructure.persistence.models import ReportMetricStats
        session = get_db_session()
        rows = (
            session.query(ReportMetricStats)
            .filter(ReportMetricStats.report_id.in_(report_ids))
            .all()
        )
        return {po.report_id: po for po in rows}
