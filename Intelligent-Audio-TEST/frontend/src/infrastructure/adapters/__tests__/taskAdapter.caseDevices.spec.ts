/**
 * INT-1434 验收：toTaskCreateDto case_devices 契约映射。
 *
 * - TaskCreateDraft.caseDevices（camelCase）→ TaskCreateDto.case_devices（snake_case）
 * - 无 caseDevices（旧调用）→ 不携带该键（后端派生兜底，零回归）
 */
import { describe, it, expect } from 'vitest'
import { toTaskCreateDto } from '../taskAdapter'
import type { TaskCreateDraft } from '../../../domain/model/task'

describe('INT-1434：toTaskCreateDto case_devices 映射', () => {
  it('caseDevices → case_devices 逐字段 snake_case 化（含 lab_id 可选）', () => {
    const dto = toTaskCreateDto({
      name: '混跑任务',
      caseIds: ['c1', 'c2'],
      deviceIds: [101],
      apiIds: [7, 9],
      caseDevices: [
        { caseId: 'c1', deviceType: 'physical', deviceId: 101 },
        { caseId: 'c1', deviceType: 'websocket_api', deviceId: 9 },
        { caseId: 'c2', deviceType: 'http_api', deviceId: 7, labId: 3 },
      ],
    })
    expect(dto.case_devices).toEqual([
      { case_id: 'c1', device_type: 'physical', device_id: 101, lab_id: undefined },
      { case_id: 'c1', device_type: 'websocket_api', device_id: 9, lab_id: undefined },
      { case_id: 'c2', device_type: 'http_api', device_id: 7, lab_id: 3 },
    ])
  })

  it('无 caseDevices（旧调用）→ 不携带 case_devices 键', () => {
    const dto = toTaskCreateDto({
      name: '旧调用草稿',
      caseIds: ['1'],
      deviceIds: [2],
    } as TaskCreateDraft)
    expect(dto.case_devices).toBeUndefined()
  })

  it('caseDevices 为空数组 → case_devices 传空数组（与 undefined 区分）', () => {
    const dto = toTaskCreateDto({
      name: '空目标任务',
      caseIds: ['1'],
      caseDevices: [],
    })
    expect(dto.case_devices).toEqual([])
  })
})
