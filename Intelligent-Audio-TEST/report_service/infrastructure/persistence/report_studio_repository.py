# -*- coding: utf-8 -*-
"""Report Studio 仓储 — SQLAlchemy 实现（INT-673）

实现 report_service/domain/repositories/report_studio_repository_abc.py。
乐观锁与「当前版 + 新版本快照同事务落库」在此强制（§15.3 snapshot 不靠
模型主动调用，每次写操作自动落历史版本）。
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import func

from shared.models.database import get_db_session
from report_service.domain.entities.report_studio import (
    ReportStudioChartSpec,
    ReportStudioDocument,
    ReportStudioExportJob,
    ReportStudioVersion,
)
from report_service.domain.repositories.report_studio_repository_abc import (
    ReportStudioRepository,
)
from report_service.infrastructure.persistence.models import (
    ReportStudioChartSpec as ChartSpecPO,
    ReportStudioDocument as DocumentPO,
    ReportStudioDocumentVersion as VersionPO,
    ReportStudioExportJob as ExportJobPO,
)

logger = logging.getLogger(__name__)


def _doc_to_entity(po: DocumentPO) -> ReportStudioDocument:
    return ReportStudioDocument(
        doc_id=po.doc_id,
        report_id=po.report_id,
        title=po.title,
        markdown_content=po.markdown_content or '',
        chart_refs=list(po.chart_refs or []),
        style_prefs=dict(po.style_prefs or {}),
        current_version=po.current_version,
        etag_hash=po.etag_hash or '',
        agent_session_id=po.agent_session_id,
        created_by=po.created_by,
        created_at=po.created_at.isoformat() if po.created_at else None,
        updated_at=po.updated_at.isoformat() if po.updated_at else None,
    )


def _version_to_entity(po: VersionPO) -> ReportStudioVersion:
    return ReportStudioVersion(
        id=po.id,
        doc_id=po.doc_id,
        version=po.version,
        markdown_content=po.markdown_content or '',
        chart_specs=dict(po.chart_specs or {}),
        parent_version=po.parent_version,
        snapshot_reason=po.snapshot_reason or 'manual_edit',
        created_by=po.created_by,
        created_at=po.created_at.isoformat() if po.created_at else None,
    )


def _chart_to_entity(po: ChartSpecPO) -> ReportStudioChartSpec:
    return ReportStudioChartSpec(
        chart_id=po.chart_id,
        doc_id=po.doc_id,
        report_id=po.report_id,
        metric_params=dict(po.metric_params or {}),
        style=dict(po.style or {}),
        version=po.version,
        created_by=po.created_by,
        created_at=po.created_at.isoformat() if po.created_at else None,
    )


def _export_to_entity(po: ExportJobPO) -> ReportStudioExportJob:
    return ReportStudioExportJob(
        export_id=po.export_id,
        doc_id=po.doc_id,
        version=po.version,
        format=po.format,
        theme=po.theme,
        status=po.status,
        file_path=po.file_path,
        error=po.error,
        progress=po.progress,
        created_by=po.created_by,
        created_at=po.created_at.isoformat() if po.created_at else None,
        updated_at=po.updated_at.isoformat() if po.updated_at else None,
    )


class ReportStudioRepositoryImpl(ReportStudioRepository):
    """Report Studio 仓储实现（scoped_session，事务内自动落版本快照）。"""

    # ---------- 文档 ----------

    def create_document(self, doc: ReportStudioDocument, version: ReportStudioVersion) -> None:
        session = get_db_session()
        try:
            session.add(DocumentPO(
                doc_id=doc.doc_id,
                report_id=doc.report_id,
                agent_session_id=doc.agent_session_id,
                title=doc.title,
                markdown_content=doc.markdown_content,
                chart_refs=doc.chart_refs or [],
                style_prefs=doc.style_prefs or {},
                current_version=doc.current_version,
                etag_hash=doc.etag_hash,
                created_by=doc.created_by,
            ))
            session.add(VersionPO(
                doc_id=version.doc_id,
                version=version.version,
                markdown_content=version.markdown_content,
                chart_specs=version.chart_specs or {},
                parent_version=version.parent_version,
                snapshot_reason=version.snapshot_reason,
                created_by=version.created_by,
            ))
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def get_document(self, doc_id: str) -> Optional[ReportStudioDocument]:
        session = get_db_session()
        try:
            po = session.query(DocumentPO).filter(DocumentPO.doc_id == doc_id).first()
            return _doc_to_entity(po) if po else None
        finally:
            session.close()

    def update_document(self, doc_id: str, expected_version: int,
                        markdown: str, chart_refs: List[str], style_prefs: Dict[str, Any],
                        etag_hash: str, new_version: int,
                        snapshot: ReportStudioVersion) -> Optional[int]:
        """乐观锁更新：current_version 与 expected_version 不一致 → 返回 None。"""
        session = get_db_session()
        try:
            po = session.query(DocumentPO).filter(DocumentPO.doc_id == doc_id).first()
            if po is None:
                return None
            if po.current_version != expected_version:
                return None
            po.markdown_content = markdown
            po.chart_refs = chart_refs or []
            po.style_prefs = style_prefs or {}
            po.current_version = new_version
            po.etag_hash = etag_hash
            session.add(VersionPO(
                doc_id=snapshot.doc_id,
                version=snapshot.version,
                markdown_content=snapshot.markdown_content,
                chart_specs=snapshot.chart_specs or {},
                parent_version=snapshot.parent_version,
                snapshot_reason=snapshot.snapshot_reason,
                created_by=snapshot.created_by,
            ))
            session.commit()
            return new_version
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    # ---------- 版本 ----------

    def list_versions(self, doc_id: str) -> List[ReportStudioVersion]:
        session = get_db_session()
        try:
            rows = session.query(VersionPO).filter(
                VersionPO.doc_id == doc_id).order_by(VersionPO.version.asc()).all()
            return [_version_to_entity(r) for r in rows]
        finally:
            session.close()

    def get_version(self, doc_id: str, version: int) -> Optional[ReportStudioVersion]:
        session = get_db_session()
        try:
            po = session.query(VersionPO).filter(
                VersionPO.doc_id == doc_id, VersionPO.version == version).first()
            return _version_to_entity(po) if po else None
        finally:
            session.close()

    def restore_version(self, doc_id: str, expected_version: int,
                        target: ReportStudioVersion, new_version: int,
                        new_etag: str) -> Optional[int]:
        """恢复目标版本为新版本（同事务；历史版本只读不可变）。"""
        session = get_db_session()
        try:
            po = session.query(DocumentPO).filter(DocumentPO.doc_id == doc_id).first()
            if po is None:
                return None
            if po.current_version != expected_version:
                return None
            po.markdown_content = target.markdown_content
            po.chart_refs = list((target.chart_specs or {}).get('chart_refs') or po.chart_refs or [])
            po.current_version = new_version
            po.etag_hash = new_etag
            session.add(VersionPO(
                doc_id=doc_id,
                version=new_version,
                markdown_content=target.markdown_content,
                chart_specs=target.chart_specs or {},
                parent_version=target.version,
                snapshot_reason='restore',
                created_by=None,
            ))
            session.commit()
            return new_version
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    # ---------- 图表 ----------

    def get_chart_spec(self, doc_id: str, chart_id: str) -> Optional[ReportStudioChartSpec]:
        session = get_db_session()
        try:
            po = session.query(ChartSpecPO).filter(
                ChartSpecPO.doc_id == doc_id, ChartSpecPO.chart_id == chart_id).first()
            return _chart_to_entity(po) if po else None
        finally:
            session.close()

    def create_chart_spec(self, spec: ReportStudioChartSpec) -> None:
        session = get_db_session()
        try:
            session.add(ChartSpecPO(
                chart_id=spec.chart_id,
                doc_id=spec.doc_id,
                report_id=spec.report_id,
                metric_params=spec.metric_params or {},
                style=spec.style or {},
                version=spec.version,
                created_by=spec.created_by,
            ))
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    # ---------- 导出作业 ----------

    def create_export_job(self, job: ReportStudioExportJob) -> None:
        session = get_db_session()
        try:
            session.add(ExportJobPO(
                export_id=job.export_id,
                doc_id=job.doc_id,
                version=job.version,
                format=job.format,
                theme=job.theme,
                status=job.status or 'pending',
                file_path=job.file_path,
                error=job.error,
                progress=job.progress or 0,
                created_by=job.created_by,
            ))
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def get_export_job(self, export_id: str) -> Optional[ReportStudioExportJob]:
        session = get_db_session()
        try:
            po = session.query(ExportJobPO).filter(
                ExportJobPO.export_id == export_id).first()
            return _export_to_entity(po) if po else None
        finally:
            session.close()

    def update_export_job(self, export_id: str, **fields) -> bool:
        session = get_db_session()
        try:
            po = session.query(ExportJobPO).filter(
                ExportJobPO.export_id == export_id).first()
            if po is None:
                return False
            for key, value in fields.items():
                if hasattr(po, key):
                    setattr(po, key, value)
            session.commit()
            return True
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
