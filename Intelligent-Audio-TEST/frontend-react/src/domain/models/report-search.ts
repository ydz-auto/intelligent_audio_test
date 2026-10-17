/**
 * 报告列表 URL 搜索态类型（domain 层共享契约）。
 * 原落位 features/reports/types.ts 与 features/reports-showcase/types.ts（interfaces 层），
 * 因 infrastructure/adapters/reportAdapter 的查询构造需要消费该形态（DDD 依赖单向：
 * interfaces→application→infrastructure→domain），类型上提 domain，features 仅 re-export
 * （INT-596 P2-5 返修：adapter 不得 type-import 特性层）。
 * 口径修正 2026-10-16：取消双页签，单一列表视图；类型/状态均为筛选条件而非页面层级。
 */
import type {
  ReportSortBy,
  ReportSortOrder,
  ReportStatus,
  ReportTimeRange,
  ReportType,
  ReportViewMode,
} from './report'

/** 报告中心 URL 搜索态（validateSearch 产物形态，供页面/子组件消费） */
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
  /** 高级搜索：任务类型（e2e/api/mixed，§2 :186） */
  taskType?: string
  /** 高级搜索：设备类型（§2 :187） */
  deviceType?: string
  /** 高级搜索：创建者（§2 :188） */
  creator?: string
  algorithmType?: string
  favorite: boolean
  trash: boolean
  sortBy: ReportSortBy
  sortOrder: ReportSortOrder
}

/** 报告展示页 URL 搜索态（validateSearch 产物形态；§2.1 INT-441 双入口拆分，仅已发布报告） */
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
