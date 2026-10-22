/**
 * APIConfig Adapter —— APIConfigDto(snake_case) ⇄ APIConfig(camelCase)
 */
import type { APIConfig, ApiEndpoint, ApiHealthCheckResult } from '../../domain/model/apiConfig'
import type { APIConfigDto, ApiEndpointDto, ApiUpsertDto, ApiHealthCheckDto } from '../dto/apiConfigDto'
import { ApiEndpointStatus } from '../../domain/enums'

// ===== DTO → Domain =====

/** meta blob 键名归一化：后端 snake_case api_key → 前端 camelCase。
 * INT-1177 endpoint 级返工：多密钥池已移至 endpoints[].api_keys，meta 不再
 * 承载 api_keys；仅转换单值密钥键，其余 meta 键整块透传（后端按 Dict 原样存储）。 */
function normalizeMetaFromDto(raw: Record<string, any> | undefined): APIConfig['meta'] {
  if (!raw || typeof raw !== 'object') return undefined
  const out: Record<string, any> = { ...raw }
  if ('api_key' in out) {
    out.apiKey = out.api_key
    delete out.api_key
  }
  return out as APIConfig['meta']
}

function toEndpoint(raw: ApiEndpointDto): ApiEndpoint {
  return {
    id: raw.id,
    endpoint: raw.endpoint,
    name: raw.name,
    maxProcess: raw.max_process,
    maxTimeout: raw.max_timeout,
    maxAudioDuration: raw.max_audio_duration,
    status: raw.status,
    healthScore: raw.health_score,
    priority: raw.priority,
    description: raw.description,
    // INT-1177 endpoint 级密钥池：完整 api_keys 响应零回显（后端读侧剥离），
    // 防御映射（若有）；编辑回显只依赖 api_keys_summary 摘要
    apiKeys: raw.api_keys,
    apiKeysSummary: raw.api_keys_summary,
  }
}

export function toAPIConfig(dto: APIConfigDto): APIConfig {
  return {
    id: dto.id,
    name: dto.name,
    vendor: dto.vendor,
    apiUrl: dto.api_url,
    description: dto.description,
    method: undefined,
    status: (dto.status || ApiEndpointStatus.OFFLINE) as APIConfig['status'],
    healthScore: dto.health_score,
    meta: normalizeMetaFromDto(dto.meta),
    algorithmType: dto.algorithm_type,
    defaultMaxProcess: dto.default_max_process,
    defaultMaxTimeout: dto.default_max_timeout,
    defaultMaxAudioDuration: dto.default_max_audio_duration,
    endpoints: dto.endpoints?.map(toEndpoint),
    outputTypes: dto.output_types,
    deviceType: dto.device_type,
    adapterClass: dto.adapter_class,
    proxyType: dto.proxy_type,
    proxyUrl: dto.proxy_url,
    audioConfig: dto.audio_config as import('../../domain/model/apiConfig').ApiAudioConfig,
    rmsSplMappingId: dto.rms_spl_mapping_id ?? undefined,
    createdAt: dto.created_at,
    updatedAt: dto.updated_at,
    currentConcurrent: dto.current_concurrent,
    maxConcurrent: dto.max_concurrent,
    queueLength: dto.queue_length,
    avgResponseTime: dto.avg_response_time,
  }
}

export function toAPIConfigList(dtos: APIConfigDto[] | null | undefined): APIConfig[] {
  return (dtos || []).map(toAPIConfig)
}

/** ApiHealthCheckDto → ApiHealthCheckResult（显式逐字段映射） */
export function toApiHealthCheckResult(dto: ApiHealthCheckDto): ApiHealthCheckResult {
  return {
    id: dto.id,
    status: dto.status,
    healthScore: dto.health_score ?? undefined,
    apiUrlStatus: dto.api_url_status ?? undefined,
    endpointsStatus: dto.endpoints_status ?? undefined,
    statusCode: dto.status_code ?? undefined,
    responseTime: dto.response_time ?? undefined,
    error: dto.error ?? undefined,
    warning: dto.warning ?? undefined,
  }
}

// ===== Domain → DTO（请求体） =====

