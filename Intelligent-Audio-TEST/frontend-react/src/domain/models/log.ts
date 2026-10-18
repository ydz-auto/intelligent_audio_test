/**
 * 日志查看领域模型（domain 层；INT-693 接线落地）。
 * 形态对照 api_gateway/schemas/log.py 实测：LogItem（snake_case 序列化，
 * 经 infrastructure/dto/log.dto.ts 唯一转换层转 camelCase 进本层）、
 * LogListData(items/total/page/per_page/pages)、LogStatsData(total/debug/info/
 * warning/error/critical)、LogRefreshData(items/count/new_count/last_id)。
 * 日志页筛选条件（LogQuery）与后端 LogListQuery 逐字段对齐。
 */

export type LogItem = {
  id: number
  time: string
  level: string
  category: string
  module: string
  source: string
  content: string
  mark: string | null
  deviceId: number | null
  taskId: number | null
  apiId: number | null
  testCaseId: string | null
  threadId: string | null
  algorithmType: string | null
}

/** 日志级别（后端 LogItem.level 取值；页面列色映射见 features/logs/constants） */
export const LOG_LEVELS = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'] as const

/** 日志统计（对应后端 LogStatsData；页面收敛展示 total/error/warning/info 四枚） */
export type LogStats = {
  total: number
  debug: number
  info: number
  warning: number
  error: number
  critical: number
}

export const EMPTY_LOG_STATS: LogStats = {
  total: 0,
  debug: 0,
  info: 0,
  warning: 0,
  error: 0,
  critical: 0,
}

/** 日志分页结果（对应后端 LogListData = PaginatedData[LogItem]） */
export type LogPage = {
  items: LogItem[]
  total: number
  page: number
  perPage: number
  pages: number
}

export const EMPTY_LOG_PAGE: LogPage = {
  items: [],
  total: 0,
  page: 1,
  perPage: 20,
  pages: 1,
}

/** 日志刷新结果（对应后端 LogRefreshData + db_max_id/reset_required 增量基准语义） */
export type LogRefreshResult = {
  items: LogItem[]
  count: number
  newCount: number
  lastId: number
  dbMaxId?: number
  resetRequired?: boolean
}

/**
 * 日志列表/统计查询条件（前端 Domain，camelCase；发往后端时由
 * infrastructure/dto/log.dto.ts toLogQueryDto 转 snake_case）。
 * 字段对齐后端 LogListQuery；userId 为「仅自己」视图范围附加参数
 * （后端当前无 user 维度过滤，见 INT-693 交付评论 §后端缺口）。
 */
export type LogQuery = {
  page?: number
  perPage?: number
  level?: string
  module?: string
  category?: string
  keyword?: string
  contentInclude?: string
  contentExclude?: string
  startTime?: string
  endTime?: string
  mark?: string
  deviceId?: number | string
  taskId?: number | string
  apiId?: number | string
  testCaseId?: string
  threadId?: string
  algorithmType?: string
  evaluationId?: string
  round?: string
  userId?: number | string
}

/** 日志标记入参（PUT /logs/mark；mark 默认 'flagged' 与后端 LogMarkRequest 一致） */
export type LogMarkInput = {
  logIds: Array<string | number>
  mark?: string
}

/** 日志清除入参（POST /logs/clear；对应后端 LogClearRequest） */
export type LogClearInput = {
  beforeDatetime?: string | null
  keepMarked?: boolean
}

/** 日志导出格式（后端 LogExportRequest.format 取值 txt/json/csv/excel；中文标签选项见 features/logs/constants） */
export type LogExportFormat = 'txt' | 'json' | 'csv' | 'excel'

export type LogExportInput = {
  logIds?: Array<string | number>
  format?: LogExportFormat
}

/** 实时监控配置（§7.11；默认值 DEFAULT_REALTIME_CONFIG / 轮询档位 REALTIME_POLL_INTERVALS 见 features/logs/constants） */
export type LogRealtimeConfig = {
  /** 轮询间隔（仅 WS 不可用降级 refresh 轮询时生效；默认跟随 VITE_LOG_POLL_IDLE_MAX_MS 语义） */
  pollIntervalMs: number
  autoScroll: boolean
  /** 新日志计数 toast 开关 */
  notifyNewLogs: boolean
}
