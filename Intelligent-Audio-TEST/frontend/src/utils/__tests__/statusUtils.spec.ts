/**
 * statusUtils 单元测试 —— 用例状态/任务状态映射纯函数
 * 全部断言使用 domain/enums 枚举值，禁止魔法字符串（与实现一致）
 */
import { describe, it, expect } from 'vitest'
import {
  transformTestCaseStatus,
  transformTaskStatus,
  getStatusText,
  getStatusType,
} from '../statusUtils'
import { TaskStatus, ExecutionStatus, EvaluationStatus } from '@/domain/enums'

describe('transformTestCaseStatus', () => {
  it('全空输入 → 默认 pending 状态', () => {
    const r = transformTestCaseStatus({})
    expect(r.status).toBe(TaskStatus.PENDING)
    expect(r.executionStatus).toBe(ExecutionStatus.PENDING)
    expect(r.evaluationStatus).toBe(EvaluationStatus.PENDING)
    expect(r.resultStatus).toBe(TaskStatus.PENDING)
    expect(r.errorMessage).toBe('')
  })

  it('running 执行态映射为 in_progress', () => {
    const r = transformTestCaseStatus({ executionStatus: TaskStatus.RUNNING })
    expect(r.executionStatus).toBe(ExecutionStatus.IN_PROGRESS)
    expect(r.status).toBe(ExecutionStatus.IN_PROGRESS)
  })

  it('queued 执行态保持 queued', () => {
    const r = transformTestCaseStatus({ executionStatus: ExecutionStatus.QUEUED })
    expect(r.status).toBe(ExecutionStatus.QUEUED)
  })

  it('failed 执行态优先级最高', () => {
    const r = transformTestCaseStatus({
      executionStatus: ExecutionStatus.FAILED,
      evaluationStatus: EvaluationStatus.COMPLETED,
    })
    expect(r.status).toBe(ExecutionStatus.FAILED)
  })

  it('执行完成 + 评估完成 + 用例通过(passed) → completed', () => {
    const r = transformTestCaseStatus({
      executionStatus: ExecutionStatus.COMPLETED,
      evaluationStatus: EvaluationStatus.COMPLETED,
      status: 'passed',
    })
    // 'passed' 经 resultStatusMap 归一为 completed
    expect(r.resultStatus).toBe(ExecutionStatus.COMPLETED)
    expect(r.status).toBe(ExecutionStatus.COMPLETED)
  })

  it('执行完成 + 评估完成 + 结果失败 → failed', () => {
    const r = transformTestCaseStatus({
      executionStatus: ExecutionStatus.COMPLETED,
      evaluationStatus: EvaluationStatus.COMPLETED,
      resultStatus: ExecutionStatus.FAILED,
    })
    expect(r.status).toBe(ExecutionStatus.FAILED)
  })

  it('执行完成 + 评估排队中 → queued', () => {
    const r = transformTestCaseStatus({
      executionStatus: ExecutionStatus.COMPLETED,
      evaluationStatus: EvaluationStatus.QUEUED,
    })
    expect(r.status).toBe(EvaluationStatus.QUEUED)
  })

  it('执行完成 + 评估计算中 → calculating', () => {
    const r = transformTestCaseStatus({
      executionStatus: ExecutionStatus.COMPLETED,
      evaluationStatus: EvaluationStatus.CALCULATING,
    })
    expect(r.status).toBe(EvaluationStatus.CALCULATING)
  })

  it('执行完成 + 评估失败 → failed', () => {
    const r = transformTestCaseStatus({
      executionStatus: ExecutionStatus.COMPLETED,
      evaluationStatus: EvaluationStatus.FAILED,
    })
    expect(r.status).toBe(EvaluationStatus.FAILED)
  })

  it('执行完成 + 评估 pending → evaluating（等待评估）', () => {
    const r = transformTestCaseStatus({
      executionStatus: ExecutionStatus.COMPLETED,
    })
    expect(r.status).toBe(TaskStatus.EVALUATING)
  })

  it('执行完成 + 评估 running → calculating', () => {
    const r = transformTestCaseStatus({
      executionStatus: ExecutionStatus.COMPLETED,
      evaluationStatus: TaskStatus.RUNNING,
    })
    expect(r.evaluationStatus).toBe(EvaluationStatus.CALCULATING)
    expect(r.status).toBe(EvaluationStatus.CALCULATING)
  })

  it('errorMessage 原样透传', () => {
    const r = transformTestCaseStatus({ errorMessage: 'boom' })
    expect(r.errorMessage).toBe('boom')
  })
})

describe('transformTaskStatus', () => {
  it('running → in_progress', () => {
    expect(transformTaskStatus(TaskStatus.RUNNING)).toBe(ExecutionStatus.IN_PROGRESS)
  })

  it('已知状态保持原值', () => {
    expect(transformTaskStatus(TaskStatus.PENDING)).toBe(TaskStatus.PENDING)
    expect(transformTaskStatus(ExecutionStatus.COMPLETED)).toBe(ExecutionStatus.COMPLETED)
    expect(transformTaskStatus(ExecutionStatus.FAILED)).toBe(ExecutionStatus.FAILED)
  })

  it('未知状态原样返回', () => {
    expect(transformTaskStatus('unknown_state')).toBe('unknown_state')
  })
})

describe('getStatusText', () => {
  it('已知状态返回中文标签', () => {
    expect(getStatusText(ExecutionStatus.PENDING)).toBe('等待中')
    expect(getStatusText(ExecutionStatus.QUEUED)).toBe('排队中')
    expect(getStatusText(ExecutionStatus.IN_PROGRESS)).toBe('执行中')
    expect(getStatusText(ExecutionStatus.COMPLETED)).toBe('已完成')
    expect(getStatusText(ExecutionStatus.STOPPED)).toBe('已停止')
    expect(getStatusText(ExecutionStatus.FAILED)).toBe('失败')
    expect(getStatusText(EvaluationStatus.CALCULATING)).toBe('评估中')
    expect(getStatusText(TaskStatus.EVALUATING)).toBe('评估中')
    expect(getStatusText(TaskStatus.REEVALUATE_QUEUED)).toBe('重新评估排队中')
    expect(getStatusText(TaskStatus.REEVALUATING)).toBe('重新评估中')
  })

  it('未知状态原样返回', () => {
    expect(getStatusText('custom_status')).toBe('custom_status')
  })
})

describe('getStatusType', () => {
  it('已知状态返回对应标签类型', () => {
    expect(getStatusType(ExecutionStatus.PENDING)).toBe('info')
    expect(getStatusType(ExecutionStatus.QUEUED)).toBe('warning')
    expect(getStatusType(ExecutionStatus.IN_PROGRESS)).toBe('primary')
    expect(getStatusType(ExecutionStatus.COMPLETED)).toBe('success')
    expect(getStatusType(ExecutionStatus.STOPPED)).toBe('warning')
    expect(getStatusType(ExecutionStatus.FAILED)).toBe('danger')
    expect(getStatusType(TaskStatus.REEVALUATING)).toBe('primary')
  })

  it('未知状态兜底 info', () => {
    expect(getStatusType('custom_status')).toBe('info')
  })
})
