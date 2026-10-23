/**
 * INT-1434 验收：buildCaseDeviceAssignments 组装「所选用例 × 选中目标」用例级设备选择。
 *
 * - 物理设备目标 → { deviceType: 'physical', deviceId: 设备 id }
 * - API 目标 → deviceType 取显式值；未显式按端点协议派生（ws/wss → websocket_api，其余 → http_api）
 */
import { describe, it, expect } from 'vitest'
import { buildCaseDeviceAssignments } from '../task'

describe('INT-1434：buildCaseDeviceAssignments', () => {
  it('设备 + HTTP API 混选 → physical + http_api 各一条（笛卡尔积）', () => {
    const assignments = buildCaseDeviceAssignments({
      caseIds: ['c1', 'c2'],
      deviceIds: [101],
      apis: [{ id: 7, deviceType: null, endpointUrl: 'https://api.example.com/asr' }],
    })
    expect(assignments).toEqual([
      { caseId: 'c1', deviceType: 'physical', deviceId: 101 },
      { caseId: 'c1', deviceType: 'http_api', deviceId: 7 },
      { caseId: 'c2', deviceType: 'physical', deviceId: 101 },
      { caseId: 'c2', deviceType: 'http_api', deviceId: 7 },
    ])
  })

  it('ws/wss 端点协议 → websocket_api（Realtime 路由前置）', () => {
    const assignments = buildCaseDeviceAssignments({
      caseIds: ['c1'],
      deviceIds: [],
      apis: [{ id: 9, deviceType: null, endpointUrl: 'ws://rt.example.com/stream' }],
    })
    expect(assignments).toEqual([
      { caseId: 'c1', deviceType: 'websocket_api', deviceId: 9 },
    ])
  })

  it('API 显式 device_type 优先于端点协议派生', () => {
    const assignments = buildCaseDeviceAssignments({
      caseIds: ['c1'],
      deviceIds: [],
      apis: [{ id: 8, deviceType: 'websocket_api', endpointUrl: 'https://api.example.com/asr' }],
    })
    expect(assignments).toEqual([
      { caseId: 'c1', deviceType: 'websocket_api', deviceId: 8 },
    ])
  })

  it('无设备无 API（或均未命中）→ 不产出任何用例级选择（后端派生兜底，零回归）', () => {
    const assignments = buildCaseDeviceAssignments({
      caseIds: ['c1'],
      deviceIds: [],
      apis: [],
    })
    expect(assignments).toEqual([])
  })

  it('未选目标时 caseIds 非空也不产出（空笛卡尔积）', () => {
    const assignments = buildCaseDeviceAssignments({
      caseIds: ['c1', 'c2'],
      deviceIds: [],
      apis: [],
    })
    expect(assignments).toEqual([])
  })
})
