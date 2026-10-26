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
      { case_id: 'c1', device_type: 'physical', device_id: '101', lab_id: undefined },
      { case_id: 'c1', device_type: 'websocket_api', device_id: '9', lab_id: undefined },
      { case_id: 'c2', device_type: 'http_api', device_id: '7', lab_id: 3 },
    ])
  })

  // INT-2024：网关 TaskCaseDeviceAssignment.device_id 为 Optional[str]，number 提交会 422
  it('INT-2024：number 形态的 deviceId 一律字符串化（API 目标与物理设备同口径）', () => {
    const dto = toTaskCreateDto({
      name: 'INT2024 回归',
      caseIds: ['c1'],
      apiIds: [369],
      caseDevices: [
        { caseId: 'c1', deviceType: 'http_api', deviceId: 369 },
        { caseId: 'c1', deviceType: 'physical', deviceId: 101 },
        { caseId: 'c1', deviceType: 'http_api', deviceId: '369' },
      ],
    })
    expect(dto.case_devices?.map(a => a.device_id)).toEqual(['369', '101', '369'])
    expect(dto.case_devices?.every(a => typeof a.device_id === 'string')).toBe(true)
  })

  it('deviceId 缺省 → device_id 保持 undefined（后端派生兜底）', () => {
    const dto = toTaskCreateDto({
      name: '无目标任务',
      caseIds: ['c1'],
      caseDevices: [{ caseId: 'c1', deviceType: 'physical' }],
    })
    expect(dto.case_devices).toEqual([
      { case_id: 'c1', device_type: 'physical', device_id: undefined, lab_id: undefined },
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
