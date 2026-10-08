# -*- coding: utf-8 -*-
"""任务数据导入导出仓储（task_service 段 7 表批量读写 + 补偿删除）

导出（读侧，无副作用）：批量读 7 表 + 测试用例引用信息。
导入（写侧）：单事务写入 task_service 段 7 表，flush 捕获冲突行新 ID 构建映射；
补偿回滚按批次主键逆依赖删除。显式 ID 插入后同步 Postgres 序列。
"""
import logging
from datetime import datetime
from typing import Callable, Dict, List, Set, Tuple

from shared.models.database import get_db_session
from shared.utils.log_handler import log_not_emit
from task_service.infrastructure.persistence.models import (
    Task,
    TaskAPI,
    TaskCase,
    TaskDevice,
    TaskMergeRelation,
    TaskTag,
    TestCase,
    TestResult,
)

logger = logging.getLogger(__name__)

_MODULE_NAME = 'transfer_repository'

# 子表写入顺序（依赖序）：关联表 → 结果表（主表由 import_task_segment 先写）
_CHILD_TABLES = ('task_case_relations', 'task_device_relations', 'task_api_relations',
                 'task_tags', 'task_merge_relations', 'test_results')
# 补偿删除顺序（逆依赖）
_ROLLBACK_ORDER = ('test_results', 'task_merge_relations', 'task_tags',
                   'task_api_relations', 'task_device_relations',
                   'task_case_relations', 'test_tasks')

_TABLE_PO = {
    'test_tasks': Task,
    'task_case_relations': TaskCase,
    'task_device_relations': TaskDevice,
    'task_api_relations': TaskAPI,
    'task_tags': TaskTag,
    'task_merge_relations': TaskMergeRelation,
    'test_results': TestResult,
}

_DATETIME_FIELDS_CACHE: Dict[str, Set[str]] = {}


def _datetime_fields(po_cls) -> Set[str]:
    """从 ORM 元数据取 DateTime 列名（缓存）——ISO 字符串反序列化用"""
    name = po_cls.__tablename__
    if name not in _DATETIME_FIELDS_CACHE:
        fields = set()
        for column in po_cls.__table__.columns:
            py_type = getattr(column.type, 'python_type', None)
            if py_type is datetime:
                fields.add(column.name)
        _DATETIME_FIELDS_CACHE[name] = fields
    return _DATETIME_FIELDS_CACHE[name]


def _coerce_row(po_cls, row: dict) -> dict:
    """JSON 行 → ORM 可接受 kwargs：丢弃未知列，ISO 字符串转 datetime"""
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
                log_not_emit('WARNING', _MODULE_NAME,
                             f'{po_cls.__tablename__}.{key} 时间格式非法: {value!r}',
                             category='system')
                value = None
        coerced[key] = value
    return coerced


def _po_to_row(po) -> dict:
    """PO → 行 dict（datetime 转 ISO，JSON 列原样）"""
    row = {}
    for column in po.__table__.columns:
        value = getattr(po, column.name)
        if isinstance(value, datetime):
            value = value.isoformat(timespec='seconds')
        row[column.name] = value
    return row


