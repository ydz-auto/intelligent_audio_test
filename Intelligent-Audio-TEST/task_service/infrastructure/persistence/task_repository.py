# -*- coding: utf-8 -*-
"""TaskRepository - 任务聚合根仓储实现（写模型）。

仓储职责：
- 从 DB 加载 Task PO 并转换为 TaskAggregate 聚合根
- 将聚合根的变更持久化回 DB（Entity → PO 字段映射）
- 提供按条件查询聚合根的方法

仓储只处理写模型，读取走 read_models（查询处理器）。

P5+DOMAIN 改造：移除对 aggregate.orm 的依赖，改为 PO ↔ Entity 显式转换。
聚合根不再持有 PO 引用，领域层与 ORM 完全隔离。
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

from shared.models.database import get_db_session, utc8now
from shared.utils.db_session import with_session, SoftDeleteMixin
from shared.utils.status_utils import derive_task_case_status
from shared.utils.status_constants import TaskStatus as SharedTaskStatus, ExecutionStatus, EvaluationStatus, TaskCaseStatus
from task_service.infrastructure.persistence.models import Task, TaskCase, TaskDevice, TaskAPI

from task_service.domain.entities import (
    TaskAggregate,
    TaskCaseEntity,
)
from task_service.domain.repositories.task_repository import TaskRepositoryABC
from task_service.domain.repositories.task_case_repository import TaskCaseRepositoryABC

_UTC_PLUS_8 = timezone(timedelta(hours=8))


# ========== PO ↔ Entity 转换 ==========

def _task_po_to_entity(po: Task) -> TaskAggregate:
    """Task PO → TaskAggregate 聚合根"""
    return TaskAggregate(
        id=po.id,
        name=po.name,
        type=po.type,
        status=po.status,
        config=po.config,
        algorithm_type=po.algorithm_type,
        algorithm_params=po.algorithm_params,
        total_cases=po.total_cases or 0,
        completed_cases=po.completed_cases or 0,
        failed_cases=po.failed_cases or 0,
        deleted=po.deleted or False,
        started_at=po.started_at,
        completed_at=po.completed_at,
        actual_duration=po.actual_duration,
        cases=[],  # 用例集合按需加载
    )


def _apply_aggregate_to_po(aggregate: TaskAggregate, po: Task) -> None:
    """将聚合根的可写字段映射回 PO（不含 id/deleted_at/created_at 等元数据）"""
    # 只更新可变字段，避免覆盖不可变字段
    po.status = aggregate.status
    po.config = aggregate.config
    po.algorithm_type = aggregate.algorithm_type
    po.algorithm_params = aggregate.algorithm_params
    po.total_cases = aggregate.total_cases
    po.completed_cases = aggregate.completed_cases
    po.failed_cases = aggregate.failed_cases
    po.deleted = aggregate.deleted
    po.started_at = aggregate.started_at
    po.completed_at = aggregate.completed_at
    po.actual_duration = aggregate.actual_duration


def _task_case_po_to_entity(po: TaskCase) -> TaskCaseEntity:
    """TaskCase PO → TaskCaseEntity 实体"""
    return TaskCaseEntity(
        id=po.id,
        task_id=po.task_id,
        test_case_id=po.test_case_id,
        status=po.status or TaskCaseStatus.PENDING,
        execution_status=po.execution_status or ExecutionStatus.PENDING,
        evaluation_status=po.evaluation_status or EvaluationStatus.PENDING,
        started_at=po.started_at,
        completed_at=po.completed_at,
        duration=po.duration,
        error_message=po.error_message,
    )


def _apply_case_entity_to_po(entity: TaskCaseEntity, po: TaskCase) -> None:
    """将 TaskCaseEntity 可写字段映射回 PO"""
    po.status = entity.status
    po.execution_status = entity.execution_status
    po.evaluation_status = entity.evaluation_status
    po.started_at = entity.started_at
    po.completed_at = entity.completed_at
    po.duration = entity.duration
    po.error_message = entity.error_message


class TaskRepository(SoftDeleteMixin, TaskRepositoryABC, TaskCaseRepositoryABC):
    """任务聚合根仓储。

    遵循 DDD 仓储模式：外部只看到聚合根，不感知 ORM。
    使用 @with_session 装饰器自动管理 session 生命周期，
    soft_delete 由 SoftDeleteMixin 提供。

    P5+DOMAIN: 通过 PO ↔ Entity 显式转换，聚合根不再持有 ORM 引用。
    """

    PO_CLASS = Task

    @with_session
    def get_by_id(self, task_id: int) -> Optional[TaskAggregate]:
        """按 ID 加载任务聚合根。

        Returns:
            TaskAggregate 或 None（任务不存在）。
        """
        po = get_db_session().get(Task, task_id)
        if po is None:
            return None
        return _task_po_to_entity(po)

    @with_session(auto_commit=True)
    def save(self, aggregate: TaskAggregate) -> None:
        """持久化聚合根变更。

        P5+DOMAIN: 通过 PO ↔ Entity 转换，将聚合根字段写回 PO，
        不再依赖 aggregate.orm 属性。
        """
        session = get_db_session()
        po = session.get(Task, aggregate.id)
        if po is None:
            # 不应发生（save 只更新已存在的聚合），但容错处理
            raise ValueError(f"Task id={aggregate.id} 不存在，无法 save")
        _apply_aggregate_to_po(aggregate, po)

    @with_session(auto_commit=True)
    def add(self, aggregate: TaskAggregate) -> int:
        """新增任务聚合根。

        Returns:
            新任务 ID。

        P5+DOMAIN: 从聚合根字段构造新 PO，不再依赖 aggregate.orm。
        """
        session = get_db_session()
        po = Task(
            name=aggregate.name,
            type=aggregate.type,
            status=aggregate.status,
            config=aggregate.config,
            algorithm_type=aggregate.algorithm_type,
            algorithm_params=aggregate.algorithm_params,
            total_cases=aggregate.total_cases,
            completed_cases=aggregate.completed_cases,
            failed_cases=aggregate.failed_cases,
            deleted=aggregate.deleted,
            started_at=aggregate.started_at,
            completed_at=aggregate.completed_at,
            actual_duration=aggregate.actual_duration,
        )
        session.add(po)
        session.flush()
        new_id = po.id
        # 将生成的 ID 回写聚合根
        aggregate.id = new_id
        return new_id

    def get_cases(self, task_id: int,
                  status: Optional[str] = None) -> List[TaskCaseEntity]:
        """加载任务下的用例实体列表。"""
        session = get_db_session()
        try:
            q = session.query(TaskCase).filter(TaskCase.task_id == task_id)
            if status:
                q = q.filter(TaskCase.status == status)
            orms = q.all()
            return [_task_case_po_to_entity(po) for po in orms]
        finally:
            session.close()

    def save_case(self, case_entity: TaskCaseEntity) -> None:
        """持久化单个用例实体变更。

        P5+DOMAIN: 通过 PO ↔ Entity 转换，不再依赖 case_entity.orm。
        """
        session = get_db_session()
        try:
            po = session.get(TaskCase, case_entity.id)
            if po is None:
                raise ValueError(f"TaskCase id={case_entity.id} 不存在，无法 save")
            _apply_case_entity_to_po(case_entity, po)
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def update_counts(self, task_id: int, completed_delta: int = 0,
                      failed_delta: int = 0) -> None:
        """原子更新任务的完成/失败计数。

        用于用例执行完成时的进度累加。
        """
        session = get_db_session()
        try:
            task = session.get(Task, task_id)
            if task is None:
                return
            if completed_delta:
                task.completed_cases = (task.completed_cases or 0) + completed_delta
            if failed_delta:
                task.failed_cases = (task.failed_cases or 0) + failed_delta
            task.updated_at = datetime.now(_UTC_PLUS_8)
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def get_api_ids(self, task_id: int) -> List[int]:
        """获取任务关联的 API ID 列表。"""
        session = get_db_session()
        try:
            rows = session.query(TaskAPI).filter_by(task_id=task_id).all()
            return [r.api_id for r in rows]
        finally:
            session.close()

    def get_device_ids(self, task_id: int) -> List[int]:
        """获取任务关联的设备 ID 列表。"""
        session = get_db_session()
        try:
            rows = session.query(TaskDevice).filter_by(task_id=task_id).all()
            return [r.device_id for r in rows]
        finally:
            session.close()

    def create_task_with_relations(
        self,
        name: str,
        task_type: str,
        description: str,
        config: Optional[Dict[str, Any]],
        algorithm_type: Optional[str],
        algorithm_params: Optional[Dict[str, Any]],
        case_ids: List[str],
        device_ids: List[int],
        api_ids: List[int],
        created_by: Optional[int],
        now: Optional[datetime] = None,
    ) -> int:
        """创建任务记录及其关联关系（用例/设备/API）。

        Args:
            name: 任务名称
            task_type: 任务类型（api / e2e）
            description: 任务描述
            config: 任务配置
            algorithm_type: 算法类型
            algorithm_params: 算法参数
            case_ids: 关联用例 ID 列表
            device_ids: 关联设备 ID 列表
            api_ids: 关联 API ID 列表
            created_by: 创建人
            now: 创建时间（调用方传入，保证时区一致）

        Returns:
            新任务 ID。

        说明：此方法在一个 DB session 内原子创建 Task + 关联表记录。
        """
        from task_service.infrastructure.persistence.models import TaskMergeRelation  # noqa: F401
        if now is None:
            now = datetime.now(_UTC_PLUS_8)

        session = get_db_session()
        try:
            task = Task(
                name=name,
                description=description,
                type=task_type,
                status=SharedTaskStatus.PENDING,
                config=config or None,
                algorithm_type=algorithm_type,
                algorithm_params=algorithm_params or None,
                total_cases=len(case_ids),
                completed_cases=0,
                failed_cases=0,
                created_by=created_by,
                created_at=now,
                updated_at=now,
            )
            session.add(task)
            session.flush()  # 获取自增 ID
            task_id = task.id

            # 关联用例
            for case_id in case_ids:
                tc = TaskCase(
                    task_id=task_id,
                    test_case_id=case_id,
                    status=TaskCaseStatus.PENDING,
                    execution_status=ExecutionStatus.PENDING,
                    evaluation_status=EvaluationStatus.PENDING,
                    created_at=now,
                )
                session.add(tc)

            # 关联设备
            for device_id in device_ids:
                session.add(TaskDevice(task_id=task_id, device_id=device_id))

            # 关联 API
            for api_id in api_ids:
                session.add(TaskAPI(task_id=task_id, api_id=api_id))

            session.commit()
            return task_id
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def merge_tasks(
        self,
        source_task_ids: List[int],
        merged_task_name: str,
        merged_task_type: str,
        description: str,
        created_by: Optional[int],
        now: Optional[datetime] = None,
    ) -> Tuple[int, int]:
        """创建合并任务并建立源任务-合并任务映射关系。

        Args:
            source_task_ids: 源任务 ID 列表
            merged_task_name: 合并后任务名称
            merged_task_type: 合并后任务类型
            description: 任务描述
            created_by: 创建人
            now: 创建时间

        Returns:
            (merged_task_id, total_results)
        """
        from task_service.infrastructure.persistence.models import TaskMergeRelation
        if now is None:
            now = datetime.now(_UTC_PLUS_8)

        session = get_db_session()
        try:
            # 统计源任务结果数量
            total_results = 0
            source_counts: List[Tuple[int, int]] = []
            for src_id in source_task_ids:
                src_task = session.get(Task, src_id)
                count = (src_task.completed_cases or 0) if src_task else 0
                source_counts.append((src_id, count))
                total_results += count

            merged_task = Task(
                name=merged_task_name,
                description=description,
                type=merged_task_type,
                status=SharedTaskStatus.PENDING,
                total_cases=total_results,
                completed_cases=0,
                failed_cases=0,
                created_by=created_by,
                created_at=now,
                updated_at=now,
            )
            session.add(merged_task)
            session.flush()
            merged_task_id = merged_task.id

            # 建立合并关系
            for src_id, count in source_counts:
                session.add(TaskMergeRelation(
                    merged_task_id=merged_task_id,
                    source_task_id=src_id,
                    source_result_count=count,
                    created_at=now,
                ))

            session.commit()
            return merged_task_id, total_results
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    # ========== task_crud_service 兼容方法 ==========

    def update_task(self, task_id: int, name: str = None,
                    description: str = None) -> bool:
        """更新任务名称/描述。

        Returns:
            True 如果任务存在且已更新；False 如果任务不存在。
        """
        session = get_db_session()
        try:
            task = session.get(Task, task_id)
            if task is None:
                return False
            if name is not None:
                task.name = name
            if description is not None:
                task.description = description
            task.updated_at = datetime.now(_UTC_PLUS_8)
            session.commit()
            return True
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def update_cases(self, task_id: int, action: str,
                     case_ids: List[str]) -> Optional[Dict[str, Any]]:
        """动态添加/移除用例。

        Args:
            task_id: 任务 ID
            action: 'add' 或 'remove'
            case_ids: 用例 ID 列表

        Returns:
            {'task_id': task_id, 'total_count': N} 或 None（任务不存在）
            或 {'error': str, 'code': int}
        """
        session = get_db_session()
        try:
            task = session.get(Task, task_id)
            if task is None:
                return None

            now = datetime.now(_UTC_PLUS_8)

            if action == 'add':
                for case_id in case_ids:
                    existing = session.query(TaskCase).filter(
                        TaskCase.task_id == task_id,
                        TaskCase.test_case_id == case_id,
                    ).first()
                    if existing is None:
                        session.add(TaskCase(
                            task_id=task_id,
                            test_case_id=case_id,
                            status=TaskCaseStatus.PENDING,
                            execution_status=ExecutionStatus.PENDING,
                            evaluation_status=EvaluationStatus.PENDING,
                            created_at=now,
                        ))
            elif action == 'remove':
                session.query(TaskCase).filter(
                    TaskCase.task_id == task_id,
                    TaskCase.test_case_id.in_(list(case_ids)),
                ).delete(synchronize_session=False)
            else:
                return {'error': f'未知操作: {action}', 'code': 400}

            session.flush()
            total = session.query(TaskCase).filter(
                TaskCase.task_id == task_id
            ).count()
            task.total_cases = total
            task.updated_at = now
            session.commit()
            return {'task_id': task_id, 'total_count': total}
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def batch_stop_and_soft_delete(self, task_ids: List[int]) -> int:
        """批量停止并软删除任务。

        调用方应先停止运行中的任务（通过执行引擎），
        此方法仅做软删除。

        Returns:
            实际删除的条数
        """
        if not task_ids:
            return 0
        session = get_db_session()
        try:
            count = session.query(Task).filter(
                Task.id.in_(task_ids)
            ).update({Task.deleted: True}, synchronize_session=False)
            session.commit()
            return count
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def get_tasks_for_export(self, task_ids: List[int]) -> List[Dict[str, Any]]:
        """获取任务导出数据（dict 列表）。"""
        session = get_db_session()
        try:
            tasks = session.query(Task).filter(
                Task.id.in_(task_ids),
                Task.deleted == False,  # noqa: E712
            ).all()
            return [{
                'id': t.id,
                'name': t.name,
                'description': t.description,
                'type': t.type,
                'status': t.status,
                'config': t.config,
                'algorithm_type': t.algorithm_type,
                'algorithm_params': t.algorithm_params,
                'total_cases': t.total_cases,
                'completed_cases': t.completed_cases,
                'failed_cases': t.failed_cases,
                'created_at': t.created_at.isoformat() if t.created_at else None,
                'updated_at': t.updated_at.isoformat() if t.updated_at else None,
                'started_at': t.started_at.isoformat() if t.started_at else None,
                'completed_at': t.completed_at.isoformat() if t.completed_at else None,
            } for t in tasks]
        finally:
            session.close()

    def count_running_by_type(self, task_type: str) -> int:
        """统计指定类型的运行中任务数量。

        Args:
            task_type: 任务类型（如 'e2e'）

        Returns:
            处于 queued/pending/running 状态且未删除的任务数
        """
        session = get_db_session()
        try:
            return (
                session.query(Task)
                .filter(
                    Task.type == task_type,
                    Task.status.in_([SharedTaskStatus.QUEUED, SharedTaskStatus.PENDING, SharedTaskStatus.RUNNING]),
                    Task.deleted == False,  # noqa: E712
                )
                .count()
            )
        finally:
            session.close()

    # ========== TaskDataService servicer 用 — dict 序列化方法 ==========

    def get_task_dict_by_id(self, task_id: int) -> Optional[dict]:
        """按 ID 读取 Task 详情（返回 dict 序列化格式，供 gRPC servicer 用）。"""
        session = get_db_session()
        try:
            task = session.get(Task, task_id)
            if task is None:
                return None
            return {
                'id': task.id,
                'name': task.name,
                'description': task.description,
                'type': task.type,
                'status': task.status,
                'config': task.config,
                'algorithm_type': task.algorithm_type,
                'algorithm_params': task.algorithm_params,
                'total_cases': task.total_cases,
                'completed_cases': task.completed_cases,
                'failed_cases': task.failed_cases,
                'created_by_user_id': task.created_by_user_id,
                'created_at': task.created_at.isoformat() if task.created_at else None,
                'updated_at': task.updated_at.isoformat() if task.updated_at else None,
                'started_at': task.started_at.isoformat() if task.started_at else None,
                'completed_at': task.completed_at.isoformat() if task.completed_at else None,
                'estimated_time': task.estimated_time,
                'actual_duration': task.actual_duration,
            }
        finally:
            session.close()

    def update_status(self, task_id: int, status: str) -> Optional[dict]:
        """更新 Task 的 status，返回 {task_id, old_status, new_status} 或 None。"""
        session = get_db_session()
        try:
            task = session.get(Task, task_id)
            if task is None:
                return None
            old_status = task.status
            task.status = status
            # 重新评估完成时自动更新计数和时间戳
            if old_status == SharedTaskStatus.REEVALUATING and status in (SharedTaskStatus.COMPLETED, SharedTaskStatus.FAILED):
                task.reevaluation_count = (task.reevaluation_count or 0) + 1
                task.reevaluated_at = utc8now()
            session.flush()
            return {
                'task_id': task.id,
                'old_status': old_status,
                'new_status': task.status,
            }
        finally:
            session.close()

    def get_task_device_dicts(self, task_id: int) -> List[dict]:
        """获取任务关联设备列表（返回 dict 列表）。"""
        session = get_db_session()
        try:
            rows = session.query(TaskDevice).filter(
                TaskDevice.task_id == task_id
            ).all()
            return [{'id': td.id, 'task_id': td.task_id, 'device_id': td.device_id} for td in rows]
        finally:
            session.close()

    def get_task_api_dicts(self, task_id: int) -> List[dict]:
        """获取任务关联 API 列表（返回 dict 列表）。"""
        session = get_db_session()
        try:
            rows = session.query(TaskAPI).filter(
                TaskAPI.task_id == task_id
            ).all()
            return [{'id': ta.id, 'task_id': ta.task_id, 'api_id': ta.api_id} for ta in rows]
        finally:
            session.close()

    def get_task_case_dicts(self, task_id: int, case_ids: List[str] = None) -> List[dict]:
        """按 task_id + case_ids 批量读取 TaskCase（返回 dict 列表）。

        case_ids 为空时返回该 task 下所有 TaskCase。
        """
        session = get_db_session()
        try:
            q = session.query(TaskCase).filter(TaskCase.task_id == task_id)
            if case_ids:
                q = q.filter(TaskCase.test_case_id.in_(list(case_ids)))
            tcs = q.all()
            return [{
                'id': tc.id,
                'task_id': tc.task_id,
                'test_case_id': tc.test_case_id,
                'status': tc.status,
                'execution_status': tc.execution_status,
                'evaluation_status': tc.evaluation_status,
                'started_at': tc.started_at.isoformat() if tc.started_at else None,
                'completed_at': tc.completed_at.isoformat() if tc.completed_at else None,
                'duration': tc.duration,
                'error_message': tc.error_message,
            } for tc in tcs]
        finally:
            session.close()

    def update_task_case_status(self, task_id: int, case_id: str,
                                 status: str = '', execution_status: str = '',
                                 evaluation_status: str = '',
                                 error_message: str = '') -> bool:
        """更新 TaskCase 状态，返回是否有更新。"""
        from shared.utils.status_utils import derive_task_case_status
        session = get_db_session()
        try:
            # 如果传了 execution_status 或 evaluation_status 但没传 status，自动推导
            if not status and (execution_status or evaluation_status):
                tc = session.query(TaskCase).filter(
                    TaskCase.task_id == task_id,
                    TaskCase.test_case_id == case_id,
                ).first()
                if tc:
                    cur_exec = execution_status or tc.execution_status or 'pending'
                    cur_eval = evaluation_status or tc.evaluation_status or 'pending'
                    status = derive_task_case_status(cur_exec, cur_eval)

            update_fields = {}
            if status:
                update_fields['status'] = status
            if execution_status:
                update_fields['execution_status'] = execution_status
            if evaluation_status:
                update_fields['evaluation_status'] = evaluation_status
            if error_message:
                update_fields['error_message'] = error_message

            if update_fields:
                session.query(TaskCase).filter(
                    TaskCase.task_id == task_id,
                    TaskCase.test_case_id == case_id,
                ).update(update_fields, synchronize_session=False)
                session.commit()
            return bool(update_fields)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def get_task_stats(self, status: str = '', algorithm_type: str = '',
                       group_by: str = '') -> dict:
        """聚合统计 Task — count / group_by。"""
        from sqlalchemy import func as _func
        session = get_db_session()
        try:
            query = session.query(Task).filter(Task.deleted == False)  # noqa: E712
            if status:
                query = query.filter(Task.status == status)
            if algorithm_type:
                query = query.filter(Task.algorithm_type == algorithm_type)

            if group_by:
                allowed = {'status': Task.status, 'algorithm_type': Task.algorithm_type,
                           'type': Task.type}
                col = allowed.get(group_by)
                if col is None:
                    return {'error': f'unsupported group_by field: {group_by}'}
                rows = session.query(col, _func.count(Task.id)).filter(
                    Task.deleted == False  # noqa: E712
                )
                if status:
                    rows = rows.filter(Task.status == status)
                if algorithm_type:
                    rows = rows.filter(Task.algorithm_type == algorithm_type)
                rows = rows.group_by(col).all()
                items = [{'key': str(k) if k is not None else '', 'count': int(c)} for k, c in rows]
                return {'items': items}

            total = query.count()
            return {'total': int(total)}
        finally:
            session.close()

    # ========== ABC 接口适配（TaskCaseRepositoryABC） ==========

    def get_task_device_ids(self, task_id: int) -> List[dict]:
        """ABC 接口 — 委托到 get_task_device_dicts。"""
        return self.get_task_device_dicts(task_id)

    def get_task_api_ids(self, task_id: int) -> List[dict]:
        """ABC 接口 — 委托到 get_task_api_dicts。"""
        return self.get_task_api_dicts(task_id)

    def get_by_task_and_case_ids(self, task_id: int,
                                 case_ids: List[str] = None) -> List[dict]:
        """ABC 接口 — 委托到 get_task_case_dicts。"""
        return self.get_task_case_dicts(task_id, case_ids)

    def get_stats(self, algorithm_type: str = '', group_id: str = '',
                  group_by: str = '') -> dict:
        """ABC 接口 — TestCase 维度聚合统计。

        签名与 TaskCaseRepositoryABC.get_stats 对齐（group_id 用于按分组过滤）。
        """
        from sqlalchemy import func as _func
        session = get_db_session()
        try:
            query = session.query(TaskCase).join(
                Task, TaskCase.task_id == Task.id
            ).filter(Task.deleted == False)  # noqa: E712
            if algorithm_type:
                query = query.filter(Task.algorithm_type == algorithm_type)
            if group_id:
                query = query.filter(Task.group_id == group_id)
            total = query.count()
            return {'total': int(total)}
        finally:
            session.close()

    # ========== task_lifecycle_service 兼容方法（ORM 风格） ==========

    def get_task_for_start_check(self, task_id: int):
        """启动前检查：返回 Task PO（含 status/id），不存在返回 None。"""
        session = get_db_session()
        try:
            return session.query(Task).filter(
                Task.id == task_id,
                Task.deleted == False,  # noqa: E712
            ).first()
        finally:
            session.close()

    def reset_task_for_start(self, task_id: int) -> bool:
        """重置失败/停止任务为 pending，清零计数。"""
        session = get_db_session()
        try:
            task = session.get(Task, task_id)
            if task is None:
                return False
            task.status = SharedTaskStatus.PENDING
            task.completed_cases = 0
            task.failed_cases = 0
            task.started_at = None
            task.completed_at = None
            task.actual_duration = None
            # 重置所有 TaskCase 为 pending
            session.query(TaskCase).filter(
                TaskCase.task_id == task_id
            ).update({
                TaskCase.status: derive_task_case_status(ExecutionStatus.PENDING, EvaluationStatus.PENDING),
                TaskCase.execution_status: ExecutionStatus.PENDING,
                TaskCase.evaluation_status: EvaluationStatus.PENDING,
                TaskCase.started_at: None,
                TaskCase.completed_at: None,
                TaskCase.duration: None,
                TaskCase.error_message: None,
            }, synchronize_session=False)
            session.commit()
            return True
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def check_environment_for_start(self, task_id: int):
        """环境预检：检查关联设备和播放设备是否在线。

        Returns:
            (can_start: bool, error_msg: str)
        """
        session = get_db_session()
        try:
            # 获取任务关联的设备
            device_rows = session.query(TaskDevice).filter(
                TaskDevice.task_id == task_id
            ).all()

            if not device_rows:
                return True, ''  # 无设备关联，跳过检查

            # 通过 gRPC 检查设备状态
            try:
                from task_service.infrastructure.acl.device_acl_repository import device_acl_repository
                device_ids = [td.device_id for td in device_rows]

                devices = device_acl_repository.get_device_statuses(device_ids)

                offline_devices = [d for d in devices if d.get('status') != 'online']

                if offline_devices:
                    names = ', '.join(
                        d.get('device_name') or d.get('name') or f"id={d.get('id')}"
                        for d in offline_devices
                    )
                    return False, f"设备离线，无法启动: {names}"

                return True, ''
            except Exception as e:
                logger.warning(f"设备状态检查异常（跳过）: {e}")
                return True, ''  # gRPC 异常时不阻塞启动
        finally:
            session.close()

    def get_task_orm(self, task_id: int):
        """获取 Task PO（lifecycle service 用）。"""
        session = get_db_session()
        try:
            return session.query(Task).filter(
                Task.id == task_id,
                Task.deleted == False,  # noqa: E712
            ).first()
        finally:
            session.close()

    def find_retry_cases(self, task_id: int):
        """查找需要重试的用例（execution_status != completed 或 status == failed）。"""
        session = get_db_session()
        try:
            return session.query(TaskCase).filter(
                TaskCase.task_id == task_id,
                TaskCase.execution_status != ExecutionStatus.COMPLETED,
            ).all()
        finally:
            session.close()

    def cleanup_case_results(self, task_id: int, case_ids: list,
                             preserve_test_result: bool = False) -> None:
        """清理用例的执行结果。"""
        session = get_db_session()
        try:
            if not case_ids:
                return
            from task_service.infrastructure.persistence.models import TestResult
            query = session.query(TestResult).filter(
                TestResult.task_id == task_id,
                TestResult.test_case_id.in_(list(case_ids)),
            )
            if preserve_test_result:
                # 只清理 algorithm_result，保留 result_data
                query.update({TestResult.algorithm_result: None}, synchronize_session=False)
            else:
                query.delete(synchronize_session=False)
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def commit_task_case(self, tc) -> None:
        """提交 TaskCase PO 变更（lifecycle service 修改 PO 后调用）。"""
        session = get_db_session()
        try:
            session.merge(tc)
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def recount_task_cases(self, task_id: int) -> None:
        """重新统计任务的完成/失败用例数。"""
        session = get_db_session()
        try:
            from sqlalchemy import func as _func
            total = session.query(_func.count(TaskCase.id)).filter(
                TaskCase.task_id == task_id
            ).scalar() or 0
            completed = session.query(_func.count(TaskCase.id)).filter(
                TaskCase.task_id == task_id,
                TaskCase.execution_status == ExecutionStatus.COMPLETED,
            ).scalar() or 0
            failed = session.query(_func.count(TaskCase.id)).filter(
                TaskCase.task_id == task_id,
                TaskCase.execution_status == ExecutionStatus.FAILED,
            ).scalar() or 0
            task = session.get(Task, task_id)
            if task:
                task.total_cases = total
                task.completed_cases = completed
                task.failed_cases = failed
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def reset_task_to_pending(self, task_id: int) -> None:
        """重置任务状态为 pending。"""
        session = get_db_session()
        try:
            task = session.get(Task, task_id)
            if task:
                task.status = SharedTaskStatus.PENDING
                session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def find_task_case(self, task_id: int, case_id: str):
        """查询单个 TaskCase PO。"""
        session = get_db_session()
        try:
            return session.query(TaskCase).filter(
                TaskCase.task_id == task_id,
                TaskCase.test_case_id == case_id,
            ).first()
        finally:
            session.close()

    def find_task_for_stop(self, task_id: int):
        """停止前检查：返回 Task PO。"""
        return self.get_task_orm(task_id)

    def find_task_for_reextract(self, task_id: int):
        """重新提取前检查：返回 Task PO。"""
        return self.get_task_orm(task_id)

    def get_task_type(self, task_id: int):
        """获取任务类型。"""
        session = get_db_session()
        try:
            task = session.get(Task, task_id)
            return task.type if task else None
        finally:
            session.close()

    def get_test_result_for_reevaluate(self, task_id: int, test_case_id: str):
        """获取测试结果 PO（用于重新评估）。"""
        session = get_db_session()
        try:
            from task_service.infrastructure.persistence.models import TestResult
            return session.query(TestResult).filter(
                TestResult.task_id == task_id,
                TestResult.test_case_id == test_case_id,
            ).first()
        finally:
            session.close()

    def get_test_case_orm(self, test_case_id: str):
        """获取 TestCase PO（跨域查询，后续改 gRPC）。"""
        session = get_db_session()
        try:
            from task_service.infrastructure.persistence.models.testcase_models import TestCase
            return session.query(TestCase).filter(
                TestCase.id == test_case_id,
            ).first()
        finally:
            session.close()


# 模块级单例
task_repository = TaskRepository()