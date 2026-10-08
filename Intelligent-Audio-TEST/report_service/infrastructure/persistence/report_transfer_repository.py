# -*- coding: utf-8 -*-
"""报告 7 表导入导出仓储（report_service 段，INT-25）

供 task_service 数据导入导出编排经 gRPC 调用：
- 导出（只读）：按 task_id 批量拉报告 7 表行
- 导入（单事务）：主键冲突剥离 + task_id/report_id 重映射 + 批量写入
- 回滚：按批次登记主键逆依赖删除
"""
import logging
from datetime import datetime
from typing import Dict, List, Set, Tuple

from shared.models.database import get_db_session
from shared.utils.log_handler import log_not_emit
from report_service.infrastructure.persistence.models import (
    Report,
    ReportCase,
    ReportComparisonMatrix,
    ReportMetricStats,
    ReportRawData,
    ReportSummary,
    ReportSummaryMeta,
)

logger = logging.getLogger(__name__)

_MODULE_NAME = 'report_transfer_repository'

_TABLE_PO = {
    'test_reports': Report,
    'report_summaries': ReportSummary,
    'report_summary_meta': ReportSummaryMeta,
    'report_raw_data': ReportRawData,
    'report_cases': ReportCase,
    'report_metric_stats': ReportMetricStats,
    'report_comparison_matrix': ReportComparisonMatrix,
}
_CHILD_TABLES = ('report_summaries', 'report_summary_meta', 'report_raw_data',
                 'report_cases', 'report_metric_stats', 'report_comparison_matrix')
_ROLLBACK_ORDER = ('report_cases', 'report_metric_stats', 'report_raw_data',
                   'report_summary_meta', 'report_summaries',
                   'report_comparison_matrix', 'test_reports')

_DATETIME_FIELDS: Dict[str, Set[str]] = {}


def _datetime_fields(po_cls) -> Set[str]:
    name = po_cls.__tablename__
    if name not in _DATETIME_FIELDS:
        _DATETIME_FIELDS[name] = {
            c.name for c in po_cls.__table__.columns
            if getattr(c.type, 'python_type', None) is datetime
        }
    return _DATETIME_FIELDS[name]


def _coerce_row(po_cls, row: dict) -> dict:
    columns = {c.name for c in po_cls.__table__.columns}
    dt_fields = _datetime_fields(po_cls)
    coerced = {}
    for key, value in row.items():
        if key not in columns:
            log_not_emit('WARNING', _MODULE_NAME,
                         f'{po_cls.__tablename__} 未知列 {key}，已丢弃', category='system')
            continue
        if value is not None and key in dt_fields and isinstance(value, str):
            try:
                value = datetime.fromisoformat(value)
            except ValueError:
                value = None
        coerced[key] = value
    return coerced


def _po_to_row(po) -> dict:
    row = {}
    for column in po.__table__.columns:
        value = getattr(po, column.name)
        if isinstance(value, datetime):
            value = value.isoformat(timespec='seconds')
        row[column.name] = value
    return row


