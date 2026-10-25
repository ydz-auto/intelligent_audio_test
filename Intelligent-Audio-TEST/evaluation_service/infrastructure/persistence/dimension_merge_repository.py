# -*- coding: utf-8 -*-
"""增量回导维度合并仓储（evaluation_service 段，INT-1762 D4）

D0 裁定（INT-1758）落地口径：
- A2-5 合并语义是 **`(test_result_id, dimension_id)` 覆盖集**，不是整行 upsert：
  先删 A 侧该结果在这些维度下的旧行（含各 `round_number`），再插包内行；包内未
  出现的维度保持不动。纯 upsert 会把「B 少评了某轮」留成脏数据。
- A2-2/A2-3 只覆盖已存在的 result：包内 `test_result_id` 在 A 库（task_service）不存在
  → 整体拒绝（`409` + 明细），零写入，不静默跳过。**判定口径是「result 存在」，
  不是「已有维度行」**：A 侧执行了但未评估/评估失败的结果在增量回导时本就没有维度
  行，B 侧重评出的分数要能插进来（与 `ImportDimensions` 整包导入同口径）。
- A2-4 维度 id 翻译：包内若仍是 B 的 `dimension_id`，由编排层按
  (name, 父链, task_type_code) 映射成 A 的 id 后传入 `dimension_id_mapping`；
  映射不到的维度行**跳过并计入回执**，绝不直写 B 的 dimension_id。
- A8 旧值快照：被覆盖的旧行 + 本批新插入行在同一事务内写入
  `evaluation_merge_snapshots`，保证「要么有快照要么没动数据」。
"""
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set, Tuple

from shared.constants.data_transfer import BATCH_TTL_SECONDS
from shared.models.database import get_db_session, utc8now
from shared.utils.log_handler import log_not_emit
from evaluation_service.infrastructure.persistence.models import (
    EvaluationMergeSnapshot,
    TestResultDimension,
)
from evaluation_service.infrastructure.persistence.dimension_transfer_repository import (
    _coerce_row,
)

logger = logging.getLogger(__name__)

_MODULE_NAME = 'dimension_merge_repository'

_TABLE = 'test_result_dimensions'


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


class MergeValidationError(Exception):
    """合并前置校验失败（携带 HTTP 语义业务码与明细，不产生任何写入）"""

    def __init__(self, message: str, code: int = 409, detail: Optional[dict] = None):
        super().__init__(message)
        self.code = code
        self.detail = detail or {}


def _as_int(value) -> Optional[int]:
    if value is None or value == '':
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _result_exists(result_id: int) -> bool:
    """A2-3 存在性校验：走 task_service ACL（DDD 红线，不直读它域表）。

    ACL 返回 None 既覆盖「不存在」也覆盖「调用失败」——两种情况都按不可写处理，
    宁可整批拒绝也不半写。映射/过滤已在 `merge_rows` 内完成，这里只看最终 A id。
    """
    from evaluation_service.infrastructure.acl.task_acl_repository import (
        task_acl_repository,
    )
    return task_acl_repository.get_test_result_by_id(result_id) is not None


