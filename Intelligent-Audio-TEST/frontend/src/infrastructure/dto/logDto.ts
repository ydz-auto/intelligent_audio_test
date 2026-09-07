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

/** 对应后端 LogArchiveStatus */
export interface LogArchiveStatusDto {
  total_logs: number
  hot_logs: number
  cold_logs: number
  archive_files: string[]
  archive_dir: string
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
