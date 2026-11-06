# -*- coding: utf-8 -*-
"""任务级执行/评估双状态 SQL 派生表达式（INT-301）。

test_tasks 表无独立评估状态列（引擎以 Task.status 过渡态 evaluating/
reevaluate_queued/reevaluating 表达评估侧），本模块用例级 TaskCase 聚合
在 SQL 层派生 (execution_status, evaluation_status) 双状态：

- 选择列：search_tasks / find_by_id_with_relations 直接 SELECT 派生表达式，
  列表/详情行免二次计算即携带双状态；
- 过滤：evaluation_status 筛选条件复用同一 CASE 表达式（== 值包裹），
  保证「徽章展示」与「筛选命中」口径严格一致。

与 shared.utils.status_utils.derive_task_dual_status 逻辑严格同构
（优先级序一致），两侧由单元测试互锁（tests/unit/test_int301_task_dual_status.py）。

评估侧优先级：evaluating（评估过渡态或存在进行中评估） > failed（执行
未失败而评估失败） > skipped（手动停止中断评估 / 执行失败评估未发生——
失败路径补写的 completed 只是收敛占位） > completed（存在评估完成用例） > pending。
执行侧：paused > running > failed > stopped > queued > completed > pending；
评估过渡态不落入执行侧。

INT-2232：移除留痕行（`error_message = '用例已被移除'`，INT-305）不参与任何
聚合——`_tc_exists` 统一并入未移除条件。否则移除失败用例后，`HAS_EXEC_FAILED`
仍为真（徽章/筛选仍判 failed），移除的 pending 行也会让 `EXEC_ALL_TERMINAL`
永远为假（与 task_case_stats 的计数口径矛盾）。用例被全部移除时（INT-305
允许删到为空）没有任何用例级聚合可依据，改按任务终态派生（`EMPTY_TERMINAL_TASK`），
避免徽章从 completed 退化为 pending。
"""
from sqlalchemy import and_, case, exists, or_, select

from task_service.infrastructure.persistence.models import Task, TaskCase
from shared.utils.status_constants import (
    ExecutionStatus, EvaluationStatus, TaskStatus, ACTIVE_EXECUTION_STATUSES,
)
from shared.utils.status_utils import task_case_not_removed

# 用例级执行终态集合（failed/stopped 之外的执行终态为 completed）
_EXEC_TERMINAL = ('completed', 'failed', 'stopped')
# 重新评估过渡态（Task.status 值；评估侧一律呈现为 evaluating）
_EVAL_TRANSITION_STATUSES = (
    'evaluating', 'reevaluate_queued', 'reevaluating',
)
# 评估进行中集合（queued/running/calculating；pending=评估未提交不计入）
_EVAL_IN_PROGRESS = (EvaluationStatus.QUEUED, EvaluationStatus.RUNNING, EvaluationStatus.CALCULATING)
# INT-2232：移除留痕行不参与双状态聚合（NULL 安全条件，模块级构造按不可变表达式复用）
_NOT_REMOVED = task_case_not_removed(TaskCase)
# 任务终态集合（空任务派生兜底：用例被全部移除时沿用任务终态）。
# 不含 skipped：执行状态筛选合法值里没有 skipped（人工复核停留在用例级），
# 避免徽章产出筛选选项集外的值。
_TERMINAL_TASK_STATUSES = (
    TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.STOPPED,
)


def _tc_exists(*criteria):
    """按 task_id 关联的 TaskCase EXISTS 子查询（移除留痕行一律剔除）。"""
    return exists(
        select(TaskCase.id)
        .where(TaskCase.task_id == Task.id, _NOT_REMOVED, *criteria)
        .correlate(Task)
    )


# ---- 用例级聚合布尔量（命名导出，供过滤分支与派生表达式共用） ----

