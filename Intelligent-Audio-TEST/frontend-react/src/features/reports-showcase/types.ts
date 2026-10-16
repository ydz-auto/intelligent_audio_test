/**
 * 报告展示页 URL 搜索态类型（validateSearch 产物形态；15_报告域.md §2.1 INT-441 双入口拆分）。
 * 展示页仅已发布报告（published），行操作仅「查看/复制链接」；无 tab/收藏/回收站态。
 */
import type {
  ReportSortBy,
  ReportSortOrder,
  ReportTimeRange,
  ReportType,
  ReportViewMode,
} from '@/domain/models/report'

export type ShowcaseSearch = {
  view: ReportViewMode
  page: number
  pageSize: number
  search?: string
  type?: ReportType
  timeRange?: ReportTimeRange
  startTime?: string
  endTime?: string
  algorithmType?: string
  sortBy: ReportSortBy
  sortOrder: ReportSortOrder
}
