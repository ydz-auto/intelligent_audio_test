import { describe, expect, it } from 'vitest'

import {
  deviceSystemLabel,
  isIosSystem,
  normalizeDeviceSystem,
} from '@/features/devices/lib/device-system'

describe('device-system 归一映射（16_设备域.md §3.4/§9；P3-24 返修）', () => {
  it('大写规范值与小写别名均归一为展示文案', () => {
    expect(normalizeDeviceSystem('harmony')?.label).toBe('HarmonyOS')
    expect(normalizeDeviceSystem('HarmonyOS')?.label).toBe('HarmonyOS')
    expect(normalizeDeviceSystem('android')?.label).toBe('Android')
    expect(normalizeDeviceSystem('Android')?.label).toBe('Android')
    expect(normalizeDeviceSystem('iOS')?.label).toBe('iOS')
  })

  it('iOS 判定命中大小写/别名，不再恒不命中', () => {
    expect(isIosSystem('iOS')).toBe(true)
    expect(isIosSystem('ios')).toBe(true)
    expect(isIosSystem('harmony')).toBe(false)
    expect(isIosSystem('android')).toBe(false)
    expect(isIosSystem(null)).toBe(false)
  })

  it('未知值原样回退展示，不影响空值', () => {
    expect(deviceSystemLabel('custom-os')).toBe('custom-os')
    expect(deviceSystemLabel(null)).toBeNull()
    expect(deviceSystemLabel(undefined)).toBeNull()
  })
})
