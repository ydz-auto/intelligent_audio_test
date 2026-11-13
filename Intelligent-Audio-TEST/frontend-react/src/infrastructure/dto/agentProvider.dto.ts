/**
 * 模型供应商 DTO（infrastructure/dto 层；snake_case ↔ camelCase 唯一转换层）。
 * 契约来源：agent_service/interfaces/api/schemas.py + provider_routes.py（INT-2488，
 * 已合入 V10.11.2）。网关对 provider 路由做透明转发，响应不带 {success,data} 信封。
 *
 * - GET    /api/v1/agent/providers            → { items: ProviderResponse[] }
 * - POST   /api/v1/agent/providers            → ProviderResponse（201）
 * - PUT    /api/v1/agent/providers/{id}       → ProviderResponse（未出现字段不变，api_key 留空不变）
 * - DELETE /api/v1/agent/providers/{id}       → { id, status: 'DELETED' }
 * - POST   /api/v1/agent/providers/{id}/verify → VerifyProviderResponse
 * - POST   /api/v1/agent/providers/{id}/set-default → ProviderResponse
 * - GET    /api/v1/agent/model-catalog        → { fallback_context_window, bounds, models[] }
 *
 * 安全：DTO 只做字段搬运，任何入参里的明文 Key 只出现在请求体，不落缓存、不回写领域对象。
 */
import {
  type AgentProvider,
  type AgentProviderInput,
  type AgentProviderStatus,
  type AgentProviderVerification,
  type ContextWindowBounds,
  type ContextWindowSource,
  type ModelCatalog,
  type ModelCatalogItem,
  normalizeAgentProviderProtocol,
  normalizeAgentProviderStatus,
  normalizeContextWindowSource,
} from '@/domain/models/agentProvider'

/** ProviderResponse（agent_service snake_case） */
export interface AgentProviderDto {
  id: string
  owner_id?: number
  tenant_id?: string
  name?: string
  protocol?: string
  base_url?: string
  model?: string
  /** 掩码（sk-****abcd）；后端永不下发明文 */
  api_key_mask?: string
  context_window?: number | null
  context_window_source?: string
  effective_context_window?: number
  catalog_context_window?: number | null
  catalog_max_output_tokens?: number | null
  context_window_warning?: string | null
  context_window_warning_message?: string | null
  is_default?: boolean
  status?: string
  last_verified_at?: string | null
  created_at?: string | null
  updated_at?: string | null
}

/** GET /agent/providers 响应（ProviderListResponse） */
export interface AgentProviderListDto {
  items?: AgentProviderDto[]
}

/** POST /agent/providers/{id}/verify 响应 */
export interface AgentProviderVerifyDto {
  provider_id: string
  ok: boolean
  code?: string
  message?: string
  status?: string
  last_verified_at?: string | null
}

/** GET /agent/model-catalog 响应 */
export interface ModelCatalogDto {
  fallback_context_window?: number
  bounds?: {
    min?: number
    max?: number
    alignment?: number
  }
  models?: ModelCatalogItemDto[]
}

export interface ModelCatalogItemDto {
  protocol?: string
  match?: string
  context_window?: number
  max_output_tokens?: number
}

/** 新建载荷（CreateProviderRequest） */
export interface AgentProviderCreatePayload {
  name?: string
  protocol: string
  base_url: string
  model: string
  api_key: string
  context_window: number | null
}

/** 修改载荷（UpdateProviderRequest；未出现的字段不变） */
export interface AgentProviderUpdatePayload {
  name?: string
  protocol?: string
  base_url?: string
  model?: string
  api_key?: string
  context_window?: number | null
}

