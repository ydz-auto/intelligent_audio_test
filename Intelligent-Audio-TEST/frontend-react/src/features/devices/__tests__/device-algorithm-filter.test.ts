import { describe, expect, it } from 'vitest'

import type { TestDevice } from '@/domain/models/testDevice'
import { filterTestDevicesByAlgorithm } from '@/features/devices/lib/device-algorithm-filter'

/** 只填过滤相关字段，其余按 domain 模型置空 */
function device(id: number, supportedAlgorithms: string[] | null): TestDevice {
  return {
    id,
    name: `设备${id}`,
    model: null,
    description: null,
    type: null,
    system: null,
    systemVersion: null,
    apiLevel: null,
    appName: null,
    appVersion: null,
    connectionType: null,
    serialNumber: null,
    ip: null,
    remark: null,
    tags: null,
    customAttributes: null,
    priority: null,
    status: null,
    lastOnlineAt: null,
    driverName: null,
    supportedAlgorithms,
    needsPromptAudio: null,
    maxAudioDuration: null,
    location: null,
    keywords: null,
    labId: null,
    labName: null,
    occupied: false,
    createdAt: null,
    updatedAt: null,
  }
}

describe('filterTestDevicesByAlgorithm（16_设备域.md §2.2；INT-1622）', () => {
  it('未选全局算法（空串）时原样返回全部设备', () => {
    const devices = [device(1, ['voice_llm']), device(2, [])]
    expect(filterTestDevicesByAlgorithm(devices, '')).toBe(devices)
  })

  it('按 supportedAlgorithms 包含全局算法类型码过滤', () => {
    const devices = [
      device(1, ['voice_llm']),
      device(2, ['voice_llm', 'other_algo']),
      device(3, ['other_algo']),
      device(4, []),
      device(5, null),
    ]
    expect(filterTestDevicesByAlgorithm(devices, 'voice_llm').map((d) => d.id)).toEqual([1, 2])
    expect(filterTestDevicesByAlgorithm(devices, 'other_algo').map((d) => d.id)).toEqual([2, 3])
  })

  it('无匹配时返回空数组（页面走筛选后空态）', () => {
    expect(filterTestDevicesByAlgorithm([device(1, ['voice_llm'])], 'not_exist')).toEqual([])
  })
})
