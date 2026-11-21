import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  HISTORY_CATEGORY_EVENT_TYPES,
  buildAvailabilitySpec,
  buildPerformanceSpec,
  filterByTimeRange,
  hasMonitorStatsData,
  resolveStatsDateRange,
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

describe('监控统计查询区间换算（INT-2670 接 /test-devices/monitor-stats）', () => {
  // 本地墙钟晚间，验证不因 toISOString 的 UTC 换算跨日
  const now = new Date('2026-11-21T20:30:00')

  it('今日 = 当天（起止同一天）', () => {
    expect(resolveStatsDateRange('today', '', '', now)).toEqual({
      startDate: '2026-11-21',
      endDate: '2026-11-21',
    })
  })

  it('近7天 / 近30天按含首尾的自然日计', () => {
    expect(resolveStatsDateRange('7d', '', '', now)).toEqual({
      startDate: '2026-11-15',
      endDate: '2026-11-21',
    })
    expect(resolveStatsDateRange('30d', '', '', now)).toEqual({
      startDate: '2026-10-23',
      endDate: '2026-11-21',
    })
  })

  it('自定义范围直接透传；缺任一日期返回 null（不发请求）', () => {
    expect(resolveStatsDateRange('custom', '2026-10-01', '2026-10-07', now)).toEqual({
      startDate: '2026-10-01',
      endDate: '2026-10-07',
    })
    expect(resolveStatsDateRange('custom', '', '2026-10-07', now)).toBeNull()
    expect(resolveStatsDateRange('custom', '2026-10-01', '', now)).toBeNull()
  })
})

describe('监控统计空态判定（契约 §1.2：无采点显示空态，不用示例曲线充数）', () => {
  const blankPoint = {
    date: '11-21',
    isoDate: '2026-11-21',
    availability: null,
    cpu: null,
    memory: null,
    battery: null,
    errors: 0,
    operations: 0,
    healthCheckSamples: 0,
  }

  it('全 null 且无错误/操作为空', () => {
    expect(hasMonitorStatsData([])).toBe(false)
    expect(hasMonitorStatsData([blankPoint, { ...blankPoint, date: '11-20' }])).toBe(false)
  })

  it('任一真实采点 / 错误 / 操作即为有数据', () => {
    expect(hasMonitorStatsData([{ ...blankPoint, availability: 0 }])).toBe(true)
    expect(hasMonitorStatsData([{ ...blankPoint, cpu: 0 }])).toBe(true)
    expect(hasMonitorStatsData([{ ...blankPoint, memory: 12 }])).toBe(true)
    expect(hasMonitorStatsData([{ ...blankPoint, battery: 90 }])).toBe(true)
    expect(hasMonitorStatsData([{ ...blankPoint, errors: 1 }])).toBe(true)
    expect(hasMonitorStatsData([{ ...blankPoint, operations: 2 }])).toBe(true)
  })
})

describe('单日范围的线图渲染（INT-2670 打回项：「今日」两张线图不再空白）', () => {
  const today = {
    date: '11-21',
    isoDate: '2026-11-21',
    availability: 66.7,
    cpu: 6.3,
    memory: 62.9,
    battery: 100,
    errors: 266,
    operations: 0,
    healthCheckSamples: 3,
  }

  it('单点（今日）可用性/性能开启点标记，当日数值可见', () => {
    expect((buildAvailabilitySpec([today]).point as { visible: boolean }).visible).toBe(true)
    expect((buildPerformanceSpec([today]).point as { visible: boolean }).visible).toBe(true)
  })

  it('多点范围仍关闭点标记，避免密集噪点', () => {
    const twoPoints = [today, { ...today, date: '11-20', isoDate: '2026-11-20' }]
    expect((buildAvailabilitySpec(twoPoints).point as { visible: boolean }).visible).toBe(false)
    expect((buildPerformanceSpec(twoPoints).point as { visible: boolean }).visible).toBe(false)
  })
})
