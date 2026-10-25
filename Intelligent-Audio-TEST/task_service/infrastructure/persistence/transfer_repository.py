# -*- coding: utf-8 -*-
"""任务数据导入导出仓储（task_service 段 8 表批量读写 + 补偿删除 + 容器内联）

导出（读侧，无副作用）：批量读 8 表 + 测试用例引用信息 + cherry-pick 容器任务
内联所选结果（INT-656：容器自身无 test_results 行，按 task_id 直查为空壳，
导出需内联被引用源结果并携带专有关系表，导入侧可重建容器及其所选结果）。
导入（写侧）：单事务写入 task_service 段 8 表，flush 捕获冲突行新 ID 构建映射；
补偿回滚按批次主键逆依赖删除。显式 ID 插入后同步 Postgres 序列。
source_map（INT-1760）：整包导入发生重映射时登记 A 原始 id → 本地 id，
唯一键 (source_server, entity_type, local_id)，upsert 幂等，供增量回导翻译。
"""
import logging
from datetime import datetime
from typing import Callable, Dict, Iterable, List, Optional, Set, Tuple

from shared.constants.data_transfer import SourceMapEntity
from shared.models.database import get_db_session
from shared.utils.log_handler import log_not_emit
from task_service.infrastructure.persistence.models import (
    DataTransferSourceMap,
    Task,
    TaskAPI,
    TaskCase,
    TaskCherryPickRelation,
    TaskDevice,
    TaskMergeRelation,
    TaskTag,
    TestCase,
    TestResult,
)

logger = logging.getLogger(__name__)

_MODULE_NAME = 'transfer_repository'

# source_map 批量读写分块（避免超长 IN 列表撑爆 SQL）
_SOURCE_MAP_CHUNK = 500

# 子表写入顺序（依赖序）：关联表 → 结果表 → cherry-pick 关系表（引用结果，
# 须在结果表 flush 拿到 test_results 映射后重写外键；主表由 import_task_segment 先写）
_CHILD_TABLES = ('task_case_relations', 'task_device_relations', 'task_api_relations',
                 'task_tags', 'task_merge_relations', 'test_results',
                 'task_cherry_pick_relations')
# 补偿删除顺序（逆依赖）
_ROLLBACK_ORDER = ('task_cherry_pick_relations', 'test_results', 'task_merge_relations',
                   'task_tags', 'task_api_relations', 'task_device_relations',
                   'task_case_relations', 'test_tasks')