class ReportTransferRepository:
    """报告 7 表导入导出仓储"""

    def export_by_task_ids(self, task_ids: List[int]) -> Dict[str, List[dict]]:
        """按 task_id 批量拉取报告 7 表只读行。返回 {表名: 行列表}"""
        session = get_db_session()
        try:
            reports = (session.query(Report)
                       .filter(Report.task_id.in_(task_ids)).all()) if task_ids else []
            rows: Dict[str, List[dict]] = {'test_reports': [_po_to_row(po) for po in reports]}
            report_ids = [po.id for po in reports]
            for table in _CHILD_TABLES:
                po_cls = _TABLE_PO[table]
                pos = (session.query(po_cls)
                       .filter(po_cls.report_id.in_(report_ids)).all()) if report_ids else []
                rows[table] = [_po_to_row(po) for po in pos]
            return rows
        finally:
            session.close()

    def import_reports(self, tables_rows: Dict[str, List[dict]],
                       task_id_mapping: Dict[int, int]) -> Tuple[Dict[int, int], Dict[str, List[int]]]:
        """单事务写入报告 7 表：冲突剥离 + 外键重映射 + 插入。

        两遍插入（缺陷 1 修复）：每表先插显式 id 行并同步自增序列，再插去 id
        冲突行，避免同批次自增分配与显式 ID 撞 UNIQUE。

        Args:
            tables_rows: 表名 → 待插入行（冲突行无 'id' 键）
            task_id_mapping: test_tasks old→new 映射（来自 task_service 段）

        Returns:
            (report_id_mapping {old: new}, inserted_pks {表名: [主键]})
        Raises: 任一写失败回滚并抛出。
        """
        session = get_db_session()
        try:
            existing_ids = {
                table: {row[0] for row in session.query(po_cls.id).all()}
                for table, po_cls in _TABLE_PO.items()
            }

            def _conflicts(table: str, rows: List[dict]) -> List[int]:
                return [r['id'] for r in rows
                        if r.get('id') is not None and r['id'] in existing_ids[table]]

            # 1) test_reports：task_id 重映射后两遍插入 → report 映射
            report_rows = tables_rows.get('test_reports') or []
            report_conflicts = _conflicts('test_reports', report_rows)
            prepared = []
            for row in report_rows:
                rewritten = dict(row)
                old_task_id = rewritten.get('task_id')
                if old_task_id is not None:
                    rewritten['task_id'] = task_id_mapping.get(old_task_id, old_task_id)
                prepared.append(rewritten)
            report_pairs = _insert_two_pass(session, Report, 'test_reports',
                                            prepared, report_conflicts)
            report_mapping = {old_id: po.id for old_id, po in report_pairs}
            inserted_pks: Dict[str, List[int]] = {
                'test_reports': [po.id for _, po in report_pairs]}

            # 2) 子表：report_id 重映射后两遍插入
            for table in _CHILD_TABLES:
                po_cls = _TABLE_PO[table]
                rows = tables_rows.get(table) or []
                conflicts = _conflicts(table, rows)
                prepared_rows = []
                for row in rows:
                    rewritten = dict(row)
                    old_report_id = rewritten.get('report_id')
                    if old_report_id is not None:
                        rewritten['report_id'] = report_mapping.get(
                            old_report_id, old_report_id)
                    prepared_rows.append(rewritten)
                pairs = _insert_two_pass(session, po_cls, table,
                                         prepared_rows, conflicts)
                inserted_pks[table] = [po.id for _, po in pairs]

            _sync_sequences(session)
            session.commit()
            return report_mapping, inserted_pks
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def rollback_by_pks(self, tables_pks: Dict[str, List[int]]) -> Dict[str, int]:
        """按批次登记主键逆依赖删除（补偿回滚）。返回 {表名: 删除行数}"""
        session = get_db_session()
        try:
            deleted: Dict[str, int] = {}
            for table in _ROLLBACK_ORDER:
                pks = tables_pks.get(table) or []
                if not pks:
                    continue
                po_cls = _TABLE_PO[table]
                count = session.query(po_cls).filter(po_cls.id.in_(pks)).delete(
                    synchronize_session=False)
                deleted[table] = count
            _sync_sequences(session)
            session.commit()
            return deleted
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

def _insert_two_pass(session, po_cls, table: str, rows: List[dict],
                     conflict_old_ids: List[int]) -> List[Tuple[int, object]]:
    """同一表内「显式 ID 行 + 去 ID 冲突行」混插的两遍插入（缺陷 1 修复）。

    冲突行判定：id 命中 conflict_old_ids（或原本就无 id，配对 conflict_old_ids
    序列）。先插全部保留行 → flush → 把该表自增序列推到 max(id) → 再插全部
    冲突行 → flush，保证自增分配避开本批次显式 ID 集合（自增序列不感知同事务
    后续显式 ID 插入）。返回 [(old_id, po)]。
    """
    conflict_set = set(conflict_old_ids or [])
    conflict_iter = iter(conflict_old_ids or [])
    kept: List[Tuple[int, dict]] = []
    conflicted: List[Tuple[int, dict]] = []
    for row in rows:
        old_id = row.get('id')
        if old_id is not None and old_id in conflict_set:
            stripped = {k: v for k, v in row.items() if k != 'id'}
            conflicted.append((old_id, stripped))
        elif old_id is not None:
            kept.append((old_id, row))
        else:
            conflicted.append((next(conflict_iter), row))

    pairs: List[Tuple[int, object]] = []
    for old_id, row in kept:
        po = po_cls(**_coerce_row(po_cls, row))
        session.add(po)
        pairs.append((old_id, po))
    session.flush()
    if conflicted:
        _sync_sequences(session, [table])
        for old_id, row in conflicted:
            po = po_cls(**_coerce_row(po_cls, row))
            session.add(po)
            pairs.append((old_id, po))
        session.flush()
    return pairs


def _sync_sequences(session, tables=None) -> None:
    """显式 ID 插入后同步 Postgres 序列（SQLite 无需）。

    Args:
        tables: 指定表名列表；None 则同步全部 7 表。
    """
    if session.bind is None or session.bind.dialect.name != 'postgresql':
        return
    from sqlalchemy import text
    for table in (tables or _TABLE_PO):
        try:
            session.execute(text(
                "SELECT setval(pg_get_serial_sequence(:tbl, 'id'), "
                "GREATEST((SELECT COALESCE(MAX(id), 0) FROM " + table + "), 1))"
            ), {'tbl': table})
        except Exception as e:
            log_not_emit('WARNING', _MODULE_NAME,
                         f'同步 {table} 序列失败: {e}', category='system')


report_transfer_repository = ReportTransferRepository()
