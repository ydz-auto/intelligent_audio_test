# -*- coding: utf-8 -*-
"""增量回导报告原地替换仓储（report_service 段，INT-1762 D4）

D0 裁定（INT-1758 A5）落地口径 —— 与设计文档初稿「先删旧报告再写新报告」相反：

1. **原地替换、保留 A 报告 id**：`UPDATE test_reports` 只覆盖内容字段
   （name / description / analysis / status），保留 `visibility` /
   `created_by_user_id` / `type` / `created_at`。B 的用户 id 在 A 不存在，直接写入
   会让 owner 校验失效、私有报告泄漏给 shared 读者。
2. **目标报告定位顺序**：① 调用方给的 `target_report_id`（编排层经 source_map
   翻译）→ ② A 原任务下 `type='task' AND deleted=false` 的最新报告（与
   `published_task_repository` 取「该任务最新报告」同口径）→ ③ 都没有则新建。
3. **单事务先写后删**：父行覆盖 + 子表重建 + 旧值快照全部在同一事务内，失败整
   事务回滚、旧报告完好；不出现「报告没了」的中间态。
4. **不得复用 `regenerate_report`** 的删旧建新路径（会换新 id，使 studio 文档 /
   收藏 / benchmark 引用全部变孤儿）。
5. A8：旧报告 7 表旧行 + 本批新写入行都落 `report_merge_snapshots`（同事务），
   供 `RollbackReportReplacement` 逐字段恢复。
"""
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from sqlalchemy import String, cast
from sqlalchemy.orm import Session

from shared.constants.data_transfer import BATCH_TTL_SECONDS
from shared.models.database import get_db_session, utc8now
from shared.utils.log_handler import log_not_emit
from report_service.infrastructure.persistence.models import (
    BenchmarkRanking,
    BenchmarkReport,
    Report,
    ReportCase,
    ReportComparisonMatrix,
    ReportFavorite,
    ReportMergeSnapshot,
    ReportMetricStats,
    ReportRawData,
    ReportShare,
    ReportStudioChartSpec,
    ReportStudioDocument,
    ReportSummary,
    ReportSummaryMeta,
)
from report_service.infrastructure.persistence.report_transfer_repository import (
    _coerce_row,
    _sync_sequences,
)

logger = logging.getLogger(__name__)

_MODULE_NAME = 'report_replacement_repository'

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

# A5-1：原地替换只覆盖内容字段，其余字段（visibility / created_by_user_id /
# type / created_at）保留 A 侧值
_CONTENT_FIELDS = ('name', 'description', 'analysis', 'status')

# A5-1 表末：引用 test_reports.id 的全部资产（孤儿检查口径）
_ORPHAN_SOURCES = (
    ('studio_doc', ReportStudioDocument, 'report_id', 'doc_id'),
    ('studio_chart', ReportStudioChartSpec, 'report_id', 'chart_id'),
    ('benchmark_report', BenchmarkReport, 'report_id', 'id'),
    ('benchmark_ranking', BenchmarkRanking, 'report_id', 'id'),
    ('share', ReportShare, 'report_id', 'id'),
)


class ReplacementValidationError(Exception):
    """替换前置校验失败（携带 HTTP 语义业务码与明细，不产生任何写入）"""

    def __init__(self, message: str, code: int = 400, detail: Optional[dict] = None):
        super().__init__(message)
        self.code = code
        self.detail = detail or {}


def _snapshot_payload(po) -> dict:
    """旧行全字段 JSON（时间戳保留微秒精度，回滚才能逐字段还原）。

    不能复用 `_po_to_row`：它按 `timespec='seconds'` 序列化，会丢掉微秒。
    """
    row = {}
    for column in po.__table__.columns:
        value = getattr(po, column.name)
        if isinstance(value, datetime):
            value = value.isoformat()
        row[column.name] = value
    return row


def _as_int(value) -> Optional[int]:
    if value is None or value == '':
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _clean_tables(rows_by_table: Dict[str, List[dict]]) -> Dict[str, List[dict]]:
    return {table: [r for r in (rows or []) if isinstance(r, dict)]
            for table, rows in (rows_by_table or {}).items() if table in _TABLE_PO}


