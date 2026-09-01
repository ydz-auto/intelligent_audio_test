# -*- coding: utf-8 -*-
"""任务仓储 — 任务创建/合并/编辑 Mixin（从 task_repository.py 拆分，P4-5）。

任务与关联（用例/设备/API）的原子创建、任务合并、名称/描述编辑、
用例动态增删、批量软删除、导出数据、运行中任务计数。
"""
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from shared.models.database import get_db_session
from shared.utils.status_constants import (
    ExecutionStatus,
    EvaluationStatus,
    TaskCaseStatus,
    TaskStatus as SharedTaskStatus,
)
from task_service.infrastructure.persistence.models import Task, TaskCase, TaskAPI, TaskDevice

logger = logging.getLogger(__name__)

# 中国标准时区（UTC+8）
from task_service.infrastructure.persistence._task_converters import _UTC_PLUS_8


class TaskCrudMixin:
    """任务创建 / 合并 / 编辑（供 TaskRepository 组合）"""

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
            task = self._build_new_task(
                name=name, description=description, task_type=task_type,
                config=config, algorithm_type=algorithm_type,
                algorithm_params=algorithm_params,
                total_cases=len(case_ids), created_by=created_by, now=now,
            )
            session.add(task)
            session.flush()  # 获取自增 ID
            task_id = task.id

            self._add_task_relations(session, task_id, case_ids, device_ids, api_ids, now)

            session.commit()
            return task_id
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    @staticmethod
    def _build_new_task(name: str, description: str, task_type: str,
                        config: Optional[Dict[str, Any]],
                        algorithm_type: Optional[str],
                        algorithm_params: Optional[Dict[str, Any]],
                        total_cases: int, created_by: Optional[int],
                        now: datetime) -> Task:
        """构造新 Task PO（统一字段初始化，消除重复）。"""
        return Task(
            name=name,
            description=description,
            type=task_type,
            status=SharedTaskStatus.PENDING,
            config=config or None,
            algorithm_type=algorithm_type,
            algorithm_params=algorithm_params or None,
            total_cases=total_cases,
            completed_cases=0,
            failed_cases=0,
            created_by=created_by,
            created_at=now,
            updated_at=now,
        )

    @staticmethod
    def _add_task_relations(session, task_id: int, case_ids: List[str],
                            device_ids: List[int], api_ids: List[int],
                            now: datetime) -> None:
        """批量添加任务关联记录（用例/设备/API）。"""
        # 关联用例
        for case_id in case_ids:
            session.add(TaskCase(
                task_id=task_id,
                test_case_id=case_id,
                status=TaskCaseStatus.PENDING,
                execution_status=ExecutionStatus.PENDING,
                evaluation_status=EvaluationStatus.PENDING,
                created_at=now,
            ))

        # 关联设备
        for device_id in device_ids:
            session.add(TaskDevice(task_id=task_id, device_id=device_id))

        # 关联 API
        for api_id in api_ids:
            session.add(TaskAPI(task_id=task_id, api_id=api_id))

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
            total_results, source_counts = self._collect_source_counts(session, source_task_ids)

            merged_task = self._build_new_task(
                name=merged_task_name, description=description, task_type=merged_task_type,
                config=None, algorithm_type=None, algorithm_params=None,
                total_cases=total_results, created_by=created_by, now=now,
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

    @staticmethod
    def _collect_source_counts(session, source_task_ids: List[int]) -> Tuple[int, List[Tuple[int, int]]]:
        """统计源任务的完成用例数，返回 (total_results, [(src_id, count), ...])。"""
        total_results = 0
        source_counts: List[Tuple[int, int]] = []
        for src_id in source_task_ids:
            src_task = session.get(Task, src_id)
            count = (src_task.completed_cases or 0) if src_task else 0
            source_counts.append((src_id, count))
            total_results += count
        return total_results, source_counts

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

            err = self._apply_case_action(session, task_id, action, case_ids, now)
            if err:
                return err

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

    @staticmethod
    def _apply_case_action(session, task_id: int, action: str,
                           case_ids: List[str], now: datetime) -> Optional[Dict[str, Any]]:
        """执行用例动态增/删动作。返回错误 dict 或 None。"""
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
        return None

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
