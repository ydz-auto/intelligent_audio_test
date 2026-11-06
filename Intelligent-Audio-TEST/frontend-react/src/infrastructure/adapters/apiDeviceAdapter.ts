/**
 * 被测 API DTO→Domain 适配器（infrastructure/adapters 层；16_设备域.md §3.6/§10）。
 * 消费 apis.dto.ts ApiItemDto（全字段），产出设备管理页 API 页签全量 ApiDevice 模型。
 * INT-1800：协议只读 `apis.protocol` 列（B0 §3.4 单一来源）——不再读 `meta.protocol`，
 * 也不再按端点前缀兜底；流式性读 `apis.streaming` 列。带值的越界协议按 null 处理（显示「—」）。
 * `meta.environment` 仍从 meta JSON 抽取（环境不是本次抬列的两个属性之一）。
 */
import type { ApiDevice, ApiEndpoint } from '@/domain/models/apiDevice'
import { isApiProtocol } from '@/domain/models/apiProtocol'
import type { ApiItemDto } from '@/infrastructure/dto/apis.dto'

function readMetaString(meta: Record<string, unknown>, key: string): string | null {
  const value = meta[key]
  return typeof value === 'string' && value ? value : null
}

export function apiDeviceFromDto(dto: ApiItemDto): ApiDevice {
  const metaEnv = readMetaString(dto.meta, 'environment')
  const endpoints: ApiEndpoint[] = dto.endpoints.map((ep) => ({
    id: ep.id,
    endpoint: ep.endpoint,
    name: ep.name,
    maxProcess: ep.max_process,
    maxTimeout: ep.max_timeout,
    maxAudioDuration: ep.max_audio_duration,
    priority: ep.priority,
    status: ep.status,
    healthScore: ep.health_score,
    description: ep.description,
    // INT-1177 密钥池：读侧只拿摘要（count + 尾号），完整 key 后端不返回
    apiKeysSummary: ep.api_keys_summary,
  }))
  return {
    id: dto.id,
    name: dto.name,
    vendor: dto.vendor,
    description: dto.description,
    status: dto.status,
    meta: dto.meta,
    protocol: isApiProtocol(dto.protocol) ? dto.protocol : null,
    streaming: dto.streaming === true,
    environment: metaEnv,
    proxyType: dto.proxy_type ?? null,
    proxyUrl: dto.proxy_url ?? null,
    algorithmType: dto.algorithm_type,
    defaultMaxProcess: dto.default_max_process,
    defaultMaxTimeout: dto.default_max_timeout,
    defaultMaxAudioDuration: dto.default_max_audio_duration,
    healthScore: dto.health_score,
    endpoints,
    // INT-1938：§5.3 API 编辑弹窗（从「测试 API」页签行「编辑」打开）回显依赖该列
    // （device_type 已随 INT-1800 退役，协议/流式性走 protocol / streaming）
    audioConfig: dto.audio_config ?? null,
    rmsSplMappingId: dto.rms_spl_mapping_id,
    rmsSplMappingName: null,
    occupied: false,
    createdAt: dto.created_at,
    updatedAt: dto.updated_at,
  }
}
