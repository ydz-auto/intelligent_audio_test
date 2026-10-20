/**
 * 被测 API DTO（infrastructure/dto 层——snake_case 唯一出现层；10_测试执行.md §9）。
 * 形态对照 api_gateway/schemas/api.py ApiItem/ApiEndpointItem/ApiHealthCheckData 实测逐字段。
 */

/** GET /apis 端点项（api.py ApiEndpointItem） */
export interface ApiEndpointItemDto {
  id: string | null
  endpoint: string
  name: string | null
  max_process: number | null
  max_timeout: number | null
  max_audio_duration: number | null
  status: string | null
  health_score: number | null
  priority: number | null
  description: string | null
}

/** GET /apis 列表项（api.py ApiItem；GET /apis 实测无后端权限门槛） */
export interface ApiItemDto {
  id: number
  name: string
  vendor: string | null
  api_url: string | null
  description: string | null
  status: string | null
  meta: Record<string, unknown>
  /** 代理配置（api.py ApiItem proxy_type/proxy_url 实测；INT-1029） */
  proxy_type: string | null
  proxy_url: string | null
  algorithm_type: string | null
  default_max_process: number | null
  default_max_timeout: number | null
  default_max_audio_duration: number | null
  health_score: number | null
  endpoints: ApiEndpointItemDto[]
  output_types: string[] | null
  device_type: string | null
  adapter_class: string | null
  audio_config: Record<string, unknown> | null
  rms_spl_mapping_id: number | null
  created_at: string | null
  updated_at: string | null
}

/** POST /apis/{id}/health 结果（api.py ApiHealthCheckData） */
export interface ApiHealthCheckDataDto {
  id: number
  status: string
  health_score: number | null
  api_url_status: string | null
  endpoints_status: string | null
  status_code: number | null
  response_time: string | null
  error: string | null
  warning: string | null
}
