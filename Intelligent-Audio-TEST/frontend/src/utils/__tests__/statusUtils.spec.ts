/**
 * statusUtils 单元测试 —— 任务状态映射纯函数
 * 全部断言使用 domain/enums 枚举值，禁止魔法字符串（与实现一致）
 *
 * INT-405：用例级单值合成函数（执行+评估两维合成一个展示状态）已废弃删除
 * （执行/评估双状态独立展示，见 utils/taskStatusBadge.ts + TaskCard.dualStatus.spec.ts）。
 */
import { describe, it, expect } from 'vitest'
import {
  transformTaskStatus,
  getStatusText,
  getStatusType,
} from '../statusUtils'
import { TaskStatus, ExecutionStatus, EvaluationStatus } from '@/domain/enums'

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
