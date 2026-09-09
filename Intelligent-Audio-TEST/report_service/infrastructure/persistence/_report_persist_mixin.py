# -*- coding: utf-8 -*-
"""Report 主表写入/删除 Mixin（从 report_repository.py 拆分，P4-5 大文件拆分）。

职责：聚合根持久化（save/add）、状态流转（update_status）、
软删除与硬删除（soft_delete/hard_delete）。
"""
from __future__ import annotations

from shared.models.database import get_db_session
from shared.utils.db_session import SoftDeleteMixin, with_session

from report_service.domain.entities import ReportAggregate
from report_service.infrastructure.persistence._report_converters import (
    _apply_report_to_po,
    _safe_json_dumps,
)


class ReportPersistMixin:
    """Report 主表写入与删除（依赖 PO_CLASS 与 _apply_report_to_po）。"""

    PO_CLASS = None  # 由 ReportRepository 提供（Report）

    @with_session(auto_commit=True)
    def save(self, aggregate: ReportAggregate) -> None:
        """持久化聚合根变更。

        P5+DOMAIN: 通过 PO ↔ Entity 转换，将聚合根字段写回 PO，
        不再依赖 aggregate.orm 属性。
        仅更新主表字段；子实体集合的变更需通过对应的 save_* 方法处理。
        """
        session = get_db_session()
        po = session.get(self.PO_CLASS, aggregate.id)
        if po is None:
            # 不应发生（save 只更新已存在的聚合），但容错处理
            raise ValueError(f"Report id={aggregate.id} 不存在，无法 save")
        _apply_report_to_po(aggregate, po)

    @with_session(auto_commit=True)
    def add(self, aggregate: ReportAggregate) -> int:
        """新增报告聚合根。

        Returns:
            新报告 ID。

        P5+DOMAIN: 从聚合根字段构造新 PO，不再依赖 aggregate.orm。
        仅写入主表；子实体集合需通过对应 add_* 方法单独写入。
        """
        session = get_db_session()
        po = self.PO_CLASS(
            task_id=aggregate.task_id,
            name=aggregate.name or '',
            type=aggregate.report_type,
            status=aggregate.status,
            analysis=_safe_json_dumps(aggregate.config) or '',
            deleted=aggregate.deleted,
        )
        session.add(po)
        session.flush()
        new_id = po.id
        # 将生成的 ID 回写聚合根
        aggregate.id = new_id
        return new_id

    @with_session(auto_commit=True)
    def update_status(self, report_id: int, status: str) -> None:
        """更新报告状态。

        用于报告生成流转（pending → generating → completed/failed）。
        """
        session = get_db_session()
        po = session.get(self.PO_CLASS, report_id)
        if po is None:
            raise ValueError(f"Report id={report_id} 不存在，无法 update_status")
        po.status = status

    @with_session
    def hard_delete(self, report_id: int) -> bool:
        """硬删除报告及其所有子表记录。

        级联删除 ReportSummary、ReportSummaryMeta、ReportRawData、
        ReportCase、ReportMetricStats、ReportComparisonMatrix。

        Returns:
            True 表示删除成功，False 表示报告不存在。
        """
        from report_service.infrastructure.persistence.models import (
            ReportSummary,
            ReportSummaryMeta,
            ReportRawData,
            ReportCase,
            ReportMetricStats,
            ReportComparisonMatrix,
        )

        session = get_db_session()
        po = session.get(self.PO_CLASS, report_id)
        if po is None:
            return False
        # 级联删除子表
        child_models = (
            ReportSummary,
            ReportSummaryMeta,
            ReportRawData,
            ReportCase,
            ReportMetricStats,
            ReportComparisonMatrix,
        )
        for model in child_models:
            session.query(model).filter(
                model.report_id == report_id
            ).delete(synchronize_session=False)
        # 删除主表
        session.delete(po)
        return True


# 注意：soft_delete 由 SoftDeleteMixin 通用提供（依赖 PO_CLASS）
