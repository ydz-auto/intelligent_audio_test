/**
 * Socket 实时进度 DTO —— snake_case
 *
 * 对应后端契约 shared/schemas/socket_payloads.py::TaskProgressPayload，
 * adapter 层统一转换为 camelCase ReadModel。
 */

export interface TaskProgressCurrentCaseDto {
  case_id: string
  name: string
  step?: string
  start_time?: number
}

export interface TaskProgressCaseItemDto {
  id: string
  status: string
  execution_status?: string
  evaluation_status?: string
  duration?: number
  error_message?: string
  round_progress?: { current: number; total: number }
}

export interface ApiResourceStatusDto {
  id: string
  name: string
  current_concurrent?: number
  queue_length?: number
  avg_response_time?: number
  max_concurrent?: number
}

export interface TaskProgressDto {
  task_id: string
  total_progress: number
  status: string
  completed_count?: number
  in_progress_count?: number
  execution_failed_count?: number
  evaluation_failed_count?: number
  total_count?: number
  current_case?: TaskProgressCurrentCaseDto | null
  test_cases?: TaskProgressCaseItemDto[]
  logs?: Array<{ id: number; level: string; message: string; timestamp: number }>
  api_resources?: ApiResourceStatusDto[]
  expected_total_time?: string | number | null
  expected_complete_time?: string | null
  used_time?: string
}

/**
 * HTTP 轮询通道进度 DTO —— 对应 GET /tasks/{id}/progress（TaskProgressData）。
 * 字段较 Socket 通道少（无 test_cases/logs/api_resources，计数为 total/completed/failed 三项）。
 */
export interface TaskProgressHttpDto {
  task_id: string
  status: string
  total_cases: number
  completed_cases: number
  failed_cases: number
  progress: number
  current_case?: {
    case_id: string
    name: string
    step?: string
    started_at?: string | null
  } | null
  updated_at?: string | null
}
