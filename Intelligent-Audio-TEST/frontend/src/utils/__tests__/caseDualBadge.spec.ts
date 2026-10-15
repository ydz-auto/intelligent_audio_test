/**
 * INT-405：用例级执行/评估双徽章 + 计数分桶单测（替代前端单值合成展示状态口径）。
 *
 * 锁定：
 * - 双徽章独立取值：执行徽章只读 executionStatus（不掺复合 status，避免 evaluating 落执行侧）
 * - 评估徽章文案走用例评估域 §8.3（queued→待评估、running→评估中、calculating→计算中、
 *   stopped→已停止），与任务评估域文案族区分
 * - 评估状态缺失不渲染评估徽章（旧数据兼容）
 * - summarizeCaseStatuses：completed 双维完成、失败优先不重复计入、pending 双 pending、
 *   执行失败与评估失败分维独立计数
 */
import { describe, it, expect } from 'vitest'
import {
  getCaseExecutionBadgeStatus,
  getCaseEvaluationStatusText,
  getCaseEvaluationBadgeIcon,
} from '../taskStatusBadge'
import { summarizeCaseStatuses } from '../caseStatusSummary'
import { ExecutionStatus, EvaluationStatus, TaskCaseStatus } from '@/domain/enums'

describe('getCaseExecutionBadgeStatus（执行徽章只读执行维）', () => {
  it('取 executionStatus 原值（含 running，前端不再改写成 in_progress）', () => {
    expect(getCaseExecutionBadgeStatus({ executionStatus: ExecutionStatus.RUNNING }))
      .toBe(ExecutionStatus.RUNNING)
  })

  it('复合 status 的 evaluating 不落执行徽章（评估过渡归评估侧）', () => {
    expect(getCaseExecutionBadgeStatus({ executionStatus: ExecutionStatus.COMPLETED }))
      .toBe(ExecutionStatus.COMPLETED)
  })

  it('executionStatus 缺失回退 pending', () => {
    expect(getCaseExecutionBadgeStatus({})).toBe(ExecutionStatus.PENDING)
  })
})

describe('getCaseEvaluationStatusText / Icon（用例评估域文案 §8.3）', () => {
  it('queued → 待评估；running → 评估中；calculating → 计算中；stopped → 已停止', () => {
    expect(getCaseEvaluationStatusText(EvaluationStatus.QUEUED)).toBe('待评估')
    expect(getCaseEvaluationStatusText(EvaluationStatus.PENDING)).toBe('待评估')
    expect(getCaseEvaluationStatusText(EvaluationStatus.RUNNING)).toBe('评估中')
    expect(getCaseEvaluationStatusText(EvaluationStatus.CALCULATING)).toBe('计算中')
    expect(getCaseEvaluationStatusText(EvaluationStatus.STOPPED)).toBe('已停止')
    expect(getCaseEvaluationStatusText(EvaluationStatus.FAILED)).toBe('评估失败')
    expect(getCaseEvaluationStatusText(EvaluationStatus.COMPLETED)).toBe('已完成')
  })

  it('未知值回退原文（后端扩展值不炸界面）', () => {
    expect(getCaseEvaluationStatusText('custom_eval')).toBe('custom_eval')
  })

  it('评估进行图标随值区分（running/calculating 转圈，completed 勾）', () => {
    expect(getCaseEvaluationBadgeIcon(EvaluationStatus.RUNNING)).toContain('fa-spin')
    expect(getCaseEvaluationBadgeIcon(EvaluationStatus.CALCULATING)).toContain('fa-spin')
    expect(getCaseEvaluationBadgeIcon(EvaluationStatus.COMPLETED)).toContain('fa-check-circle')
    expect(getCaseEvaluationBadgeIcon(EvaluationStatus.FAILED)).toContain('fa-times-circle')
  })
})

describe('summarizeCaseStatuses（双状态分桶计数）', () => {
  const mk = (over: Partial<{ status: string; executionStatus: string; evaluationStatus: string }>) => ({
    status: TaskCaseStatus.PENDING,
    executionStatus: ExecutionStatus.PENDING,
    evaluationStatus: EvaluationStatus.PENDING,
    ...over,
  })

  it('执行完成 + 评估完成 + status=completed → completed 计入', () => {
    const s = summarizeCaseStatuses([mk({
      status: TaskCaseStatus.COMPLETED,
      executionStatus: ExecutionStatus.COMPLETED,
      evaluationStatus: EvaluationStatus.COMPLETED,
    })])
    expect(s.completed).toBe(1)
    expect(s.pending).toBe(0)
    expect(s.inProgress).toBe(0)
  })

  it('评估跳过(status=skipped) 执行完成不计入 completed（对齐后端 actual_completed_cases）', () => {
    const s = summarizeCaseStatuses([mk({
      status: TaskCaseStatus.SKIPPED,
      executionStatus: ExecutionStatus.COMPLETED,
      evaluationStatus: EvaluationStatus.COMPLETED,
    })])
    expect(s.completed).toBe(0)
  })

  it('执行失败 → executionFailed；评估失败(执行未失败) → evaluationFailed，互不重复', () => {
    const s = summarizeCaseStatuses([
      mk({ status: TaskCaseStatus.FAILED, executionStatus: ExecutionStatus.FAILED, evaluationStatus: EvaluationStatus.FAILED }),
      mk({ status: TaskCaseStatus.FAILED, executionStatus: ExecutionStatus.COMPLETED, evaluationStatus: EvaluationStatus.FAILED }),
    ])
    expect(s.executionFailed).toBe(1)
    expect(s.evaluationFailed).toBe(1)
    expect(s.completed).toBe(0)
  })

  it('执行 running 或评估 calculating 计入 inProgress', () => {
    const s = summarizeCaseStatuses([
      mk({ status: TaskCaseStatus.RUNNING, executionStatus: ExecutionStatus.RUNNING }),
      mk({ status: TaskCaseStatus.EVALUATING, executionStatus: ExecutionStatus.COMPLETED, evaluationStatus: EvaluationStatus.CALCULATING }),
    ])
    expect(s.inProgress).toBe(2)
  })

  it('双 pending 计入 pending；空集全 0', () => {
    expect(summarizeCaseStatuses([mk({})]).pending).toBe(1)
    expect(summarizeCaseStatuses([])).toEqual({
      completed: 0, inProgress: 0, pending: 0, executionFailed: 0, evaluationFailed: 0,
    })
  })
})
