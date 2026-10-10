/**
 * INT-79 缺陷8 回归 —— 对比报告结论文案由 device_types 派生，
 * 不再读取已废弃的 task.type（原实现产生 "涵盖了 undefined 测试类型"）。
 */
import { describe, it, expect } from 'vitest'
import { updateComparisonReportConclusion } from '../useReportComparison'
import { comparisonReport } from '@/store/reportComparisonStore'
import { DeviceType, TaskStatus } from '@/domain/enums'

const baseTask = {
  id: 1,
  name: '任务1',
  status: TaskStatus.COMPLETED,
  deviceCount: 2,
  caseCount: 5,
}

describe('updateComparisonReportConclusion', () => {
  it('物理任务 → 文案含物理设备，无 undefined', () => {
    updateComparisonReportConclusion([
      { ...baseTask, deviceTypes: [DeviceType.PHYSICAL] },
    ])
    const c = comparisonReport.value.conclusion
    expect(c).toContain('物理设备')
    expect(c).not.toContain('undefined')
  })

  it('混合 API 任务 → 文案含 HTTP API 与 WebSocket API 标签', () => {
    updateComparisonReportConclusion([
      { ...baseTask, deviceTypes: [DeviceType.HTTP_API] },
      { ...baseTask, id: 2, deviceTypes: [DeviceType.WEBSOCKET_API] },
    ])
    const c = comparisonReport.value.conclusion
    expect(c).toContain('HTTP API')
    expect(c).toContain('WebSocket API')
    expect(c).not.toContain('undefined')
  })

  it('task 无 deviceTypes 键（旧 DTO 形状）→ 不产生 undefined 文案', () => {
    updateComparisonReportConclusion([{ ...baseTask, deviceTypes: undefined }])
    expect(comparisonReport.value.conclusion).not.toContain('undefined')
  })

  it('0 任务占位文案为被测设备类型口径，无 undefined', () => {
    updateComparisonReportConclusion([])
    const c = comparisonReport.value.conclusion
    expect(c).toContain('被测设备类型')
    expect(c).not.toContain('undefined')
  })
})
