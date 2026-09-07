/**
 * APIConfig（外部被测 API 服务）领域模型 —— camelCase
 * 对应后端 api_gateway/schemas/api.py::ApiItem
 */
import type { ApiEndpointStatusType } from '../enums'

/** API 端点状态（语义与 ../../domain/enums.ts 的 ApiEndpointStatus 对齐，禁止各自硬编码） */
export type ApiEndpointStatus = ApiEndpointStatusType

/** API 端点（对应后端 ApiEndpointItem） */
export interface ApiEndpoint {
  id?: string
  endpoint: string
  name?: string
  maxProcess?: number
  maxTimeout?: number
  maxAudioDuration?: number
  status?: string
  healthScore?: number
  priority?: number
  description?: string
}

/**
 * API 元信息（对应后端 ApiItem.meta JSON 对象的已知键；
 * 该对象为整块透传的 JSON blob，后端按 Dict[str, Any] 原样存储）
 */
export interface ApiMeta {
  protocol?: string
  environment?: string
  version?: string
  apiKey?: string
  headers?: Record<string, string>
  /** 请求体模板（后端原值键 body_template，整块透传） */
  bodyTemplate?: Record<string, unknown>
  body_template?: Record<string, unknown>
  timeout?: number
}

/** API 配置（对应后端 ApiItem） */
export interface APIConfig {
  id: string | number
  name: string
  vendor?: string
  apiUrl?: string
  description?: string
  method?: string
  status: ApiEndpointStatus
  healthScore?: number
  meta?: ApiMeta
  algorithmType?: string
  defaultMaxProcess?: number
  defaultMaxTimeout?: number
  defaultMaxAudioDuration?: number
  endpoints?: ApiEndpoint[]
  createdAt?: string
  updatedAt?: string
  // ===== 运行时指标（进度/列表页附加字段） =====
  currentConcurrent?: number
  maxConcurrent?: number
  queueLength?: number
  avgResponseTime?: number
}

/** API 连接测试结果（对应后端 ApiHealthCheckData） */
export interface ApiHealthCheckResult {
  id: number
  status: string
  healthScore?: number
  apiUrlStatus?: string
  endpointsStatus?: string
  statusCode?: number
  responseTime?: string
  error?: string
  warning?: string
}

// ===== API 健康检查（前端展示用） =====

/** API 健康检查结果 */
export interface APIHealthResult {
  success: boolean
  latency?: number
  status?: string
  error?: string
  endpoints?: APIEndpointHealthResult[]
}

/** API 端点健康检查结果 */
export interface APIEndpointHealthResult {
  url: string
  name: string
  success: boolean
  latency: number
  error?: string
}

/** API 设置（前端本地状态） */
export interface APISettings {
  timeout?: number
  retry?: number
  [key: string]: any
}

/** API 健康检查弹窗数据 */
export interface APIHealthResultModalData {
  dimension: import('./dimension').Dimension
  results: APIHealthResult
}
