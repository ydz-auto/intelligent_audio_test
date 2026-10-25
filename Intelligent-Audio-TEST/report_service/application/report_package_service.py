# -*- coding: utf-8 -*-
"""报告包（链路 3a + 3b + 3c）导入导出应用服务（report_service，INT-1764 D6）

链路 3a：平台报告 7 表原地替换（复用 INT-1762 D4 `ReplaceReports` 的同一实现）；
链路 3b / 3c：Report Studio 文档、版本快照、图表规格的拓扑序搬运。

本服务只处理 report_service 自有数据；任务定位 / 可见性 / ZIP 包结构与 manifest
由 task_service 编排层负责（DDD：跨服务读写一律 gRPC + ACL）。
"""
import logging
from typing import Dict, List, Optional

from shared.constants.data_transfer import (
    DEFAULT_DOC_VERSION_SCOPE,
    DocVersionScope,
    ReportPackageEntity,
    ReportStudioTable,
    REPORT_PACKAGE_WARNINGS_CAP,
)
from shared.utils.grpc_json import fold_business_code
from shared.utils.log_handler import log_not_emit
from report_service.application.report_replacement_service import (
    report_replacement_service,
)
from report_service.infrastructure.persistence.report_studio_transfer_repository import (
    report_studio_transfer_repository,
)
from report_service.infrastructure.persistence.report_transfer_repository import (
    report_transfer_repository,
)

logger = logging.getLogger(__name__)

_MODULE_NAME = 'report_package_service'

_REPORT_TABLE = 'test_reports'


def _as_int(value) -> Optional[int]:
    if value is None or value == '':
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _cap_warnings(warnings: List[str]) -> Dict[str, object]:
    """回执 warnings 截断（保留前 N 条 + 总条数）"""
    items = [str(w) for w in (warnings or [])]
    return {
        'warnings': items[:REPORT_PACKAGE_WARNINGS_CAP],
        'warningCount': len(items),
        'warningsTruncated': len(items) > REPORT_PACKAGE_WARNINGS_CAP,
    }