class DimensionMergeRepository:
    """维度评分覆盖集合并 + 批次快照回滚"""

    # ---- 合并 ----

    def merge_rows(self, rows: List[dict],
                   result_id_mapping: Optional[Dict[int, int]] = None,
                   dimension_id_mapping: Optional[Dict[int, int]] = None,
                   batch_id: str = '') -> dict:
        """按 (result_id, dimension_id) 覆盖集合并包内维度行（单事务）。

        Args:
            rows: 包内 test_result_dimensions 行（引用 A 原始 test_result_id）
            result_id_mapping: 可选 old→new（增量包内已是 A id 时为空/等价）
            dimension_id_mapping: 可选 B 维度 id → A 维度 id；非空时未命中映射的行
                被跳过并计入 `skipped_dimensions`
            batch_id: 编排方批次 ID（快照按它回滚）

        Raises:
            MergeValidationError: 包内 result id 在 A 库不存在（code=409）；已有维度行
                与否不影响成败（无维度行时 deleted=0，直接插入）。
        """
        if not batch_id:
            raise MergeValidationError('batch_id 不能为空', code=400)

        result_map = {int(k): int(v) for k, v in (result_id_mapping or {}).items()}
        dim_map = {int(k): int(v) for k, v in (dimension_id_mapping or {}).items()}

        prepared: List[dict] = []
        skipped_dims: List[int] = []
        invalid_rows: List[int] = []
        for index, raw in enumerate(rows or []):
            if not isinstance(raw, dict):
                invalid_rows.append(index)
                continue
            result_id = _as_int(raw.get('test_result_id'))
            if result_id is None:
                invalid_rows.append(index)
                continue
            raw_dim_id = _as_int(raw.get('dimension_id'))
            if raw_dim_id is None:
                invalid_rows.append(index)
                continue
            if dim_map:
                mapped_dim_id = dim_map.get(raw_dim_id)
                if mapped_dim_id is None:
                    # A2-4：匹配不到的维度行跳过并计入回执，不直写 B 的 dimension_id
                    skipped_dims.append(raw_dim_id)
                    continue
            else:
                mapped_dim_id = raw_dim_id

            row = dict(raw)
            row['test_result_id'] = result_map.get(result_id, result_id)
            row['dimension_id'] = mapped_dim_id
            prepared.append(row)

        if invalid_rows:
            raise MergeValidationError(
                f'维度行缺少 test_result_id/dimension_id（包内行号 {invalid_rows[:20]}）',
                code=400, detail={'invalid_rows': invalid_rows})

        result_ids = sorted({row['test_result_id'] for row in prepared})
        if not result_ids:
            return {'imported': 0, 'deleted': 0, 'id_mapping': {},
                    'skipped_dimensions': sorted(set(skipped_dims)),
                    'batch_id': batch_id, 'rollback_available': True}

        # A2-3：包内 result id 必须在 A 库存在。判定的对象是 result 本身，不是它
        # 有没有维度行——A 侧执行了但未评估的结果（增量回导典型场景）没有维度行
        # 也要允许插入，此时 deleted=0。校验放在开事务前：跨服务 ACL 调用期间
        # 不占数据库连接。任何未命中（含 ACL 调用失败）一律整批拒绝，零写入。
        missing = [rid for rid in result_ids if not _result_exists(rid)]
        if missing:
            # A2-3：禁止把 B 的本地 id 当 A id 写入
            raise MergeValidationError(
                f'包内 {len(missing)} 个 test_result_id 在目标库不存在: {missing[:20]}',
                code=409, detail={'missing_result_ids': missing})

        session = get_db_session()
        try:
            existing_pos = (session.query(TestResultDimension)
                            .filter(TestResultDimension.test_result_id.in_(result_ids))
                            .all())
            pairs: Set[Tuple[int, int]] = {
                (row['test_result_id'], row['dimension_id']) for row in prepared}
            old_pos = [po for po in existing_pos
                       if (po.test_result_id, po.dimension_id) in pairs]

            # A8：旧值快照与删除/覆盖同事务写入
            snapshot_rows = []
            for po in old_pos:
                snapshot_rows.append(EvaluationMergeSnapshot(
                    batch_id=batch_id, entity_table=_TABLE, entity_pk=po.id,
                    old_row=_snapshot_payload(po)))
            old_pks = [po.id for po in old_pos]
            if old_pks:
                (session.query(TestResultDimension)
                 .filter(TestResultDimension.id.in_(old_pks))
                 .delete(synchronize_session=False))
                session.flush()

            new_pairs: List[Tuple[int, object]] = []
            for row in prepared:
                payload = _coerce_row({k: v for k, v in row.items() if k != 'id'})
                po = TestResultDimension(**payload)
                session.add(po)
                new_pairs.append((_as_int(row.get('id')), po))
            session.flush()

            for old_id, po in new_pairs:
                snapshot_rows.append(EvaluationMergeSnapshot(
                    batch_id=batch_id, entity_table=_TABLE, entity_pk=po.id,
                    old_row=None))
            session.add_all(snapshot_rows)
            self._purge_expired_snapshots(session)
            session.commit()

            id_mapping = {old_id: po.id for old_id, po in new_pairs
                          if old_id is not None}
            log_not_emit('INFO', _MODULE_NAME,
                         f'维度合并完成 batch={batch_id} imported={len(new_pairs)} '
                         f'deleted={len(old_pks)} skipped={len(skipped_dims)}',
                         category='system')
            return {
                'imported': len(new_pairs),
                'deleted': len(old_pks),
                'id_mapping': {str(k): v for k, v in id_mapping.items()},
                'skipped_dimensions': sorted(set(skipped_dims)),
                'affected_result_ids': result_ids,
                'batch_id': batch_id,
                'rollback_available': True,
            }
        except MergeValidationError:
            raise
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    # ---- 回滚 ----

    def rollback_by_batch(self, batch_id: str) -> dict:
        """按批次快照回滚：删除本批新插入行 + 原样插回被覆盖的旧行（单事务）。

        无快照（已回滚或超过 7 天 TTL）→ 视为无可回滚内容（与现有
        `RollbackDimensionImport` 语义一致），不报错。
        """
        session = get_db_session()
        try:
            snapshots = (session.query(EvaluationMergeSnapshot)
                         .filter(EvaluationMergeSnapshot.batch_id == batch_id)
                         .order_by(EvaluationMergeSnapshot.id.asc())
                         .all())
            if not snapshots:
                return {'batch_id': batch_id, 'deleted': 0, 'restored': 0,
                        'nothing_to_rollback': True}

            new_pks = [snap.entity_pk for snap in snapshots
                       if snap.old_row is None and snap.entity_pk is not None]
            old_rows = [snap.old_row for snap in snapshots if snap.old_row is not None]

            deleted = 0
            if new_pks:
                deleted = (session.query(TestResultDimension)
                           .filter(TestResultDimension.id.in_(new_pks))
                           .delete(synchronize_session=False))

            restored = 0
            for old_row in old_rows:
                payload = _coerce_row(dict(old_row))
                session.merge(TestResultDimension(**payload))
                restored += 1
            session.flush()

            (session.query(EvaluationMergeSnapshot)
             .filter(EvaluationMergeSnapshot.batch_id == batch_id)
             .delete(synchronize_session=False))
            self._sync_sequence(session)
            session.commit()
            log_not_emit('INFO', _MODULE_NAME,
                         f'维度合并回滚完成 batch={batch_id} deleted={deleted} '
                         f'restored={restored}', category='system')
            return {'batch_id': batch_id, 'deleted': deleted, 'restored': restored}
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    # ---- 内部 ----

    @staticmethod
    def _purge_expired_snapshots(session) -> None:
        """清掉超过 BATCH_TTL_SECONDS 的批次快照（A8-4：保留 7 天供人工回滚）。

        未独立建清理任务，随每次合并顺带清理；失败不影响本次合并。
        """
        try:
            deadline = utc8now() - timedelta(seconds=BATCH_TTL_SECONDS)
            (session.query(EvaluationMergeSnapshot)
             .filter(EvaluationMergeSnapshot.created_at < deadline)
             .delete(synchronize_session=False))
        except Exception as e:
            log_not_emit('WARNING', _MODULE_NAME,
                         f'清理过期合并快照失败: {e}', category='system')

    @staticmethod
    def _sync_sequence(session) -> None:
        """回滚插回旧主键后把自增序列上调到 GREATEST(last_value, MAX(id))。

        与导入路径同口径（只上调不下调），仅 Postgres 需要。
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


dimension_merge_repository = DimensionMergeRepository()
