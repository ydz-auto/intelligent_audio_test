/**
 * APIConfig（外部被测 API）DTO —— snake_case
 * 对应后端 api_gateway/schemas/api.py::ApiItem / ApiCreateInput
 */

export interface ApiEndpointDto {
  id?: string
  endpoint: string
  name?: string
  max_process?: number
  max_timeout?: number
  max_audio_duration?: number
  status?: string
  health_score?: number
  priority?: number
  description?: string
}

export interface APIConfigDto {
  id: number | string
  name: string
  vendor?: string
  api_url?: string
  description?: string
  status?: string
  meta?: Record<string, any>
  algorithm_type?: string
  default_max_process?: number
  default_max_timeout?: number
  default_max_audio_duration?: number
  health_score?: number
  endpoints?: ApiEndpointDto[]
  created_at?: string
  updated_at?: string
  // 运行时指标（列表页附加）
  current_concurrent?: number
  max_concurrent?: number
  queue_length?: number
  avg_response_time?: number
}

/** API 创建/更新请求体 */
export interface ApiUpsertDto {
  name?: string
  vendor?: string
  api_url?: string
  description?: string
  status?: string
  meta?: Record<string, any>
  algorithm_type?: string
  default_max_process?: number
  default_max_timeout?: number
  default_max_audio_duration?: number
  endpoints?: ApiEndpointDto[]
}

/** 对应后端 ApiHealthCheckData（POST /apis/{id}/health 返回） */
export interface ApiHealthCheckDto {
  id: number
  status: string
  health_score?: number | null
  api_url_status?: string | null
  endpoints_status?: string | null
  status_code?: number | null
  response_time?: string | null
  error?: string | null
  warning?: string | null
}
