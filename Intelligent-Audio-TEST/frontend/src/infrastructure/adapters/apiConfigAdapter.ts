/**
 * APIConfig Adapter —— APIConfigDto(snake_case) ⇄ APIConfig(camelCase)
 */
import type { APIConfig, ApiEndpoint, ApiHealthCheckResult } from '../../domain/model/apiConfig'
import type { APIConfigDto, ApiEndpointDto, ApiUpsertDto, ApiHealthCheckDto } from '../dto/apiConfigDto'
import { ApiEndpointStatus } from '../../domain/enums'

// ===== DTO → Domain =====

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
    meta: dto.meta as APIConfig['meta'],
    algorithmType: dto.algorithm_type,
    defaultMaxProcess: dto.default_max_process,
    defaultMaxTimeout: dto.default_max_timeout,
    defaultMaxAudioDuration: dto.default_max_audio_duration,
    endpoints: dto.endpoints?.map(toEndpoint),
    outputTypes: dto.output_types,
    // INT-2025：协议 / 流式性两列（后端已废弃 device_type，读侧不再返回）
    protocol: dto.protocol ?? undefined,
    streaming: dto.streaming ?? undefined,
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

function toEndpointDto(ep: ApiEndpoint): ApiEndpointDto {
  return {
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
}

export function toApiUpsertDto(config: Partial<APIConfig>): ApiUpsertDto {
  return {
    name: config.name,
    vendor: config.vendor,
    api_url: config.apiUrl,
    description: config.description,
    status: config.status,
    meta: config.meta as Record<string, any>,
    algorithm_type: config.algorithmType,
    default_max_process: config.defaultMaxProcess,
    default_max_timeout: config.defaultMaxTimeout,
    default_max_audio_duration: config.defaultMaxAudioDuration,
    endpoints: config.endpoints?.map(toEndpointDto),
    output_types: config.outputTypes,
    // INT-2025：按后端新契约提交 protocol + streaming 两维；
    // device_type 已废弃（写侧携带非空值一律 400），这里不再出现该键。
    protocol: config.protocol,
    streaming: config.streaming,
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
