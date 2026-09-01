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
        page: int = 1,
        page_size: int = 20,
    ) -> List[object]:
        """分页列出报告聚合根（未删除）。

        Args:
            status: 可选状态过滤（pending/generating/completed/failed）
            page: 页码（从 1 开始）
            page_size: 每页数量

        Returns:
            聚合根列表（不含子实体集合）。
        """
        session = get_db_session()
        query = session.query(self.PO_CLASS).filter(self.PO_CLASS.deleted == False)  # noqa: E712
        if status:
            query = query.filter(self.PO_CLASS.status == status)
        query = query.order_by(self.PO_CLASS.created_at.desc())
        # 分页：limit/offset（避免依赖 Flask-SQLAlchemy paginate）
        page = max(page, 1)
        page_size = max(page_size, 1)
        rows = query.limit(page_size).offset((page - 1) * page_size).all()
        return [_report_po_to_entity(po) for po in rows]

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
