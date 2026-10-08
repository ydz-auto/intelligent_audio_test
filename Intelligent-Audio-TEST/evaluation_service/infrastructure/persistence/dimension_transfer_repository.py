# -*- coding: utf-8 -*-
"""维度评分导入导出仓储（evaluation_service 段：test_result_dimensions）

供 task_service 数据导入导出编排经 gRPC 调用：
- 导出（只读）：按 result_id 批量拉维度评分行 + 引用到的维度定义快照
- 导入（单事务）：主键冲突剥离 + test_result_id 重映射 + 批量写入
- 回滚：按批次登记主键删除
"""
import logging
from datetime import datetime
from typing import Dict, List, Set, Tuple

from shared.models.database import get_db_session
from shared.utils.log_handler import log_not_emit
from evaluation_service.infrastructure.persistence.models import (
    Dimension,
    TestResultDimension,
)

logger = logging.getLogger(__name__)

_MODULE_NAME = 'dimension_transfer_repository'

_DATETIME_FIELDS: Set[str] = {
    c.name for c in TestResultDimension.__table__.columns
    if getattr(c.type, 'python_type', None) is datetime
}


def _coerce_row(row: dict) -> dict:
    columns = {c.name for c in TestResultDimension.__table__.columns}
    coerced = {}
    for key, value in row.items():
        if key not in columns:
            log_not_emit('WARNING', _MODULE_NAME,
                         f'test_result_dimensions 未知列 {key}，已丢弃', category='system')
            continue
        if (value is not None and key in _DATETIME_FIELDS and isinstance(value, str)):
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


class DimensionTransferRepository:
    """维度评分导入导出仓储"""

    def export_by_result_ids(self, result_ids: List[int]) -> Tuple[List[dict], List[dict]]:
        """按 result_id 批量拉取维度评分行 + 引用到的维度定义快照（只读）"""
        if not result_ids:
            return [], []
        session = get_db_session()
        try:
            pos = (session.query(TestResultDimension)
                   .filter(TestResultDimension.test_result_id.in_(result_ids))
                   .all())
            rows = [_po_to_row(po) for po in pos]
            dim_ids = {row['dimension_id'] for row in rows if row.get('dimension_id') is not None}
            dim_defs = []
            if dim_ids:
                dim_pos = session.query(Dimension).filter(Dimension.id.in_(dim_ids)).all()
                for po in dim_pos:
                    dim_defs.append({
                        'id': po.id,
                        'name': po.name,
                        'dimension_type': po.dimension_type,
                        'parent_dimension_id': po.parent_dimension_id,
                        'description': po.description,
                        'type': po.type,
                        'result_type': po.result_type,
                        'weight': po.weight,
                        'sort_order': po.sort_order,
                        'statistic_method': po.statistic_method,
                    })
            return rows, dim_defs
        finally:
            session.close()

    def fetch_existing_ids(self) -> Set[int]:
        """test_result_dimensions 现有主键集合（冲突判定）"""
        session = get_db_session()
        try:
            return {row[0] for row in session.query(TestResultDimension.id).all()}
        finally:
            session.close()

    def import_rows(self, rows: List[dict],
                    result_id_mapping: Dict[int, int]) -> Tuple[Dict[int, int], List[int]]:
        """单事务写入维度评分：冲突剥离 + test_result_id 重映射 + 插入。

        两遍插入（缺陷 1 修复）：先插显式 id 行并同步自增序列，再插去 id 冲突行，
        避免同批次自增分配与显式 ID 撞 UNIQUE。

        Returns:
            (id_mapping {old: new}（含映射到自身）, inserted_pks)
        Raises: 任一写失败回滚并抛出。
        """
        session = get_db_session()
        try:
            existing = {row[0] for row in session.query(TestResultDimension.id).all()}
            kept: List[Tuple[int, dict]] = []
            conflicted: List[Tuple[int, dict]] = []
            for row in rows:
                rewritten = dict(row)
                old_result_id = rewritten.get('test_result_id')
                if old_result_id is not None:
                    rewritten['test_result_id'] = result_id_mapping.get(
                        old_result_id, old_result_id)
                old_id = rewritten.get('id')
                if old_id is not None and old_id in existing:
                    # 冲突行：去 id 交由自增分配，old_id 记入映射
                    rewritten.pop('id', None)
                    conflicted.append((old_id, rewritten))
                else:
                    kept.append((old_id, rewritten))

            pairs: List[Tuple[int, TestResultDimension]] = []
            for old_id, row in kept:
                po = TestResultDimension(**_coerce_row(row))
                session.add(po)
                pairs.append((old_id, po))
            session.flush()
            if conflicted:
                self._sync_sequences(session)
                for old_id, row in conflicted:
                    po = TestResultDimension(**_coerce_row(row))
                    session.add(po)
                    pairs.append((old_id, po))
                session.flush()
            self._sync_sequences(session)
            session.commit()
            return ({old_id: po.id for old_id, po in pairs},
                    [po.id for _, po in pairs])
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def rollback_by_pks(self, pks: List[int]) -> int:
        """按批次登记主键删除（补偿回滚）。返回删除行数"""
        if not pks:
            return 0
        session = get_db_session()
        try:
            count = session.query(TestResultDimension).filter(
                TestResultDimension.id.in_(pks)).delete(synchronize_session=False)
            session.commit()
            return count
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    @staticmethod
    def _sync_sequences(session) -> None:
        """显式 ID 插入后把自增序列上调到 GREATEST(当前 last_value, MAX(id))。

        审计问题 3：只上调不下调，避免回拨撞并发未提交消费的 id。
        仅 Postgres 需要；SQLite 无需处理。
        """
        if session.bind is None or session.bind.dialect.name != 'postgresql':
            return
        from sqlalchemy import text
        try:
            seq = session.execute(text(
                "SELECT pg_get_serial_sequence('test_result_dimensions', 'id')")).scalar()
            if not seq:
                return
            session.execute(text(
                "SELECT setval(:seq, GREATEST((SELECT last_value FROM " + seq + "), "
                "(SELECT COALESCE(MAX(id), 0) FROM test_result_dimensions), 1))"
            ), {'seq': seq})
        except Exception as e:
            log_not_emit('WARNING', _MODULE_NAME,
                         f'同步 test_result_dimensions 序列失败: {e}', category='system')


dimension_transfer_repository = DimensionTransferRepository()
