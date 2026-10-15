/**
 * INT-405：用例计数分桶单一源（执行/评估双状态独立口径）。
 *
 * 原口径先在前端把两维合成单值展示状态、再按合成值分桶，
 * 该合成已废弃（负责人裁定 2026-10-15，INT-400 #5，INT-301 双徽章为准）：
 * 执行状态与评估状态两维独立展示，计数同样只读后端两维原值 +
 * 后端 derive_task_case_status 派生的复合结果态（status 字段）。
 *
 * 分桶与后端读模型严格同构（task_read_model_progress_stats / _progress.py）：
 * - completed：status==completed（执行完成且评估完成），与
 *   actual_completed_cases 的 SQL 条件等价，评估跳过留痕行不计入；
 * - inProgress：执行 queued/running 或评估 queued/running/calculating；
 * - executionFailed / evaluationFailed：按维度独立计数，
 *   评估失败计数在执行同例失败时不重复计入（对齐旧口径与统计展示）。
 */
import { ExecutionStatus, EvaluationStatus, TaskCaseStatus } from '../domain/enums'

/** 参与分桶的最小字段集（TaskProgressCaseItem / AssociatedCase / TaskCaseBrief 均满足） */
export interface CaseStatusFields {
  status?: string
  executionStatus?: string
  evaluationStatus?: string
}

export interface CaseStatusSummary {
  completed: number
  inProgress: number
  pending: number
  executionFailed: number
  evaluationFailed: number
}

export function summarizeCaseStatuses(cases: readonly CaseStatusFields[]): CaseStatusSummary {
  let completed = 0
  let inProgress = 0
  let pending = 0
  let executionFailed = 0
  let evaluationFailed = 0

  cases.forEach((tc) => {
    const execFailed = tc.executionStatus === ExecutionStatus.FAILED
    const evalFailed = tc.evaluationStatus === EvaluationStatus.FAILED

    if (execFailed) executionFailed++
    if (evalFailed && !execFailed) evaluationFailed++

    if (execFailed || evalFailed) return
    if (tc.status === TaskCaseStatus.COMPLETED && tc.executionStatus === ExecutionStatus.COMPLETED) {
      completed++
      return
    }
    const execActive = tc.executionStatus === ExecutionStatus.RUNNING
      || tc.executionStatus === ExecutionStatus.QUEUED
    const evalActive = tc.evaluationStatus === EvaluationStatus.RUNNING
      || tc.evaluationStatus === EvaluationStatus.CALCULATING
      || tc.evaluationStatus === EvaluationStatus.QUEUED
    if (execActive || evalActive) {
      inProgress++
      return
    }
    if (tc.executionStatus === ExecutionStatus.PENDING && tc.evaluationStatus === EvaluationStatus.PENDING) {
      pending++
    }
  })

  return { completed, inProgress, pending, executionFailed, evaluationFailed }
}
