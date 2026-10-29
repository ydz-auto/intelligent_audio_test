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
    MERGED = 'merged'

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
    # INT-340 人工复核：执行状态可改判 skipped（负责人 2026-10-15 拍板全集；
    # 原执行流程不产出 skipped，仅复核改判可写入）
    SKIPPED = 'skipped'


class EvaluationStatus(str):
    """用例评估过程状态。"""
    PENDING = 'pending'
    QUEUED = 'queued'
    RUNNING = 'running'
    CALCULATING = 'calculating'
    COMPLETED = 'completed'
    STOPPED = 'stopped'
    FAILED = 'failed'
    # 任务级派生徽章专用：评估未实际发生（执行失败/手动停止中断），非落库值
    SKIPPED = 'skipped'


class ResultExcludeStatus(str):
    """测试结果排除语义（INT-305：终态任务删除用例，级联处置 TestResult）。

    被删用例的 TestResult 不物理删除（保审计），execution_status 原值保留、
    以 excluded 标记列盖写：报告/聚合按 excluded 过滤剔除，不计入总数/通过率
    （对齐评估维度隔离的聚合口径）。
    """
    INCLUDED = 0
    EXCLUDED = 1


# ---- 状态集合常量（frozenset 不可变，杜绝魔法数组） ----

# 任务终态状态集合（completed/failed/stopped）
FINISHED_TASK_STATUSES = frozenset({TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.STOPPED})

# 结果类型缺值哨兵（INT-1510 §8.2.2）：UX「结果类型待补充」桶的对外取值。
# 落库为 NULL（test_results.result_type），读侧输出本值，过滤参数同值命中缺值桶。
# 定义在本模块（零依赖）以免读侧为拿一个常量而 import 对象存储基础设施。
RESULT_TYPE_PENDING = 'default'

# 结果类型取值（执行通道/产出形态；落库列 test_results.result_type）
# - api：API 通道执行结果
# - e2e：设备 E2E 执行结果
# - final：多轮用例的最终聚合结果（e2e get_final_results）
RESULT_TYPE_API = 'api'
RESULT_TYPE_E2E = 'e2e'
RESULT_TYPE_FINAL = 'final'

# 执行终态状态集合（completed/failed；ExecutionStatus 无 SKIPPED）
FINISHED_EXECUTION_STATUSES = frozenset({ExecutionStatus.COMPLETED, ExecutionStatus.FAILED})

# 评估终态状态集合（completed/failed）
FINISHED_EVALUATION_STATUSES = frozenset({EvaluationStatus.COMPLETED, EvaluationStatus.FAILED})

# 用例终态状态集合（completed/failed/skipped）
FINISHED_CASE_STATUSES = frozenset({TaskCaseStatus.COMPLETED, TaskCaseStatus.FAILED, TaskCaseStatus.SKIPPED})

# 活跃执行状态集合（queued/running）
ACTIVE_EXECUTION_STATUSES = frozenset({ExecutionStatus.QUEUED, ExecutionStatus.RUNNING})

# 设备占用聚合活跃执行状态集合（pending/queued/running，INT-493 §4.3）
# 与 ACTIVE_EXECUTION_STATUSES 的区别：占用聚合把排队中的 pending 也计入
# （任务刚创建未调度即算占用），running 单列判定 testing。
DEVICE_OCCUPANCY_EXECUTION_STATUSES = frozenset({
    ExecutionStatus.PENDING, ExecutionStatus.QUEUED, ExecutionStatus.RUNNING,
})

# 活跃评估状态集合（pending/queued/running/calculating）
ACTIVE_EVALUATION_STATUSES = frozenset({
    EvaluationStatus.PENDING, EvaluationStatus.QUEUED,
    EvaluationStatus.RUNNING, EvaluationStatus.CALCULATING,
})

# 服务重启可安全判定为中断的任务状态集合（不含 PENDING：保留待 DB 兜底调度自动拉起）
INTERRUPTED_TASK_STATUSES = frozenset({
    TaskStatus.QUEUED, TaskStatus.RUNNING, TaskStatus.EVALUATING,
    TaskStatus.REEVALUATE_QUEUED, TaskStatus.REEVALUATING, TaskStatus.PAUSED,
})

# 服务重启可安全判定为中断的执行状态集合（queued/running；PENDING 保留待自动拉起）
INTERRUPTED_EXECUTION_STATUSES = frozenset({ExecutionStatus.QUEUED, ExecutionStatus.RUNNING})

# INT-340 人工复核可改判状态集合（负责人 2026-10-15 拍板全集）：
# - 执行状态：completed/failed/stopped/skipped（禁 pending/queued/running）
# - 评估状态：completed/failed（双状态口径，对齐 status_fields_relationship.md §8.3）
REVIEWABLE_EXECUTION_STATUSES = frozenset({
    ExecutionStatus.COMPLETED, ExecutionStatus.FAILED,
    ExecutionStatus.STOPPED, ExecutionStatus.SKIPPED,
})
REVIEWABLE_EVALUATION_STATUSES = frozenset({
    EvaluationStatus.COMPLETED, EvaluationStatus.FAILED,
})
