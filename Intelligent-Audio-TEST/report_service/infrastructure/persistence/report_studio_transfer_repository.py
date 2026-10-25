# -*- coding: utf-8 -*-
"""Report Studio 三表离线搬运仓储（report_service，INT-1764 / D6）

供报告包（3a 平台报告 + 3b 上传文档 + 3c Agent 总结）导出 / 导入使用：
- 导出：按平台报告 id 收集文档闭包（含 `parent_doc_id` 指向的上传文档），
  再按版本策略取版本快照与图表规格；
- 导入：文档拓扑序落库（先源文档、后 Agent 总结），按 report / doc /
  chart 三类映射翻译引用，孤立引用降级为空并在回执 `warnings` 中列出。

设计依据：《任务数据离线搬运与增量回导功能设计文档》§6.3 关键规则的
1（agent_session_id 不迁移）、2（拓扑序）、3（源缺失降级）、4（版本策略）、
5（图表降级）。
"""
import logging
from datetime import datetime
from typing import Dict, List, Optional
from uuid import uuid4

from shared.constants.data_transfer import (
    DocVersionScope,
    ReportPackageEntity,
    ReportStudioTable,
)
from shared.models.database import get_db_session
from shared.models.common_enums import ReportStudioSourceType
from shared.utils.log_handler import log_not_emit
from report_service.infrastructure.persistence.models.report_studio_models import (
    ReportStudioChartSpec as ChartSpecPO,
    ReportStudioDocument as DocumentPO,
    ReportStudioDocumentVersion as VersionPO,
)

logger = logging.getLogger(__name__)

_MODULE_NAME = 'report_studio_transfer_repository'

# 导入拓扑序：平台报告文档 → 上传文档 → Agent 总结
_SOURCE_TYPE_ORDER = {
    ReportStudioSourceType.PLATFORM_REPORT.value: 0,
    ReportStudioSourceType.UPLOADED_FILE.value: 1,
    ReportStudioSourceType.AGENT_SUMMARY.value: 2,
}


def _iso(value):
    return value.isoformat(timespec='seconds') if isinstance(value, datetime) else value


def _parse_dt(value):
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value:
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    return None


def _document_row(po: DocumentPO) -> dict:
    return {
        'doc_id': po.doc_id,
        'report_id': po.report_id,
        'source_type': po.source_type,
        'parent_doc_id': po.parent_doc_id,
        'source_file_path': po.source_file_path,
        'source_format': po.source_format,
        'source_file_size': po.source_file_size,
        'agent_session_id': po.agent_session_id,
        'title': po.title,
        'markdown_content': po.markdown_content,
        'chart_refs': po.chart_refs or [],
        'style_prefs': po.style_prefs or {},
        'current_version': po.current_version,
        'etag_hash': po.etag_hash,
        'created_by': po.created_by,
        'created_at': _iso(po.created_at),
        'updated_at': _iso(po.updated_at),
    }


def _version_row(po: VersionPO) -> dict:
    return {
        'doc_id': po.doc_id,
        'version': po.version,
        'markdown_content': po.markdown_content,
        'chart_specs': po.chart_specs or {},
        'parent_version': po.parent_version,
        'snapshot_reason': po.snapshot_reason,
        'created_by': po.created_by,
        'created_at': _iso(po.created_at),
    }


def _chart_row(po: ChartSpecPO) -> dict:
    return {
        'chart_id': po.chart_id,
        'doc_id': po.doc_id,
        'report_id': po.report_id,
        'metric_params': po.metric_params or {},
        'style': po.style or {},
        'version': po.version,
        'created_by': po.created_by,
        'created_at': _iso(po.created_at),
    }


