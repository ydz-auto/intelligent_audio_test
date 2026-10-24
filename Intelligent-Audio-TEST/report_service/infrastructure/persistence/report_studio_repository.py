# -*- coding: utf-8 -*-
"""Report Studio 仓储 — SQLAlchemy 实现（INT-673）

实现 report_service/domain/repositories/report_studio_repository_abc.py。
乐观锁与「当前版 + 新版本快照同事务落库」在此强制（§15.3 snapshot 不靠
模型主动调用，每次写操作自动落历史版本）。
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import func, update

from shared.models.database import get_db_session, utc8now
from shared.models.common_enums import ReportStudioSourceType
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
        source_type=po.source_type or ReportStudioSourceType.PLATFORM_REPORT.value,
        parent_doc_id=po.parent_doc_id,
        source_file_path=po.source_file_path,
        source_format=po.source_format,
        source_file_size=po.source_file_size,
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
                source_type=doc.source_type or ReportStudioSourceType.PLATFORM_REPORT.value,
                parent_doc_id=doc.parent_doc_id,
                source_file_path=doc.source_file_path,
                source_format=doc.source_format,
                source_file_size=doc.source_file_size,
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

    def list_documents(self, report_id: Optional[int] = None,
                       source_type: Optional[str] = None,
                       parent_doc_id: Optional[str] = None,
                       created_by: Optional[int] = None,
                       limit: int = 100, offset: int = 0):
        """按来源/报告/父文档过滤的文档列表（INT-1763，设计文档 §6.4）。

        过滤条件全部显式给出：``report_id`` 非空时天然排除上传文档（其 report_id
        为 NULL），再叠 ``source_type`` 才能保证平台报告文档列表与迁移前一致。
        返回 ``(rows, total)``，total 为过滤后全量计数（分页用）。
        """
        session = get_db_session()
        try:
            query = session.query(DocumentPO)
            if report_id is not None:
                query = query.filter(DocumentPO.report_id == report_id)
            if source_type:
                query = query.filter(DocumentPO.source_type == source_type)
            if parent_doc_id:
                query = query.filter(DocumentPO.parent_doc_id == parent_doc_id)
            if created_by is not None:
                query = query.filter(DocumentPO.created_by == created_by)
            total = query.count()
            rows = query.order_by(
                DocumentPO.updated_at.desc(), DocumentPO.doc_id.asc()
            ).offset(max(int(offset), 0)).limit(max(int(limit), 1)).all()
            return [_doc_to_entity(r) for r in rows], total
        finally:
            session.close()

    def update_document(self, doc_id: str, expected_version: int,
                        markdown: str, chart_refs: List[str], style_prefs: Dict[str, Any],
                        etag_hash: str, new_version: int,
                        snapshot: ReportStudioVersion) -> Optional[int]:
        """乐观锁更新：带版本谓词的条件写（WHERE current_version=:expected）。

        原子性（验收标准 2）：并发 PUT 同 expected_version 时，后提交者的条件
        UPDATE 匹配 0 行 → 返回 None → 服务层转 409 + diff，不再依赖版本快照
        UNIQUE(doc_id, version) 兜底把 IntegrityError 原样上抛成 500。每次写
        操作同一事务落不可变版本快照（§15.3）。
        """
        session = get_db_session()
        try:
            result = session.execute(
                update(DocumentPO)
                .where(DocumentPO.doc_id == doc_id)
                .where(DocumentPO.current_version == expected_version)
                .values(
                    markdown_content=markdown,
                    chart_refs=chart_refs or [],
                    style_prefs=style_prefs or {},
                    current_version=new_version,
                    etag_hash=etag_hash,
                    updated_at=utc8now(),
                )
            )
            if result.rowcount == 0:
                # 文档不存在（服务层已先查 404，且无删除路径）或版本已被他人推进 → 冲突
                session.rollback()
                return None
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
        """恢复目标版本为新版本（同事务；历史版本只读不可变）。

        与 update_document 同为带版本谓词的条件写：并发 restore 同 expected_version
        时后提交者匹配 0 行 → 返回 None → 服务层 409，不依赖 UNIQUE 兜底。
        """
        session = get_db_session()
        try:
            po = session.query(DocumentPO).filter(DocumentPO.doc_id == doc_id).first()
            if po is None:
                return None
            result = session.execute(
                update(DocumentPO)
                .where(DocumentPO.doc_id == doc_id)
                .where(DocumentPO.current_version == expected_version)
                .values(
                    markdown_content=target.markdown_content,
                    chart_refs=list((target.chart_specs or {}).get('chart_refs')
                                    or po.chart_refs or []),
                    current_version=new_version,
                    etag_hash=new_etag,
                    updated_at=utc8now(),
                )
            )
            if result.rowcount == 0:
                session.rollback()
                return None
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
