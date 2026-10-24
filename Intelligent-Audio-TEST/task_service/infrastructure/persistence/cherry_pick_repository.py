# -*- coding: utf-8 -*-
"""挑选合并仓储（INT-339）：购物车 / 容器关系 / 挑选集 读写。

per-user 语义对齐 favorite_repository（user_id 来自 JWT x-user-id metadata，
未认证 NULL 禁止写入）；容器关系引用方案 A（result 引用不复制，
test_results.task_id 禁止改挂——红线）。
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import case, func as sa_func
from sqlalchemy.exc import IntegrityError

from shared.infrastructure.visibility_filter import visible_condition
from shared.models.common_enums import PickableTaskStatus
from shared.models.database import get_db_session
from shared.utils.db_session import with_session
from shared.utils.status_constants import RESULT_TYPE_PENDING
from task_service.infrastructure.persistence.models import (
    Task, TestResult,
    CherryPickCartItem, TaskCherryPickRelation, CherryPickSet, CherryPickSetItem,
)

logger = logging.getLogger(__name__)


def _result_trace_snapshot(result: TestResult, source_task: Optional[Task]) -> Dict[str, Any]:
    """从 TestResult + 源 Task 提取溯源快照字段（加购/下单/另存共用）。"""
    return {
        'result_id': result.id,
        'source_task_id': result.task_id,
        'source_task_name': source_task.name if source_task else None,
        'source_case_id': result.test_case_id,
        'source_device_id': result.device_id,
        'source_api_id': result.api_id,
        # INT-577 §11-5：来源结果类型快照（取落库列，缺值 default）
        'source_result_type': _extract_result_type(result),
        'execution_status': result.execution_status,
    }


def _extract_result_type(result: TestResult) -> str:
    """结果行 result_type 快照（INT-1669 返工：与候选行同一落库列口径）。

    读 `test_results.result_type`，缺值（NULL / 空串）输出缺值哨兵
    `RESULT_TYPE_PENDING`（UX「结果类型待补充」桶）。**不解析**
    `result_data` / `result_data_path`，加购与另存路径零对象存储往返，
    与候选行不再构成双口径。
    """
    value = getattr(result, 'result_type', None)
    if value is None:
        return RESULT_TYPE_PENDING
    text = str(value).strip()
    return text or RESULT_TYPE_PENDING


class CherryPickRepository:
    """挑选合并仓储：购物车 / 容器关系 / 挑选集。"""

    # ==================== 购物车（per-user） ====================

    @staticmethod
    def _load_result(session, result_id: int):
        """读取源结果 + 源任务（校验存在且未删除）。"""
        result = session.get(TestResult, int(result_id))
        if result is None:
            return None, None
        source_task = session.get(Task, result.task_id) if result.task_id else None
        if source_task is not None and source_task.deleted:
            return result, None
        return result, source_task

    @with_session(auto_commit=True)
    def cart_add(self, user_id, items: List[Dict[str, Any]]) -> dict:
        """批量加入购物车（幂等：同一用户同一结果只加购一次）。

        items: [{result_id: int}, ...]——溯源快照由仓储从源行提取（客户端
        不传溯源字段，杜绝伪造来源）。
        """
        if not user_id:
            raise ValueError("未认证用户禁止使用购物车（user_id 缺失）")
        result_ids = sorted({int(it.get('result_id')) for it in (items or [])
                             if it.get('result_id') is not None})
        if not result_ids:
            return {'added': [], 'missing': [], 'duplicated': []}

        session = get_db_session()
        existing_ids = {int(r[0]) for r in session.query(CherryPickCartItem.result_id)
                        .filter(CherryPickCartItem.user_id == user_id,
                                CherryPickCartItem.result_id.in_(result_ids)).all()}

        added: List[int] = []
        missing: List[int] = []
        duplicated: List[int] = []
        for rid in result_ids:
            if rid in existing_ids:
                duplicated.append(rid)
                continue
            result, source_task = self._load_result(session, rid)
            if result is None or source_task is None:
                missing.append(rid)
                continue
            snapshot = _result_trace_snapshot(result, source_task)
            session.add(CherryPickCartItem(
                user_id=user_id,
                result_id=snapshot['result_id'],
                source_task_id=snapshot['source_task_id'],
                source_task_name=snapshot['source_task_name'],
                source_case_id=snapshot['source_case_id'],
                source_device_id=snapshot['source_device_id'],
                source_api_id=snapshot['source_api_id'],
                # INT-577 §11-5：购物车条目快照补 source_result_type
                source_result_type=snapshot['source_result_type'],
                execution_status=snapshot['execution_status'],
            ))
            added.append(rid)
        return {'added': added, 'missing': missing, 'duplicated': duplicated}

    @with_session(auto_commit=True)
    def cart_remove(self, user_id, item_ids: List[int]) -> dict:
        """从购物车移除（按条目 ID，仅限本人的条目）。"""
        if not user_id:
            raise ValueError("未认证用户禁止操作购物车（user_id 缺失）")
        session = get_db_session()
        deleted = session.query(CherryPickCartItem).filter(
            CherryPickCartItem.user_id == user_id,
            CherryPickCartItem.id.in_([int(i) for i in (item_ids or [])]),
        ).delete(synchronize_session=False)
        return {'removed': int(deleted or 0)}

    @with_session(auto_commit=True)
    def cart_clear(self, user_id, keep_result_ids: Optional[List[int]] = None) -> dict:
        """清空购物车；keep_result_ids 提供时仅清除其余条目（下单出清口径）。"""
        if not user_id:
            raise ValueError("未认证用户禁止操作购物车（user_id 缺失）")
        session = get_db_session()
        q = session.query(CherryPickCartItem).filter(CherryPickCartItem.user_id == user_id)
        if keep_result_ids:
            keep = {int(r) for r in keep_result_ids}
            rows = q.all()
            removed = 0
            for row in rows:
                if row.result_id not in keep:
                    session.delete(row)
                    removed += 1
            return {'removed': removed}
        removed = q.delete(synchronize_session=False)
        return {'removed': int(removed or 0)}

    @with_session(auto_commit=False)
    def cart_list(self, user_id) -> List[Dict[str, Any]]:
        """当前用户购物车内容（加购时间序，按来源任务分组由应用层组装）。"""
        if not user_id:
            return []
        session = get_db_session()
        rows = (session.query(CherryPickCartItem)
                .filter(CherryPickCartItem.user_id == user_id)
                .order_by(CherryPickCartItem.id).all())
        return [self._cart_item_to_dict(row) for row in rows]

    @staticmethod
    def _cart_item_to_dict(row: CherryPickCartItem) -> Dict[str, Any]:
        return {
            'item_id': row.id,
            'result_id': row.result_id,
            'source_task_id': row.source_task_id,
            'source_task_name': row.source_task_name,
            'source_case_id': row.source_case_id,
            'source_device_id': row.source_device_id,
            'source_api_id': row.source_api_id,
            # INT-577 §11-5：购物车条目补 source_result_type
            'source_result_type': row.source_result_type,
            'execution_status': row.execution_status,
            'created_at': row.created_at.isoformat() if row.created_at else None,
        }

    # ==================== 挑选集（per-user） ====================

    @with_session(auto_commit=True)
    def set_save(self, user_id, name: str, description: Optional[str],
                 items: List[Dict[str, Any]]) -> dict:
        """购物车另存为挑选集（同名允许重复保存，§10）。

        items: [{result_id: int}, ...]（与购物车同构，溯源快照由仓储提取）。
        """
        if not user_id:
            raise ValueError("未认证用户禁止保存挑选集（user_id 缺失）")
        if not (name or '').strip():
            raise ValueError("挑选集名称不能为空")
        result_ids = sorted({int(it.get('result_id')) for it in (items or [])
                             if it.get('result_id') is not None})
        session = get_db_session()
        picked_set = CherryPickSet(
            user_id=user_id, name=name.strip(),
            description=(description or '').strip() or None,
            created_by_user_id=user_id,
        )
        session.add(picked_set)
        session.flush()
        for rid in result_ids:
            result, source_task = self._load_result(session, rid)
            if result is None or source_task is None:
                continue  # 源结果已失效的条目不进入挑选集
            snapshot = _result_trace_snapshot(result, source_task)
            session.add(CherryPickSetItem(
                set_id=picked_set.id,
                result_id=snapshot['result_id'],
                source_task_id=snapshot['source_task_id'],
                source_task_name=snapshot['source_task_name'],
                source_case_id=snapshot['source_case_id'],
                source_device_id=snapshot['source_device_id'],
                source_api_id=snapshot['source_api_id'],
                source_result_type=snapshot['source_result_type'],
                execution_status=snapshot['execution_status'],
            ))
        session.flush()
        return {'set_id': picked_set.id, 'name': picked_set.name,
                'item_count': len(result_ids)}

    @with_session(auto_commit=False)
    def set_list(self, user_id) -> List[Dict[str, Any]]:
        """当前用户的挑选集列表（含条目数）。"""
        if not user_id:
            return []
        session = get_db_session()
        sets = (session.query(CherryPickSet)
                .filter(CherryPickSet.user_id == user_id)
                .order_by(CherryPickSet.id.desc()).all())
        if not sets:
            return []
        counts: Dict[int, int] = {}
        for sid, in session.query(CherryPickSetItem.set_id).filter(
                CherryPickSetItem.set_id.in_([s.id for s in sets])).all():
            counts[sid] = counts.get(sid, 0) + 1
        return [{
            'set_id': s.id,
            'name': s.name,
            'description': s.description,
            'item_count': counts.get(s.id, 0),
            'created_at': s.created_at.isoformat() if s.created_at else None,
        } for s in sets]

    @with_session(auto_commit=False)
    def set_detail(self, user_id, set_id: int) -> Optional[Dict[str, Any]]:
        """挑选集详情（含条目溯源列表）。"""
        if not user_id:
            return None
        session = get_db_session()
        picked_set = session.query(CherryPickSet).filter(
            CherryPickSet.id == int(set_id),
            CherryPickSet.user_id == user_id).first()
        if picked_set is None:
            return None
        items = (session.query(CherryPickSetItem)
                 .filter(CherryPickSetItem.set_id == picked_set.id)
                 .order_by(CherryPickSetItem.id).all())
        return {
            'set_id': picked_set.id,
            'name': picked_set.name,
            'description': picked_set.description,
            'created_at': picked_set.created_at.isoformat() if picked_set.created_at else None,
            'items': [{
                'result_id': it.result_id,
                'source_task_id': it.source_task_id,
                'source_task_name': it.source_task_name,
                'source_case_id': it.source_case_id,
                'source_device_id': it.source_device_id,
                'source_api_id': it.source_api_id,
                'source_result_type': it.source_result_type,
                'execution_status': it.execution_status,
            } for it in items],
        }

    @with_session(auto_commit=True)
    def set_delete(self, user_id, set_id: int) -> dict:
        """删除挑选集（仅限本人的挑选集）。"""
        if not user_id:
            raise ValueError("未认证用户禁止操作挑选集（user_id 缺失）")
        session = get_db_session()
        target = session.query(CherryPickSet).filter(
            CherryPickSet.id == int(set_id),
            CherryPickSet.user_id == user_id).first()
        if target is None:
            return {'deleted': 0}
        session.query(CherryPickSetItem).filter(
            CherryPickSetItem.set_id == target.id).delete(synchronize_session=False)
        session.delete(target)
        return {'deleted': 1}

    # ==================== 容器任务关系（引用方案 A） ====================

    @with_session(auto_commit=True)
    def relations_create(self, cherry_pick_task_id: int, items: List[Dict[str, Any]],
                         created_by_user_id: Optional[int]) -> int:
        """为容器任务批量写入结果引用关系（在同一事务内与容器任务创建原子）。

        items: 溯源快照 dict 列表（_result_trace_snapshot 形状）。
        """
        session = get_db_session()
        for item in items or []:
            session.add(TaskCherryPickRelation(
                cherry_pick_task_id=cherry_pick_task_id,
                result_id=item['result_id'],
                source_task_id=item['source_task_id'],
                source_task_name=item.get('source_task_name'),
                source_case_id=item.get('source_case_id'),
                source_device_id=item.get('source_device_id'),
                source_api_id=item.get('source_api_id'),
                created_by_user_id=created_by_user_id,
            ))
        return len(items or [])

    @with_session(auto_commit=False)
    def relations_by_container(self, cherry_pick_task_id: int) -> List[Dict[str, Any]]:
        """容器任务的全部引用关系（读链路解析/溯源/导出内联共用）。"""
        session = get_db_session()
        rows = (session.query(TaskCherryPickRelation)
                .filter(TaskCherryPickRelation.cherry_pick_task_id == int(cherry_pick_task_id))
                .order_by(TaskCherryPickRelation.id).all())
        return [{
            'id': r.id,
            'result_id': r.result_id,
            'source_task_id': r.source_task_id,
            'source_task_name': r.source_task_name,
            'source_case_id': r.source_case_id,
            'source_device_id': r.source_device_id,
            'source_api_id': r.source_api_id,
            'created_at': r.created_at.isoformat() if r.created_at else None,
        } for r in rows]

    @with_session(auto_commit=False)
    def relations_by_containers(self, container_ids: List[int]) -> List[Dict[str, Any]]:
        """批量取容器任务的引用关系（候选查询容器命中解析，INT-657）。

        返回含容器任务名/状态标注（候选命中项归属展示用），避免逐容器 N+1。
        """
        ids = [int(t) for t in (container_ids or [])]
        if not ids:
            return []
        session = get_db_session()
        rows = (session.query(TaskCherryPickRelation, Task)
                .join(Task, Task.id == TaskCherryPickRelation.cherry_pick_task_id)
                .filter(TaskCherryPickRelation.cherry_pick_task_id.in_(ids))
                .order_by(TaskCherryPickRelation.id).all())
        return [{
            'id': r.id,
            'cherry_pick_task_id': r.cherry_pick_task_id,
            'container_task_name': task.name if task else None,
            'container_task_status': task.status if task else None,
            'result_id': r.result_id,
            'source_task_id': r.source_task_id,
            'source_task_name': r.source_task_name,
            'source_case_id': r.source_case_id,
            'source_device_id': r.source_device_id,
            'source_api_id': r.source_api_id,
            'created_at': r.created_at.isoformat() if r.created_at else None,
        } for r, task in rows]

    @with_session(auto_commit=False)
    def container_ids_by_source(self, source_task_id: int) -> List[int]:
        """按来源任务反查引用它的容器任务（源任务删除/审计用）。"""
        session = get_db_session()
        rows = (session.query(TaskCherryPickRelation.cherry_pick_task_id)
                .filter(TaskCherryPickRelation.source_task_id == int(source_task_id))
                .distinct().all())
        return [r[0] for r in rows]

    @with_session(auto_commit=False)
    def is_cherry_pick_container(self, task_id: int) -> bool:
        """cherry-pick 容器任务判定（专有关系表存在性，§5.4）。"""
        session = get_db_session()
        return session.query(TaskCherryPickRelation.id).filter(
            TaskCherryPickRelation.cherry_pick_task_id == int(task_id)
        ).first() is not None

    @with_session(auto_commit=False)
    def container_ids_in(self, task_ids: List[int]) -> List[int]:
        """批量判定容器任务（列表 cherry_pick 输出用，避免 N+1）。"""
        ids = [int(t) for t in (task_ids or [])]
        if not ids:
            return []
        session = get_db_session()
        rows = (session.query(TaskCherryPickRelation.cherry_pick_task_id)
                .filter(TaskCherryPickRelation.cherry_pick_task_id.in_(ids))
                .distinct().all())
        return [r[0] for r in rows]


    # ==================== 可挑选任务清单（INT-1496 阶段 1） ====================

    @with_session(auto_commit=False)
    def pickable_tasks(self, keyword: Optional[str] = None, status: Optional[str] = None,
                       sort_by: str = 'status', sort_order: str = 'asc',
                       page: int = 1, per_page: int = 50,
                       user_id=None, is_admin: bool = False) -> Dict[str, Any]:
        """可挑选任务清单（设计文档 §8.1，INT-1496）：任务级聚合 + 服务端分页。

        性能硬性 1/2：`test_tasks ⋈ test_results` 在单条 SQL 内按 `t.id`
        GROUP BY 出 `pickable_count`，`count(*) over()` 出筛选命中的任务总数，
        再在聚合结果上 LIMIT/OFFSET；不把结果行或全量任务行拉进进程内存。
        返回体只含任务级字段（不含结果行 / 用例 / 设备 / 评估装饰）。

        口径：
        - keyword：任务名模糊匹配（只匹配任务名，不匹配任务 ID）
        - status：任务状态过滤（PickableTaskStatus 枚举值；None = 全部三终态）
        - sort_by：status（权重 completed→failed→stopped）/ name / created_at；
          sort_order=desc 时主键与次级键同向反转
        - 次序稳定：任何排序键后都追加 `t.id ASC` 兜底
        - execution_status 返回的是**任务**状态（不是结果级执行状态）
        - created_at 返回的是**任务**创建时间（不是首条结果时间）
        - user_id / is_admin：INT-423 可见性（非 owner 非 admin 看不到私有任务）

        Returns:
            {'items': [{id, name, execution_status, pickable_count, created_at}],
             'total': 命中任务总数（不受分页影响）}
        """
        session = get_db_session()
        statuses = [s.value for s in PickableTaskStatus]
        filters = [
            Task.deleted == False,  # noqa: E712
            Task.status.in_([status] if status else statuses),
            TestResult.excluded == 0,
            visible_condition(Task.created_by_user_id, Task.visibility, user_id, is_admin),
        ]
        if keyword:
            filters.append(Task.name.ilike(f'%{keyword}%'))

        # 状态权重：枚举声明顺序即 completed → failed → stopped
        status_weight = case(
            {s.value: idx for idx, s in enumerate(PickableTaskStatus)},
            value=Task.status,
            else_=len(statuses),
        )
        order_cols = []
        if sort_by == 'created_at':
            order_cols.append(Task.created_at)
        elif sort_by == 'name':
            order_cols.append(Task.name)
        else:
            order_cols.append(status_weight)
            order_cols.append(Task.name)  # 同权重按任务名
        if sort_order == 'desc':
            order_cols = [col.desc() for col in order_cols]
        else:
            order_cols = [col.asc() for col in order_cols]
        order_cols.append(Task.id.asc())  # 兜底稳定次序

        rows = (session.query(
                    Task.id.label('id'),
                    Task.name.label('name'),
                    Task.status.label('execution_status'),
                    Task.created_at.label('created_at'),
                    sa_func.count(TestResult.id).label('pickable_count'),
                    sa_func.count().over().label('total'),
                )
                .join(TestResult, TestResult.task_id == Task.id)
                .filter(*filters)
                .group_by(Task.id, Task.name, Task.status, Task.created_at)
                .having(sa_func.count(TestResult.id) > 0)
                .order_by(*order_cols)
                .limit(per_page)
                .offset((page - 1) * per_page)
                .all())

        if rows:
            total = int(rows[0].total or 0)
        else:
            # 翻到末页之后：窗口列无可读行，按同一筛选口径另取分组计数
            grouped = (session.query(Task.id)
                       .join(TestResult, TestResult.task_id == Task.id)
                       .filter(*filters)
                       .group_by(Task.id)
                       .subquery())
            total = int(session.query(sa_func.count()).select_from(grouped).scalar() or 0)

        return {
            'items': [{
                'id': row.id,
                'name': row.name,
                'execution_status': row.execution_status,
                'pickable_count': int(row.pickable_count or 0),
                'created_at': row.created_at.isoformat() if row.created_at else None,
            } for row in rows],
            'total': total,
        }


# 单例
cherry_pick_repository = CherryPickRepository()