class ReportPackageService:
    """报告包导出 / 导入编排（report_service 段）"""

    def export_package(self, task_ids: List[int], report_ids: List[int] = None,
                       doc_version_scope: str = None) -> dict:
        """导出报告包数据段（3a 7 表 + 3b/3c Studio 三表）。

        Returns: {'success', 'message', 'data': {tables, studio, reportIds, entities}}
        """
        scope = (doc_version_scope or DEFAULT_DOC_VERSION_SCOPE).strip().lower()
        if scope not in {item.value for item in DocVersionScope}:
            return {'success': False, 'code': 400,
                    'message': f'docVersionScope 非法: {doc_version_scope!r}'}
        clean_task_ids = sorted({int(t) for t in (task_ids or []) if _as_int(t) is not None})
        clean_report_ids = sorted({int(r) for r in (report_ids or []) if _as_int(r) is not None})
        if not clean_task_ids and not clean_report_ids:
            return {'success': False, 'code': 400,
                    'message': 'taskId / reportIds 至少提供一个'}

        tables = report_transfer_repository.export_by_task_ids(clean_task_ids) \
            if clean_task_ids else {_REPORT_TABLE: []}
        if clean_report_ids:
            by_report = report_transfer_repository.export_by_report_ids(clean_report_ids)
            tables = self._merge_tables(tables, by_report)
        if not clean_task_ids:
            # 只按 reportIds 导出时，task_ids 由报告行反推（供编排层写 manifest）
            clean_task_ids = sorted({int(row['task_id'])
                                     for row in (tables.get(_REPORT_TABLE) or [])
                                     if _as_int(row.get('task_id')) is not None})

        package_report_ids = [int(row['id']) for row in (tables.get(_REPORT_TABLE) or [])
                              if _as_int(row.get('id')) is not None]
        studio = report_studio_transfer_repository.export_studio_rows(
            package_report_ids, scope)
        entities = self._collect_entities(tables, studio)
        return {'success': True, 'message': '', 'data': {
            'tables': {k: v for k, v in tables.items()},
            'studio': studio,
            'reportIds': package_report_ids,
            'taskIds': clean_task_ids,
            'docVersionScope': scope,
            'entities': entities,
            'counts': self._counts(tables, studio),
        }}

    def import_package(self, task_id, tables: Dict[str, List[dict]],
                       studio: Dict[str, List[dict]] = None,
                       target_report_id=None, batch_id: str = '',
                       doc_version_scope: str = None) -> dict:
        """导入报告包：3a 原地替换 → 3b/3c 拓扑序落库，失败按批次快照补偿。

        Returns: {'success', 'message', 'data': 回执, 'code'}
        """
        batch_id = batch_id or ''
        task_id_int = _as_int(task_id)
        if task_id_int is None:
            return {'success': False, 'code': 400,
                    'message': 'sourceTask.id 不能为空'}
        scope = (doc_version_scope or DEFAULT_DOC_VERSION_SCOPE).strip().lower()
        if scope not in {item.value for item in DocVersionScope}:
            return {'success': False, 'code': 400,
                    'message': f'docVersionScope 非法: {doc_version_scope!r}'}

        package_reports = [r for r in (tables.get(_REPORT_TABLE) or [])
                           if isinstance(r, dict)]
        warnings: List[str] = []
        replace_result: Dict[str, object] = {}
        report_id = None

        if package_reports:
            replace_result = report_replacement_service.replace_reports(
                tables, task_id_int, _as_int(target_report_id), batch_id)
            if not replace_result.get('success'):
                return {'success': False,
                        'message': replace_result.get('message') or '报告替换失败',
                        'code': replace_result.get('code') or 500,
                        'data': replace_result.get('data') or {}}
            replace_data = replace_result.get('data') or {}
            report_id = _as_int(replace_data.get('report_id'))
            warnings.extend(replace_data.get('warnings') or [])
        else:
            warnings.append('包内无平台报告行，仅导入 Studio 文档')

        # 3a 报告 id → A 报告 id：原地替换后包内报告统一指向目标报告
        report_id_mapping = {}
        if report_id is not None:
            for row in package_reports:
                source_report_id = _as_int(row.get('id'))
                if source_report_id is not None:
                    report_id_mapping[source_report_id] = report_id

        studio_tables = studio or {}
        studio_result = {}
        try:
            if any(studio_tables.get(table.value) for table in ReportStudioTable):
                studio_result = report_studio_transfer_repository.import_studio_rows(
                    studio_tables, report_id_mapping, scope)
        except Exception as e:
            log_not_emit('ERROR', _MODULE_NAME,
                         f'Studio 文档导入失败，补偿回滚 3a 替换 batch={batch_id}: {e}',
                         category='system', exc_info=True)
            compensation_error = None
            if package_reports and batch_id:
                try:
                    rollback = report_replacement_service.rollback_replacement(batch_id)
                    if not rollback.get('success'):
                        compensation_error = rollback.get('message')
                except Exception as re:
                    compensation_error = str(re)
            payload = {'batch_id': batch_id,
                       'compensationErrors': [compensation_error] if compensation_error else [],
                       'studioImportFailed': str(e)}
            return {'success': False,
                    'message': f'Studio 文档导入失败: {e}',
                    'code': 500,
                    'data': fold_business_code(payload, 500)}

        warnings.extend(studio_result.get('warnings') or [])
        receipt = {
            'sourceTaskId': task_id_int,
            'reportId': report_id,
            'targetResolvedBy': (replace_result.get('data') or {}).get('target_resolved_by'),
            'deletedCounts': (replace_result.get('data') or {}).get('deleted_counts') or {},
            'insertedCounts': (replace_result.get('data') or {}).get('inserted_counts') or {},
            'documentIdMapping': studio_result.get('document_id_mapping') or {},
            'chartIdMapping': studio_result.get('chart_id_mapping') or {},
            'imported': studio_result.get('imported') or {},
            # 规则 1 明示：DSH 会话不迁移，文档降级为普通可编辑文档
            'agentSessionDropped': int(studio_result.get('session_dropped') or 0),
            'docVersionScope': scope,
            'batchId': batch_id,
            'rollbackAvailable': bool(package_reports and batch_id),
        }
        receipt.update(_cap_warnings(warnings))
        log_not_emit('INFO', _MODULE_NAME,
                     f'报告包导入完成 task={task_id_int} report={report_id} '
                     f'docs={(studio_result.get("imported") or {}).get("report_studio_documents", 0)} '
                     f'warnings={len(warnings)}', category='system')
        return {'success': True, 'message': '', 'data': receipt}

    # ---------- 内部 ----------

    @staticmethod
    def _merge_tables(base: Dict[str, List[dict]],
                      extra: Dict[str, List[dict]]) -> Dict[str, List[dict]]:
        """按主键合并两次导出的表行（taskIds 与 reportIds 同时给出时取并集）"""
        merged: Dict[str, List[dict]] = {k: list(v or []) for k, v in base.items()}
        for table, rows in (extra or {}).items():
            current = merged.setdefault(table, [])
            seen = {row.get('id') for row in current if isinstance(row, dict)}
            for row in rows or []:
                if not isinstance(row, dict):
                    continue
                if row.get('id') is not None and row.get('id') in seen:
                    continue
                current.append(row)
        return merged

    @staticmethod
    def _collect_entities(tables: Dict[str, List[dict]],
                          studio: Dict[str, List[dict]]) -> List[str]:
        entities = []
        if tables.get(_REPORT_TABLE):
            entities.append(ReportPackageEntity.PLATFORM_REPORT.value)
        documents = studio.get(ReportStudioTable.DOCUMENTS.value) or []
        if any(d.get('source_type') == ReportPackageEntity.UPLOADED_FILE.value
               for d in documents):
            entities.append(ReportPackageEntity.UPLOADED_FILE.value)
        if any(d.get('source_type') == ReportPackageEntity.AGENT_SUMMARY.value
               for d in documents):
            entities.append(ReportPackageEntity.AGENT_SUMMARY.value)
        return entities

    @staticmethod
    def _counts(tables: Dict[str, List[dict]],
                studio: Dict[str, List[dict]]) -> Dict[str, int]:
        counts = {table: len(rows or []) for table, rows in (tables or {}).items()}
        counts.update({table: len(rows or []) for table, rows in (studio or {}).items()})
        return counts


report_package_service = ReportPackageService()
