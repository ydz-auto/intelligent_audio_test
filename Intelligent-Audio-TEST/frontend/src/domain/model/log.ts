/**
 * 日志领域模型 —— camelCase
 * 对应后端 api_gateway/schemas/log.py::LogItem / LogListData / LogStatsData /
 * LogRefreshData / LogArchiveStatus
 *
 * 后端序列化输出为 snake_case（APIModel，serialize_by_alias=False），
 * Infrastructure 层 adapter 负责字段名转换，本层零后端依赖。
 */
import type { LogLevelOption } from './logTypes'

/** 日志条目（对应后端 LogItem；socket 通道日志额外带 timestamp 字段） */
export interface Log {
  id: number
  level: string
  module?: string
  category?: string
  source?: string
  content: string
  time?: string | number
  timestamp?: string | number
  createdAt?: string
  taskId?: number | string
  deviceId?: number
  apiId?: number
  threadId?: string | number
  mark?: string
  testCaseId?: string | number
  algorithmType?: string
}

/** 高级过滤条件（前端 Domain，camelCase；发往后端时由 API 层转 snake_case） */
export interface AdvancedLogFilters {
  deviceId?: string
  taskId?: string
  userId?: string
  threadId?: string
  /** 评估ID/轮次（INT-81：业务日志文件路径第三段检索键） */
  evaluationId?: string
  contentInclude?: string
  contentExclude?: string
}

/** 日志统计（前端汇总视图模型，仅含日志页展示的三类计数） */
export interface LogStats {
  total: number
  error: number
  warning: number
  info: number
}

/** 日志统计（对应后端 LogStatsData：按级别细分） */
export interface LogStatsData {
  total: number
  debug: number
  info: number
  warning: number
  error: number
  critical: number
}

/** 日志列表查询条件（前端 Domain，camelCase；发往后端时由 API 层转 snake_case） */
export interface LogQuery extends AdvancedLogFilters {
  keyword?: string
  startTime?: string
  endTime?: string
  category?: string
  module?: string
  mark?: string
  level?: string
  page?: number
  perPage?: number
  algorithmType?: string
  testCaseId?: string
}

/** 日志分页结果（对应后端 LogListData = PaginatedData[LogItem]） */
export interface LogPage {
  items: Log[]
  total: number
  page: number
  perPage: number
  pages: number
}

/** 日志刷新结果（对应后端 LogRefreshData） */
export interface LogRefreshResult {
  items: Log[]
  count: number
  newCount: number
  lastId: number
}

/** 日志标记入参（前端 Domain；adapter 转 snake_case body） */
export interface LogMarkInput {
  logIds: (string | number)[]
  mark?: string
}

/** 日志清除入参（对应后端 LogClearRequest） */
export interface LogClearInput {
  beforeDatetime?: string
  keepMarked?: boolean
}

/** 日志导出查询（对应后端 LogExportQuery + LogExportRequest） */
export interface LogExportQuery {
  level?: string
  module?: string
  /** 逗号分隔的日志 id 串（后端 log_ids 原样） */
  logIds?: string
  format?: string
  page?: number
  perPage?: number
}

/** 归档状态（对应后端 GET /logs/archive/status 返回体；后端为 raw dict，字段即 camelCase） */
export interface LogArchiveStatus {
  totalLogs: number
  hotLogs: number
  coldLogs: number
  archiveDir: string
  /** 归档文件分组计数（OSS archives 桶内 task/case/other 前缀下的 JSON 文件数） */
  taskArchives: number
  caseArchives: number
  otherArchives: number
}

/** 触发归档入参（对应后端 LogArchiveRequest：保留最近 N 天热数据 + dry_run 预览） */
export interface LogArchiveInput {
  days?: number
  dryRun?: boolean
}

/** 触发归档结果（对应后端 LogArchiveResult 及 dry_run 预览返回；字段按实际返回体可选） */
export interface LogArchiveResult {
  message?: string
  archivedCount?: number
  deletedCount?: number
  archiveFile?: string | null
  remainingCount?: number
  /** dry_run 预览字段 */
  coldLogsCount?: number
  cutoffDate?: string
}

/** 已归档日志列表（对应后端 GET /logs/archive/logs 返回体 {items,total,source}） */
export interface LogArchiveList {
  items: Log[]
  total: number
  source: string
}

/** 归档日志查询（对应后端 LogArchiveQuery） */
export interface LogArchiveQuery {
  taskId?: number
  testCaseId?: string
}

export type { LogLevelOption }

/** 日志筛选器（前端 Domain 侧统一 camelCase；发往后端时由 buildQueryParams 映射为后端 key） */
export interface LogFilters {
  startDateTime: string
  endDateTime: string
  logCategory: string
  logModule: string
  markFilter: string
  algorithmType: string
}
