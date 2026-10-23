/**
 * 被测 API DTO→Domain 适配器（infrastructure/adapters 层；16_设备域.md §3.6/§10）。
 * 消费 apis.dto.ts ApiItemDto（全字段），产出设备管理页 API 页签全量 ApiDevice 模型。
 * meta.protocol/meta.environment 从 meta JSON 抽取（§3.6 协议/环境列）；未显式标注时按
 * 首个 endpoint 协议前缀兜底（http→http、ws→ws），覆盖有端点但 meta 无 protocol 的存量记录
 * （INT-1223：api_url 已移除，协议推断改 meta.protocol / 端点前缀两来源；
 * 无端点且无 meta.protocol → protocol 为 null，列表显示「—」）。
 */
import type { ApiDevice, ApiEndpoint } from '@/domain/models/apiDevice'
import type { ApiItemDto } from '@/infrastructure/dto/apis.dto'

function readMetaString(meta: Record<string, unknown>, key: string): string | null {
  const value = meta[key]
  return typeof value === 'string' && value ? value : null
}

function fallbackProtocol(endpoint: string | null): string | null {
  if (!endpoint) return null
  if (/^wss:\/\//i.test(endpoint)) return 'wss'
  if (/^ws:\/\//i.test(endpoint)) return 'ws'
  if (/^https:\/\//i.test(endpoint)) return 'https'
  if (/^http:\/\//i.test(endpoint)) return 'http'
  return null
}

export function apiDeviceFromDto(dto: ApiItemDto): ApiDevice {
  const metaProtocol = readMetaString(dto.meta, 'protocol')
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
    protocol: metaProtocol ?? fallbackProtocol(dto.endpoints[0]?.endpoint ?? null),
    environment: metaEnv,
    proxyType: dto.proxy_type ?? null,
    proxyUrl: dto.proxy_url ?? null,
    algorithmType: dto.algorithm_type,
    defaultMaxProcess: dto.default_max_process,
    defaultMaxTimeout: dto.default_max_timeout,
    defaultMaxAudioDuration: dto.default_max_audio_duration,
    healthScore: dto.health_score,
    endpoints,
    rmsSplMappingId: dto.rms_spl_mapping_id,
    rmsSplMappingName: null,
    occupied: false,
    createdAt: dto.created_at,
    updatedAt: dto.updated_at,
  }
}
