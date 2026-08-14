# -*- coding: utf-8 -*-
"""命令处理器 (Command Handlers) - CQRS 写模型处理器。

重要原则：委托给已有的 ExecutionEngine / ReevaluationExecutor，不重写执行逻辑。
每个 handler 方法对应一个命令，返回 (success, message, data) 三元组。
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Tuple

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
    CreateTaskConfigCommand,
    UpdateTaskCommand,
    DeleteTaskCommand,
    UpdateTaskCasesCommand,
    BatchActionTaskCommand,
    MergeTasksConfigCommand,
    StartTaskLifecycleCommand,
    RetryTaskCommand,
    ControlTaskCommand,
    StopTaskLifecycleCommand,
    RextractTaskCommand,
    CreateTestCaseCommand,
    UpdateTestCaseCommand,
    DeleteTestCaseCommand,
    CopyTestCaseCommand,
    BatchActionTestCaseCommand,
    UpdateTestCaseRefParamsCommand,
    CreateTagCategoryCommand,
    UpdateTagCategoryCommand,
    DeleteTagCategoryCommand,
    CreateTagCommand,
    UpdateTagCommand,
    DeleteTagCommand,
    BatchUpdateTagCategoryCommand,
)
from task_service.domain.entities import TaskStatus
from task_service.domain.events import TaskCreated
from task_service.infrastructure.persistence.task_repository import task_repository

# 东八区时区
_UTC_PLUS_8 = timezone(timedelta(hours=8))


class TaskCommandHandler:
    """任务命令处理器。

    所有写操作通过此类入口，内部委托给 ExecutionEngine 单例。
    保持 handler 无状态（ExecutionEngine 自身是单例）。
    """

    def __init__(self):
        self._engine = None
        self._task_repository = task_repository
        self._task_crud_service = None
        self._task_lifecycle_service = None
        self._testcase_crud_service = None
        self._tag_crud_service = None

    @property
    def task_repository(self):
        """注入的任务仓储（TaskRepository 单例）。"""
        return self._task_repository

    @property
    def engine(self):
        """延迟加载 ExecutionEngine 单例，避免循环导入。"""
        if self._engine is None:
            from task_service.core.execution_engine import execution_engine
            self._engine = execution_engine
        return self._engine

    @property
    def task_crud_service(self):
        """延迟加载 task_crud_service 旧服务（过渡期兼容层）。"""
        if self._task_crud_service is None:
            from task_service.application.task.task_crud_service import task_crud_service
            self._task_crud_service = task_crud_service
        return self._task_crud_service

    @property
    def task_lifecycle_service(self):
        """延迟加载 task_lifecycle_service 旧服务（过渡期兼容层）。"""
        if self._task_lifecycle_service is None:
            from task_service.application.task.task_lifecycle_service import task_lifecycle_service
            self._task_lifecycle_service = task_lifecycle_service
        return self._task_lifecycle_service

    @property
    def testcase_crud_service(self):
        """延迟加载 testcase_crud_service 旧服务（过渡期兼容层）。"""
        if self._testcase_crud_service is None:
            from task_service.application.testcase.testcase_crud_service import testcase_crud_service
            self._testcase_crud_service = testcase_crud_service
        return self._testcase_crud_service

    @property
    def tag_crud_service(self):
        """延迟加载 tag_crud_service 旧服务（过渡期兼容层）。"""
        if self._tag_crud_service is None:
            from task_service.application.testcase.tag_crud_service import tag_crud_service
            self._tag_crud_service = tag_crud_service
        return self._tag_crud_service

    # ---- 命令处理 ----

    def handle_create_task(self, cmd: CreateTaskCommand) -> Tuple[bool, str, Dict]:
        """处理创建任务命令。

        通过 task_repository 创建 Task 记录及关联关系，返回新任务 ID。
        注意：仅创建记录，不启动执行，启动需调用 StartTaskCommand。
        """
        try:
            now = datetime.now(_UTC_PLUS_8)
            task_id = self.task_repository.create_task_with_relations(
                name=cmd.name,
                task_type=cmd.task_type,
                description=cmd.description,
                config=cmd.config or None,
                algorithm_type=cmd.algorithm_type,
                algorithm_params=cmd.algorithm_params or None,
                case_ids=cmd.case_ids,
                device_ids=cmd.device_ids,
                api_ids=cmd.api_ids,
                created_by=cmd.created_by,
                now=now,
            )

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
            return False, f'创建任务失败: {e}', {}

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
        """处理重新评估任务命令。

        P1.7 改造：task_service 不再持有 ReevaluationExecutor（已迁移至
        evaluation_service.application.handlers.reevaluation_executor），
        改为通过 gRPC 调用 evaluation_service.EvaluationService.Reevaluate。
        """
        try:
            from task_service.infrastructure.acl.evaluation_acl_repository import evaluation_acl_repository
            result = evaluation_acl_repository.submit_reevaluate(
                task_id=cmd.task_id,
                reextract_device_output=cmd.reextract_device_output,
                reevaluate_type=cmd.reevaluate_type,
            )
            success = bool(result.get('success'))
            message = result.get('message', '')
            return success, message, {
                'task_id': cmd.task_id,
                'submitted': success,
                'message': message,
            }
        except Exception as e:
            return False, f'重新评估异常: {e}', {'task_id': cmd.task_id}

    def handle_merge_tasks(self, cmd: MergeTasksCommand) -> Tuple[bool, str, Dict]:
        """处理合并任务命令。

        通过 task_repository 创建一个新的合并任务，并建立源任务-合并任务的映射关系。
        合并后任务的用例列表和结果需由上层服务进一步处理。
        """
        if not cmd.source_task_ids:
            return False, '源任务列表不能为空', {}

        try:
            now = datetime.now(_UTC_PLUS_8)
            merged_task_id, total_results = self.task_repository.merge_tasks(
                source_task_ids=cmd.source_task_ids,
                merged_task_name=cmd.merged_task_name,
                merged_task_type=cmd.merged_task_type,
                description=cmd.description,
                created_by=cmd.created_by,
                now=now,
            )

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
            return False, f'合并任务失败: {e}', {}

    # ==================================================================
    # task 域 CRUD/批量/合并命令（gRPC servicer 入口）
    # 委托 task_crud_service 旧服务作为过渡，返回 dict: {success, message, data, code?}
    # ==================================================================

    def handle_create_task_config(self, cmd: CreateTaskConfigCommand) -> Dict:
        """处理创建任务配置命令（dict 参数版）。委托 task_crud_service.create。"""
        return self.task_crud_service.create(cmd.data)

    def handle_update_task(self, cmd: UpdateTaskCommand) -> Dict:
        """处理更新任务命令（名称/描述）。委托 task_crud_service.update。"""
        return self.task_crud_service.update(cmd.task_id, cmd.data)

    def handle_delete_task(self, cmd: DeleteTaskCommand) -> Dict:
        """处理软删除任务命令。委托 task_crud_service.delete。"""
        return self.task_crud_service.delete(cmd.task_id)

    def handle_update_task_cases(self, cmd: UpdateTaskCasesCommand) -> Dict:
        """处理动态添加/移除任务用例命令。委托 task_crud_service.update_cases。"""
        return self.task_crud_service.update_cases(cmd.task_id, cmd.data)

    def handle_batch_action_task(self, cmd: BatchActionTaskCommand) -> Dict:
        """处理任务批量操作命令（delete/export）。委托 task_crud_service.batch_action。"""
        return self.task_crud_service.batch_action(cmd.data, cmd.query_args)

    def handle_merge_tasks_config(self, cmd: MergeTasksConfigCommand) -> Dict:
        """处理合并任务命令（dict 参数版）。委托 task_crud_service.merge。"""
        return self.task_crud_service.merge(cmd.data)

    # ==================================================================
    # task 域生命周期命令（gRPC servicer 入口）
    # 委托 task_lifecycle_service 旧服务作为过渡，保留状态校验等完整逻辑
    # ==================================================================

    def handle_start_task_lifecycle(self, cmd: StartTaskLifecycleCommand) -> Dict:
        """处理启动任务生命周期命令。委托 task_lifecycle_service.start。"""
        return self.task_lifecycle_service.start(cmd.task_id)

    def handle_retry_task(self, cmd: RetryTaskCommand) -> Dict:
        """处理重试失败用例命令。委托 task_lifecycle_service.retry。"""
        return self.task_lifecycle_service.retry(cmd.task_id)

    def handle_control_task(self, cmd: ControlTaskCommand) -> Dict:
        """处理任务运行时控制命令。委托 task_lifecycle_service.control。"""
        return self.task_lifecycle_service.control(cmd.task_id, cmd.data)

    def handle_stop_task_lifecycle(self, cmd: StopTaskLifecycleCommand) -> Dict:
        """处理停止任务生命周期命令。委托 task_lifecycle_service.stop。"""
        return self.task_lifecycle_service.stop(cmd.task_id)

    def handle_reextract_task(self, cmd: RextractTaskCommand) -> Dict:
        """处理重新提取设备输出命令。委托 task_lifecycle_service.reextract。"""
        return self.task_lifecycle_service.rextract(cmd.task_id, cmd.data)

    # ==================================================================
    # testcase 域命令（gRPC servicer 入口）
    # 委托 testcase_crud_service 旧服务作为过渡
    # ==================================================================

    def handle_create_testcase(self, cmd: CreateTestCaseCommand) -> Dict:
        """处理创建测试用例命令。委托 testcase_crud_service.create。"""
        return self.testcase_crud_service.create(cmd.data)

    def handle_update_testcase(self, cmd: UpdateTestCaseCommand) -> Dict:
        """处理更新测试用例命令。委托 testcase_crud_service.update。"""
        return self.testcase_crud_service.update(cmd.tc_id, cmd.data)

    def handle_delete_testcase(self, cmd: DeleteTestCaseCommand) -> Dict:
        """处理软删除测试用例命令。委托 testcase_crud_service.delete。"""
        return self.testcase_crud_service.delete(cmd.tc_id)

    def handle_copy_testcase(self, cmd: CopyTestCaseCommand) -> Dict:
        """处理复制测试用例命令。委托 testcase_crud_service.copy。"""
        return self.testcase_crud_service.copy(cmd.tc_id)

    def handle_batch_action_testcase(self, cmd: BatchActionTestCaseCommand) -> Dict:
        """处理测试用例批量操作命令。委托 testcase_crud_service.batch_action。"""
        return self.testcase_crud_service.batch_action(cmd.data)

    def handle_update_testcase_ref_params(self, cmd: UpdateTestCaseRefParamsCommand) -> Dict:
        """处理更新用例参考参数命令。委托 testcase_crud_service.update_ref_params。"""
        return self.testcase_crud_service.update_ref_params(
            cmd.tc_id, cmd.round_number, cmd.data
        )

    # ==================================================================
    # tag 域命令（gRPC servicer 入口）
    # 委托 tag_crud_service 旧服务作为过渡
    # ==================================================================

    def handle_create_tag_category(self, cmd: CreateTagCategoryCommand) -> Dict:
        """处理创建标签分类命令。委托 tag_crud_service.create_category。"""
        return self.tag_crud_service.create_category(cmd.data)

    def handle_update_tag_category(self, cmd: UpdateTagCategoryCommand) -> Dict:
        """处理更新标签分类命令。委托 tag_crud_service.update_category。"""
        return self.tag_crud_service.update_category(cmd.category_id, cmd.data)

    def handle_delete_tag_category(self, cmd: DeleteTagCategoryCommand) -> Dict:
        """处理删除标签分类命令。委托 tag_crud_service.delete_category。"""
        return self.tag_crud_service.delete_category(cmd.category_id)

    def handle_create_tag(self, cmd: CreateTagCommand) -> Dict:
        """处理创建标签命令。委托 tag_crud_service.create_tag。"""
        return self.tag_crud_service.create_tag(cmd.data)

    def handle_update_tag(self, cmd: UpdateTagCommand) -> Dict:
        """处理更新标签命令。委托 tag_crud_service.update_tag。"""
        return self.tag_crud_service.update_tag(cmd.tag_id, cmd.data)

    def handle_delete_tag(self, cmd: DeleteTagCommand) -> Dict:
        """处理删除标签命令。委托 tag_crud_service.delete_tag。"""
        return self.tag_crud_service.delete_tag(cmd.tag_id)

    def handle_batch_update_tag_category(self, cmd: BatchUpdateTagCategoryCommand) -> Dict:
        """处理批量更新标签分类命令。委托 tag_crud_service.batch_update_category。"""
        return self.tag_crud_service.batch_update_category(cmd.data)


# 模块级单例
task_command_handler = TaskCommandHandler()