class TransferRepository:
    """task_service 段导入导出仓储"""

    # ---------- 导出（读侧，查询不产生副作用） ----------

    def fetch_export_rows(self, task_ids: List[int]) -> Dict[str, List[dict]]:
        """批量读取 task_service 段 7 表（Task 仅取未删除）。

        task_merge_relations 仅取 merged_task_id 与 source_task_id 都在导出集内的
        记录（防悬空外键，见 INT-25 规格第 6 条）。
        返回 {表名: 行列表}
        """
        session = get_db_session()
        try:
            rows: Dict[str, List[dict]] = {}
            tasks = (session.query(Task)
                     .filter(Task.id.in_(task_ids), Task.deleted == False)  # noqa: E712
                     .all())
            rows['test_tasks'] = [_po_to_row(po) for po in tasks]
            found_ids = [po.id for po in tasks]
            for table, po_cls in _TABLE_PO.items():
                if table == 'test_tasks':
                    continue
                if not found_ids:
                    rows[table] = []
                    continue
                if table == 'task_merge_relations':
                    pos = (session.query(po_cls)
                           .filter(po_cls.merged_task_id.in_(found_ids),
                                   po_cls.source_task_id.in_(found_ids))
                           .all())
                else:
                    pos = session.query(po_cls).filter(po_cls.task_id.in_(found_ids)).all()
                rows[table] = [_po_to_row(po) for po in pos]
            return rows
        finally:
            session.close()

    def fetch_case_configs(self, case_ids: List[str]) -> Dict[str, dict]:
        """按用例 ID 批量读取引用信息（参考参数路径 + 配置，导出收集文件用）"""
        if not case_ids:
            return {}
        session = get_db_session()
        try:
            cases = session.query(TestCase).filter(TestCase.id.in_(case_ids)).all()
            return {
                case.id: {'reference_params': case.reference_params, 'config': case.config}
                for case in cases
            }
        finally:
            session.close()

    def fetch_existing_case_ids(self, case_ids: List[str]) -> Set[str]:
        """目标库中实际存在的用例 ID 集合（预检 warning 用）"""
        if not case_ids:
            return set()
        session = get_db_session()
        try:
            found = session.query(TestCase.id).filter(TestCase.id.in_(case_ids)).all()
            return {row[0] for row in found}
        finally:
            session.close()

    def fetch_task_names(self, task_ids: List[int]) -> Dict[int, str]:
        """按 ID 列表取任务名（预检冲突展示用）"""
        if not task_ids:
            return {}
        session = get_db_session()
        try:
            found = session.query(Task.id, Task.name).filter(Task.id.in_(task_ids)).all()
            return {row[0]: row[1] for row in found}
        finally:
            session.close()

    def fetch_existing_ids(self) -> Dict[str, Set[int]]:
        """7 表当前全部主键集合（导入冲突判定 + 预检）"""
        session = get_db_session()
        try:
            return {
                table: {row[0] for row in session.query(po_cls.id).all()}
                for table, po_cls in _TABLE_PO.items()
            }
        finally:
            session.close()

    # ---------- 导入（写侧） ----------

    def import_task_segment(self,
                            rows_by_table: Dict[str, List[dict]],
                            conflicts_by_table: Dict[str, List[int]],
                            rewrite_fk_fn: Callable[[str, List[dict], Dict[int, int]], List[dict]],
                            progress_fn: Callable[[str, int], None] = None,
                            ) -> Tuple[Dict[str, Dict[int, int]], Dict[str, List[int]]]:
        """单事务写入 task_service 段 7 表。

        Args:
            rows_by_table: 表名 → 已剥离冲突 id 的待插入行（行序与导出包一致；
                冲突行无 'id' 键，与 conflicts_by_table 按序一一对应）
            conflicts_by_table: 表名 → 被剥离的原主键列表（行序）
            rewrite_fk_fn: (table, rows, tasks_mapping) → 按 FK 规则重写后的行
                （tasks 映射 flush 后才可知，子表外键必须在插入前于同一事务内重写；
                实现为 domain 层 rewrite_fk_rows 的包装）
            progress_fn: (table, processed_rows) 每表 flush 后回调（进度推送用）

        Returns:
            (mappings, inserted_pks)
            mappings: {'tasks': {...}, 'test_results': {...}} 完整 old→new 映射（含映射到自身）
            inserted_pks: {表名: [本批次插入主键]}（批次登记 + 补偿回滚用）

        Raises: 任一写失败即整体回滚并抛出。
        """
        session = get_db_session()
        try:
            mappings: Dict[str, Dict[int, int]] = {}
            inserted_pks: Dict[str, List[int]] = {}

            # 1) 主表 test_tasks：flush 捕获冲突行自增新 id → tasks 映射
            task_rows = rows_by_table.get('test_tasks') or []
            conflict_iter = iter(conflicts_by_table.get('test_tasks') or [])
            task_pairs: List[Tuple[int, Task]] = []
            for row in task_rows:
                old_id = row.get('id')
                if old_id is None:
                    old_id = next(conflict_iter)
                po = Task(**_coerce_row(Task, row))
                session.add(po)
                task_pairs.append((old_id, po))
            session.flush()
            mappings['tasks'] = {old_id: po.id for old_id, po in task_pairs}
            inserted_pks['test_tasks'] = [po.id for _, po in task_pairs]
            task_map = mappings['tasks']
            if progress_fn:
                progress_fn('test_tasks', len(task_pairs))

            # 2) 关联表 + test_results：先按规则重写外键再插入
            for table in _CHILD_TABLES:
                rows = rows_by_table.get(table) or []
                rewritten = rewrite_fk_fn(table, rows, task_map)
                po_cls = _TABLE_PO[table]
                conflict_iter = iter(conflicts_by_table.get(table) or [])
                pairs: List[Tuple[int, object]] = []
                for row in rewritten:
                    old_id = row.get('id')
                    if old_id is None:
                        old_id = next(conflict_iter)
                    po = po_cls(**_coerce_row(po_cls, row))
                    session.add(po)
                    pairs.append((old_id, po))
                session.flush()
                inserted_pks[table] = [po.id for _, po in pairs]
                if progress_fn:
                    progress_fn(table, len(pairs))
                if table == 'test_results':
                    mappings['test_results'] = {old_id: po.id for old_id, po in pairs}

            self._sync_sequences(session)
            session.commit()
            return mappings, inserted_pks
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def update_result_data_paths(self, changes: List[Tuple[int, str]]) -> int:
        """导入文件段完成后更新 result_data_path（task_id 重映射的行）。

        独立小事务（updating_paths 步骤）；失败抛出由编排层走全量补偿。
        """
        if not changes:
            return 0
        session = get_db_session()
        try:
            for result_id, new_path in changes:
                session.query(TestResult).filter(TestResult.id == result_id).update(
                    {TestResult.result_data_path: new_path}, synchronize_session=False)
            session.commit()
            return len(changes)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def rollback_task_segment(self, tables_pks: Dict[str, List[int]]) -> Dict[str, int]:
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
            self._sync_sequences(session)
            session.commit()
            return deleted
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    @staticmethod
    def _sync_sequences(session) -> None:
        """显式 ID 插入后把自增序列推到 max(id)，防止后续自增主键冲突。

        仅 Postgres 需要；SQLite（开发库）自增取 max(rowid)+1 无需处理。
        """
        if session.bind is None or session.bind.dialect.name != 'postgresql':
            return
        from sqlalchemy import text
        for table in _TABLE_PO:
            try:
                session.execute(text(
                    "SELECT setval(pg_get_serial_sequence(:tbl, 'id'), "
                    "GREATEST((SELECT COALESCE(MAX(id), 0) FROM " + table + "), 1))"
                ), {'tbl': table})
            except Exception as e:
                log_not_emit('WARNING', _MODULE_NAME,
                             f'同步 {table} 序列失败（不影响导入提交）: {e}', category='system')


transfer_repository = TransferRepository()