HAS_EXEC_ACTIVE = _tc_exists(TaskCase.execution_status.in_(ACTIVE_EXECUTION_STATUSES))
HAS_EXEC_FAILED = _tc_exists(TaskCase.execution_status == ExecutionStatus.FAILED)
HAS_EXEC_STOPPED = _tc_exists(TaskCase.execution_status == ExecutionStatus.STOPPED)
# 全部用例执行到终态且任务确有用例（存在未终态用例为假 + 存在 pending 用例为假
# ——不用裸列 EXISTS（PG 要求 boolean），以「不存在未终态用例 AND 存在任一终态
# 用例」组合判定）
EXEC_ALL_TERMINAL = and_(
    _tc_exists(TaskCase.execution_status.in_(_EXEC_TERMINAL)),
    ~_tc_exists(~TaskCase.execution_status.in_(_EXEC_TERMINAL)),
)
HAS_EVAL_IN_PROGRESS = _tc_exists(TaskCase.evaluation_status.in_(_EVAL_IN_PROGRESS))
HAS_EVAL_FAILED = _tc_exists(and_(
    TaskCase.evaluation_status == EvaluationStatus.FAILED,
    TaskCase.execution_status.notin_(('failed', 'stopped')),
))
HAS_EVAL_COMPLETED = _tc_exists(TaskCase.evaluation_status == EvaluationStatus.COMPLETED)

# INT-2232：空任务（用例被全部移除，INT-305 允许删到为空）没有任何
# 用例级聚合可依据——EXEC_ALL_TERMINAL 要求「存在未移除的终态行」恒为假，
# 徽章会从 completed 退化为 pending，与任务行的终态 status 自相矛盾。
EMPTY_TASK = ~_tc_exists()
EMPTY_TERMINAL_TASK = and_(EMPTY_TASK, Task.status.in_(_TERMINAL_TASK_STATUSES))

# ---- 派生 CASE 表达式（与 derive_task_dual_status 同构） ----

EXECUTION_STATUS_EXPR = case(
    (Task.status == 'paused', 'paused'),
    (HAS_EXEC_ACTIVE, ExecutionStatus.RUNNING),
    (HAS_EXEC_FAILED, ExecutionStatus.FAILED),
    (HAS_EXEC_STOPPED, ExecutionStatus.STOPPED),
    (Task.status == 'queued', 'queued'),
    (EXEC_ALL_TERMINAL, ExecutionStatus.COMPLETED),
    # 空任务沿用任务终态（completed 的移除不会产生 failed；stopped/skipped
    # 是手动停止/跳过语义，原样透出）
    (EMPTY_TERMINAL_TASK, Task.status),
    else_=ExecutionStatus.PENDING,
).label('execution_status')

EVALUATION_STATUS_EXPR = case(
    (or_(Task.status.in_(_EVAL_TRANSITION_STATUSES), HAS_EVAL_IN_PROGRESS), 'evaluating'),
    (HAS_EVAL_FAILED, EvaluationStatus.FAILED),
    (Task.status == 'stopped', EvaluationStatus.SKIPPED),
    (HAS_EXEC_FAILED, EvaluationStatus.SKIPPED),
    (HAS_EVAL_COMPLETED, EvaluationStatus.COMPLETED),
    # 空任务沿用任务终态：任务已完成 → 评估完成；失败/跳过 → 评估未实际发生
    (and_(EMPTY_TERMINAL_TASK, Task.status == TaskStatus.COMPLETED),
     EvaluationStatus.COMPLETED),
    (EMPTY_TERMINAL_TASK, EvaluationStatus.SKIPPED),
    else_=EvaluationStatus.PENDING,
).label('evaluation_status')

# 评估状态筛选合法取值（前端 BadgeFilter 选项）
EVALUATION_FILTER_VALUES = (
    EvaluationStatus.PENDING, 'evaluating', EvaluationStatus.COMPLETED,
    EvaluationStatus.FAILED, EvaluationStatus.SKIPPED,
)

# 执行状态筛选合法取值（前端 BadgeFilter 选项，纯执行域；INT-301 F1 打回补齐）
EXECUTION_FILTER_VALUES = (
    ExecutionStatus.PENDING, TaskStatus.QUEUED, ExecutionStatus.RUNNING,
    TaskStatus.PAUSED, ExecutionStatus.COMPLETED, ExecutionStatus.FAILED,
    ExecutionStatus.STOPPED, TaskStatus.MERGED,
)


def evaluation_filter_condition(evaluation_status: str):
    """评估状态筛选条件：复用派生表达式（展示与筛选口径一致）。"""
    return EVALUATION_STATUS_EXPR == evaluation_status


def execution_filter_condition(execution_status: str):
    """执行状态筛选条件（INT-301 F1）：复用派生表达式，徽章展示与筛选命中同口径。"""
    return EXECUTION_STATUS_EXPR == execution_status
