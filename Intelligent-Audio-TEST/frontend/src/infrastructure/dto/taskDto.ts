/**
 * Task DTO —— snake_case
 * 与后端 api_gateway/schemas/task.py 一一对应（serialize_by_alias=False 输出 snake_case）。
 */

/** 任务关联设备简报（TaskDeviceBrief） */
export interface TaskDeviceBriefDto {
  id: number
  name: string
  status?: string | null
  model?: string | null
}

/** 任务关联 API 简报（TaskApiBrief） */
export interface TaskApiBriefDto {
  id: number
  name: string
  status?: string | null
}

/** 任务关联报告项（TaskReportsData.reports[]） */
export interface TaskReportItemDto {
  id: number
  name: string
  status: string
  type: string
  created_at?: string
}

/** 任务关联报告聚合（TaskReportsData） */
export interface TaskReportsDataDto {
  count: number
  reports: TaskReportItemDto[]
}

// ===== 列表 / 详情 =====

/** 列表项（TaskListItem） */
export interface TaskDto {
  id: number | string
  name: string
  description?: string | null
  status: string
  type: string
  progress?: number | null
  config?: Record<string, any>
  algorithm_type?: string | null
  algorithm_params?: Record<string, any> | null
  started_at?: string | null
  completed_at?: string | null
  expected_total_time?: string | number | null
  expected_complete_time?: string | null
  used_time?: string | null
  total_cases?: number | null
  case_count?: number | null
  device_count?: number | null
  completed_cases?: number | null
  failed_cases?: number | null
  tags: string[]
  created_at?: string | null
  updated_at?: string | null
  finished_at?: string | null
  error?: string | null
  deleted?: boolean
  result?: any
  reports?: TaskReportsDataDto | null
  devices: TaskDeviceBriefDto[]
  apis: TaskApiBriefDto[]
}

/** 任务详情关联用例简报（TaskCaseBrief） */
export interface TaskCaseBriefDto {
  case_id: string
  name: string
  status?: string | null
  execution_status?: string | null
  evaluation_status?: string | null
  started_at?: string | null
  completed_at?: string | null
  duration?: number | null
  error_message?: string | null
  group_name?: string | null
  tags: string[]
}

/** 任务详情（TaskDetailData；在列表项字段之上新增 cases） */
export interface TaskDetailDto extends TaskDto {
  cases: TaskCaseBriefDto[]
}

// ===== 请求体 =====

/** 任务创建请求体（TaskCreateRequest） */
export interface TaskCreateDto {
  name: string
  type: string
  description?: string | null
  config?: Record<string, any>
  created_by?: string | null
  case_ids?: string[]
  device_ids?: number[]
  api_ids?: number[]
  tags?: string[]
  algorithm_type?: string | null
  algorithm_params?: Record<string, any> | null
}

/** 任务更新请求体（网关 update 直传 JSON，未走 schema 校验） */
export interface TaskUpdateDto {
  name?: string
  description?: string
}

/** 任务启动响应（TaskStartData） */
export interface TaskStartDto {
  task_id: string
  start_time?: unknown
  status: string
  expected_total_time?: number | null
  expected_complete_time?: string | null
}

/** 任务动态调整用例响应（TaskUpdateCasesData） */
export interface TaskUpdateCasesDto {
  task_id: string
  total_count: number
}

/** 任务统计响应（TaskStatsData） */
export interface TaskStatsDto {
  total: number
  completed: number
  failed: number
  pending: number
  skipped: number
  pass_rate: number
  tag_stats: Record<string, any>
}

/** 任务批量操作请求体（TaskBatchActionRequest） */
export interface TaskBatchActionDto {
  action: string
  task_ids: Array<number | string>
}

/** 任务合并请求体（TaskMergeRequest） */
export interface TaskMergeDto {
  task_ids: Array<number | string>
}

/** 任务动态调整用例请求体（TaskUpdateCasesRequest） */
export interface TaskUpdateCasesRequestDto {
  action: string
  case_ids: Array<number | string>
}

/** 任务列表查询参数（TaskListQuery） */
export interface TaskListQueryDto {
  page: number
  per_page: number
  status?: string
  type?: string
  algorithm_type?: string
  search?: string
  start_date?: string
  end_date?: string
}
