/**
 * APIConfig（外部被测 API 服务）领域模型 —— camelCase
 * 对应后端 api_gateway/schemas/api.py::ApiItem
 */
import type { ApiEndpointStatusType, ProxyTypeType } from '../enums'

/** API 端点状态（语义与 ../../domain/enums.ts 的 ApiEndpointStatus 对齐，禁止各自硬编码） */
export type ApiEndpointStatus = ApiEndpointStatusType

/** 被测 API 网络代理类型（值 = 后端 proxy_type 原值；不配置 = 不用代理） */
export type ProxyType = ProxyTypeType

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
  /** 【历史遗留，只读】协议已抬为顶层 `protocol` 列（INT-1799）；新写入不再写 meta.protocol */
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

/** 目标音频格式声明（后端 apis.audio_config JSON；未配置回退 24000/s16/mono/pcm） */
export interface ApiAudioConfig {
  sampleRate?: number
  /** s16/s24/s32（或数字 16/24/32） */
  bitDepth?: string | number
  channels?: 1 | 2
  /** pcm/wav（UC-0901 键名 format 与 §2.2 键名 container 同义，后端双兼容） */
  container?: 'pcm' | 'wav' | (string & {})
  format?: 'pcm' | 'wav' | (string & {})
  chunkDurationMs?: number
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
  /** API 输出类型（值 = OutputType 枚举原值） */
  outputTypes?: string[]
  /**
   * 传输协议（INT-2025：读 `apis.protocol` 列，值域 http / websocket / sse / grpc；
   * 后端已废弃 `device_type`，执行道不再由它决定）
   */
  protocol?: string
  /** 流式性（INT-2025：读 `apis.streaming` 列；true = 流式/实时，执行道唯一判据） */
  streaming?: boolean
  /** 指定适配器类名（未指定时按 protocol+vendor 自动匹配） */
  adapterClass?: string
  /** 网络代理类型（http/https/socks5/socks5h；未配置 = 不用代理） */
  proxyType?: ProxyType
  /** 网络代理地址 [user:pass@]host:port（不含 scheme，INT-839：认证必填时校验必须带 user:pass@ 前缀） */
  proxyUrl?: string
  /** 目标音频格式声明 {sampleRate, bitDepth, channels, container} */
  audioConfig?: ApiAudioConfig
  /** 当前默认 RMS→SPL 映射 ID（api_rms_spl_mappings） */
  rmsSplMappingId?: number | null
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