/** INT-1177 endpoint 级密钥池提取：textarea 草稿（apiKeysText，每行一个 key、
 * 可整段粘贴拆行）优先，回退显式 apiKeys；空/留空返回 []。 */
function extractEndpointApiKeys(ep: ApiEndpoint): string[] {
  const source = ep.apiKeysText ?? (ep.apiKeys as string[] | undefined)
  if (Array.isArray(source)) {
    return source.map(v => String(v).trim()).filter(v => v !== '')
  }
  if (typeof source === 'string' && source.trim()) {
    return source.split(/\r?\n/).map(v => v.trim()).filter(v => v !== '')
  }
  return []
}

function toEndpointDto(ep: ApiEndpoint): ApiEndpointDto {
  const dto: ApiEndpointDto = {
    id: ep.id,
    endpoint: ep.endpoint,
    name: ep.name,
    max_process: ep.maxProcess,
    max_timeout: ep.maxTimeout,
    max_audio_duration: ep.maxAudioDuration,
    status: ep.status,
    priority: ep.priority,
    description: ep.description,
  }
  // INT-1177 endpoint 级密钥池：textarea 草稿/显式 apiKeys → api_keys 落库。
  // 空/留空不发送（读侧剥离完整密钥，编辑未改动时保留既有池，不误清空）。
  const keys = extractEndpointApiKeys(ep)
  if (keys.length > 0) {
    dto.api_keys = keys
  }
  return dto
}

/**
 * meta blob 键名归一化（写侧，INT-1177 endpoint 级返工）：
 * - 单值 apiKey（camelCase，表单） → api_key（后端密钥链 meta_key）
 * - 密钥池已移至 endpoints[].api_keys，meta 不再承载；apiKeys /
 *   apiKeysSummary 防御剔除（残留不落库）
 * 其余 meta 键整块透传（后端按 Dict 原样存储）。
 */
function normalizeMetaForUpsert(meta: Record<string, any> | undefined): Record<string, any> | undefined {
  if (!meta || typeof meta !== 'object') return undefined
  const out: Record<string, any> = {}
  for (const [key, value] of Object.entries(meta)) {
    if (key === 'apiKey') {
      out.api_key = value
    } else if (key === 'apiKeys' || key === 'apiKeysSummary') {
      // INT-1177 endpoint 级返工：meta 不再承载密钥池，防御剔除
      continue
    } else {
      out[key] = value
    }
  }
  return out
}

export function toApiUpsertDto(config: Partial<APIConfig>): ApiUpsertDto {
  return {
    name: config.name,
    vendor: config.vendor,
    api_url: config.apiUrl,
    description: config.description,
    status: config.status,
    meta: normalizeMetaForUpsert(config.meta as Record<string, any>),
    algorithm_type: config.algorithmType,
    default_max_process: config.defaultMaxProcess,
    default_max_timeout: config.defaultMaxTimeout,
    default_max_audio_duration: config.defaultMaxAudioDuration,
    endpoints: config.endpoints?.map(toEndpointDto),
    output_types: config.outputTypes,
    device_type: config.deviceType,
    adapter_class: config.adapterClass,
    proxy_type: config.proxyType,
    proxy_url: config.proxyUrl,
    audio_config: config.audioConfig
      ? {
          sample_rate: config.audioConfig.sampleRate,
          bit_depth: config.audioConfig.bitDepth,
          channels: config.audioConfig.channels,
          container: config.audioConfig.container ?? config.audioConfig.format,
          chunk_duration_ms: config.audioConfig.chunkDurationMs,
        }
      : undefined,
    rms_spl_mapping_id: config.rmsSplMappingId ?? null,
  }
}

/**
 * API 列表查询参数：camelCase Domain → snake_case query
 * 对应后端 ApiListQuery（page / per_page / keyword / status / algorithm_type）
 */
export function toApiQueryDto(query: Record<string, any>): Record<string, any> {
  const params: Record<string, any> = {}
  if (query.page !== undefined) params.page = query.page
  if (query.perPage !== undefined) params.per_page = query.perPage
  if (query.keyword) params.keyword = query.keyword
  if (query.status) params.status = query.status
  if (query.algorithmType) params.algorithm_type = query.algorithmType
  return params
}
