/**
 * Log Adapter —— LogDto(snake_case) → Log Domain(camelCase)
 *
 * 出口契约：domain/model/log.ts；查询参数/请求体转换在同文件下半部分。
 */
import type {
  Log,
  LogPage,
  LogStatsData,
  LogRefreshResult,
  LogArchiveStatus,
  LogQuery,
  LogExportQuery,
  LogMarkInput,
  LogClearInput,
} from '../../domain/model/log'
import type {
  LogItemDto,
  LogListDto,
  LogStatsDto,
  LogRefreshDto,
  LogArchiveStatusDto,
  LogMarkDto,
  LogClearDto,
  LogRefreshRequestDto,
} from '../dto/logDto'
import { toSafeNumber as toNum, toPaginated } from './commonAdapter'

// ===== DTO → Domain =====

/** LogItemDto → Log（显式逐字段映射；时间字段保留后端原值） */
export function toLog(dto: LogItemDto): Log {
  return {
    id: dto.id,
    level: dto.level ?? '',
    module: dto.module ?? undefined,
    category: dto.category ?? undefined,
    source: dto.source ?? undefined,
    content: dto.content ?? '',
    time: dto.time,
    taskId: dto.task_id ?? undefined,
    deviceId: dto.device_id ?? undefined,
    apiId: dto.api_id ?? undefined,
    threadId: dto.thread_id ?? undefined,
    mark: dto.mark ?? undefined,
    testCaseId: dto.test_case_id ?? undefined,
    algorithmType: dto.algorithm_type ?? undefined,
  }
}

/** 日志分页 → LogPage（复用 commonAdapter.toPaginated） */
export function toLogPage(dto: LogListDto | null | undefined): LogPage {
  return toPaginated(dto, toLog)
}

/** 日志统计 → LogStatsData（数值兜底为 0） */
export function toLogStatsData(dto: LogStatsDto | null | undefined): LogStatsData {
  return {
    total: toNum(dto?.total),
    debug: toNum(dto?.debug),
    info: toNum(dto?.info),
    warning: toNum(dto?.warning),
    error: toNum(dto?.error),
    critical: toNum(dto?.critical),
  }
}

/** 日志刷新结果 → LogRefreshResult */
export function toLogRefreshResult(dto: LogRefreshDto | null | undefined): LogRefreshResult {
  return {
    items: (dto?.items ?? []).map(toLog),
    count: dto?.count ?? 0,
    newCount: dto?.new_count ?? 0,
    lastId: dto?.last_id ?? 0,
  }
}

/** 归档状态 → LogArchiveStatus */
export function toLogArchiveStatus(dto: LogArchiveStatusDto | null | undefined): LogArchiveStatus {
  return {
    totalLogs: dto?.total_logs ?? 0,
    hotLogs: dto?.hot_logs ?? 0,
    coldLogs: dto?.cold_logs ?? 0,
    archiveFiles: dto?.archive_files ?? [],
    archiveDir: dto?.archive_dir ?? '',
  }
}

// ===== Domain → DTO（查询参数/请求体，显式 snake_case） =====

/**
 * 日志查询条件 → snake_case query
 * 后端 LogListQuery：page / per_page / level / module / category / keyword /
 * content_include / content_exclude / start_time / end_time / mark / device_id /
 * task_id / api_id / test_case_id / thread_id / algorithm_type
 */
export function toLogQueryDto(query: LogQuery): Record<string, string | number | boolean> {
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
  if (query.deviceId !== undefined && query.deviceId !== '') params.device_id = String(query.deviceId)
  if (query.taskId !== undefined && query.taskId !== '') params.task_id = String(query.taskId)
  if (query.threadId) params.thread_id = String(query.threadId)
  if (query.testCaseId) params.test_case_id = String(query.testCaseId)
  if (query.contentInclude) params.content_include = query.contentInclude
  if (query.contentExclude) params.content_exclude = query.contentExclude
  return params
}

/** 日志导出查询 → snake_case query（含逗号分隔 log_ids 与 format） */
export function toLogExportQueryDto(query: LogExportQuery): Record<string, string | number> {
  const params: Record<string, string | number> = toLogQueryDto(query) as Record<string, string | number>
  if (query.logIds) params.log_ids = query.logIds
  if (query.format) params.format = query.format
  return params
}

/** 标记请求体：logIds + mark → LogMarkDto */
export function toLogMarkDto(input: LogMarkInput, defaultMark = 'flagged'): LogMarkDto {
  return {
    log_ids: input.logIds,
    mark: input.mark ?? defaultMark,
  }
}

/** 清除请求体：LogClearInput → LogClearDto */
export function toLogClearDto(input: LogClearInput): LogClearDto {
  return {
    before_datetime: input.beforeDatetime,
    keep_marked: input.keepMarked,
  }
}

/** 刷新请求体：lastId → LogRefreshRequestDto */
export function toLogRefreshRequestDto(lastId: string | number): LogRefreshRequestDto {
  return { last_id: Number(lastId) || 0 }
}
