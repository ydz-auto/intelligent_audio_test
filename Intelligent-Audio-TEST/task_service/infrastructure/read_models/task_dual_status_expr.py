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
未失败而评估失败） > skipped（手动停止中断评估） > completed（存在评估
完成用例） > pending。执行侧：paused > running > failed > stopped >
queued > completed > pending；评估过渡态不落入执行侧。
"""
from sqlalchemy import and_, case, exists, or_, select

from task_service.infrastructure.persistence.models import Task, TaskCase
from shared.utils.status_constants import (
    ExecutionStatus, EvaluationStatus, ACTIVE_EXECUTION_STATUSES,
)

# 用例级执行终态集合（failed/stopped 之外的执行终态为 completed）
_EXEC_TERMINAL = ('completed', 'failed', 'stopped')
# 重新评估过渡态（Task.status 值；评估侧一律呈现为 evaluating）
_EVAL_TRANSITION_STATUSES = (
    'evaluating', 'reevaluate_queued', 'reevaluating',
)
# 评估进行中集合（queued/running/calculating；pending=评估未提交不计入）
_EVAL_IN_PROGRESS = (EvaluationStatus.QUEUED, EvaluationStatus.RUNNING, EvaluationStatus.CALCULATING)


def _tc_exists(*criteria):
    """按 task_id 关联的 TaskCase EXISTS 子查询。"""
    return exists(
        select(TaskCase.id)
        .where(TaskCase.task_id == Task.id, *criteria)
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

# ---- 派生 CASE 表达式（与 derive_task_dual_status 同构） ----

EXECUTION_STATUS_EXPR = case(
    (Task.status == 'paused', 'paused'),
    (HAS_EXEC_ACTIVE, ExecutionStatus.RUNNING),
    (HAS_EXEC_FAILED, ExecutionStatus.FAILED),
    (HAS_EXEC_STOPPED, ExecutionStatus.STOPPED),
    (Task.status == 'queued', 'queued'),
    (EXEC_ALL_TERMINAL, ExecutionStatus.COMPLETED),
    else_=ExecutionStatus.PENDING,
).label('execution_status')

EVALUATION_STATUS_EXPR = case(
    (or_(Task.status.in_(_EVAL_TRANSITION_STATUSES), HAS_EVAL_IN_PROGRESS), 'evaluating'),
    (HAS_EVAL_FAILED, EvaluationStatus.FAILED),
    (Task.status == 'stopped', 'skipped'),
    (HAS_EVAL_COMPLETED, EvaluationStatus.COMPLETED),
    else_=EvaluationStatus.PENDING,
).label('evaluation_status')

# 评估状态筛选合法取值（前端 BadgeFilter 选项）
EVALUATION_FILTER_VALUES = (
    EvaluationStatus.PENDING, 'evaluating', EvaluationStatus.COMPLETED,
    EvaluationStatus.FAILED, 'skipped',
)


def evaluation_filter_condition(evaluation_status: str):
    """评估状态筛选条件：复用派生表达式（展示与筛选口径一致）。"""
    return EVALUATION_STATUS_EXPR == evaluation_status
