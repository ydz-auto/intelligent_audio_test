/**
 * Log（日志）DTO —— snake_case
 * 对应后端 api_gateway/schemas/log.py::LogItem / LogListData / LogStatsData /
 * LogRefreshData / LogArchiveStatus，及各请求体 Schema
 */
import type { PaginatedDto } from './common'

/** 对应后端 LogItem */
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

/** 对应后端 LogListData = PaginatedData[LogItem] */
export type LogListDto = PaginatedDto<LogItemDto>

/** 对应后端 LogStatsData */
export interface LogStatsDto {
  total: number
  debug: number
  info: number
  warning: number
  error: number
  critical: number
}

/** 对应后端 LogRefreshData */
export interface LogRefreshDto {
  items: LogItemDto[]
  count: number
  new_count: number
  last_id: number
}

/** 对应后端 GET /logs/archive/status 返回体。
 *  注意：该端点后端实现为 raw dict（success_response({totalLogs,...})），
 *  字段即 camelCase，不经 APIModel 序列化——DTO 按实际 wire 格式声明。
 */
export interface LogArchiveStatusDto {
  totalLogs?: number
  hotLogs?: number
  coldLogs?: number
  archiveDir?: string
  taskArchives?: number
  caseArchives?: number
  otherArchives?: number
}

/** 已归档日志列表（对应后端 GET /logs/archive/logs 返回体 {items,total,source}） */
export interface LogArchiveListDto {
  items: LogItemDto[]
  total: number
  source: string
}

/** 触发归档结果（对应后端 POST /logs/archive 返回体；dry_run 预览与真实归档两种形态） */
export interface LogArchiveResultDto {
  message?: string
  archived_count?: number
  deleted_count?: number
  archive_file?: string | null
  remaining_count?: number
  cold_logs_count?: number
  cutoff_date?: string
}

// ===== 请求体（snake_case） =====

/** 对应后端 LogMarkRequest */
export interface LogMarkDto {
  log_ids: (string | number)[]
  mark: string
}

/** 对应后端 LogClearRequest */
export interface LogClearDto {
  before_datetime?: string | null
  keep_marked?: boolean
}

/** 对应后端 LogRefreshRequest */
export interface LogRefreshRequestDto {
  last_id: number
}

/** 对应后端 LogArchiveRequest */
export interface LogArchiveRequestDto {
  days: number
  dry_run: boolean
}

/** 对应后端 LogExportRequest（POST /logs/export 请求体；log_ids 为 int 数组） */
export interface LogExportRequestDto {
  log_ids?: number[]
  format?: string
}
