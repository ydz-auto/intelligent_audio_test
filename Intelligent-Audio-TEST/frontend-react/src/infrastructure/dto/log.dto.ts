/**
 * 日志 DTO（infrastructure/dto 层；snake_case ↔ camelCase 唯一转换层）。
 * 对照 api_gateway/schemas/log.py 实测：
 * LogItem（id/time/level/category/module/source/content/mark/device_id/task_id/
 * api_id/test_case_id/thread_id/algorithm_type）、LogListData(items/total/page/
 * per_page/pages)、LogStatsData、LogRefreshData(items/count/new_count/last_id)。
 * 请求体/查询参数显式 snake_case（last_id/log_ids/before_datetime/keep_marked/
 * per_page/start_time 等）；写方向 toXxxDto 转回 snake_case 提交。
 */
import type {
  LogClearInput,
  LogExportInput,
  LogItem,
  LogMarkInput,
  LogPage,
  LogQuery,
  LogRefreshResult,
  LogStats,
} from '@/domain/models/log'

// ===== 响应 DTO（snake_case，对应后端 LogItem/LogListData/LogStatsData/LogRefreshData） =====

export interface LogItemDto {
  id: number
  time: string
  level: string
  category: string
  module: string
  source: string
  content: string
  mark?: string | null
  device_id?: number | null
  task_id?: number | null
  api_id?: number | null
  test_case_id?: string | null
  thread_id?: string | null
  algorithm_type?: string | null
}

export interface LogListDto {
  items: LogItemDto[]
  total: number
  page: number
  per_page: number
  pages: number
}

export interface LogStatsDto {
  total: number
  debug: number
  info: number
  warning: number
  error: number
  critical: number
}

export interface LogRefreshDto {
  items: LogItemDto[]
  count: number
  new_count: number
  last_id: number
  /** 后端增量基准（list_logs_after_id → db_max_id）；last_id 超前时前端需重置 */
  db_max_id?: number
  reset_required?: boolean
}

// ===== 请求 DTO（snake_case 请求体/查询参数） =====

export interface LogMarkDto {
  log_ids: Array<string | number>
  mark: string
}

export interface LogClearDto {
  before_datetime?: string | null
  keep_marked?: boolean
}

export interface LogRefreshRequestDto {
  last_id: number
}

export interface LogExportRequestDto {
  log_ids?: Array<string | number>
  format?: string
}

// ===== WS/Socket.IO /ws/logs 载荷（socketio_server.broadcast_log wire：{task_id, log}） =====

/** task_log 事件 log 载荷（_websocket_mixin log_payload 字段子集：id/time/level/module/content/mark/task_id/test_case_id/category/source） */
export interface LogWsLogDto {
  id?: number
  time?: string
  level?: string
  module?: string
  content?: string
  mark?: string | null
  task_id?: number | string | null
  test_case_id?: string | null
  category?: string | null
  source?: string | null
}

/** task_log 事件信封（socketio_server.py:122-125 wire：task_id + log） */
export interface LogWsTaskLogDto {
  task_id?: number | string | null
  log?: LogWsLogDto | null
}

// ===== DTO → Domain（响应） =====

function toNumber(value: unknown): number {
  const n = Number(value)
  return Number.isFinite(n) ? n : 0
}

/** LogItemDto → LogItem（显式逐字段映射；时间字段保留后端原值） */
export function toLog(dto: LogItemDto): LogItem {
  return {
    id: dto.id,
    time: dto.time ?? '',
    level: dto.level ?? '',
    category: dto.category ?? '',
    module: dto.module ?? '',
    source: dto.source ?? '',
    content: dto.content ?? '',
    mark: dto.mark ?? null,
    deviceId: dto.device_id ?? null,
    taskId: dto.task_id ?? null,
    apiId: dto.api_id ?? null,
    testCaseId: dto.test_case_id ?? null,
    threadId: dto.thread_id ?? null,
    algorithmType: dto.algorithm_type ?? null,
  }
}

/**
 * WS task_log 载荷 → LogItem（INT-928 接线；Socket.IO 通道增量插顶）。
 * 通道 log 载荷字段子集（无 device_id/api_id/thread_id/algorithm_type），缺失置 null；
 * task_id/test_case_id snake_case 收敛 camelCase，与 HTTP 侧同口径（本层唯一转换点）。
 */
