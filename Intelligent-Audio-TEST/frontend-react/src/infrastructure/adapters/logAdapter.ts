/**
 * Log DTO → Domain 转换层（infrastructure/adapters 唯一转换层；对齐整站
 * `infrastructure/adapters/*` 约定——17_配置运维.md §4）。interfaces 层只见
 * camelCase Domain 字段，本层是唯一知 snake_case 的地方。
 * 查询参数/请求体转换（Domain → snake_case DTO）在同文件下半部分。
 */
import type {
  Log,
  LogPage,
  LogStatsData,
  LogRefreshResult,
  LogQuery,
  LogExportQuery,
  LogMarkInput,
  LogClearInput,
} from '@/domain/models/log'
import type {
  LogItemDto,
  LogListDto,
  LogStatsDto,
  LogRefreshDto,
  LogMarkDto,
  LogClearDto,
  LogRefreshRequestDto,
} from '@/infrastructure/dto/log.dto'

/** 数值兜底（null/undefined → 0） */
function toNum(value: unknown): number {
  const n = Number(value)
  return Number.isFinite(n) ? n : 0
}

// ===== DTO → Domain =====

/** LogItemDto → Log（显式逐字段映射；时间字段保留后端原值） */
export function toLog(dto: LogItemDto): Log {
  return {
    id: dto.id,
    time: dto.time ?? '',
    level: dto.level ?? '',
    category: dto.category ?? '',
    module: dto.module ?? '',
    source: dto.source ?? '',
    content: dto.content ?? '',
    mark: dto.mark ?? undefined,
    deviceId: dto.device_id ?? undefined,
    taskId: dto.task_id ?? undefined,
    apiId: dto.api_id ?? undefined,
    testCaseId: dto.test_case_id ?? undefined,
    threadId: dto.thread_id ?? undefined,
    algorithmType: dto.algorithm_type ?? undefined,
  }
}

/** LogListDto → LogPage（分页信封） */
export function toLogPage(dto: LogListDto | null | undefined): LogPage {
  const safe = (dto ?? {}) as Partial<LogListDto>
  return {
    items: (safe.items ?? []).map(toLog),
    total: toNum(safe.total),
    page: toNum(safe.page) || 1,
    pages: toNum(safe.pages) || 1,
    perPage: toNum(safe.per_page) || 50,
  }
}

/** LogStatsDto → LogStatsData（数值兜底为 0） */
export function toLogStatsData(dto: LogStatsDto | null | undefined): LogStatsData {
  const safe = (dto ?? {}) as Partial<LogStatsDto>
  return {
    total: toNum(safe.total),
    debug: toNum(safe.debug),
    info: toNum(safe.info),
    warning: toNum(safe.warning),
    error: toNum(safe.error),
    critical: toNum(safe.critical),
  }
}

/** LogRefreshDto → LogRefreshResult */
export function toLogRefreshResult(dto: LogRefreshDto | null | undefined): LogRefreshResult {
  const safe = (dto ?? {}) as Partial<LogRefreshDto>
  return {
    items: (safe.items ?? []).map(toLog),
    count: toNum(safe.count),
    newCount: toNum(safe.new_count),
    lastId: toNum(safe.last_id),
  }
}

// ===== Domain → DTO（查询参数/请求体，显式 snake_case） =====

/**
 * LogQuery → snake_case query 参数。
 * 后端 LogListQuery（api_gateway/schemas/log.py:84）：page/per_page/level/module/
 * category/keyword/content_include/content_exclude/start_time/end_time/mark/
 * device_id/task_id/api_id/test_case_id/thread_id/algorithm_type/evaluation_id/round。
 * level 为多级别逗号串（task_service log_repository level.split(',') 实测）。
 */
export function toLogQueryDto(query: LogQuery): Record<string, string | number> {
  const params: Record<string, string | number> = {}
  if (query.page !== undefined) params.page = query.page
  if (query.perPage !== undefined) params.per_page = query.perPage
  if (query.level) params.level = query.level
  if (query.module && query.module !== 'all') params.module = query.module
  if (query.category && query.category !== 'all') params.category = query.category
  if (query.mark && query.mark !== 'all') params.mark = query.mark
  if (query.keyword) params.keyword = query.keyword
  if (query.algorithmType && query.algorithmType !== 'all') params.algorithm_type = query.algorithmType
  if (query.startTime) params.start_time = query.startTime
  if (query.endTime) params.end_time = query.endTime
  if (query.deviceId) params.device_id = String(query.deviceId)
  if (query.taskId) params.task_id = String(query.taskId)
  if (query.evaluationId) params.evaluation_id = String(query.evaluationId)
  if (query.userId) params.user_id = String(query.userId)
  if (query.threadId) params.thread_id = String(query.threadId)
  if (query.contentInclude) params.content_include = query.contentInclude
  if (query.contentExclude) params.content_exclude = query.contentExclude
  return params
}

/** LogExportQuery → snake_case query（level/module；log_ids/format 走请求体） */
export function toLogExportQueryDto(query: LogExportQuery): Record<string, string | number> {
  const params: Record<string, string | number> = {}
  if (query.level) params.level = query.level
  if (query.module) params.module = query.module
  return params
}

/** LogMarkInput → LogMarkDto（mark 默认 'flagged'，与后端 LogMarkRequest 一致） */
export function toLogMarkDto(input: LogMarkInput, defaultMark = 'flagged'): LogMarkDto {
  return {
    log_ids: input.logIds,
    mark: input.mark ?? defaultMark,
  }
}

/** LogClearInput → LogClearDto */
export function toLogClearDto(input: LogClearInput): LogClearDto {
  return {
    before_datetime: input.beforeDatetime,
    keep_marked: input.keepMarked,
  }
}

/** lastId → LogRefreshRequestDto */
export function toLogRefreshRequestDto(lastId: string | number): LogRefreshRequestDto {
  return { last_id: Number(lastId) || 0 }
}
