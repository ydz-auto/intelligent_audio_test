# -*- coding: utf-8 -*-
"""任务用例统计（用例级口径）

`task_case_relations` 一行 = (用例 × 目标)：一个用例关联多个 API/设备时会有多行。
对外展示与统计统一按 `test_case_id` 去重后的**用例数**计，执行行只在用例内
作为 `targets` 承载（任务详情、total_cases、进度、报告同一口径）。

本模块是唯一口径来源：
- refresh_task_counts_atomic：用例级计数写库（多实例安全，SQL 子查询一次 UPDATE）
- aggregate_case_rows：把同一用例的多行聚合为用例级视图（含 targets）
"""
from typing import Dict, Iterable, List, Optional

from shared.utils.status_constants import (
    ACTIVE_EVALUATION_STATUSES,
    ACTIVE_EXECUTION_STATUSES,
    EvaluationStatus,
    ExecutionStatus,
    TaskCaseStatus,
)
from shared.utils.status_utils import (
    derive_case_evaluation_status,
    derive_task_case_status,
)

# 用例移除留痕（INT-305）：留痕行不参与任何统计
REMOVED_CASE_MESSAGE = '用例已被移除'

# 用例行终止态（completed/skipped 视为已完成侧）
_DONE_CASE_STATUSES = (TaskCaseStatus.COMPLETED, TaskCaseStatus.SKIPPED)

# 执行失败/停止行上的评估 completed 不足以证明评估真实发生（可能是失败补写占位）
_NON_EVALUATING_EXEC_STATUSES = (ExecutionStatus.FAILED, ExecutionStatus.STOPPED)



def _fmt(dt) -> Optional[str]:
    return dt.isoformat() if dt else None


def _aggregate_execution(exec_statuses: List[str]) -> str:
    """多行执行状态 → 用例级执行状态（执行中优先，便于显示"执行中"）"""
    if any(s in ACTIVE_EXECUTION_STATUSES for s in exec_statuses):
        return ExecutionStatus.RUNNING
    if all(s in (ExecutionStatus.COMPLETED, ExecutionStatus.SKIPPED) for s in exec_statuses):
        return ExecutionStatus.COMPLETED
    if any(s == ExecutionStatus.FAILED for s in exec_statuses):
        return ExecutionStatus.FAILED
    if any(s == ExecutionStatus.STOPPED for s in exec_statuses):
        return ExecutionStatus.STOPPED
    return ExecutionStatus.PENDING


def _aggregate_evaluation(eval_statuses: List[str]) -> str:
    """多行评估状态 → 用例级评估状态"""
    if any(s in ACTIVE_EVALUATION_STATUSES for s in eval_statuses):
        return EvaluationStatus.RUNNING
    if all(s in (EvaluationStatus.COMPLETED, EvaluationStatus.SKIPPED) for s in eval_statuses):
        return EvaluationStatus.COMPLETED
    if any(s == EvaluationStatus.FAILED for s in eval_statuses):
        return EvaluationStatus.FAILED
    if any(s == EvaluationStatus.STOPPED for s in eval_statuses):
        return EvaluationStatus.STOPPED
    return EvaluationStatus.PENDING


def _row_has_real_evaluation(row) -> bool:
    """该执行行是否为真实评估完成（执行未失败/停止）。"""
    return ((row.evaluation_status or EvaluationStatus.PENDING) == EvaluationStatus.COMPLETED
            and (row.execution_status or ExecutionStatus.PENDING)
            not in _NON_EVALUATING_EXEC_STATUSES)


def _row_target(row) -> Dict:
    """执行行 → 目标摘要（API 行 device_id 即 apis.id）"""
    from shared.models.common_enums import DeviceType

    device_type = row.device_type or None
    device_id = row.device_id or None
    api_id = None
    if device_id is not None:
        try:
            api_id = int(device_id)
        except (TypeError, ValueError):
            api_id = None
    is_api = device_type in (DeviceType.HTTP_API.value, DeviceType.WEBSOCKET_API.value)
    return {
        'task_case_id': row.id,
        'target_type': 'api' if is_api else 'device',
        'device_type': device_type,
        'device_id': device_id,
        'api_id': api_id,
        'status': row.status,
        'execution_status': row.execution_status,
        'evaluation_status': derive_case_evaluation_status(
            row.execution_status, row.evaluation_status,
            real_evaluation_happened=_row_has_real_evaluation(row)),
        'started_at': _fmt(row.started_at),
        'completed_at': _fmt(row.completed_at),
        'duration': row.duration,
        'error_message': row.error_message,
    }


