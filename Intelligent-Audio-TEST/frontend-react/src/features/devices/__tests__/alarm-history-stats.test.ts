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

describe('线图渲染的点标记（INT-2670 打回项：「今日」与「多日仅一天有采点」两张线图不再空白）', () => {
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
  const blank = {
    date: '11-18',
    isoDate: '2026-11-18',
    availability: null,
    cpu: null,
    memory: null,
    battery: null,
    errors: 0,
    operations: 0,
    healthCheckSamples: 0,
  }
  const visibleOf = (spec: Record<string, unknown>) =>
    (spec.point as { visible: boolean }).visible

  it('单点（今日）可用性/性能开启点标记，当日数值可见', () => {
    expect(visibleOf(buildAvailabilitySpec([today]))).toBe(true)
    expect(visibleOf(buildPerformanceSpec([today]))).toBe(true)
  })

  it('多点范围仍关闭点标记，避免密集噪点', () => {
    const twoPoints = [today, { ...today, date: '11-20', isoDate: '2026-11-20' }]
    expect(visibleOf(buildAvailabilitySpec(twoPoints))).toBe(false)
    expect(visibleOf(buildPerformanceSpec(twoPoints))).toBe(false)
  })

  it('多日范围里仅一天有采点（其余天全 null）也开启点标记', () => {
    const onlyOneDay = [blank, { ...today, date: '11-19', isoDate: '2026-11-19' }]
    expect(visibleOf(buildAvailabilitySpec(onlyOneDay))).toBe(true)
    expect(visibleOf(buildPerformanceSpec(onlyOneDay))).toBe(true)
  })

  it('多日区间（6 天）只有末一天有健康检查采点时，性能图同样开启点标记', () => {
    const sixDays = [
      { ...blank, date: '11-14', isoDate: '2026-11-14' },
      { ...blank, date: '11-15', isoDate: '2026-11-15' },
      { ...blank, date: '11-16', isoDate: '2026-11-16' },
      { ...blank, date: '11-17', isoDate: '2026-11-17' },
      { ...blank, date: '11-18', isoDate: '2026-11-18' },
      { ...today, date: '11-19', isoDate: '2026-11-19' },
    ]
    expect(visibleOf(buildPerformanceSpec(sixDays))).toBe(true)
    expect(visibleOf(buildAvailabilitySpec(sixDays))).toBe(true)
  })

  it('每个系列分别计数：三条性能指标都多点时保持关闭（个别指标全 null 不算单点）', () => {
    const manyDays = [
      { ...today, date: '11-19', isoDate: '2026-11-19', battery: null },
      { ...today, date: '11-20', isoDate: '2026-11-20', battery: null },
      { ...today, date: '11-21', isoDate: '2026-11-21', battery: null },
    ]
    expect(visibleOf(buildPerformanceSpec(manyDays))).toBe(false)
  })

  it('区间内无任何真实采点时不开启点标记（走空态，不画点）', () => {
    const allBlank = [blank, { ...blank, date: '11-19', isoDate: '2026-11-19' }]
    expect(visibleOf(buildAvailabilitySpec(allBlank))).toBe(false)
    expect(visibleOf(buildPerformanceSpec(allBlank))).toBe(false)
  })
})
