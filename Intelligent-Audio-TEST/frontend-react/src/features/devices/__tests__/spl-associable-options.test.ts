/**
 * 播放设备编辑抽屉「可关联声压映射」选项过滤（INT-2347）：
 * 与后端 associate_spl 校验同口径——他机归属/类型不符的映射不可选，
 * 当前已关联映射恒保留（即便归属/类型已不再匹配）以便回显名称。
 */
import { describe, expect, it } from 'vitest'

import type { SplMapping } from '@/domain/models/splMapping'
import { filterAssociableSplMappings } from '@/features/devices/lib/spl-associable-options'

function mapping(overrides: Partial<SplMapping> & Pick<SplMapping, 'id'>): SplMapping {
  return {
    name: `映射 ${overrides.id}`,
    description: null,
    deviceId: null,
    deviceName: null,
    deviceModel: null,
    deviceType: null,
    distance: 1,
    targetSpl: 65,
    digitalGain: 0,
    calibrationStatus: 'calibrated',
    testFrequency: 1000,
    calibrationData: null,
    isCurrent: null,
    createdAt: null,
    updatedAt: null,
    ...overrides,
  }
}

const MAPPINGS = [
  mapping({ id: 1, name: '未归属-干声', deviceType: 'dry' }),
  mapping({ id: 2, name: '未归属-噪声', deviceType: 'noise' }),
  mapping({ id: 3, name: '归属本设备', deviceId: 6, deviceType: 'dry' }),
  mapping({ id: 4, name: '归属他机', deviceId: 12, deviceType: 'dry' }),
  mapping({ id: 5, name: '类型未标注', deviceType: null }),
]

describe('filterAssociableSplMappings', () => {
  it('保留未归属/归属本设备且类型匹配的映射，排除他机归属与类型不符', () => {
    const ids = filterAssociableSplMappings(MAPPINGS, {
      deviceId: 6,
      deviceType: 'dry',
    }).map((m) => m.id)

    expect(ids).toEqual([1, 3, 5])
  })

  it('当前已关联映射恒保留，即使归属他机或类型不符', () => {
    const ids = filterAssociableSplMappings(MAPPINGS, {
      deviceId: 6,
      deviceType: 'dry',
      currentMappingId: 4,
    }).map((m) => m.id)

    expect(ids).toContain(4)
  })

  it('设备类型未知时不做类型收窄（仍排除他机归属）', () => {
    const ids = filterAssociableSplMappings(MAPPINGS, {
      deviceId: 6,
      deviceType: null,
    }).map((m) => m.id)

    expect(ids).toEqual([1, 2, 3, 5])
  })
})
