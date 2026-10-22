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
  /** INT-1177 endpoint 级密钥池（多密钥轮换，INT-1230 审计 D1'/D6'）：
   * 每端点一池，password 输入不回显；保存时 adapter 层转 api_keys 落库 */
  apiKeys?: string[]
  /** 密钥池非敏感摘要（编辑回显「已配置 N 个 / 尾号」，不回显完整值） */
  apiKeysSummary?: ApiKeysSummary
  /** 端点行内密钥池 textarea 草稿（INT-1177 endpoint 级 UI）：每行一个密钥、
   * 可整段粘贴自动拆行；完整密钥不回显（读侧无值），留空保存时保留既有池。
   * 仅表单瞬态字段，adapter 层转 api_keys 落库，不回传自身。 */
  apiKeysText?: string
}

/**
 * API 元信息（对应后端 ApiItem.meta JSON 对象的已知键；
 * 该对象为整块透传的 JSON blob，后端按 Dict[str, Any] 原样存储）
 * INT-1177 密钥池（endpoint 级返工）：多密钥池已移至 api_endpoints[].api_keys，
 * meta 仅保留单值 apiKey（回退链 meta_key）；apiKeys/apiKeysSummary 不再承载。
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

/** 密钥池非敏感摘要（对应后端 ApiEndpointItem.api_keys_summary：{count, tails[]}） */
export interface ApiKeysSummary {
  count: number
  tails: string[]
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
  /** 被测设备类型（值 = DeviceType 枚举原值，决定执行路由） */
  deviceType?: string
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