class ReportStudioTransferRepository:
    """Report Studio 文档 / 版本 / 图表规格的只读导出与拓扑序导入"""

    # ---------- 导出 ----------

    def export_studio_rows(self, report_ids: List[int],
                           doc_version_scope: str = None) -> Dict[str, List[dict]]:
        """按平台报告 id 收集 Studio 三表行（只读）。

        文档闭包：`report_id ∈ report_ids` 的文档 + 其 `parent_doc_id` 链上的
        文档（3c Agent 总结 → 3b 上传文档）。版本按 `doc_version_scope` 过滤
        （latest 只带当前版本）。
        """
        scope = doc_version_scope or DocVersionScope.FULL.value
        clean_ids = sorted({int(rid) for rid in (report_ids or [])})
        empty = {table.value: [] for table in ReportStudioTable}
        if not clean_ids:
            return empty

        session = get_db_session()
        try:
            docs: List[DocumentPO] = []
            seen = set()
            # 闭包 BFS：先按 report_id 取文档，再按 parent_doc_id 反复向外扩展
            pending = (session.query(DocumentPO)
                       .filter(DocumentPO.report_id.in_(clean_ids)).all())
            while pending:
                fresh = [po for po in pending if po.doc_id not in seen]
                if not fresh:
                    break
                docs.extend(fresh)
                seen.update(po.doc_id for po in fresh)
                pending = (session.query(DocumentPO)
                           .filter(DocumentPO.parent_doc_id.in_(list(seen))).all())

            doc_ids = sorted(seen)
            versions: List[VersionPO] = []
            if doc_ids:
                current_versions = {po.doc_id: po.current_version for po in docs}
                version_rows = (session.query(VersionPO)
                                .filter(VersionPO.doc_id.in_(doc_ids))
                                .order_by(VersionPO.doc_id, VersionPO.version).all())
                if scope == DocVersionScope.LATEST.value:
                    versions = [po for po in version_rows
                                if po.version == current_versions.get(po.doc_id)]
                else:
                    versions = version_rows
            charts: List[ChartSpecPO] = []
            if doc_ids:
                charts = (session.query(ChartSpecPO)
                          .filter(ChartSpecPO.doc_id.in_(doc_ids))
                          .order_by(ChartSpecPO.doc_id, ChartSpecPO.chart_id).all())
            return {
                ReportStudioTable.DOCUMENTS.value: [_document_row(po) for po in docs],
                ReportStudioTable.DOCUMENT_VERSIONS.value: [_version_row(po) for po in versions],
                ReportStudioTable.CHART_SPECS.value: [_chart_row(po) for po in charts],
            }
        finally:
            session.close()

    # ---------- 导入 ----------

    def import_studio_rows(self, tables: Dict[str, List[dict]],
                           report_id_mapping: Dict[int, int],
                           doc_version_scope: str = None) -> dict:
        """拓扑序导入 Studio 三表（单事务）。

        Args:
            tables: 三张 Studio 表名 → 行列表
            report_id_mapping: 包内报告 id → A 报告 id（3a 原地替换结果）
            doc_version_scope: full / latest（latest 只落当前版本）

        Returns: {'document_id_mapping', 'chart_id_mapping', 'imported',
                  'warnings', 'session_dropped'}
        Raises: 写失败回滚并抛出。
        """
        from shared.infrastructure.user_context import get_current_user_id

        scope = doc_version_scope or DocVersionScope.FULL.value
        created_by = get_current_user_id()
        docs = [r for r in (tables.get(ReportStudioTable.DOCUMENTS.value) or [])
                if isinstance(r, dict) and r.get('doc_id')]
        versions = [r for r in (tables.get(ReportStudioTable.DOCUMENT_VERSIONS.value) or [])
                    if isinstance(r, dict) and r.get('doc_id')]
        charts = [r for r in (tables.get(ReportStudioTable.CHART_SPECS.value) or [])
                  if isinstance(r, dict) and r.get('doc_id')]

        warnings: List[str] = []
        doc_mapping: Dict[str, str] = {}
        chart_mapping: Dict[str, str] = {}
        session_dropped = 0
        inserted = {ReportStudioTable.DOCUMENTS.value: 0,
                    ReportStudioTable.DOCUMENT_VERSIONS.value: 0,
                    ReportStudioTable.CHART_SPECS.value: 0}

        session = get_db_session()
        try:
            # 版本 / 图表按源 doc_id 分组，减少导入期查询
            versions_by_doc: Dict[str, List[dict]] = {}
            for row in versions:
                versions_by_doc.setdefault(str(row.get('doc_id')), []).append(row)
            charts_by_doc: Dict[str, List[dict]] = {}
            for row in charts:
                charts_by_doc.setdefault(str(row.get('doc_id')), []).append(row)

            existing_chart_ids = {cid for (cid,) in session.query(ChartSpecPO.chart_id).all()}
            # 先为包内全部图表分配 A 侧 chart_id（跨文档引用：Agent 总结的 chart_refs
            # 常指向父上传文档的图表，不能只看本文档自己的图表）
            for row in charts:
                source_chart_id = str(row.get('chart_id') or '')
                if source_chart_id and source_chart_id not in chart_mapping:
                    chart_mapping[source_chart_id] = self._allocate_chart_id(
                        source_chart_id, existing_chart_ids)

            for source in self._topological_order(docs, warnings):
                source_doc_id = str(source.get('doc_id'))
                new_doc_id = str(uuid4())
                doc_mapping[source_doc_id] = new_doc_id

                source_report_id = _as_int(source.get('report_id'))
                report_id = None
                if source_report_id is not None:
                    report_id = report_id_mapping.get(source_report_id)
                    if report_id is None:
                        warnings.append(
                            f'文档 {source_doc_id} 的来源报告 {source_report_id} 未随包搬运，'
                            f'report_id 已置空（需重新绑定）')

                source_parent = source.get('parent_doc_id')
                parent_doc_id = None
                if source_parent:
                    parent_doc_id = doc_mapping.get(str(source_parent))
                    if parent_doc_id is None:
                        warnings.append(
                            f'文档 {source_doc_id} 的父文档 {source_parent} 未随包搬运，'
                            f'parent_doc_id 已置空（孤儿文档）')

                if source.get('agent_session_id'):
                    session_dropped += 1

                chart_refs = self._translate_chart_refs(
                    source.get('chart_refs') or [], chart_mapping, warnings)
                session.add(DocumentPO(
                    doc_id=new_doc_id,
                    report_id=report_id,
                    source_type=source.get('source_type')
                    or ReportStudioSourceType.PLATFORM_REPORT.value,
                    parent_doc_id=parent_doc_id,
                    source_file_path=source.get('source_file_path'),
                    source_format=source.get('source_format'),
                    source_file_size=source.get('source_file_size'),
                    # 规则 1：DSH 会话不迁移，导入置空 → 文档降级为普通可编辑文档
                    agent_session_id=None,
                    title=source.get('title') or '',
                    markdown_content=source.get('markdown_content') or '',
                    chart_refs=chart_refs,
                    style_prefs=source.get('style_prefs') or {},
                    current_version=_as_int(source.get('current_version')) or 1,
                    etag_hash=source.get('etag_hash') or '',
                    created_by=created_by,
                    created_at=_parse_dt(source.get('created_at')) or None,
                ))
                inserted[ReportStudioTable.DOCUMENTS.value] += 1

                # 版本策略：full 全带；latest 只带当前版本
                doc_versions = versions_by_doc.get(source_doc_id) or []
                if scope == DocVersionScope.LATEST.value:
                    current_version = _as_int(source.get('current_version')) or 1
                    doc_versions = [r for r in doc_versions
                                    if _as_int(r.get('version')) == current_version]
                    if not doc_versions:
                        warnings.append(
                            f'文档 {source_doc_id} 缺少当前版本 {current_version} 的快照，'
                            f'已按无版本链导入')
                for row in doc_versions:
                    chart_specs = self._translate_chart_specs(
                        row.get('chart_specs') or {}, chart_mapping)
                    session.add(VersionPO(
                        doc_id=new_doc_id,
                        version=_as_int(row.get('version')) or 1,
                        markdown_content=row.get('markdown_content') or '',
                        chart_specs=chart_specs,
                        parent_version=_as_int(row.get('parent_version')),
                        snapshot_reason=row.get('snapshot_reason') or 'manual_edit',
                        created_by=created_by,
                        created_at=_parse_dt(row.get('created_at')) or None,
                    ))
                    inserted[ReportStudioTable.DOCUMENT_VERSIONS.value] += 1

                for row in charts_by_doc.get(source_doc_id) or []:
                    source_chart_id = str(row.get('chart_id') or '')
                    if not source_chart_id:
                        continue
                    new_chart_id = chart_mapping[source_chart_id]
                    source_report_id = _as_int(row.get('report_id'))
                    chart_report_id = report_id_mapping.get(source_report_id) \
                        if source_report_id is not None else None
                    if source_report_id is not None and chart_report_id is None:
                        warnings.append(
                            f'图表 {source_chart_id} 的来源报告 {source_report_id} 未随包搬运，'
                            f'report_id 已置空（需重新绑定）')
                    session.add(ChartSpecPO(
                        chart_id=new_chart_id,
                        doc_id=new_doc_id,
                        report_id=chart_report_id,
                        metric_params=row.get('metric_params') or {},
                        style=row.get('style') or {},
                        version=_as_int(row.get('version')) or 1,
                        created_by=created_by,
                        created_at=_parse_dt(row.get('created_at')) or None,
                    ))
                    inserted[ReportStudioTable.CHART_SPECS.value] += 1

            session.commit()
            log_not_emit('INFO', _MODULE_NAME,
                         f'Studio 文档导入完成 docs={inserted["report_studio_documents"]} '
                         f'versions={inserted["report_studio_document_versions"]} '
                         f'charts={inserted["report_studio_chart_specs"]} '
                         f'sessionDropped={session_dropped} warnings={len(warnings)}',
                         category='system')
            return {
                'document_id_mapping': doc_mapping,
                'chart_id_mapping': chart_mapping,
                'imported': inserted,
                'warnings': warnings,
                'session_dropped': session_dropped,
            }
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    # ---------- 内部 ----------

    @staticmethod
    def _topological_order(docs: List[dict], warnings: List[str]) -> List[dict]:
        """按 source_type 优先 + parent_doc_id 依赖排序（父文档先落）。

        包内存在环时，剩余文档按 source_type 顺序落库并把父引用降级为空。
        """
        by_id = {str(r.get('doc_id')): r for r in docs}
        ordered: List[dict] = []
        placed = set()
        pending = sorted(docs, key=lambda r: _SOURCE_TYPE_ORDER.get(
            str(r.get('source_type') or ''), len(_SOURCE_TYPE_ORDER)))
        while pending:
            progressed = False
            rest = []
            for row in pending:
                doc_id = str(row.get('doc_id'))
                parent = row.get('parent_doc_id')
                if not parent or str(parent) not in by_id or str(parent) in placed:
                    ordered.append(row)
                    placed.add(doc_id)
                    progressed = True
                else:
                    rest.append(row)
            if not progressed:
                # 父链成环：剩余行保留顺序落库，parent 在导入时降级为空
                for row in rest:
                    warnings.append(
                        f'文档 {row.get("doc_id")} 的父文档引用成环，parent_doc_id 已置空')
                    ordered.append(row)
                break
            pending = rest
        return ordered

    @staticmethod
    def _translate_chart_refs(chart_refs, chart_mapping: Dict[str, str],
                              warnings: List[str]) -> List[str]:
        """把 `chart:{sourceChartId}` 翻译成 A 侧 chart_id（包内全局映射）。

        跨文档引用（Agent 总结指向父文档图表）同样可翻译；包内确实没有的图表
        引用丢弃并写 warnings。
        """
        translated: List[str] = []
        for ref in chart_refs or []:
            text = str(ref)
            if text.startswith('chart:'):
                source_chart_id = text[len('chart:'):]
                new_chart_id = chart_mapping.get(source_chart_id)
                if new_chart_id is None:
                    warnings.append(f'文档图表引用 {text} 未随包搬运，已丢弃该引用')
                    continue
                translated.append(f'chart:{new_chart_id}')
            else:
                translated.append(text)
        return translated

    @staticmethod
    def _translate_chart_specs(chart_specs, rewrites: Dict[str, str]):
        """版本快照里的 chart_specs 可能内嵌 `chart:<id>` 文本，按映射替换。"""
        if not rewrites or chart_specs is None:
            return chart_specs or {}
        if isinstance(chart_specs, str):
            text = chart_specs
            for old, new in rewrites.items():
                text = text.replace(f'chart:{old}', f'chart:{new}')
            return text
        if isinstance(chart_specs, list):
            return [ReportStudioTransferRepository._translate_chart_specs(v, rewrites)
                    for v in chart_specs]
        if isinstance(chart_specs, dict):
            return {k: ReportStudioTransferRepository._translate_chart_specs(v, rewrites)
                    for k, v in chart_specs.items()}
        return chart_specs

    @staticmethod
    def _allocate_chart_id(source_chart_id: str, existing: set) -> str:
        if source_chart_id not in existing:
            existing.add(source_chart_id)
            return source_chart_id
        new_id = str(uuid4())
        while new_id in existing:
            new_id = str(uuid4())
        existing.add(new_id)
        return new_id


def _as_int(value) -> Optional[int]:
    if value is None or value == '':
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


report_studio_transfer_repository = ReportStudioTransferRepository()
