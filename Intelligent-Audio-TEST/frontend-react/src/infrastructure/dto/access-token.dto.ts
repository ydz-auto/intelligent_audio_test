/**
 * Access Token DTO（infrastructure/dto 层；snake_case ↔ camelCase 唯一转换层）。
 * 对照 INT-1140 数据模型草案 / INT-1148 后端实施契约（auth_service access_tokens 表）：
 * - 列表：GET /api/v1/auth/access-tokens → { items: [...] } 或裸数组（后端定稿前
 *   兼容 items 包裹与裸数组两种形态）；
 * - 创建：POST /api/v1/auth/access-tokens → { token: <明文一次>, item: {...} }；
 * - 更新：PATCH /api/v1/auth/access-tokens/{id} → 更新后条目；
 * - 删除：DELETE /api/v1/auth/access-tokens/{id} → 空。
 */
import type { AccessToken, AccessTokenStatus } from '@/domain/models/access-token'

/** 后端条目（snake_case，与 access_tokens 表字段对齐） */
export interface AccessTokenItemDto {
  id: number
  name: string
  token_hint: string
  scopes: string[]
  expires_at: number
  status: string
  last_used_at: number | null
  last_used_ip: string | null
  created_at: number
  deleted_at?: number | null
}

/** 列表响应（兼容 { items: [...] } 包裹与裸数组） */
export interface AccessTokenListDto {
  items?: AccessTokenItemDto[]
}

/** 创建响应：明文 token 仅此一次 */
export interface AccessTokenCreatedDto {
  token: string
  item?: AccessTokenItemDto
}

/** 创建载荷（snake_case） */
export interface AccessTokenCreatePayload {
  name: string
  scopes: string[]
  expires_at: number
}

/** 更新载荷（snake_case；传哪些字段更新哪些） */
export interface AccessTokenUpdatePayload {
  name?: string
  scopes?: string[]
  expires_at?: number
  status?: AccessTokenStatus
}

function toAccessTokenStatus(raw: string | undefined): AccessTokenStatus {
  return raw === 'disabled' ? 'disabled' : 'enabled'
}

/** 后端条目 → 领域 AccessToken */
export function toAccessToken(raw: AccessTokenItemDto): AccessToken {
  return {
    id: String(raw.id),
    name: raw.name ?? '',
    tokenHint: raw.token_hint ?? '',
    scopes: raw.scopes ?? [],
    expiresAt: raw.expires_at ?? 0,
    status: toAccessTokenStatus(raw.status),
    lastUsedAt: raw.last_used_at != null ? raw.last_used_at : null,
    lastUsedIp: raw.last_used_ip ?? null,
    createdAt: raw.created_at ?? 0,
    deletedAt: raw.deleted_at ?? null,
  }
}

/** 列表响应 → 领域数组（兼容 items 包裹 / 裸数组） */
export function toAccessTokenList(raw: AccessTokenListDto | AccessTokenItemDto[] | null): AccessToken[] {
  if (!raw) return []
  const items = Array.isArray(raw) ? raw : (raw.items ?? [])
  return items.map(toAccessToken)
}