function toNumberOrNull(value: unknown): number | null {
  if (value === null || value === undefined || value === '') return null
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

/** ProviderResponse → 领域 AgentProvider */
export function toAgentProvider(dto: AgentProviderDto): AgentProvider {
  const protocol = normalizeAgentProviderProtocol(dto.protocol)
  const contextWindow = toNumberOrNull(dto.context_window)
  const effective =
    toNumberOrNull(dto.effective_context_window) ??
    contextWindow ??
    toNumberOrNull(dto.catalog_context_window) ??
    0
  return {
    id: String(dto.id ?? ''),
    name: dto.name?.trim() || dto.model?.trim() || '',
    protocol,
    baseUrl: dto.base_url ?? '',
    model: dto.model ?? '',
    apiKeyMask: dto.api_key_mask ?? '',
    contextWindow,
    contextWindowSource: normalizeContextWindowSource(dto.context_window_source),
    effectiveContextWindow: effective,
    catalogContextWindow: toNumberOrNull(dto.catalog_context_window),
    catalogMaxOutputTokens: toNumberOrNull(dto.catalog_max_output_tokens),
    contextWindowWarning: dto.context_window_warning ?? null,
    contextWindowWarningMessage: dto.context_window_warning_message ?? null,
    isDefault: dto.is_default === true,
    status: normalizeAgentProviderStatus(dto.status),
    lastVerifiedAt: dto.last_verified_at ?? null,
    createdAt: dto.created_at ?? null,
    updatedAt: dto.updated_at ?? null,
  }
}

export function toAgentProviders(dto: AgentProviderListDto | null | undefined): AgentProvider[] {
  return (dto?.items ?? []).map(toAgentProvider)
}

/** VerifyProviderResponse → 领域结果 */
export function toAgentProviderVerification(
  dto: AgentProviderVerifyDto
): AgentProviderVerification {
  return {
    providerId: String(dto.provider_id ?? ''),
    ok: dto.ok === true,
    code: dto.code ?? '',
    message: dto.message ?? '',
    status: normalizeAgentProviderStatus(dto.status),
    lastVerifiedAt: dto.last_verified_at ?? null,
  }
}

/** ModelCatalog 响应 → 领域模型目录 */
export function toModelCatalog(dto: ModelCatalogDto | null | undefined): ModelCatalog {
  const fallback = toNumberOrNull(dto?.fallback_context_window)
  const bounds: ContextWindowBounds = {
    min: toNumberOrNull(dto?.bounds?.min) ?? 8_192,
    max: toNumberOrNull(dto?.bounds?.max) ?? 2_097_152,
    alignment: toNumberOrNull(dto?.bounds?.alignment) ?? 1_024,
  }
  const models: ModelCatalogItem[] = (dto?.models ?? []).map((item) => ({
    protocol: item.protocol ?? '*',
    match: item.match ?? '',
    contextWindow: toNumberOrNull(item.context_window) ?? 0,
    maxOutputTokens: toNumberOrNull(item.max_output_tokens) ?? 0,
  }))
  return {
    fallbackContextWindow: fallback ?? 131_072,
    bounds,
    models,
  }
}

/** 领域输入 → 新建载荷（snake_case） */
export function toCreateProviderPayload(
  input: AgentProviderInput
): AgentProviderCreatePayload {
  return {
    name: input.name.trim() || undefined,
    protocol: input.protocol,
    base_url: input.baseUrl.trim(),
    model: input.model.trim(),
    api_key: input.apiKey?.trim() ?? '',
    context_window: input.contextWindow,
  }
}

/** 领域输入 → 修改载荷；api_key 留空表示不变（后端按未出现 / 空值处理） */
export function toUpdateProviderPayload(
  input: AgentProviderInput
): AgentProviderUpdatePayload {
  const payload: AgentProviderUpdatePayload = {
    name: input.name.trim() || undefined,
    protocol: input.protocol,
    base_url: input.baseUrl.trim(),
    model: input.model.trim(),
    context_window: input.contextWindow,
  }
  const key = input.apiKey?.trim()
  if (key) payload.api_key = key
  return payload
}

/** 供应商状态（供 tests / 页面复用同一归一逻辑） */
export type { AgentProviderStatus, ContextWindowSource }
