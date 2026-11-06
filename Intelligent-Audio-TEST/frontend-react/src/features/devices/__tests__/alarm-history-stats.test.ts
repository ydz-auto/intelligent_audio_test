import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  HISTORY_CATEGORY_EVENT_TYPES,
  filterByTimeRange,
} from '@/features/devices/lib/alarm-history-stats'

describe('历史监控时间范围筛选（16_设备域.md §3.7；P2-4 返修）', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-10-17T12:00:00'))
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  const todayIso = '2026-10-17T08:00:00'
  const threeDaysAgoIso = '2026-10-14T08:00:00'
  const fortyDaysAgoIso = '2026-09-07T08:00:00'

  it('今日范围只保留当天事件', () => {
    expect(filterByTimeRange(todayIso, 'today')).toBe(true)
    expect(filterByTimeRange(threeDaysAgoIso, 'today')).toBe(false)
  })

  it('近7天保留 3 天前、排除 40 天前', () => {
    expect(filterByTimeRange(threeDaysAgoIso, '7d')).toBe(true)
    expect(filterByTimeRange(fortyDaysAgoIso, '7d')).toBe(false)
  })

  it('自定义起止范围生效（起止为闭区间）', () => {
    expect(filterByTimeRange('2026-10-10T08:00:00', 'custom', '2026-10-09', '2026-10-11')).toBe(true)
    expect(filterByTimeRange('2026-10-08T08:00:00', 'custom', '2026-10-09', '2026-10-11')).toBe(false)
    expect(filterByTimeRange('2026-10-12T08:00:00', 'custom', '2026-10-09', '2026-10-11')).toBe(false)
    expect(filterByTimeRange('2026-10-10T08:00:00', 'custom', '', '2026-10-11')).toBe(true)
    expect(filterByTimeRange('2026-10-12T08:00:00', 'custom', '2026-10-09', '')).toBe(true)
  })

  it('空/非法时间不误杀（无法解析则放行）', () => {
    expect(filterByTimeRange(null, '7d')).toBe(true)
    expect(filterByTimeRange('not-a-date', 'today')).toBe(true)
  })

  it('四类历史事件类别划分（状态/性能/操作/错误）', () => {
    expect(HISTORY_CATEGORY_EVENT_TYPES.status).toContain('online')
    expect(HISTORY_CATEGORY_EVENT_TYPES.status).toContain('error')
    expect(HISTORY_CATEGORY_EVENT_TYPES.performance).toContain('health_check')
    expect(HISTORY_CATEGORY_EVENT_TYPES.operation).toContain('operation')
    expect(HISTORY_CATEGORY_EVENT_TYPES.error).toEqual(['error'])
  })
})
