/**
 * 任务域真实接口 DTO（infrastructure/dto 层——snake_case 唯一出现层；09_任务域.md §10）。
 * 形态对照 api_gateway/schemas/task.py TaskListItem/TaskDetailData、published_task.py
 * PublishedTaskItem、log.py LogEntry 实测契约（Vue 侧 INT-623 已比对；本卡接线 React 侧）。
 * domain/models/task.ts 任务域模型同为 snake_case 字段（09 任务域卡时代落位），
 * 本层 DTO 与 Domain 近乎同构，转换函数仅补派生字段（api_count/source_task_count 等）。
 */

/** 分页信封（common.py PaginatedData，task_bp/published_task_bp 列表响应统一形态） */
export interface PaginatedDto<T> {
  items: T[]
  total: number
  page: number
  per_page: number
  pages: number
}

/** 任务列表项 DTO（task.py TaskListItem 实测） */
export interface TaskListItemDto {
  id: number
  name: string
  description: string | null
  status: string
  execution_status: string | null
  evaluation_status: string | null
  device_types: string[]
  config: Record<string, unknown>
  algorithm_type: string | null
  algorithm_params: Record<string, unknown> | null
  started_at: string | null
  completed_at: string | null
  total_cases: number | null
  case_count: number | null
  device_count: number | null
  completed_cases: number | null
  failed_cases: number | null
  tags: string[]
  created_at: string | null
  updated_at: string | null
  is_favorite: boolean | null
  /** INT-339：挑选合并容器标记（专有关系表存在性判定，§5.4） */
  is_cherry_pick: boolean | null
  deleted: boolean | null
  deleted_at: string | null
  deleted_by_user_id: number | null
  reports: TaskReportsDto | null
  devices: TaskDeviceBriefDto[]
  apis: TaskApiBriefDto[]
  source_tasks: TaskSourceBriefDto[]
}

export interface TaskReportItemDto {
  id: number
  name: string | null
  status: string | null
  type: string | null
  created_at: string | null
}

export interface TaskReportsDto {
  count: number
  reports: TaskReportItemDto[]
}

export interface TaskDeviceBriefDto {
  id: number
  name: string
  status: string | null
  model: string | null
}

export interface TaskApiBriefDto {
  id: number
  name: string
  status: string | null
}

export interface TaskSourceBriefDto {
  id: number
  name: string
  status: string | null
  total_cases: number | null
  completed_cases: number | null
  failed_cases: number | null
  created_at: string | null
}

/** 任务详情 DTO（task.py TaskDetailData 实测；与 domain TaskDetailData 同构） */
export interface TaskDetailDto {
  id: number
  name: string
  description: string | null
  status: string
  execution_status: string | null
  evaluation_status: string | null
  device_types: string[]
  config: Record<string, unknown>
  algorithm_type: string | null
  algorithm_params: Record<string, unknown> | null
  started_at: string | null
  completed_at: string | null
  expected_total_time: string | null
  expected_complete_time: string | null
  used_time: string | null
  total_cases: number | null
  case_count: number | null
  device_count: number | null
  completed_cases: number | null
  failed_cases: number | null
  tags: string[]
  cases: TaskCaseBriefDto[]
  devices: TaskDeviceBriefDto[]
  apis: TaskApiBriefDto[]
  created_at: string | null
  updated_at: string | null
}

export interface TaskCaseBriefDto {
  case_id: string
  name: string
  status: string | null
  execution_status: string | null
  evaluation_status: string | null
  started_at: string | null
  completed_at: string | null
  duration: number | null
  error_message: string | null
  group_name: string | null
  tags: string[]
  evaluation_dimensions: Array<{ id: number | string; name: string }>
}

/** 任务域统计 DTO（task.py TaskDomainStatsData；与 domain TaskDomainStats 同构） */
export interface TaskDomainStatsDto {
  total: number
  deleted_total: number
  status_counts: Record<string, number>
  type_counts: Record<string, number>
  trend: Array<{ key: string; count: number }>
  granularity: string
}

/** 已发布任务列表项 DTO（published_task.py PublishedTaskItem 实测） */
export interface PublishedTaskItemDto {
  id: number
  source_task_id: number | null
  name: string
  description: string | null
  type: 'api' | 'e2e' | null
  algorithm_type: string | null
  status: string
  benchmark: boolean
  version: number
  is_current: boolean
  version_count: number | null
  published_by: string | null
  published_at: string | null
  archived_at: string | null
  created_at: string | null
}

/** 日志行 DTO（log.py LogEntry 实测；GET /logs?task_id= 任务日志数据源） */
export interface TaskLogEntryDto {
  id: number
  /** LogEntry.time（MM-DD HH:mm:ss.mmm 字符串） */
  time: string | null
  level: string
  content: string | null
  module: string | null
  category: string | null
  source: string | null
  task_id: number | null
  test_case_id: string | null
}