def aggregate_case_rows(rows: Iterable) -> Dict:
    """同一用例的多行 → 用例级视图（含 targets）

    纯函数，不触库；`rows` 为已按用例过滤的 ORM 行（或具同名属性的对象）。
    """
    rows = list(rows)
    exec_statuses = [r.execution_status or ExecutionStatus.PENDING for r in rows]
    eval_statuses = [r.evaluation_status or EvaluationStatus.PENDING for r in rows]
    execution_status = _aggregate_execution(exec_statuses)
    # 执行失败且无任一目标真实评估完成：completed 只是失败补写占位 → 展示 skipped
    evaluation_status = derive_case_evaluation_status(
        execution_status, _aggregate_evaluation(eval_statuses),
        real_evaluation_happened=any(_row_has_real_evaluation(r) for r in rows))

    started = [r.started_at for r in rows if r.started_at]
    completed = [r.completed_at for r in rows if r.completed_at]
    # 耗时：优先落库 duration；缺失时按行 start/completed 推算（API 行历史未写 duration）
    durations = []
    for r in rows:
        if r.duration is not None:
            durations.append(r.duration)
        elif r.started_at and r.completed_at:
            try:
                durations.append(max(0, int((r.completed_at - r.started_at).total_seconds())))
            except TypeError:
                # 历史数据 tz-aware/naive 混用，跳过该行
                continue
    terminal = execution_status in (ExecutionStatus.COMPLETED, ExecutionStatus.FAILED,
                                   ExecutionStatus.STOPPED)

    return {
        'status': derive_task_case_status(execution_status, evaluation_status),
        'execution_status': execution_status,
        'evaluation_status': evaluation_status,
        'started_at': _fmt(min(started)) if started else None,
        'completed_at': _fmt(max(completed)) if (terminal and completed) else None,
        'duration': sum(durations) if durations else None,
        'error_message': next((r.error_message for r in rows if r.error_message), None),
        'target_count': len(rows),
        'targets': [_row_target(r) for r in rows],
    }


def case_level_counts(rows: Iterable) -> Dict[str, int]:
    """按用例去重后的 total/completed/failed 计数（与写库口径一致）"""
    groups: Dict[str, List] = {}
    for row in rows:
        groups.setdefault(str(row.test_case_id), []).append(row)
    completed = failed = 0
    for group in groups.values():
        agg = aggregate_case_rows(group)
        if agg['status'] in _DONE_CASE_STATUSES:
            completed += 1
        elif agg['status'] == TaskCaseStatus.FAILED:
            failed += 1
    return {'total': len(groups), 'completed': completed, 'failed': failed}


def refresh_task_counts_atomic(task_id) -> None:
    """用例级计数原子刷新（多实例安全）

    total_cases  = 去重用例数
    completed    = 全部执行行 completed/skipped 的用例数
    failed       = 已无进行中行且存在 failed 行的用例数
    """
    from sqlalchemy import text
    from shared.models.database import get_engine

    sql = text("""
        UPDATE test_tasks SET
            total_cases = (
                SELECT COUNT(DISTINCT test_case_id) FROM task_case_relations
                WHERE task_id = :task_id
                  AND (error_message IS NULL OR error_message <> :removed)
            ),
            completed_cases = (
                SELECT COUNT(*) FROM (
                    SELECT test_case_id FROM task_case_relations
                    WHERE task_id = :task_id
                      AND (error_message IS NULL OR error_message <> :removed)
                    GROUP BY test_case_id
                    HAVING SUM(CASE WHEN status IN ('completed', 'skipped') THEN 1 ELSE 0 END) = COUNT(*)
                ) AS done_cases
            ),
            failed_cases = (
                SELECT COUNT(*) FROM (
                    SELECT test_case_id FROM task_case_relations
                    WHERE task_id = :task_id
                      AND (error_message IS NULL OR error_message <> :removed)
                    GROUP BY test_case_id
                    HAVING SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) > 0
                       AND SUM(CASE WHEN status IN ('pending', 'running', 'evaluating') THEN 1 ELSE 0 END) = 0
                ) AS failed_cases
            )
        WHERE id = :task_id
    """)
    try:
        with get_engine().connect() as conn:
            conn.execute(sql, {'task_id': int(task_id), 'removed': REMOVED_CASE_MESSAGE})
            conn.commit()
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"原子刷新任务 {task_id} 计数失败: {e}")
