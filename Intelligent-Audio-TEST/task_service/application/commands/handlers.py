# -*- coding: utf-8 -*-
"""命令处理器 (Command Handlers) - CQRS 写模型处理器。

重要原则：委托给已有的 ExecutionEngine / ReevaluationExecutor，不重写执行逻辑。
每个 handler 方法对应一个命令，返回 (success, message, data) 三元组。
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Tuple

from shared.models.database import db
from shared.models.models import (Task, TaskCase, TaskAPI, TaskDevice,
                                  TaskMergeRelation)
from shared.utils.log_handler import log_and_emit

from task_service.application.commands.task_commands import (
    CreateTaskCommand,
    StartTaskCommand,
    StopTaskCommand,
    PauseTaskCommand,
    ResumeTaskCommand,
    RemoveFromQueueCommand,
    ReevaluateTaskCommand,
    MergeTasksCommand,
)
from task_service.domain.entities import TaskStatus
from task_service.domain.events import TaskCreated

# 东八区时区
_UTC_PLUS_8 = timezone(timedelta(hours=8))


class TaskCommandHandler:
    """任务命令处理器。

    所有写操作通过此类入口，内部委托给 ExecutionEngine 单例。
    保持 handler 无状态（ExecutionEngine 自身是单例）。
    """

    def __init__(self):
        self._engine = None

    @property
    def engine(self):
        """延迟加载 ExecutionEngine 单例，避免循环导入。"""
        if self._engine is None:
            from task_service.core.execution_engine import execution_engine
            self._engine = execution_engine
        return self._engine

    # ---- 命令处理 ----

    def handle_create_task(self, cmd: CreateTaskCommand) -> Tuple[bool, str, Dict]:
        """处理创建任务命令。

        在 DB 中创建 Task 记录及关联关系，返回新任务 ID。
        注意：仅创建记录，不启动执行，启动需调用 StartTaskCommand。
        """
        session = db.session()
        try:
            now = datetime.now(_UTC_PLUS_8)
            task = Task(
                name=cmd.name,
                description=cmd.description,
                type=cmd.task_type,
                status=TaskStatus.PENDING.value,
                config=cmd.config or None,
                algorithm_type=cmd.algorithm_type,
                algorithm_params=cmd.algorithm_params or None,
                total_cases=len(cmd.case_ids),
                completed_cases=0,
                failed_cases=0,
                created_by=cmd.created_by,
                created_at=now,
                updated_at=now,
            )
            session.add(task)
            session.flush()  # 获取自增 ID

            task_id = task.id

            # 关联用例
            for case_id in cmd.case_ids:
                tc = TaskCase(
                    task_id=task_id,
                    test_case_id=case_id,
                    status='pending',
                    execution_status='pending',
                    evaluation_status='pending',
                    created_at=now,
                )
                session.add(tc)

            # 关联设备
            for device_id in cmd.device_ids:
                session.add(TaskDevice(task_id=task_id, device_id=device_id))

            # 关联 API
            for api_id in cmd.api_ids:
                session.add(TaskAPI(task_id=task_id, api_id=api_id))

            session.commit()

            # 发布领域事件
            event = TaskCreated(
                task_id=task_id,
                task_name=cmd.name,
                task_type=cmd.task_type,
                total_cases=len(cmd.case_ids),
                created_by=cmd.created_by,
            )
            log_and_emit(
                level='INFO',
                module='TaskCommandHandler',
                content=f"任务创建成功: {cmd.name} (id={task_id})",
                category='execution',
                task_id=task_id,
            )

            return True, 'ok', {
                'task_id': task_id,
                'name': cmd.name,
                'status': TaskStatus.PENDING.value,
                'total_cases': len(cmd.case_ids),
            }
        except Exception as e:
            session.rollback()
            return False, f'创建任务失败: {e}', {}
        finally:
            session.close()

    def handle_start_task(self, cmd: StartTaskCommand) -> Tuple[bool, str, Dict]:
        """处理启动任务命令。委托给 ExecutionEngine.start_task。"""
        try:
            success, message = self.engine.start_task(cmd.task_id)
            self.engine.trigger_scheduler_check()
            return success, message, {
                'task_id': cmd.task_id,
                'started': success,
                'message': message,
            }
        except Exception as e:
            return False, f'启动任务异常: {e}', {'task_id': cmd.task_id}

    def handle_stop_task(self, cmd: StopTaskCommand) -> Tuple[bool, str, Dict]:
        """处理停止任务命令。委托给 ExecutionEngine.control_task。"""
        try:
            success, message = self.engine.control_task(cmd.task_id, 'stop')
            return success, message, {
                'task_id': cmd.task_id,
                'stopped': success,
                'message': message,
            }
        except Exception as e:
            return False, f'停止任务异常: {e}', {'task_id': cmd.task_id}

    def handle_pause_task(self, cmd: PauseTaskCommand) -> Tuple[bool, str, Dict]:
        """处理暂停任务命令。"""
        try:
            success, message = self.engine.control_task(cmd.task_id, 'pause')
            return success, message, {
                'task_id': cmd.task_id,
                'paused': success,
                'message': message,
            }
        except Exception as e:
            return False, f'暂停任务异常: {e}', {'task_id': cmd.task_id}

    def handle_resume_task(self, cmd: ResumeTaskCommand) -> Tuple[bool, str, Dict]:
        """处理恢复任务命令。"""
        try:
            success, message = self.engine.control_task(cmd.task_id, 'resume')
            return success, message, {
                'task_id': cmd.task_id,
                'resumed': success,
                'message': message,
            }
        except Exception as e:
            return False, f'恢复任务异常: {e}', {'task_id': cmd.task_id}

    def handle_remove_from_queue(self, cmd: RemoveFromQueueCommand) -> Tuple[bool, str, Dict]:
        """处理从队列移除任务命令。委托给 ExecutionEngine.remove_from_queue。"""
        try:
            removed = self.engine.remove_from_queue(cmd.task_id)
            message = '已从队列移除' if removed else '任务不在队列中'
            return True, message, {
                'task_id': cmd.task_id,
                'removed': removed,
            }
        except Exception as e:
            return False, f'移除队列异常: {e}', {'task_id': cmd.task_id}

    def handle_reevaluate_task(self, cmd: ReevaluateTaskCommand) -> Tuple[bool, str, Dict]:
        """处理重新评估任务命令。委托给 ReevaluationExecutor。"""
        try:
            from task_service.core.reevaluation_executor import ReevaluationExecutor
            executor = ReevaluationExecutor.get_instance()
            success, message = executor.submit(
                cmd.task_id,
                reextract_device_output=cmd.reextract_device_output,
                reevaluate_type=cmd.reevaluate_type,
            )
            return success, message, {
                'task_id': cmd.task_id,
                'submitted': success,
                'message': message,
            }
        except Exception as e:
            return False, f'重新评估异常: {e}', {'task_id': cmd.task_id}

    def handle_merge_tasks(self, cmd: MergeTasksCommand) -> Tuple[bool, str, Dict]:
        """处理合并任务命令。

        创建一个新的合并任务，并建立源任务-合并任务的映射关系。
        合并后任务的用例列表和结果需由上层服务进一步处理。
        """
        if not cmd.source_task_ids:
            return False, '源任务列表不能为空', {}

        session = db.session()
        try:
            now = datetime.now(_UTC_PLUS_8)

            # 统计源任务结果数量
            total_results = 0
            for src_id in cmd.source_task_ids:
                src_task = session.get(Task, src_id)
                if src_task:
                    total_results += (src_task.completed_cases or 0)

            merged_task = Task(
                name=cmd.merged_task_name,
                description=cmd.description,
                type=cmd.merged_task_type,
                status=TaskStatus.PENDING.value,
                total_cases=total_results,
                completed_cases=0,
                failed_cases=0,
                created_by=cmd.created_by,
                created_at=now,
                updated_at=now,
            )
            session.add(merged_task)
            session.flush()
            merged_task_id = merged_task.id

            # 建立合并关系
            for src_id in cmd.source_task_ids:
                src_task = session.get(Task, src_id)
                count = (src_task.completed_cases or 0) if src_task else 0
                session.add(TaskMergeRelation(
                    merged_task_id=merged_task_id,
                    source_task_id=src_id,
                    source_result_count=count,
                    created_at=now,
                ))

            session.commit()

            log_and_emit(
                level='INFO',
                module='TaskCommandHandler',
                content=(f"任务合并创建成功: {cmd.merged_task_name} "
                         f"(id={merged_task_id}, sources={cmd.source_task_ids})"),
                category='execution',
                task_id=merged_task_id,
            )

            return True, 'ok', {
                'merged_task_id': merged_task_id,
                'source_task_ids': cmd.source_task_ids,
                'total_results': total_results,
            }
        except Exception as e:
            session.rollback()
            return False, f'合并任务失败: {e}', {}
        finally:
            session.close()


# 模块级单例
task_command_handler = TaskCommandHandler()
