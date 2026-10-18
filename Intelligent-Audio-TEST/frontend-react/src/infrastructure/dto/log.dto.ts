/**
 * 日志 DTO（infrastructure 层；snake_case = 后端 api_gateway/schemas/log.py 原值）。
 * 转换只在 infrastructure/adapters 发生，interfaces 层零 snake_case。
 */

/** LogItemDto（对应后端 LogItem） */
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

/** LogListDto（对应后端 LogListData，INT-297 分页信封） */
export interface LogListDto {
  items: LogItemDto[]
  total: number
  page: number
  pages: number
  per_page: number
}

/** LogStatsDto（对应后端 LogStatsData） */
export interface LogStatsDto {
  total: number
  debug: number
  info: number
  warning: number
  error: number
  critical: number
}

/** LogRefreshDto（对应后端 LogRefreshData） */
export interface LogRefreshDto {
  items: LogItemDto[]
  count: number
  new_count: number
  last_id: number
}

/** LogMarkDto（PUT /logs/mark 请求体） */
export interface LogMarkDto {
  log_ids: (string | number)[]
  mark: string
}

/** LogClearDto（POST /logs/clear 请求体） */
export interface LogClearDto {
  before_datetime?: string
  keep_marked?: boolean
}

/** LogRefreshRequestDto（POST /logs/refresh 请求体） */
export interface LogRefreshRequestDto {
  last_id: number
}
