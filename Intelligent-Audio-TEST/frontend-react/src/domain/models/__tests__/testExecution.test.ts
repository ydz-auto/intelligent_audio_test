import { describe, expect, it } from 'vitest'

import { deriveTaskDeviceTypes } from '../testExecution'

describe('deriveTaskDeviceTypes（INT-2195）', () => {
  it('只有 HTTP API 目标时不含 websocket_api（执行步不渲染实时内容流）', () => {
    expect(
      deriveTaskDeviceTypes([
        { deviceType: 'http_api', deviceId: '11' },
        { deviceType: 'http_api', deviceId: '12' },
      ])
    ).toEqual(['http_api'])
  })

  it('同时选中流式 API 与物理设备时去重列出两类', () => {
    expect(
      deriveTaskDeviceTypes([
        { deviceType: 'physical', deviceId: '3' },
        { deviceType: 'websocket_api', deviceId: '21' },
        { deviceType: 'websocket_api', deviceId: '22' },
      ])
    ).toEqual(['physical', 'websocket_api'])
  })

  it('空分配（无选中目标）返回空数组', () => {
    expect(deriveTaskDeviceTypes([])).toEqual([])
  })
})
