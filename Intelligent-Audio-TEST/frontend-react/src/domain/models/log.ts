/**
 * 日志领域模型（domain 层；17_配置运维.md §4 / INT-763 接线）。
 * 形态对照 api_gateway/schemas/log.py::LogItem / LogListData / LogStatsData /
 * LogRefreshData / LogListQuery（后端序列化 snake_case，转换收敛在 infrastructure）。
 */

/** 日志条目（对应后端 LogItem） */
export interface Log {
  id: number
  time: string
  level: string
  category: string
  module: string
  source: string
  content: string
  mark?: string
  deviceId?: number
  taskId?: number
  apiId?: number
  testCaseId?: string
  threadId?: string
  algorithmType?: string
}

/** 日志分页结果（对应后端 LogListData，INT-297 分页信封） */
export interface LogPage {
  items: Log[]
  total: number
  page: number
  pages: number
  perPage: number
}

/** 日志统计（对应后端 LogStatsData；前端收敛展示 total/error/warning/info 四枚） */
export interface LogStatsData {
  total: number
  debug: number
  info: number
  warning: number
  error: number
  critical: number
}

/** 日志刷新结果（对应后端 LogRefreshData；last_id 增量拉取） */
export interface LogRefreshResult {
  items: Log[]
  count: number
  newCount: number
  lastId: number
}

/** 日志列表查询条件（前端 camelCase；发后端由 adapter 转 snake_case） */
export interface LogQuery {
  keyword?: string
  startTime?: string
  endTime?: string
  category?: string
  module?: string
  mark?: string
  algorithmType?: string
  /** 多级别逗号串（后端 LogListQuery.level.split(',') 实测） */
  level?: string
  deviceId?: string
  taskId?: string
  evaluationId?: string
  /** 仅自己范围（LogListQuery extra ignore，后端 userId 过滤为设计口径） */
  userId?: string
  threadId?: string
  contentInclude?: string
  contentExclude?: string
  page?: number
  perPage?: number
}

/** 日志导出查询（对应后端 LogExportRequest + LogExportQuery：format/log_ids 走 body，level/module 走 query） */
export interface LogExportQuery {
  /** 逗号分隔的日志 id 串（后端 log_ids 原样） */
  logIds?: string
  /** 文本 txt / JSON json / CSV csv（后端 default excel） */
  format?: string
  /** 级别逗号串（query） */
  level?: string
  /** 模块（query） */
  module?: string
}

/** 日志标记入参（对应后端 LogMarkRequest） */
export interface LogMarkInput {
  logIds: (string | number)[]
  mark?: string
}

/** 日志清除入参（对应后端 LogClearRequest） */
export interface LogClearInput {
  beforeDatetime?: string
  keepMarked?: boolean
}

/** 日志级别（§4.2 级别 tag 多选；顺序 = 展示顺序） */
export const LOG_LEVELS = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'] as const
export type LogLevel = (typeof LOG_LEVELS)[number]

/** 日志分类选项（§4.2 分类 Select） */
export const LOG_CATEGORY_OPTIONS = [
  { value: 'system', label: '系统日志' },
  { value: 'test', label: '测试日志' },
  { value: 'error', label: '错误日志' },
] as const

/** 日志模块选项（§4.2 模块 Select；值 = 后端 Log.module 原值，TestType api/e2e 同源） */
export const LOG_MODULE_OPTIONS = [
  { value: 'api', label: 'API模块' },
  { value: 'e2e', label: 'E2E测试' },
  { value: 'device', label: '设备管理' },
] as const

/** 标记颜色选项（§4.2 标记 Select + §4.5 批量标记） */
export const LOG_MARK_OPTIONS = [
  { value: 'yellow', label: '黄色' },
  { value: 'red', label: '红色' },
  { value: 'green', label: '绿色' },
  { value: 'blue', label: '蓝色' },
] as const
