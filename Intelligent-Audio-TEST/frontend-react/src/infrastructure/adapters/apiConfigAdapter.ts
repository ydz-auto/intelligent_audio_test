/**
 * API 配置 DTO→Domain 适配器（infrastructure/adapters 层；10_测试执行.md §9）。
 * 消费 dto/ 原始 snake_case 类型，产出 domain 模型；现 Vue apiAdapter.ts 平移。
 */
import type {
  ApiConfig,
  ApiEndpoint,
  ApiHealthCheckResult,
  ApiParsePreviewResult,
  ApiProtoSymbolTable,
} from '@/domain/models/apiConfig'
import type {
  ApiEndpointItemDto,
  ApiHealthCheckDataDto,
  ApiItemDto,
  ApiParsePreviewDataDto,
  ApiProtoUploadDataDto,
} from '@/infrastructure/dto/apis.dto'
import { isApiProtocol } from '@/domain/models/apiProtocol'

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
    maxAudioDuration: dto.max_audio_duration,
    priority: dto.priority,
    status: dto.status,
    healthScore: dto.health_score,
    description: dto.description,
    // INT-1177 密钥池：读侧只拿摘要（count + 尾号），完整 key 后端不返回
    apiKeysSummary: dto.api_keys_summary,
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
    description: dto.description,
    status: toApiStatus(dto.status),
    algorithmType: dto.algorithm_type,
    defaultMaxProcess: dto.default_max_process,
    defaultMaxTimeout: dto.default_max_timeout,
    defaultMaxAudioDuration: dto.default_max_audio_duration,
    healthScore: dto.health_score,
    endpoints,
    maxConcurrent,
    // INT-1800：协议 / 流式性两维只读列（不再有 device_type、不再读 meta.protocol）；
    // 越界或缺失一律 null，界面显示「—」——前后端同批上线，前端不猜协议。
    protocol: isApiProtocol(dto.protocol) ? dto.protocol : null,
    streaming: dto.streaming === true,
    // INT-1777：meta / audio_config 读写通路（meta 整块 replace，前端以读侧为 base 合并；
    // audio_config 是顶层列，不是 meta.audio_config）
    meta: dto.meta ?? {},
    audioConfig: dto.audio_config ?? null,
  }
}

export function apiHealthFromDto(dto: ApiHealthCheckDataDto): ApiHealthCheckResult {
  return {
    id: dto.id,
    status: dto.status,
    healthScore: dto.health_score,
    endpointsStatus: dto.endpoints_status,
    statusCode: dto.status_code,
    responseTime: dto.response_time,
    error: dto.error,
    warning: dto.warning,
  }
}

/** proto 上传结果（INT-1952 §4.3）snake_case → 领域符号表；缺字段一律按空，不猜 */
export function apiProtoSymbolTableFromDto(dto: ApiProtoUploadDataDto): ApiProtoSymbolTable {
  return {
    objectKey: dto.object_key ?? '',
    sha256: dto.sha256 ?? '',
    size: dto.size ?? 0,
    services: (dto.services ?? []).map((service) => ({
      name: service.name ?? '',
      methods: (service.methods ?? []).map((method) => ({
        name: method.name ?? '',
        methodKind: method.method_kind ?? '',
        inputType: method.input_type ?? '',
        outputType: method.output_type ?? '',
        inputFields: method.input_fields ?? [],
        outputFields: method.output_fields ?? [],
      })),
    })),
  }
}

/** 解析预览结果（INT-1772）：纯结果透传，字段名已是请求里的配置键 */
export function apiParsePreviewFromDto(dto: ApiParsePreviewDataDto): ApiParsePreviewResult {
  return {
    extracted: dto?.extracted ?? {},
    unresolved: dto?.unresolved ?? [],
  }
}
