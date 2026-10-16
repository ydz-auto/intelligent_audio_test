/**
 * API 配置 DTO→Domain 适配器（infrastructure/adapters 层；10_测试执行.md §9）。
 * 消费 dto/ 原始 snake_case 类型，产出 domain 模型；现 Vue apiAdapter.ts 平移。
 */
import type {
  ApiConfig,
  ApiEndpoint,
  ApiHealthCheckResult,
} from '@/domain/models/apiConfig'
import type {
  ApiEndpointItemDto,
  ApiHealthCheckDataDto,
  ApiItemDto,
} from '@/infrastructure/dto/apis.dto'

export function toApiStatus(status: string | null): string | null {
  if (!status) return null
  // 在线=online/active 均视为在线语义；其余离线/未知
  return status === 'online' || status === 'active' ? 'online' : 'offline'
}

export function endpointFromDto(dto: ApiEndpointItemDto): ApiEndpoint {
  return {
    id: dto.id,
    endpoint: dto.endpoint,
    name: dto.name,
    maxProcess: dto.max_process,
    maxTimeout: dto.max_timeout,
    status: dto.status,
    healthScore: dto.health_score,
    description: dto.description,
  }
}

export function apiConfigFromDto(dto: ApiItemDto): ApiConfig {
  const endpoints = (dto.endpoints ?? []).map(endpointFromDto)
  // 端点级聚合 max（并发参数卡自动求合用；apiTest.steps.ts:154-158 口径平移）
  const maxProcessValues = endpoints
    .map((e) => e.maxProcess)
    .filter((v): v is number => typeof v === 'number')
  const maxConcurrent = maxProcessValues.length
    ? Math.max(...maxProcessValues, dto.default_max_process ?? 0)
    : (dto.default_max_process ?? 0)

  return {
    id: dto.id,
    name: dto.name,
    vendor: dto.vendor,
    apiUrl: dto.api_url,
    description: dto.description,
    status: toApiStatus(dto.status),
    algorithmType: dto.algorithm_type,
    defaultMaxProcess: dto.default_max_process,
    defaultMaxTimeout: dto.default_max_timeout,
    defaultMaxAudioDuration: dto.default_max_audio_duration,
    healthScore: dto.health_score,
    endpoints,
    maxConcurrent,
    deviceType: dto.device_type,
  }
}

export function apiHealthFromDto(dto: ApiHealthCheckDataDto): ApiHealthCheckResult {
  return {
    id: dto.id,
    status: dto.status,
    healthScore: dto.health_score,
    apiUrlStatus: dto.api_url_status,
    endpointsStatus: dto.endpoints_status,
    statusCode: dto.status_code,
    responseTime: dto.response_time,
    error: dto.error,
    warning: dto.warning,
  }
}
