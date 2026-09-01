# -*- coding: utf-8 -*-
"""任务 & 用例状态常量定义

所有服务统一使用这些常量，禁止硬编码状态字符串。
"""


class TaskStatus(str):
    """任务状态。"""
    PENDING = 'pending'
    QUEUED = 'queued'
    RUNNING = 'running'
    EVALUATING = 'evaluating'
    REEVALUATE_QUEUED = 'reevaluate_queued'
    REEVALUATING = 'reevaluating'
    COMPLETED = 'completed'
    FAILED = 'failed'
    STOPPED = 'stopped'
    PAUSED = 'paused'
    SKIPPED = 'skipped'

    @classmethod
    def is_terminal(cls, status: str) -> bool:
        return status in (cls.COMPLETED, cls.FAILED, cls.STOPPED, cls.SKIPPED)

    @classmethod
    def is_running(cls, status: str) -> bool:
        return status in (cls.RUNNING, cls.EVALUATING, cls.REEVALUATING)


class TaskCaseStatus(str):
    """用例最终结果状态（由 execution_status + evaluation_status 推导，不直接修改）。"""
    PENDING = 'pending'
    RUNNING = 'running'
    EVALUATING = 'evaluating'
    COMPLETED = 'completed'
    FAILED = 'failed'
    SKIPPED = 'skipped'


class ExecutionStatus(str):
    """用例执行过程状态。"""
    PENDING = 'pending'
    QUEUED = 'queued'
    RUNNING = 'running'
    COMPLETED = 'completed'
    STOPPED = 'stopped'
    FAILED = 'failed'


class EvaluationStatus(str):
    """用例评估过程状态。"""
    PENDING = 'pending'
    QUEUED = 'queued'
    RUNNING = 'running'
    CALCULATING = 'calculating'
    COMPLETED = 'completed'
    STOPPED = 'stopped'
    FAILED = 'failed'


# ---- 状态集合常量（frozenset 不可变，杜绝魔法数组） ----

# 任务终态状态集合（completed/failed/stopped）
FINISHED_TASK_STATUSES = frozenset({TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.STOPPED})

# 执行终态状态集合（completed/failed；ExecutionStatus 无 SKIPPED）
FINISHED_EXECUTION_STATUSES = frozenset({ExecutionStatus.COMPLETED, ExecutionStatus.FAILED})

# 评估终态状态集合（completed/failed）
FINISHED_EVALUATION_STATUSES = frozenset({EvaluationStatus.COMPLETED, EvaluationStatus.FAILED})

# 用例终态状态集合（completed/failed/skipped）
FINISHED_CASE_STATUSES = frozenset({TaskCaseStatus.COMPLETED, TaskCaseStatus.FAILED, TaskCaseStatus.SKIPPED})

# 活跃执行状态集合（queued/running）
ACTIVE_EXECUTION_STATUSES = frozenset({ExecutionStatus.QUEUED, ExecutionStatus.RUNNING})

# 活跃评估状态集合（pending/queued/running/calculating）
ACTIVE_EVALUATION_STATUSES = frozenset({
    EvaluationStatus.PENDING, EvaluationStatus.QUEUED,
    EvaluationStatus.RUNNING, EvaluationStatus.CALCULATING,
})
