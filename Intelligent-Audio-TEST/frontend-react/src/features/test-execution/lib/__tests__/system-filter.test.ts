import { describe, expect, it } from 'vitest'

import { matchesSystemFilter } from '@/features/test-execution/lib/system-filter'

describe('开始测试系统筛选归一（INT-2650）', () => {
  it('鸿蒙筛选同时命中 harmony 与 HarmonyOS 两种原始值', () => {
    expect(matchesSystemFilter('harmony', 'harmony')).toBe(true)
    expect(matchesSystemFilter('HarmonyOS', 'harmony')).toBe(true)
  })

  it('Android 筛选同时命中 android 与 Android 两种原始值', () => {
    expect(matchesSystemFilter('android', 'android')).toBe(true)
    expect(matchesSystemFilter('Android', 'android')).toBe(true)
  })

  it('系统之间不串命中', () => {
    expect(matchesSystemFilter('HarmonyOS', 'android')).toBe(false)
    expect(matchesSystemFilter('Android', 'harmony')).toBe(false)
    expect(matchesSystemFilter('harmony', 'android')).toBe(false)
    expect(matchesSystemFilter('android', 'harmony')).toBe(false)
  })

  it('iOS / 未知 / 空值不命中 Android 或鸿蒙', () => {
    expect(matchesSystemFilter('iOS', 'harmony')).toBe(false)
    expect(matchesSystemFilter('iOS', 'android')).toBe(false)
    expect(matchesSystemFilter('custom-os', 'harmony')).toBe(false)
    expect(matchesSystemFilter(null, 'harmony')).toBe(false)
    expect(matchesSystemFilter(undefined, 'android')).toBe(false)
  })
})
