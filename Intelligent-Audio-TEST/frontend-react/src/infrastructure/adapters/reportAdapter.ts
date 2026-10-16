/**
 * 报告域 URL 态 → 列表查询 DTO 转换（infrastructure/adapters 层；DDD 契约：DTO→Domain
 * camelCase 转换唯一层，interfaces 层零 snake_case）。
 * 报告中心 buildReportListQuery（§3.5）+ 展示页 buildShowcaseQuery（§2.1）平移；
 * 口径修正 2026-10-16：取消双页签，report_type 一律由 URL type 透传（默认 undefined=全部）。
 */
import type { ReportListQuery } from '@/domain/models/report'
import type { ReportsSearch } from '@/features/reports/types'
import type { ShowcaseSearch } from '@/features/reports-showcase/types'

/** 时间范围 → start_time/end_time（本地推算，today/yesterday/week/month/custom） */
export function computeTimeRange(
  range: ReportsSearch['timeRange'],
  customStart?: string,
  customEnd?: string
): { startTime?: string; endTime?: string } {
  if (range === 'custom') {
    return {
      startTime: customStart ? customStart.replace('T', ' ').slice(0, 16) : undefined,
      endTime: customEnd ? customEnd.replace('T', ' ').slice(0, 16) : undefined,
    }
  }
  const now = new Date()
  const start = new Date(now)
  if (range === 'today') {
    start.setHours(0, 0, 0, 0)
  } else if (range === 'yesterday') {
    start.setDate(now.getDate() - 1)
    start.setHours(0, 0, 0, 0)
  } else if (range === 'week') {
    start.setDate(now.getDate() - 7)
  } else if (range === 'month') {
    start.setDate(now.getDate() - 30)
  }
  if (range) {
    return {
      startTime: start.toISOString().slice(0, 16),
      endTime: now.toISOString().slice(0, 16),
    }
  }
  return {}
}

/** 报告中心 URL 态 → 列表查询 DTO（type→report_type、keyword→search、startTime/endTime→start_time/end_time、algorithmType→algorithm_type、sortBy/sortOrder→sort_by/order） */
export function buildReportListQuery(search: ReportsSearch): ReportListQuery {
  const { startTime, endTime } = computeTimeRange(
    search.timeRange,
    search.startTime,
    search.endTime
  )
  return {
    page: search.page ?? 1,
    per_page: search.pageSize ?? 20,
    report_type: search.type ?? undefined,
    // 状态筛选（draft/published）与类型同为筛选条件，默认全部
    status: search.status ?? undefined,
    keyword: search.search || undefined,
    task_type: search.taskType || undefined,
    device_type: search.deviceType || undefined,
    creator: search.creator || undefined,
    start_time: startTime,
    end_time: endTime,
    algorithm_type: search.algorithmType || undefined,
    sort_by: search.sortBy ?? 'created_at',
    order: search.sortOrder ?? 'desc',
    favorite: search.favorite ?? false,
    deleted: search.trash ?? false,
  }
}

/** 展示页时间范围 → start_time/end_time（本地推算，today/yesterday/week/month/custom） */
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

/** 展示页 URL 态 → 列表查询 DTO（search→keyword、startTime/endTime→start_time/end_time、algorithmType→algorithm_type、sortBy/sortOrder→sort_by/order；展示页固定 status='published' 由 usePublishedReportList 注入） */
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