_TABLE_PO = {
    'test_tasks': Task,
    'task_case_relations': TaskCase,
    'task_device_relations': TaskDevice,
    'task_api_relations': TaskAPI,
    'task_tags': TaskTag,
    'task_merge_relations': TaskMergeRelation,
    'task_cherry_pick_relations': TaskCherryPickRelation,
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


def _source_map_to_dict(po) -> dict:
    """source_map PO → dict（对外只暴露翻译所需的业务字段 + 时间戳）"""
    return {
        'source_server': po.source_server,
        'source_task_id': int(po.source_task_id),
        'entity_type': po.entity_type,
        'source_id': int(po.source_id),
        'local_id': int(po.local_id),
        'updated_at': po.updated_at.isoformat(timespec='seconds')
        if isinstance(po.updated_at, datetime) else po.updated_at,
    }


class TransferRepository:
    """task_service 段导入导出仓储"""

    # ---------- 导出（读侧，查询不产生副作用） ----------

    def fetch_export_rows(self, task_ids: List[int]) -> Dict[str, List[dict]]:
        """批量读取 task_service 段 8 表（Task 仅取未删除）。

        task_merge_relations 仅取 merged_task_id 与 source_task_id 都在导出集内的
        记录（防悬空外键，见 INT-25 规格第 6 条）；task_cherry_pick_relations 与
        内联结果由 _inline_cherry_pick_results 追加（INT-656）。
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
                if table in ('test_tasks', 'task_cherry_pick_relations'):
                    continue  # 容器关系表按 cherry_pick_task_id 由内联分支处理
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
            self._inline_cherry_pick_results(session, rows, found_ids)
            return rows
        finally:
            session.close()

    def _inline_cherry_pick_results(self, session, rows: Dict[str, List[dict]],
                                    found_ids: List[int]) -> None:
        """cherry-pick 容器任务导出内联（INT-656，引用方案 A）。

        容器任务（task_cherry_pick_relations.cherry_pick_task_id 存在性判定）自身无
        test_results 行，7 表按 task_id 直查导出为空壳。此处：
        - 携带容器任务的专有关系表行（导入侧重建引用关系，维持引用方案 A）
        - 内联被引用源结果：源任务同批导出时结果已随源任务在包内（按 result_id
          去重不重复内联）；源任务未导出时把结果行 task_id 重写为引用它的容器任务
          （导入可重建且不产生悬空/串挂任务外键）。存储 key 首段保持源任务 id，
          文件条目按容器 id 归档——见 file_transfer.iter_result_file_entries 与
          导入侧 _update_result_paths 的对应处理。
        """
        rows.setdefault('task_cherry_pick_relations', [])
        if not found_ids:
            return
        relations = (session.query(TaskCherryPickRelation)
                     .filter(TaskCherryPickRelation.cherry_pick_task_id.in_(found_ids))
                     .order_by(TaskCherryPickRelation.id).all())
        rows['task_cherry_pick_relations'] = [_po_to_row(r) for r in relations]
        if not relations:
            return
        existing_result_ids = {
            row['id'] for row in rows.get('test_results', []) if row.get('id') is not None
        }
        inlined: List[dict] = []
        for relation in relations:
            rid = relation.result_id
            if rid is None or rid in existing_result_ids:
                continue
            po = session.get(TestResult, rid)
            if po is None:
                continue
            row = _po_to_row(po)
            row['task_id'] = relation.cherry_pick_task_id  # 归入引用它的容器任务
            existing_result_ids.add(rid)
            inlined.append(row)
        if inlined:
            rows.setdefault('test_results', []).extend(inlined)

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

    def fetch_case_availability(self, case_ids: List[str],
                                user_id: Optional[int] = None,
                                is_admin: Optional[bool] = None) -> Dict[str, Set[str]]:
        """目标库中用例的可用性三分（INT-1759 用例一致性硬校验，D0 裁定 A10-4）

        - missing：目标库不存在，或已软删（`test_cases.deleted`）
        - invisible：存在且未软删，但私有用例且操作人非 owner / 非 admin
          （可见性口径同 `visible_condition`，厂商私有数据不可当作"已存在"）
        - available：其余（导入后可重新执行的用例）

        身份缺省取 gRPC metadata 透传的当前操作人（x-user-id / x-user-is-admin）。

        Args:
            case_ids: 导出包内 task_case_relations 引用的用例 ID（str）
            user_id: 显式操作人（None 时取上下文）
            is_admin: 显式管理员标志（None 时取上下文）
        """
        ids = {str(cid) for cid in case_ids or [] if cid is not None}
        if not ids:
            return {'available': set(), 'missing': set(), 'invisible': set()}
        from task_service.infrastructure.visibility_context import visibility_identity
        from shared.infrastructure.visibility_filter import check_visible, VisibilityDenied
        uid, admin = visibility_identity(user_id)
        if is_admin is not None:
            admin = bool(is_admin)
        session = get_db_session()
        try:
            rows = (session.query(TestCase.id, TestCase.created_by_user_id,
                                  TestCase.visibility, TestCase.deleted)
                    .filter(TestCase.id.in_(ids)).all())
        finally:
            session.close()
        existing = {str(row[0]) for row in rows if not row[3]}
        invisible: Set[str] = set()
        for case_id, owner, visibility, deleted in rows:
            if deleted:
                continue
            try:
                check_visible(owner, visibility or 'shared', uid, admin)
            except VisibilityDenied:
                invisible.add(str(case_id))
        return {
            'available': existing - invisible,
            'missing': ids - existing,
            'invisible': invisible,
        }

    def fetch_existing_case_ids(self, case_ids: List[str],
                                user_id: Optional[int] = None,
                                is_admin: Optional[bool] = None) -> Set[str]:
        """目标库中**可用**用例 ID 集合（预检 warning / 一致性校验共用）

        可用 = 未软删 且 当前操作人可见（INT-1759：软删用例、私有非 owner 用例
        都不算"已存在"，否则导入后无法重新执行却通过校验）。
        """
        return self.fetch_case_availability(case_ids, user_id, is_admin)['available']

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

    # ---------- 增量回导（INT-1761：定位原任务 / 指纹 / 反向 id 校验） ----------

    def fetch_task_identity(self, task_id: int) -> Optional[dict]:
        """任务基础身份（增量导入按 manifest.sourceTask.id 定位 A 原任务用）。

        Returns: {'id', 'name', 'status', 'deleted'}；任务不存在返回 None。
        软删任务也返回（deleted=True），由调用方按 404 语义拒绝（A7）。
        """
        if task_id is None:
            return None
        session = get_db_session()
        try:
            row = (session.query(Task.id, Task.name, Task.status, Task.deleted)
                   .filter(Task.id == int(task_id)).first())
            if row is None:
                return None
            return {'id': int(row[0]), 'name': row[1], 'status': row[2],
                    'deleted': bool(row[3])}
        finally:
            session.close()

    def fetch_task_case_ids(self, task_id: int) -> List[str]:
        """任务当前用例 id 列表（caseSetHash 指纹计算口径，A7）。"""
        if task_id is None:
            return []
        session = get_db_session()
        try:
            rows = (session.query(TaskCase.test_case_id)
                    .filter(TaskCase.task_id == int(task_id)).all())
            return [str(row[0]) for row in rows if row[0] is not None]
        finally:
            session.close()

    def fetch_existing_result_ids(self, result_ids: Iterable[int]) -> Set[int]:
        """给定结果 id 中在目标库**存在**的集合（A2-3 反向 id 校验用）。

        判定口径是「结果行存在」而不是「已评估」：A 侧执行了但未评估的结果
        在增量回导时本就没有维度行，B 侧重评出的分数要能插进来（与 D4 合并
        仓储同口径）。
        """
        ids = sorted({int(rid) for rid in (result_ids or []) if rid is not None})
        if not ids:
            return set()
        session = get_db_session()
        try:
            found: Set[int] = set()
            for start in range(0, len(ids), _SOURCE_MAP_CHUNK):
                chunk = ids[start:start + _SOURCE_MAP_CHUNK]
                found.update(int(row[0]) for row in
                             session.query(TestResult.id).filter(TestResult.id.in_(chunk)).all())
            return found
        finally:
            session.close()

    def fetch_task_existence(self, task_ids: List[int]) -> Dict[int, bool]:
        """task id → 是否已软删（INT-1764 报告包导入定位原任务用）。

        不存在于结果里的 id 表示任务行不存在；`True` 表示已软删。
        """
        ids = sorted({int(i) for i in (task_ids or [])})
        if not ids:
            return {}
        session = get_db_session()
        try:
            rows = session.query(Task.id, Task.deleted).filter(Task.id.in_(ids)).all()
            return {int(row[0]): bool(row[1]) for row in rows}
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
                            rewrite_fk_fn: Callable[[str, List[dict], Dict[str, Dict[int, int]]], List[dict]],
                            progress_fn: Callable[[str, int], None] = None,
                            ) -> Tuple[Dict[str, Dict[int, int]], Dict[str, List[int]]]:
        """单事务写入 task_service 段 8 表。

        Args:
            rows_by_table: 表名 → 已剥离冲突 id 的待插入行（行序与导出包一致；
                冲突行无 'id' 键，与 conflicts_by_table 按序一一对应）
            conflicts_by_table: 表名 → 被剥离的原主键列表（行序）
            rewrite_fk_fn: (table, rows, mappings) → 按 FK 规则重写后的行
                （mappings 为演进中的 old→new 主键映射：'tasks' 在 flush 后可用，
                子表外键须在插入前于同一事务内重写；'test_results' 在结果表 flush
                后可用——task_cherry_pick_relations 在 _CHILD_TABLES 中位于结果表
                之后，其 result_id 重写依赖该映射；实现为 domain 层 rewrite_fk_rows
                的包装）
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
            task_pairs = self._insert_two_pass(
                session, Task, 'test_tasks',
                rows_by_table.get('test_tasks') or [],
                conflicts_by_table.get('test_tasks') or [])
            mappings['tasks'] = {old_id: po.id for old_id, po in task_pairs}
            inserted_pks['test_tasks'] = [po.id for _, po in task_pairs]
            if progress_fn:
                progress_fn('test_tasks', len(task_pairs))

            # 2) 关联表 + test_results + cherry-pick 关系表：先按规则重写外键再插入
            for table in _CHILD_TABLES:
                rows = rows_by_table.get(table) or []
                rewritten = rewrite_fk_fn(table, rows, mappings)
                po_cls = _TABLE_PO[table]
                pairs = self._insert_two_pass(
                    session, po_cls, table, rewritten,
                    conflicts_by_table.get(table) or [])
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

    def _insert_two_pass(self, session, po_cls, table: str,
                         rows: List[dict],
                         conflict_old_ids: List[int]) -> List[Tuple[int, object]]:
        """同一表内「显式 ID 行 + 去 ID 冲突行」混插的两遍插入（缺陷 1 修复）。

        自增序列不感知同批次后续显式 ID：包内保留行 id=2 与冲突行自增分配的
        id=2 相互撞 UNIQUE（SQLite rowid 与 Postgres nextval 同样命中）。
        顺序：先插全部保留行 → flush → 把该表自增序列推到 max(id) → 再插全部
        冲突行 → flush，保证自增分配避开本批次显式 ID 集合。

        冲突行判定兼容两种约定：行已剥 id（task 段计划层剥离，old_id 从
        conflict_old_ids 按序配对）或行仍带 id 但命中 conflict_old_ids
        （评测/报告段本地判活场景，直接去 id）。

        Returns:
            [(old_id, po)]：保留行在前，冲突行按包内相对顺序在后。
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
            self._sync_sequences(session, [table])
            for old_id, row in conflicted:
                po = po_cls(**_coerce_row(po_cls, row))
                session.add(po)
                pairs.append((old_id, po))
            session.flush()
        return pairs

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
            session.commit()
            return deleted
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    # ---------- 离线搬运 source_map（INT-1760：A 原始 id → 本地 id） ----------

    def upsert_source_maps(self, entries: List[dict]) -> Dict[str, object]:
        """单事务 upsert 映射登记（D0 A3：编排层唯一写入方，一次事务）。

        唯一键 (source_server, entity_type, local_id)；冲突即覆盖 source_id /
        source_task_id —— 重复导入 / 失败重放幂等（D0 A4 第 3、4 条）。

        Returns:
            {'inserted': [本批次新增的条目], 'insertedCount', 'updatedCount',
             'total'}。inserted 供补偿精确回删：只删本批次新建的行，已存在被
            覆盖的行不做处理（旧值无快照，删掉等于丢历史映射）。
        Raises: 写失败回滚并抛出（编排层按「远端已提交、本地登记失败」处理）。
        """
        clean = self._clean_source_map_entries(entries)
        if not clean:
            return {'inserted': [], 'insertedCount': 0, 'updatedCount': 0, 'total': 0}
        session = get_db_session()
        try:
            existing = self._existing_source_map_keys(session, clean)
            self._apply_source_map_upsert(session, clean)
            session.commit()
            inserted = [e for e in clean
                        if (e['source_server'], e['entity_type'], e['local_id'])
                        not in existing]
            return {'inserted': inserted,
                    'insertedCount': len(inserted),
                    'updatedCount': len(clean) - len(inserted),
                    'total': len(clean)}
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def delete_source_maps(self, entries: List[dict]) -> int:
        """按唯一键删除映射（本批次补偿 / 批次回滚）。返回删除行数。"""
        clean = self._clean_source_map_entries(entries)
        if not clean:
            return 0
        session = get_db_session()
        try:
            deleted = self._delete_source_map_rows(session, clean)
            session.commit()
            return deleted
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def fetch_source_maps(self, source_server: str,
                          source_task_id: int) -> List[dict]:
        """按「源服务 + 源任务」取该任务的全部映射行（增量导出翻译用）。

        返回行按 entity_type / source_id 排序；一条查询覆盖四类实体（D0 A4 的
        索引 idx_transfer_source_map_task 即为此路径建）。
        """
        session = get_db_session()
        try:
            rows = (session.query(DataTransferSourceMap)
                    .filter(DataTransferSourceMap.source_server == source_server,
                            DataTransferSourceMap.source_task_id == source_task_id)
                    .order_by(DataTransferSourceMap.entity_type,
                              DataTransferSourceMap.source_id)
                    .all())
            return [_source_map_to_dict(row) for row in rows]
        finally:
            session.close()

    def fetch_source_maps_grouped(self, source_server: str,
                                  source_task_id: int) -> Dict[str, List[dict]]:
        """同 fetch_source_maps，按 entity_type 分组（导出侧按实体取用）。"""
        grouped: Dict[str, List[dict]] = {}
        for row in self.fetch_source_maps(source_server, source_task_id):
            grouped.setdefault(row['entity_type'], []).append(row)
        return grouped

    def fetch_source_task_refs(self, local_task_ids: Iterable[int]) -> List[dict]:
        """B 本地任务 → 源任务引用（增量导出反查用，INT-1761）。

        导出侧只拿得到 B 的本地 task_id，需先反查它当初整包导入时的
        `(source_server, source_id)`，再按「源服务 + 源任务」取四类实体的映射。
        同一本地任务若被不同源服务导入过，会返回多行——调用方按 source_server
        去重，多源时拒绝导出（映射不唯一无法确定翻译基准）。
        """
        ids = sorted({int(tid) for tid in (local_task_ids or [])})
        if not ids:
            return []
        session = get_db_session()
        try:
            rows = (session.query(DataTransferSourceMap)
                    .filter(DataTransferSourceMap.entity_type == SourceMapEntity.TASKS.value,
                            DataTransferSourceMap.local_id.in_(ids))
                    .order_by(DataTransferSourceMap.source_server,
                              DataTransferSourceMap.local_id)
                    .all())
            return [_source_map_to_dict(row) for row in rows]
        finally:
            session.close()

    def fetch_source_ids_by_local_ids(self, source_server: str, entity_type: str,
                                      local_ids: Iterable[int]) -> Dict[int, int]:
        """local id → 源 id 反查（导出侧把 B 库 id 翻译回 A 原始 id）。

        缺失的 local id 不出现在结果里（调用方自行判定「无映射即无法离线搬运」）。
        """
        ids = sorted({int(i) for i in (local_ids or [])})
        if not ids:
            return {}
        mapping: Dict[int, int] = {}
        session = get_db_session()
        try:
            for start in range(0, len(ids), _SOURCE_MAP_CHUNK):
                chunk = ids[start:start + _SOURCE_MAP_CHUNK]
                rows = (session.query(DataTransferSourceMap.local_id,
                                      DataTransferSourceMap.source_id)
                        .filter(DataTransferSourceMap.source_server == source_server,
                                DataTransferSourceMap.entity_type == entity_type,
                                DataTransferSourceMap.local_id.in_(chunk))
                        .all())
                for local_id, source_id in rows:
                    mapping[int(local_id)] = int(source_id)
            return mapping
        finally:
            session.close()

    @staticmethod
    def _clean_source_map_entries(entries: Iterable[dict]) -> List[dict]:
        """过滤空条目 + 统一 int 类型（gRPC/JSON 来的 id 可能是字符串）"""
        clean: List[dict] = []
        for entry in entries or []:
            if not isinstance(entry, dict):
                continue
            server = entry.get('source_server')
            entity_type = entry.get('entity_type')
            if not server or not entity_type:
                continue
            try:
                clean.append({
                    'source_server': str(server),
                    'source_task_id': int(entry['source_task_id']),
                    'entity_type': str(entity_type),
                    'source_id': int(entry['source_id']),
                    'local_id': int(entry['local_id']),
                })
            except (KeyError, TypeError, ValueError):
                log_not_emit('WARNING', _MODULE_NAME,
                             f'source_map 条目字段非法，已跳过: {entry!r}',
                             category='system')
        return clean

    @staticmethod
    def _existing_source_map_keys(session, entries: List[dict]) -> Set[Tuple[str, str, int]]:
        """本批次涉及的已存在唯一键集合（判定 inserted / updated）"""
        existing: Set[Tuple[str, str, int]] = set()
        by_scope: Dict[Tuple[str, str], List[int]] = {}
        for entry in entries:
            by_scope.setdefault(
                (entry['source_server'], entry['entity_type']), []).append(entry['local_id'])
        for (server, entity_type), local_ids in by_scope.items():
            for start in range(0, len(local_ids), _SOURCE_MAP_CHUNK):
                chunk = local_ids[start:start + _SOURCE_MAP_CHUNK]
                rows = (session.query(DataTransferSourceMap.local_id)
                        .filter(DataTransferSourceMap.source_server == server,
                                DataTransferSourceMap.entity_type == entity_type,
                                DataTransferSourceMap.local_id.in_(chunk))
                        .all())
                existing.update((server, entity_type, int(row[0])) for row in rows)
        return existing

    @staticmethod
    def _apply_source_map_upsert(session, entries: List[dict]) -> None:
        """按方言生成 upsert（Postgres / SQLite 均用 ON CONFLICT）"""
        dialect = session.bind.dialect.name if session.bind is not None else ''
        if dialect == 'postgresql':
            from sqlalchemy.dialects.postgresql import insert as _insert
        elif dialect == 'sqlite':
            from sqlalchemy.dialects.sqlite import insert as _insert
        else:  # 兜底：逐条 select-update / insert（无 ON CONFLICT 的方言）
            TransferRepository._apply_source_map_upsert_fallback(session, entries)
            return
        stmt = _insert(DataTransferSourceMap).values(entries)
        stmt = stmt.on_conflict_do_update(
            index_elements=['source_server', 'entity_type', 'local_id'],
            set_={
                'source_task_id': stmt.excluded.source_task_id,
                'source_id': stmt.excluded.source_id,
                'updated_at': datetime.now(),
            })
        session.execute(stmt)

    @staticmethod
    def _apply_source_map_upsert_fallback(session, entries: List[dict]) -> None:
        now = datetime.now()
        for entry in entries:
            row = (session.query(DataTransferSourceMap)
                   .filter(DataTransferSourceMap.source_server == entry['source_server'],
                           DataTransferSourceMap.entity_type == entry['entity_type'],
                           DataTransferSourceMap.local_id == entry['local_id'])
                   .one_or_none())
            if row is None:
                session.add(DataTransferSourceMap(**entry))
            else:
                row.source_task_id = entry['source_task_id']
                row.source_id = entry['source_id']
                row.updated_at = now
        session.flush()

    @staticmethod
    def _delete_source_map_rows(session, entries: List[dict]) -> int:
        """按 (source_server, entity_type, local_id) 分块删除，返回删除行数。"""
        deleted = 0
        by_scope: Dict[Tuple[str, str], List[int]] = {}
        for entry in entries:
            by_scope.setdefault(
                (entry['source_server'], entry['entity_type']), []).append(entry['local_id'])
        for (server, entity_type), local_ids in by_scope.items():
            for start in range(0, len(local_ids), _SOURCE_MAP_CHUNK):
                chunk = local_ids[start:start + _SOURCE_MAP_CHUNK]
                deleted += (session.query(DataTransferSourceMap)
                            .filter(DataTransferSourceMap.source_server == server,
                                    DataTransferSourceMap.entity_type == entity_type,
                                    DataTransferSourceMap.local_id.in_(chunk))
                            .delete(synchronize_session=False))
        return deleted

    @staticmethod
    def _sync_sequences(session, tables=None) -> None:
        """显式 ID 插入后把自增序列上调到 GREATEST(当前 last_value, MAX(id))。

        审计问题 3：只上调不下调——向下回拨会与并发事务已消费但未提交的更大
        id 撞 UNIQUE。两遍插入的正确性只依赖 nextval > 本批次显式 max，上调即满足。
        仅 Postgres 需要；SQLite（开发库）自增取 max(rowid)+1 无需处理。
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
                             f'同步 {table} 序列失败（不影响导入提交）: {e}', category='system')


transfer_repository = TransferRepository()