export function toLogFromWs(dto: LogWsTaskLogDto | null | undefined): LogItem | null {
  const log = dto?.log
  if (!log || typeof log !== 'object') return null
  return {
    id: toNumber(log.id),
    time: log.time ?? '',
    level: log.level ?? '',
    category: log.category ?? '',
    module: log.module ?? '',
    source: log.source ?? '',
    content: log.content ?? '',
    mark: log.mark ?? null,
    deviceId: null,
    taskId: log.task_id != null ? toNumber(log.task_id) : null,
    apiId: null,
    testCaseId: log.test_case_id ?? null,
    threadId: null,
    algorithmType: null,
  }
}

/** 日志分页 → LogPage */
export function toLogPage(dto: LogListDto | null | undefined): LogPage {
  const items = Array.isArray(dto?.items) ? dto.items.map(toLog) : []
  return {
    items,
    total: toNumber(dto?.total),
    page: toNumber(dto?.page) || 1,
    perPage: toNumber(dto?.per_page) || items.length || 20,
    pages: toNumber(dto?.pages) || 1,
  }
}

/** 日志统计 → LogStats（数值兜底 0） */
export function toLogStats(dto: LogStatsDto | null | undefined): LogStats {
  return {
    total: toNumber(dto?.total),
    debug: toNumber(dto?.debug),
    info: toNumber(dto?.info),
    warning: toNumber(dto?.warning),
    error: toNumber(dto?.error),
    critical: toNumber(dto?.critical),
  }
}

/** 日志刷新结果 → LogRefreshResult */
export function toLogRefreshResult(
  dto: LogRefreshDto | null | undefined
): LogRefreshResult {
  return {
    items: Array.isArray(dto?.items) ? dto.items.map(toLog) : [],
    count: toNumber(dto?.count),
    newCount: toNumber(dto?.new_count),
    lastId: toNumber(dto?.last_id),
    dbMaxId: toNumber(dto?.db_max_id) || undefined,
    resetRequired: Boolean(dto?.reset_required),
  }
}

// ===== Domain → DTO（请求方向） =====

/**
 * 日志查询条件 → snake_case query。
 * 字段对齐后端 LogListQuery（page/per_page/level/module/category/keyword/
 * content_include/content_exclude/start_time/end_time/mark/device_id/task_id/
 * api_id/test_case_id/thread_id/algorithm_type/evaluation_id/round/user_id）。
 */
export function toLogQueryDto(
  query: LogQuery
): Record<string, string | number | boolean> {
  const params: Record<string, string | number | boolean> = {}
  if (query.page !== undefined) params.page = query.page
  if (query.perPage !== undefined) params.per_page = query.perPage
  if (query.level) params.level = query.level
  if (query.module) params.module = query.module
  if (query.category) params.category = query.category
  if (query.mark) params.mark = query.mark
  if (query.keyword) params.keyword = query.keyword
  if (query.algorithmType) params.algorithm_type = query.algorithmType
  if (query.startTime) params.start_time = query.startTime
  if (query.endTime) params.end_time = query.endTime
  if (query.deviceId !== undefined && query.deviceId !== '')
    params.device_id = String(query.deviceId)
  if (query.taskId !== undefined && query.taskId !== '')
    params.task_id = String(query.taskId)
  if (query.apiId !== undefined && query.apiId !== '')
    params.api_id = String(query.apiId)
  if (query.testCaseId) params.test_case_id = String(query.testCaseId)
  if (query.threadId) params.thread_id = String(query.threadId)
  if (query.evaluationId) params.evaluation_id = String(query.evaluationId)
  if (query.round) params.round = String(query.round)
  if (query.contentInclude) params.content_include = query.contentInclude
  if (query.contentExclude) params.content_exclude = query.contentExclude
  if (query.userId !== undefined && query.userId !== '')
    params.user_id = String(query.userId)
  return params
}

/** 标记请求体：logIds + mark → LogMarkDto（mark 默认 'flagged'） */
export function toLogMarkDto(
  input: LogMarkInput,
  defaultMark = 'flagged'
): LogMarkDto {
  return {
    log_ids: input.logIds,
    mark: input.mark ?? defaultMark,
  }
}

/** 清除请求体：LogClearInput → LogClearDto */
export function toLogClearDto(input: LogClearInput): LogClearDto {
  return {
    before_datetime: input.beforeDatetime ?? null,
    keep_marked: input.keepMarked ?? true,
  }
}

/** 刷新请求体：lastId → LogRefreshRequestDto */
export function toLogRefreshRequestDto(lastId: string | number): LogRefreshRequestDto {
  return { last_id: Number(lastId) || 0 }
}

/** 导出请求体：LogExportInput → LogExportRequestDto（POST /logs/export） */
export function toLogExportRequestDto(input: LogExportInput): LogExportRequestDto {
  return {
    log_ids: input.logIds,
    format: input.format ?? 'txt',
  }
}
