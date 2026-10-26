/**
 * APIConfig（外部被测 API）DTO —— snake_case
 * 对应后端 api_gateway/schemas/api.py::ApiItem / ApiCreateInput
 */

/** 被测 API 网络代理类型（INT-839，值 = 后端 proxy_type 原值；NULL 或空 = 不用代理） */
export type ApiProxyType = 'http' | 'https' | 'socks5' | 'socks5h'

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
  output_types?: string[]
  /** 传输协议（INT-2025：apis.protocol 列，http/websocket/sse/grpc；读侧不再返回 device_type） */
  protocol?: string
  /** 流式性（INT-2025：apis.streaming 列；true = 流式） */
  streaming?: boolean
  adapter_class?: string
  /** 网络代理类型（INT-839：http/https/socks5/socks5h；NULL 或空 = 不用代理） */
  proxy_type?: ApiProxyType
  /** 网络代理地址 [user:pass@]host:port（不含 scheme） */
  proxy_url?: string
  audio_config?: Record<string, any>
  rms_spl_mapping_id?: number | null
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
  output_types?: string[]
  /** 传输协议（INT-2025：写侧顶层列；不再提交已废弃的 device_type） */
  protocol?: string
  /** 流式性（INT-2025：写侧顶层布尔列） */
  streaming?: boolean
  adapter_class?: string
  /** 网络代理类型（INT-839：http/https/socks5/socks5h；NULL 或空 = 不用代理） */
  proxy_type?: ApiProxyType
  /** 网络代理地址 [user:pass@]host:port（不含 scheme） */
  proxy_url?: string
  audio_config?: Record<string, any>
  rms_spl_mapping_id?: number | null
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