class ReportReplacementRepository:
    """报告 7 表原地替换 + 批次快照回滚"""

    # ---- 替换 ----

    def replace_reports(self, rows_by_table: Dict[str, List[dict]],
                        task_id: int,
                        target_report_id: Optional[int] = None,
                        batch_id: str = '') -> dict:
        """把包内报告 7 表原地替换到 A 原任务的目标报告上（单事务）。

        Raises:
            ReplacementValidationError: 包内容非法（400）或目标报告解析失败。
        """
        if not batch_id:
            raise ReplacementValidationError('batch_id 不能为空', code=400)
        task_id = _as_int(task_id)
        if task_id is None:
            raise ReplacementValidationError('task_id 不能为空', code=400)

        tables = _clean_tables(rows_by_table)
        package_reports = tables.get('test_reports') or []
        if not package_reports:
            raise ReplacementValidationError('包内缺少 test_reports 行', code=400)

        warnings: List[str] = []
        source = self._pick_package_report(package_reports, target_report_id, warnings)
        package_report_id = _as_int(source.get('id'))

        session = get_db_session()
        try:
            target = self._resolve_target(session, task_id, target_report_id)
            deleted_counts: Dict[str, int] = {}
            snapshot_rows: List[ReportMergeSnapshot] = []

            if target is None:
                report = self._create_report(session, source, task_id)
            else:
                self._snapshot_report(session, target, batch_id, snapshot_rows)
                # 子表旧行快照（随后删除重建）
                for table in _CHILD_TABLES:
                    po_cls = _TABLE_PO[table]
                    old_pos = (session.query(po_cls)
                               .filter(po_cls.report_id == target.id).all())
                    for po in old_pos:
                        snapshot_rows.append(ReportMergeSnapshot(
                            batch_id=batch_id, entity_table=table,
                            entity_pk=po.id, old_row=_snapshot_payload(po)))
                    if old_pos:
                        count = (session.query(po_cls)
                                 .filter(po_cls.report_id == target.id)
                                 .delete(synchronize_session=False))
                        deleted_counts[table] = count
                self._apply_content(session, target, source)
                report = target

            session.flush()
            report_id = report.id

            # 子表重建：id 由 A 重新分配，report_id 固定为目标报告 id
            inserted_pks: Dict[str, List[int]] = {}
            for table in _CHILD_TABLES:
                po_cls = _TABLE_PO[table]
                rows = self._package_child_rows(tables, table, package_report_id,
                                                report_id)
                new_pos = []
                for row in rows:
                    po = po_cls(**_coerce_row(po_cls, row))
                    session.add(po)
                    new_pos.append(po)
                if new_pos:
                    session.flush()
                inserted_pks[table] = [po.id for po in new_pos]
                for po in new_pos:
                    snapshot_rows.append(ReportMergeSnapshot(
                        batch_id=batch_id, entity_table=table,
                        entity_pk=po.id, old_row=None))

            session.add_all(snapshot_rows)
            self._purge_expired_snapshots(session)
            orphan_refs = self._orphan_references(session)
            session.commit()

            if orphan_refs:
                warnings.append(f'替换后存在 {len(orphan_refs)} 条悬空报告引用: {orphan_refs[:20]}')
            log_not_emit('INFO', _MODULE_NAME,
                         f'报告原地替换完成 batch={batch_id} task={task_id} '
                         f'report={report_id} deleted={deleted_counts} '
                         f'inserted={ {k: len(v) for k, v in inserted_pks.items()} }',
                         category='system')
            return {
                'replaced_tasks': [task_id],
                'report_id': report_id,
                'target_resolved_by': ('target_report_id' if target_report_id
                                       and target_report_id == report_id
                                       else ('latest_report' if target is not None
                                             else 'created')),
                'deleted_counts': deleted_counts,
                'inserted_counts': {k: len(v) for k, v in inserted_pks.items()},
                'inserted_report_ids': [report_id],
                'warnings': warnings,
                'batch_id': batch_id,
                'rollback_available': True,
            }
        except ReplacementValidationError:
            raise
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    # ---- 回滚 ----

    def rollback_by_batch(self, batch_id: str) -> dict:
        """按批次快照回滚：删除本批新行 + 原样插回旧报告 7 表行（单事务）。

        无快照（已回滚或超过 7 天 TTL）→ 视为无可回滚内容，不报错；补偿过程中
        任一步失败则整体回滚并抛错（编排层据此显式要求人工介入）。
        """
        session = get_db_session()
        try:
            snapshots = (session.query(ReportMergeSnapshot)
                         .filter(ReportMergeSnapshot.batch_id == batch_id)
                         .order_by(ReportMergeSnapshot.id.asc())
                         .all())
            if not snapshots:
                return {'batch_id': batch_id, 'deleted': {}, 'restored': {},
                        'nothing_to_rollback': True}

            new_by_table: Dict[str, List[int]] = {}
            old_by_table: Dict[str, List[dict]] = {}
            for snap in snapshots:
                if snap.old_row is None:
                    if snap.entity_pk is not None:
                        new_by_table.setdefault(snap.entity_table, []).append(snap.entity_pk)
                else:
                    old_by_table.setdefault(snap.entity_table, []).append(snap.old_row)

            deleted: Dict[str, int] = {}
            # 1) 删本批新行：子表先删、父表最后（逆依赖）
            for table in _CHILD_TABLES + ('test_reports',):
                pks = new_by_table.get(table) or []
                if not pks:
                    continue
                po_cls = _TABLE_PO[table]
                deleted[table] = (session.query(po_cls)
                                  .filter(po_cls.id.in_(pks))
                                  .delete(synchronize_session=False))
            # 2) 删当前同名旧主键行（父行被原地 UPDATE，需先移除当前内容）
            for table in _CHILD_TABLES + ('test_reports',):
                for old_row in old_by_table.get(table) or []:
                    pk = _as_int(old_row.get('id'))
                    if pk is None:
                        continue
                    po_cls = _TABLE_PO[table]
                    (session.query(po_cls).filter(po_cls.id == pk)
                     .delete(synchronize_session=False))
            # 3) 插回旧行：父表先插、子表按依赖顺序
            restored: Dict[str, int] = {}
            for table in ('test_reports',) + _CHILD_TABLES:
                rows = old_by_table.get(table) or []
                if not rows:
                    continue
                po_cls = _TABLE_PO[table]
                for old_row in rows:
                    session.add(po_cls(**_coerce_row(po_cls, dict(old_row))))
                restored[table] = len(rows)
            session.flush()
            _sync_sequences(session)

            (session.query(ReportMergeSnapshot)
             .filter(ReportMergeSnapshot.batch_id == batch_id)
             .delete(synchronize_session=False))
            session.commit()
            log_not_emit('INFO', _MODULE_NAME,
                         f'报告替换回滚完成 batch={batch_id} deleted={deleted} '
                         f'restored={restored}', category='system')
            return {'batch_id': batch_id, 'deleted': deleted, 'restored': restored}
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    # ---- 内部 ----

    @staticmethod
    def _pick_package_report(package_reports: List[dict],
                             target_report_id: Optional[int],
                             warnings: List[str]) -> dict:
        """从包内 test_reports 行里挑出「本次要写入的那一份」。

        A5 只替换一个目标报告（历史多报告场景不动其它报告）：优先取 id 与
        target_report_id 一致的行，否则取 created_at 最新的一行。
        """
        if target_report_id is not None:
            for row in package_reports:
                if _as_int(row.get('id')) == target_report_id:
                    return row
        if len(package_reports) == 1:
            return package_reports[0]
        latest = max(package_reports,
                     key=lambda r: str(r.get('created_at') or ''))
        ignored = [r.get('id') for r in package_reports if r is not latest]
        if ignored:
            warnings.append(f'包内存在多份报告，仅替换最新一份，忽略: {ignored}')
        return latest

    @staticmethod
    def _resolve_target(session: Session, task_id: int,
                        target_report_id: Optional[int]) -> Optional[Report]:
        """目标报告定位：① 指定 id → ② 任务下最新 task 型报告 → ③ None（新建）"""
        if target_report_id is not None:
            po = session.query(Report).filter(Report.id == target_report_id).first()
            if po is not None and not po.deleted:
                return po
        return (session.query(Report)
                .filter(Report.task_id == task_id,
                        Report.type == 'task',
                        Report.deleted.is_(False))
                .order_by(Report.id.desc())
                .first())

    @staticmethod
    def _snapshot_report(session: Session, report: Report, batch_id: str,
                         snapshot_rows: List[ReportMergeSnapshot]) -> None:
        snapshot_rows.append(ReportMergeSnapshot(
            batch_id=batch_id, entity_table='test_reports',
            entity_pk=report.id, old_row=_snapshot_payload(report)))

    @staticmethod
    def _apply_content(session: Session, report: Report, source: dict) -> None:
        """A5-1：只覆盖内容字段，保留 visibility / created_by_user_id / type / created_at"""
        for field in _CONTENT_FIELDS:
            if field in source and source[field] is not None:
                setattr(report, field, source[field])

    @staticmethod
    def _create_report(session: Session, source: dict, task_id: int) -> Report:
        """A5-2 ③：原任务下没有任何报告 → 按包内父行新建。

        B 的用户 id / 私有可见性在本服务无意义（引用方本来就为空），统一落
        `visibility='shared'`、`created_by_user_id=None`，避免写入 A 不存在的用户。
        """
        report = Report(
            name=source.get('name') or '导入报告',
            type=source.get('type') or 'task',
            description=source.get('description'),
            analysis=source.get('analysis'),
            status=source.get('status') or 'published',
            task_id=task_id,
            visibility='shared',
            created_by_user_id=None,
        )
        session.add(report)
        session.flush()
        return report

    @staticmethod
    def _package_child_rows(tables: Dict[str, List[dict]], table: str,
                            package_report_id: Optional[int], report_id: int) -> List[dict]:
        """取该包内报告的子表行：id 剥离、report_id 固定为目标报告 id。

        包内多报告时只取被选中那一份的子表行（它按 report_id 引用自己的父行）；
        包内父行无 id（单报告包）时取全部行。
        """
        rows = tables.get(table) or []
        if package_report_id is not None:
            selected = [r for r in rows
                        if _as_int(r.get('report_id')) == package_report_id]
        else:
            selected = rows
        cleaned = []
        for row in selected:
            payload = {k: v for k, v in row.items() if k not in ('id', 'report_id')}
            payload['report_id'] = report_id
            cleaned.append(payload)
        return cleaned

    @staticmethod
    def _orphan_references(session: Session) -> List[str]:
        """A5-5：替换后引用方孤儿检查（期望为空）。

        原地替换保留报告 id，理论上不应产生新孤儿；仍按 A5 口径逐表核对一次，
        结果非空时写进回执 warnings。`report_favorites.entity_id` 是字符串化 id。
        """
        found: List[str] = []
        for name, po_cls, column, pk_name in _ORPHAN_SOURCES:
            pk = getattr(po_cls, pk_name)
            rows = (session.query(pk)
                    .filter(getattr(po_cls, column).isnot(None),
                            ~session.query(Report.id).filter(
                                Report.id == getattr(po_cls, column)).exists())
                    .limit(20).all())
            found.extend(f'{name}:{row[0]}' for row in rows)
        # 收藏：entity_type='report' + entity_id 为字符串化的报告 id
        exists = (session.query(Report.id)
                  .filter(cast(Report.id, String) == ReportFavorite.entity_id,
                          ReportFavorite.entity_type == 'report').exists())
        fav_rows = (session.query(ReportFavorite.id)
                    .filter(ReportFavorite.entity_type == 'report',
                            ~exists)
                    .limit(20).all())
        found.extend(f'favorite:{row[0]}' for row in fav_rows)
        return found

    @staticmethod
    def _purge_expired_snapshots(session: Session) -> None:
        """清掉超过 BATCH_TTL_SECONDS 的批次快照（A8-4：保留 7 天供人工回滚）。"""
        try:
            deadline = utc8now() - timedelta(seconds=BATCH_TTL_SECONDS)
            (session.query(ReportMergeSnapshot)
             .filter(ReportMergeSnapshot.created_at < deadline)
             .delete(synchronize_session=False))
        except Exception as e:
            log_not_emit('WARNING', _MODULE_NAME,
                         f'清理过期报告快照失败: {e}', category='system')


report_replacement_repository = ReportReplacementRepository()
