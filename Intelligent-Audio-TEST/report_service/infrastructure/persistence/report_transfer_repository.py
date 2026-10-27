# -*- coding: utf-8 -*-
"""报告 8 表导入导出仓储（report_service 段，INT-25 / INT-1995）

供 task_service 数据导入导出编排经 gRPC 调用：
- 导出（只读）：按 task_id 批量拉报告 8 表行（含 report_case_snapshots，
  按被引用 sha 携带；payload_gz 为 bytea，JSON 包内按 base64 编码）
- 导入（单事务）：主键冲突剥离 + task_id/report_id 重映射 + 批量写入；
  快照行**先建**（ON CONFLICT (sha256) DO NOTHING）、再建用例行（避免悬空指针）
- 回滚：按批次登记主键逆依赖删除（**不含**快照行——快照被多份报告共享，
  按报告删会打断别的报告的解引用，孤儿由低频 sweep 回收）
"""
import base64
import logging
from datetime import datetime
from typing import Dict, List, Set, Tuple

from shared.models.database import get_db_session
from shared.utils.log_handler import log_not_emit
from report_service.infrastructure.persistence.models import (
    Report,
    ReportCase,
    ReportCaseSnapshot,
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

# INT-1995（档4 M1）：快照表不在 _TABLE_PO/_CHILD_TABLES 里——它无自增 id（不能走
# _insert_two_pass）、无 report_id（不能按报告过滤），是内容寻址共享资产。单独
# 一组常量：导出按被引用 sha 携带，导入先行 ON CONFLICT 写入，回滚不碰它。
_SNAPSHOT_TABLE = 'report_case_snapshots'
_SNAPSHOT_PO = ReportCaseSnapshot

_DATETIME_FIELDS: Dict[str, Set[str]] = {}


def apply_snapshot_to_row(session, row: dict) -> dict:
    """导入 / 搬运链路：按行上九字段内容列重算用例配置快照并覆盖 4 个指针列。

    INT-1994（档4 R1）：``report_case_snapshots`` 不随导出包迁移，包里带过来的
    ``snapshot_sha256`` 在目标库是悬空指针 —— 不重算就会让快照读源的报告详情
    直接报错。

    INT-1995（档4 M1）：快照表已纳入 transfer 表集，M1 之后的包只带「指针列 +
    快照行」（内容列已 DROP），本函数对纯指针行原样保留（快照行已由导入侧先行
    写入）；R1 时代的旧包（带内容列）仍按内容列重算覆盖，双向兼容。
    """
    from report_service.infrastructure.persistence.report_case_snapshot_store import (
        apply_to_row,
    )
    return apply_to_row(session, row)


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


# ------------------------------------------------------------------ 快照行（INT-1995）

def _snapshot_po_to_row(po) -> dict:
    """快照行导出：``payload_gz``（bytea）按 base64 进 JSON（JSON 不能直带 bytes）。

    其余列与 ``_po_to_row`` 同口径（``created_at`` timestamptz → ISO 串）。
    """
    row = {}
    for column in po.__table__.columns:
        value = getattr(po, column.name)
        if column.name == 'payload_gz':
            value = base64.b64encode(bytes(value or b'')).decode('ascii')
        elif isinstance(value, datetime):
            value = value.isoformat(timespec='seconds')
        row[column.name] = value
    return row


def _coerce_snapshot_row(row: dict) -> dict:
    """快照行导入：先按通用列过滤，再把 ``payload_gz`` 的 base64 串解码回 bytes。"""
    coerced = _coerce_row(_SNAPSHOT_PO, row)
    raw = coerced.get('payload_gz')
    if isinstance(raw, str):
        try:
            coerced['payload_gz'] = base64.b64decode(raw)
        except (ValueError, TypeError):
            coerced['payload_gz'] = None
    return coerced


def _insert_snapshots(session, rows: List[dict]) -> None:
    """内容寻址快照行：``INSERT ... ON CONFLICT (sha256) DO NOTHING``（幂等）。

    与在线写路径 ``report_case_snapshot_store.put`` 同语义；不走 ``_insert_two_pass``
    （那张路径为自增 id 表设计，快照表主键是 ``sha256`` 且无 ``id``）。同一事务内
    必须**先于此批用例行**写入，否则「行上有指针、表里没内容」悬空。
    """
    if not rows:
        return
    dialect = session.bind.dialect.name if session.bind is not None else ''
    if dialect in ('postgresql', 'sqlite'):
        if dialect == 'postgresql':
            from sqlalchemy.dialects.postgresql import insert as _insert
        else:
            from sqlalchemy.dialects.sqlite import insert as _insert
    else:  # pragma: no cover - 生产是 PG，测试是 sqlite
        _insert = None
    for row in rows:
        if not isinstance(row, dict):
            continue
        coerced = _coerce_snapshot_row(row)
        sha = str(coerced.get('sha256') or '').strip()
        if not sha or coerced.get('payload_gz') is None:
            log_not_emit('WARNING', _MODULE_NAME,
                         f'快照行缺 sha256 或 payload_gz，已跳过', category='system')
            continue
        if _insert is not None:
            stmt = _insert(_SNAPSHOT_PO).values(**coerced).on_conflict_do_nothing(
                index_elements=['sha256'])
            session.execute(stmt)
        else:  # pragma: no cover - 兜底方言
            exists = session.query(_SNAPSHOT_PO.sha256).filter(
                _SNAPSHOT_PO.sha256 == sha).first()
            if exists is None:
                session.add(_SNAPSHOT_PO(**coerced))


def _referenced_snapshot_shas(case_rows: List[dict]) -> List[str]:
    """用例行里被引用的快照 sha（去空 / 去重，供导出携带快照行）。"""
    return sorted({str(row.get('snapshot_sha256') or '').strip()
                   for row in (case_rows or [])
                   if str(row.get('snapshot_sha256') or '').strip()})


def _export_snapshots(session, shas: List[str]) -> List[dict]:
    """按 sha 列表拉取快照行（内容寻址，同一 sha 天然只出现一次）。"""
    if not shas:
        return []
    pos = (session.query(_SNAPSHOT_PO)
           .filter(_SNAPSHOT_PO.sha256.in_(shas)).all())
    return [_snapshot_po_to_row(po) for po in pos]


class ReportTransferRepository:
    """报告 8 表导入导出仓储"""

    def export_by_task_ids(self, task_ids: List[int]) -> Dict[str, List[dict]]:
        """按 task_id 批量拉取报告 8 表只读行。返回 {表名: 行列表}"""
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
            # INT-1995：快照表随包携带（只带本批用例行引用的 sha，内容寻址去重）
            case_shas = _referenced_snapshot_shas(rows.get('report_cases') or [])
            rows[_SNAPSHOT_TABLE] = _export_snapshots(session, case_shas)
            return rows
        finally:
            session.close()

    def export_by_report_ids(self, report_ids: List[int]) -> Dict[str, List[dict]]:
        """按报告 id 批量拉取报告 8 表只读行（INT-1764：报告包按 reportIds 导出）"""
        clean_ids = [int(rid) for rid in (report_ids or [])]
        session = get_db_session()
        try:
            reports = (session.query(Report)
                       .filter(Report.id.in_(clean_ids)).all()) if clean_ids else []
            rows: Dict[str, List[dict]] = {'test_reports': [_po_to_row(po) for po in reports]}
            found_ids = [po.id for po in reports]
            for table in _CHILD_TABLES:
                po_cls = _TABLE_PO[table]
                pos = (session.query(po_cls)
                       .filter(po_cls.report_id.in_(found_ids)).all()) if found_ids else []
                rows[table] = [_po_to_row(po) for po in pos]
            # INT-1995：快照表随包携带（只带本批用例行引用的 sha）
            case_shas = _referenced_snapshot_shas(rows.get('report_cases') or [])
            rows[_SNAPSHOT_TABLE] = _export_snapshots(session, case_shas)
            return rows
        finally:
            session.close()

    def import_reports(self, tables_rows: Dict[str, List[dict]],
                       task_id_mapping: Dict[int, int]) -> Tuple[Dict[int, int], Dict[str, List[int]]]:
        """单事务写入报告 8 表：冲突剥离 + 外键重映射 + 插入。

        两遍插入（缺陷 1 修复）：每表先插显式 id 行并同步自增序列，再插去 id
        冲突行，避免同批次自增分配与显式 ID 撞 UNIQUE。

        INT-1995（档4 M1）：**先建快照行再建用例行**——快照行走内容寻址
        ``ON CONFLICT (sha256) DO NOTHING``（无自增 id，不走两遍插入）；用例行
        带包内指针，快照先行保证「行上有指针、表里有内容」不悬空。回滚不碰
        快照行（共享资产，孤儿由低频 sweep 回收）。

        Args:
            tables_rows: 表名 → 待插入行（冲突行无 'id' 键）
            task_id_mapping: test_tasks old→new 映射（来自 task_service 段）

        Returns:
            (report_id_mapping {old: new}, inserted_pks {表名: [主键]})
        Raises: 任一写失败回滚并抛出。
        """
        session = get_db_session()
        try:
            # 0) 快照行先行（内容寻址、幂等；M1 包携带，R1 旧包无此行则 no-op）
            _insert_snapshots(session, tables_rows.get(_SNAPSHOT_TABLE) or [])

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
                    if table == 'report_cases':
                        # INT-1994/1995：快照行已先行写入（或 R1 旧包按内容列重算，
                        # 见 apply_snapshot_to_row）——先写快照再插用例行，不悬空。
                        rewritten = apply_snapshot_to_row(session, rewritten)
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
            # 审计问题 3：回滚路径不做序列同步（纯装饰性且可能向下回拨）
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
    """显式 ID 插入后把自增序列上调到 GREATEST(当前 last_value, MAX(id))。

    审计问题 3：只上调不下调，避免回拨撞并发未提交消费的 id。
    仅 Postgres 需要；SQLite 无需处理。
    Args:
        tables: 指定表名列表；None 则同步全部 7 表。
    """
    if session.bind is None or session.bind.dialect.name != 'postgresql':
        return
    from sqlalchemy import text
    for table in (tables or _TABLE_PO):
        try:
            seq = session.execute(text("SELECT pg_get_serial_sequence(:tbl, 'id')"),
                                  {'tbl': table}).scalar()
            if not seq:
                continue
            session.execute(text(
                "SELECT setval(:seq, GREATEST((SELECT last_value FROM " + seq + "), "
                "(SELECT COALESCE(MAX(id), 0) FROM " + table + "), 1))"
            ), {'seq': seq})
        except Exception as e:
            log_not_emit('WARNING', _MODULE_NAME,
                         f'同步 {table} 序列失败: {e}', category='system')


report_transfer_repository = ReportTransferRepository()
