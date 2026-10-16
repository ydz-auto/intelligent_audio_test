/**
 * 报告中心 URL 搜索态类型（validateSearch 产物形态，供页面/子组件消费；
 * 避免 routes → features 循环引用，类型独立于此文件）。
 * 口径修正 2026-10-16：取消双页签，单一列表视图；类型/状态均为筛选条件而非页面层级。
 */
import type {
  ReportSortBy,
  ReportSortOrder,
  ReportStatus,
  ReportTimeRange,
  ReportType,
  ReportViewMode,
} from '@/domain/models/report'

export type ReportsSearch = {
  view: ReportViewMode
  page: number
  pageSize: number
  search?: string
  type?: ReportType
  status?: ReportStatus
  timeRange?: ReportTimeRange
  startTime?: string
  endTime?: string
  algorithmType?: string
  favorite: boolean
  trash: boolean
  sortBy: ReportSortBy
  sortOrder: ReportSortOrder
}
