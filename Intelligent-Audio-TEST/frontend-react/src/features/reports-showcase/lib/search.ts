/**
 * 报告展示页 URL 态 → 列表查询 DTO（15_报告域.md §2.1：search→keyword、
 * startTime/endTime→start_time/end_time、algorithmType→algorithm_type、sortBy/sortOrder→sort_by/order）。
 * 展示页固定 status='published'（已发布），由 usePublishedReportList 注入。
 */
import type { ReportListQuery } from '@/domain/models/report'
import type { ShowcaseSearch } from '@/features/reports-showcase/types'

/** 时间范围 → start_time/end_time（本地推算，today/yesterday/week/month） */
export function computeShowcaseTimeRange(
  range: ShowcaseSearch['timeRange'],
  customStart?: string,
  customEnd?: string
): { startTime?: string; endTime?: string } {
  if (range === 'custom') {
    return {
      startTime: customStart ? customStart.replace('T', ' ').slice(0, 16) : undefined,
      endTime: customEnd ? customEnd.replace('T', ' ').slice(0, 16) : undefined,
    }
  }
  if (!range) return {}
  const now = new Date()
  const start = new Date(now)
  if (range === 'today') start.setHours(0, 0, 0, 0)
  else if (range === 'yesterday') {
    start.setDate(now.getDate() - 1)
    start.setHours(0, 0, 0, 0)
  } else if (range === 'week') start.setDate(now.getDate() - 7)
  else if (range === 'month') start.setDate(now.getDate() - 30)
  return {
    startTime: start.toISOString().slice(0, 16),
    endTime: now.toISOString().slice(0, 16),
  }
}

export function buildShowcaseQuery(search: ShowcaseSearch): ReportListQuery {
  const { startTime, endTime } = computeShowcaseTimeRange(
    search.timeRange,
    search.startTime,
    search.endTime
  )
  return {
    page: search.page ?? 1,
    per_page: search.pageSize ?? 20,
    report_type: search.type ?? undefined,
    keyword: search.search || undefined,
    start_time: startTime,
    end_time: endTime,
    algorithm_type: search.algorithmType || undefined,
    sort_by: search.sortBy ?? 'created_at',
    order: search.sortOrder ?? 'desc',
    favorite: false,
    deleted: false,
  }
}
