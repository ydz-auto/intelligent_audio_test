/**
 * features/reports/lib/search 纯函数测试（对位规范 §3.5：
 * type→report_type、keyword→search、时间范围→start_time/end_time、算法/排序透传）。
 */
import { describe, expect, it } from 'vitest'

import {
  buildReportListQuery,
  computeTimeRange,
} from '@/features/reports/lib/search'
import type { ReportsSearch } from '@/features/reports/types'

const baseSearch: ReportsSearch = {
  tab: 'test',
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
  it('测试报告页签固定 report_type=task，忽略 URL type', () => {
    const query = buildReportListQuery(
      { ...baseSearch, type: 'comparison', search: '回归' },
      'test'
    )
    expect(query.report_type).toBe('task')
    expect(query.keyword).toBe('回归')
    expect(query.status).toBeUndefined()
  })

  it('历史报告页签透传 type/status 与分页默认值', () => {
    const query = buildReportListQuery(
      {
        ...baseSearch,
        tab: 'history',
        type: 'task',
        status: 'draft',
        favorite: true,
        trash: false,
      },
      'history'
    )
    expect(query.report_type).toBe('task')
    expect(query.status).toBe('draft')
    expect(query.favorite).toBe(true)
    expect(query.deleted).toBe(false)
    expect(query.sort_by).toBe('created_at')
    expect(query.order).toBe('desc')
    expect(query.per_page).toBe(20)
  })

  it('自定义时间范围进入 DTO', () => {
    const query = buildReportListQuery(
      {
        ...baseSearch,
        tab: 'history',
        timeRange: 'custom',
        startTime: '2026-10-01T09:00:00',
        endTime: '2026-10-16T18:00:00',
      },
      'history'
    )
    expect(query.start_time).toBe('2026-10-01 09:00')
    expect(query.end_time).toBe('2026-10-16 18:00')
  })
})
