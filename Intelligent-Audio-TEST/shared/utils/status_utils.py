# -*- coding: utf-8 -*-
"""TaskCase 状态推导工具

status 字段由 execution_status + evaluation_status 推导，不手动赋值。
所有服务统一使用此函数，确保 status 始终一致。

INT-301：新增任务级双状态推导（derive_task_dual_status）——执行状态与
评估状态完全分离，评估推进（含重新评估）只落评估侧，执行侧不变。
"""
from shared.utils.status_constants import (
    ExecutionStatus,
    EvaluationStatus,
    TaskCaseStatus,
    TaskStatus,
)


def derive_task_case_status(execution_status: str, evaluation_status: str) -> str:
    """根据 execution_status 和 evaluation_status 推导 status。

    推导规则：
    - execution_status=failed/stopped → failed
    - execution_status=skipped → skipped（INT-340 人工复核改判；原执行流程不产出）
    - execution_status=completed AND evaluation_status=completed → completed
    - execution_status=completed AND evaluation_status=failed/stopped → failed
    - execution_status=completed AND evaluation_status IN (queued/running/calculating/pending) → evaluating
    - execution_status IN (queued/running) → running
    - 其余 → pending
    """
    if execution_status in (ExecutionStatus.FAILED, ExecutionStatus.STOPPED):
        return TaskCaseStatus.FAILED
    if execution_status == ExecutionStatus.SKIPPED:
        return TaskCaseStatus.SKIPPED
    if execution_status == ExecutionStatus.COMPLETED:
        if evaluation_status == EvaluationStatus.COMPLETED:
            return TaskCaseStatus.COMPLETED
        if evaluation_status in (EvaluationStatus.FAILED, EvaluationStatus.STOPPED):
            return TaskCaseStatus.FAILED
        return TaskCaseStatus.EVALUATING
    if execution_status in (ExecutionStatus.QUEUED, ExecutionStatus.RUNNING):
        return TaskCaseStatus.RUNNING
    return TaskCaseStatus.PENDING


def derive_task_dual_status(task_status: str, *,
                            has_exec_active: bool,
                            has_exec_failed: bool,
                            has_exec_stopped: bool,
                            exec_all_terminal: bool,
                            has_eval_in_progress: bool,
                            has_eval_failed: bool,
                            has_eval_completed: bool) -> tuple:
    """任务级执行/评估双状态推导（INT-301，与 task_read_model SQL 条件严格同构）。

    输入为 TaskCase 聚合布尔量 + Task.status：
    - has_exec_*：用例级 execution_status 聚合（queued/running、failed、stopped、
      全部到执行终态且有用例）
    - has_eval_in_progress：evaluation_status IN 评估进行中集合
      （queued/running/calculating；pending=评估未提交不计入）
    - has_eval_failed：执行未失败的用例中存在 evaluation_status=failed
    - has_eval_completed：存在 evaluation_status=completed

    返回 (execution_status, evaluation_status)：
    - 执行侧：paused > running（有活跃执行） > failed > stopped > queued
      > completed（全部用例执行终态） > pending；评估过渡态（evaluating/
      reevaluate_queued/reevaluating）不落入执行侧——评估推进不改执行徽章。
    - 评估侧优先级：evaluating（评估过渡态或存在进行中评估） > failed
      （执行未失败而评估失败） > skipped（手动停止中断评估） > completed
      （存在评估完成用例，不要求任务已收敛——评估完成即评估完成） >
      pending（尚未进入评估）。
    """
    # ---- 执行侧（纯执行域）----
    if task_status == TaskStatus.PAUSED:
        execution = TaskStatus.PAUSED
    elif has_exec_active:
        execution = ExecutionStatus.RUNNING
    elif has_exec_failed:
        execution = ExecutionStatus.FAILED
    elif has_exec_stopped:
        execution = ExecutionStatus.STOPPED
    elif task_status == TaskStatus.QUEUED:
        execution = TaskStatus.QUEUED
    elif exec_all_terminal:
        execution = ExecutionStatus.COMPLETED
    else:
        execution = ExecutionStatus.PENDING

    # ---- 评估侧（评估域 + 重新评估过渡）----
    if task_status in (TaskStatus.EVALUATING, TaskStatus.REEVALUATE_QUEUED, TaskStatus.REEVALUATING) \
            or has_eval_in_progress:
        evaluation = 'evaluating'
    elif has_eval_failed:
        evaluation = EvaluationStatus.FAILED
    elif task_status == TaskStatus.STOPPED:
        # 停止中断评估（即使部分评估已完成，整体评估被截断）
        evaluation = 'skipped'
    elif has_eval_completed:
        evaluation = EvaluationStatus.COMPLETED
    else:
        evaluation = EvaluationStatus.PENDING

    return execution, evaluation


# ---- INT-305：用例移除留痕 ----

REMOVED_CASE_MESSAGE = '用例已被移除'


def task_case_not_removed(TaskCase):
    """构造"未移除"过滤条件（NULL 安全：NULL != 'x' 在 SQL 中为 NULL 而非 True）。

    用法（传入 TaskCase PO 类，避免跨服务 import task_service）：
        session.query(TaskCase).filter(
            TaskCase.task_id == task_id,
            task_case_not_removed(TaskCase),
        )
    """
    from sqlalchemy import or_
    return or_(
        TaskCase.error_message.is_(None),
        TaskCase.error_message != REMOVED_CASE_MESSAGE,
    )
