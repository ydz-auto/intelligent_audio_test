/**
 * infrastructure/adapters/reportAdapter 纯函数测试（对位规范 §3.5 + 口径修正 2026-10-16：
 * 取消双页签后 report_type 一律由 URL type 透传、默认 undefined=全部）。
 */
import { describe, expect, it } from 'vitest'

import {
  buildReportListQuery,
  buildShowcaseQuery,
  computeShowcaseTimeRange,
  computeTimeRange,
} from '@/infrastructure/adapters/reportAdapter'
import type { ReportsSearch } from '@/features/reports/types'

const baseSearch: ReportsSearch = {
  view: 'card',
  page: 1,
  pageSize: 20,
  favorite: false,
  trash: false,
  sortBy: 'created_at',
  sortOrder: 'desc',
}

describe('computeTimeRange', () => {
  it('custom 范围把 datetime-local 输入折叠为空格分隔的 16 位', () => {
    expect(
      computeTimeRange('custom', '2026-10-16T14:30:00', '2026-10-17T08:00:00')
    ).toEqual({
      startTime: '2026-10-16 14:30',
      endTime: '2026-10-17 08:00',
    })
  })

  it('无 range 时返回空对象', () => {
    expect(computeTimeRange(undefined)).toEqual({})
  })

  it('today/week/month 返回 ISO 前缀的时间窗口', () => {
    const today = computeTimeRange('today')
    expect(today.startTime).toBeTruthy()
    expect(today.endTime).toBeTruthy()
    const month = computeTimeRange('month')
    expect(month.startTime).toBeTruthy()
    expect(month.endTime).toBeTruthy()
  })
})

describe('buildReportListQuery', () => {
  it('report_type 默认 undefined（全部报告），keyword 透传', () => {
    const query = buildReportListQuery({
      ...baseSearch,
      search: '回归',
    })
    expect(query.report_type).toBeUndefined()
    expect(query.keyword).toBe('回归')
    expect(query.status).toBeUndefined()
  })

  it('type/status 作为筛选条件透传，与分页默认值', () => {
    const query = buildReportListQuery({
      ...baseSearch,
      type: 'comparison',
      status: 'draft',
      favorite: true,
      trash: false,
    })
    expect(query.report_type).toBe('comparison')
    expect(query.status).toBe('draft')
    expect(query.favorite).toBe(true)
    expect(query.deleted).toBe(false)
    expect(query.sort_by).toBe('created_at')
    expect(query.order).toBe('desc')
    expect(query.per_page).toBe(20)
  })

  it('自定义时间范围进入 DTO', () => {
    const query = buildReportListQuery({
      ...baseSearch,
      timeRange: 'custom',
      startTime: '2026-10-01T09:00:00',
      endTime: '2026-10-16T18:00:00',
    })
    expect(query.start_time).toBe('2026-10-01 09:00')
    expect(query.end_time).toBe('2026-10-16 18:00')
  })
})

describe('buildShowcaseQuery / computeShowcaseTimeRange', () => {
  it('展示页无 timeRange 返回空时间窗口、report_type 透传', () => {
    const query = buildShowcaseQuery({
      view: 'table',
      page: 1,
      pageSize: 20,
      type: 'benchmark',
      sortBy: 'created_at',
      sortOrder: 'desc',
    })
    expect(query.report_type).toBe('benchmark')
    expect(query.start_time).toBeUndefined()
    expect(query.favorite).toBe(false)
    expect(query.deleted).toBe(false)
  })

  it('展示页 custom 时间范围折叠', () => {
    const range = computeShowcaseTimeRange('custom', '2026-10-01T09:00:00', '2026-10-16T18:00:00')
    expect(range).toEqual({ startTime: '2026-10-01 09:00', endTime: '2026-10-16 18:00' })
  })
})
