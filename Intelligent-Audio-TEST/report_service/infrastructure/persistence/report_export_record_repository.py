# -*- coding: utf-8 -*-
"""报告导出记录仓储（INT-1555）

report_export_records 表读写。业务语义（scope 描述、可见性过滤）在应用
服务层完成，本仓储只做 PO 级读写与计数（@with_session 管理事务）。
"""
from __future__ import annotations

import logging
from typing import List, Optional, Tuple

from shared.models.database import get_db_session
from shared.utils.db_session import with_session

logger = logging.getLogger(__name__)


class ReportExportRecordRepository:
    """report_export_records 读写"""

    @with_session(auto_commit=True)
    def create(
        self,
        report_ids: List[int],
        scope: str,
        format_type: str,
        status: str,
        error: Optional[str] = None,
        filename: Optional[str] = None,
        created_by: Optional[int] = None,
    ) -> int:
        """新增导出记录，返回主键 ID（created_at 落 DB 默认值）。

        返回值只取主键：auto_commit 提交后 ORM 实例属性过期，调用方不得
        再持有该实例（session 随后 close）。
        """
        from report_service.infrastructure.persistence.models import (
            ReportExportRecord,
        )
        session = get_db_session()
        record = ReportExportRecord(
            report_ids=[int(rid) for rid in (report_ids or [])],
            scope=scope or '',
            format=format_type or 'csv',
            status=status,
            error=error,
            filename=filename,
            created_by=created_by,
        )
        session.add(record)
        session.flush()
        return record.id

    @with_session(auto_commit=False)
    def list_page(
        self, page: int, per_page: int, created_by: Optional[int] = None,
    ) -> Tuple[List, int]:
        """按导出时间倒序分页（created_by 非空时只取该用户的导出）。

        Returns:
            (records, total)；records 为 PO 列表（字段已加载，session 关闭后
            仍可读，调用方在应用层转 dict）。
        """
        from report_service.infrastructure.persistence.models import (
            ReportExportRecord,
        )
        session = get_db_session()
        query = session.query(ReportExportRecord)
        if created_by is not None:
            query = query.filter(ReportExportRecord.created_by == int(created_by))
        total = query.order_by(None).count()
        records = (
            query.order_by(ReportExportRecord.created_at.desc(),
                           ReportExportRecord.id.desc())
            .limit(per_page)
            .offset((page - 1) * per_page)
            .all()
        )
        return records, total

    @with_session(auto_commit=False)
    def report_names(self, report_ids: List[int]) -> dict:
        """批量取报告名（含已软删报告），用于拼导出范围描述。"""
        from report_service.infrastructure.persistence.models import Report
        ids = [int(rid) for rid in (report_ids or [])]
        if not ids:
            return {}
        session = get_db_session()
        rows = session.query(Report.id, Report.name).filter(
            Report.id.in_(ids),
        ).all()
        return {int(row[0]): row[1] for row in rows}


# 模块级单例
report_export_record_repository = ReportExportRecordRepository()
