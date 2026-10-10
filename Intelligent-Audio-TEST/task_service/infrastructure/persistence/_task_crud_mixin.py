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
from task_service.infrastructure.persistence.models import Task, TaskCase, TaskAPI, TaskDevice, TaskTag

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
        case_devices: Optional[List[Dict[str, Any]]] = None,
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
            case_devices: 用例级设备选择（执行域 P0 新增）：
                [{"case_id": str, "device_type": str, "device_id": str, "lab_id": int|None}, ...]，
                为空时保持旧语义（按 task_type 路由）。

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

            self._add_task_relations(session, task_id, case_ids, device_ids, api_ids, now, case_devices)

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
                            now: datetime,
                            case_devices: Optional[List[Dict[str, Any]]] = None) -> None:
        """批量添加任务关联记录（用例/设备/API）。

        Args:
            case_devices: 用例级设备选择（执行域 P0 新增）：
                [{"case_id": str, "device_type": str, "device_id": str, "lab_id": int|None}, ...]，
                按 case_id 归一化后写入 TaskCase.device_type / device_id / lab_id。
        """
        # 归一化用例级设备选择: {case_id: {device_type, device_id, lab_id}}
        device_map: Dict[str, Dict[str, Any]] = {}
        for item in case_devices or []:
            case_id = item.get('case_id')
            if case_id is not None:
                device_map[str(case_id)] = item

        # 关联用例
        for case_id in case_ids:
            dev = device_map.get(str(case_id), {})
            session.add(TaskCase(
                task_id=task_id,
                test_case_id=case_id,
                status=TaskCaseStatus.PENDING,
                execution_status=ExecutionStatus.PENDING,
                evaluation_status=EvaluationStatus.PENDING,
                device_type=dev.get('device_type') or None,
                device_id=str(dev['device_id']) if dev.get('device_id') is not None else None,
                lab_id=dev.get('lab_id') or None,
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

        说明（迁移自 V9.7.10 task_controller.merge 增强）:
        - 允许合并已完成/合并任务/已合并任务（后两者会展开为原始源任务，
          使"合并任务再次被合并"时不会丢失其历史源任务）
        - 用例集合以源任务 TaskCase 为准（TestResult 可能包含已删除用例的执行记录，
          否则会导致合并任务 TaskCase 数量与 total_cases 不一致）
        - 新建 TaskCase 继承源任务的执行/评估状态，避免合并任务详情中所有用例显示为待执行
        - 设备/API/标签从源任务关联表继承
        """
        from task_service.infrastructure.persistence.models import (
            TaskMergeRelation, TaskCase, TaskDevice, TaskAPI, TaskTag,
        )
        if now is None:
            now = datetime.now(_UTC_PLUS_8)

        session = get_db_session()
        try:
            tasks = session.query(Task).filter(Task.id.in_(list(source_task_ids))).all()
            if len(tasks) != len(source_task_ids):
                raise ValueError("部分任务未找到")

            for t in tasks:
                # 允许合并已完成任务、合并任务、已合并任务（后两者在下方展开为原始源任务）
                if t.status not in (SharedTaskStatus.COMPLETED, SharedTaskStatus.MERGED):
                    raise ValueError(f"任务 '{t.name}' 未完成，无法合并")

            # 展开合并任务/已合并任务：找到合并之前的原始源任务
            final_source_ids = set()
            remerged_task_ids = set()
            for t in tasks:
                if t.type == 'merged':
                    relations = session.query(TaskMergeRelation).filter_by(merged_task_id=t.id).all()
                    if relations:
                        final_source_ids.update(r.source_task_id for r in relations)
                        remerged_task_ids.add(t.id)
                        continue
                    final_source_ids.add(t.id)
                elif t.status == SharedTaskStatus.MERGED:
                    relations = (session.query(TaskMergeRelation)
                                 .filter_by(source_task_id=t.id)
                                 .order_by(TaskMergeRelation.id.desc()).all())
                    if relations:
                        latest_merged_id = relations[0].merged_task_id
                        source_relations = (session.query(TaskMergeRelation)
                                            .filter_by(merged_task_id=latest_merged_id).all())
                        if source_relations:
                            final_source_ids.update(r.source_task_id for r in source_relations)
                            remerged_task_ids.add(latest_merged_id)
                            continue
                    final_source_ids.add(t.id)
                else:
                    final_source_ids.add(t.id)

            if not final_source_ids:
                raise ValueError("合并后没有可用的源任务")

            source_tasks = session.query(Task).filter(Task.id.in_(list(final_source_ids))).all()
            source_task_map = {st.id: st for st in source_tasks}
            ordered_source_ids = [sid for sid in final_source_ids if sid in source_task_map]

            # 源任务贡献结果数、设备/API/用例/标签集合
            source_result_counts = {}
            device_ids_set = set()
            api_ids_set = set()
            case_ids_set = set()
            tag_ids_set = set()

            for task in source_tasks:
                source_result_counts[task.id] = task.completed_cases or 0
                for td in session.query(TaskDevice).filter_by(task_id=task.id).all():
                    device_ids_set.add(td.device_id)
                for ta in session.query(TaskAPI).filter_by(task_id=task.id).all():
                    api_ids_set.add(ta.api_id)
                for tc in session.query(TaskCase).filter_by(task_id=task.id).all():
                    case_ids_set.add(tc.test_case_id)
                for tag in task.tags:
                    tag_ids_set.add(tag.id)

            # total_cases 与合并任务的 TaskCase 集合保持一致（源任务用例重叠时 SUM 会重复计数）
            total_cases = len(case_ids_set)

            merged_task = self._build_new_task(
                name=merged_task_name, description=description, task_type='merged',
                config=None, algorithm_type=None, algorithm_params=None,
                total_cases=total_cases, created_by=created_by, now=now,
            )
            merged_task.status = SharedTaskStatus.COMPLETED
            merged_task.completed_cases = 0
            merged_task.failed_cases = 0
            started_list = [t.started_at for t in source_tasks if t.started_at]
            completed_list = [t.completed_at for t in source_tasks if t.completed_at]
            if started_list:
                merged_task.started_at = min(started_list)
            if completed_list:
                merged_task.completed_at = max(completed_list)
            session.add(merged_task)
            session.flush()
            merged_task_id = merged_task.id

            # 关联设备
            for device_id in device_ids_set:
                existing = session.query(TaskDevice).filter_by(
                    task_id=merged_task_id, device_id=device_id).first()
                if not existing:
                    session.add(TaskDevice(task_id=merged_task_id, device_id=device_id))

            # 关联 API
            for api_id in api_ids_set:
                existing = session.query(TaskAPI).filter_by(
                    task_id=merged_task_id, api_id=api_id).first()
                if not existing:
                    session.add(TaskAPI(task_id=merged_task_id, api_id=api_id))

            # 源任务用例状态映射，供合并任务新建 TaskCase 时继承
            source_case_status = {}
            for task in tasks:
                for tc in session.query(TaskCase).filter_by(task_id=task.id).all():
                    if tc.test_case_id not in source_case_status:
                        source_case_status[tc.test_case_id] = tc

            for case_id in case_ids_set:
                existing = session.query(TaskCase).filter_by(
                    task_id=merged_task_id, test_case_id=case_id).first()
                if not existing:
                    src_tc = source_case_status.get(case_id)
                    # 继承源任务的执行/评估状态，避免合并任务详情中所有用例都显示为待执行
                    session.add(TaskCase(
                        task_id=merged_task_id,
                        test_case_id=case_id,
                        status=(src_tc.status if src_tc else TaskCaseStatus.COMPLETED),
                        execution_status=(src_tc.execution_status if src_tc else ExecutionStatus.COMPLETED),
                        evaluation_status=(src_tc.evaluation_status if src_tc else EvaluationStatus.COMPLETED),
                        started_at=getattr(src_tc, 'started_at', None) if src_tc else None,
                        completed_at=getattr(src_tc, 'completed_at', None) if src_tc else None,
                        duration=getattr(src_tc, 'duration', None) if src_tc else None,
                        error_message=getattr(src_tc, 'error_message', None) if src_tc else None,
                        created_at=now,
                    ))

            # 关联标签
            for tag_id in tag_ids_set:
                existing = session.query(TaskTag).filter_by(
                    task_id=merged_task_id, tag_id=tag_id).first()
                if not existing:
                    session.add(TaskTag(task_id=merged_task_id, tag_id=tag_id))

            # 被再次合并的合并任务标记为已合并（其历史源任务由新合并任务接管）
            for mid in remerged_task_ids:
                m_task = session.get(Task, mid)
                if m_task:
                    m_task.status = SharedTaskStatus.MERGED

            # 原始源任务标记为已合并（已是 merged 的保持不动）
            for sid in ordered_source_ids:
                s_task = source_task_map[sid]
                if s_task.status != SharedTaskStatus.MERGED:
                    s_task.status = SharedTaskStatus.MERGED

            # 新合并任务直接关联展开后的原始源任务
            for sid in ordered_source_ids:
                session.add(TaskMergeRelation(
                    merged_task_id=merged_task_id,
                    source_task_id=sid,
                    source_result_count=source_result_counts.get(sid, 0),
                    created_at=now,
                ))

            # 以合并任务自身 TaskCase 统计完成/失败数，保证与总用例数自洽
            session.flush()
            merged_task.total_cases = session.query(TaskCase).filter_by(task_id=merged_task_id).count()
            merged_task.completed_cases = session.query(TaskCase).filter_by(
                task_id=merged_task_id, status=TaskCaseStatus.COMPLETED).count()
            merged_task.failed_cases = session.query(TaskCase).filter_by(
                task_id=merged_task_id, status=TaskCaseStatus.FAILED).count()

            session.commit()
            return merged_task_id, merged_task.total_cases
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

    def batch_restore(self, task_ids: List[int]) -> int:
        """批量恢复软删除任务（仅已删除行会恢复）。

        TaskCase 关联行在软删除期间未被清理（60 天硬清理按任务整体过期），
        恢复任务行即恢复其用例关联，无需二次处理。

        Returns:
            实际恢复的条数（已删除行数；未删除/不存在的 ID 不计入）
        """
        if not task_ids:
            return 0
        session = get_db_session()
        try:
            count = session.query(Task).filter(
                Task.id.in_(task_ids),
                Task.deleted == True,  # noqa: E712
            ).update(
                {Task.deleted: False, Task.deleted_at: None},
                synchronize_session=False,
            )
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
