/**
 * Access Token DTO（infrastructure/dto 层；snake_case ↔ camelCase 唯一转换层）。
 * 对照 INT-1148 后端实施契约（auth_service/interfaces/api/routes.py，已合主分支）：
 * - 列表：GET /api/v1/auth/access-tokens → data: { total, items: [...] }（兼容裸数组）；
 * - 创建：POST /api/v1/auth/access-tokens → data: 扁平条目 + 顶层 token（明文一次）；
 * - 更新：PATCH /api/v1/auth/access-tokens/{id} → { success, message } 无 data；
 * - 删除：DELETE /api/v1/auth/access-tokens/{id} → { success, message } 无 data。
 * 时间字段 wire 形态（后端 _access_token_to_dict）：expires_at=0 永不过期，否则
 * ISO 字符串；last_used_at/created_at/deleted_at 为 ISO 字符串或 null。本层把 ISO
 * 解析为 Unix 毫秒（领域 AccessToken 时间字段统一 ms），UI 不再做 seconds*1000。
 */
import type { AccessToken, AccessTokenStatus } from '@/domain/models/access-token'

/** expires_at 入参/出参值：0=永不过期，否则 ISO 时间字符串（后端仅接受 0 或 ISO） */
export type AccessTokenExpiryValue = 0 | string

/** 后端条目（snake_case，与 access_tokens 表字段对齐） */
export interface AccessTokenItemDto {
  id: number
  name: string
  token_hint: string
  scopes: string[]
  /** 0=永不过期，否则 ISO 时间字符串（后端 _expires_at_out 输出） */
  expires_at: AccessTokenExpiryValue
  status: string
  last_used_at: string | null
  last_used_ip: string | null
  created_at: string | null
  deleted_at?: string | null
}

/** 列表响应（后端 data: { total, items }；兼容裸数组） */
export interface AccessTokenListDto {
  items?: AccessTokenItemDto[]
}

/** 创建响应：后端 data 为扁平条目，token（明文）在顶层 */
export interface AccessTokenCreatedDto extends AccessTokenItemDto {
  token: string
}

/** 创建载荷（snake_case；expires_at=0 永不过期或 ISO 字符串） */
export interface AccessTokenCreatePayload {
  name: string
  scopes: string[]
  expires_at: AccessTokenExpiryValue
}

/** 更新载荷（snake_case；传哪些字段更新哪些） */
export interface AccessTokenUpdatePayload {
  name?: string
  scopes?: string[]
  expires_at?: AccessTokenExpiryValue
  status?: AccessTokenStatus
}

function toAccessTokenStatus(raw: string | undefined): AccessTokenStatus {
  return raw === 'disabled' ? 'disabled' : 'enabled'
}

/** ISO 字符串 / null / 空 → Unix 毫秒；0/空输入归一为 0 */
function toEpochMs(value: string | null | undefined): number {
  if (!value) return 0
  return new Date(value).getTime()
}

/** 后端条目 → 领域 AccessToken（ISO 时间字段 → Unix 毫秒；0 仍表永不过期） */
export function toAccessToken(raw: AccessTokenItemDto): AccessToken {
  return {
    id: String(raw.id),
    name: raw.name ?? '',
    tokenHint: raw.token_hint ?? '',
    scopes: raw.scopes ?? [],
    expiresAt: raw.expires_at === 0 ? 0 : toEpochMs(raw.expires_at),
    status: toAccessTokenStatus(raw.status),
    lastUsedAt: raw.last_used_at != null ? new Date(raw.last_used_at).getTime() : null,
    lastUsedIp: raw.last_used_ip ?? null,
    createdAt: toEpochMs(raw.created_at),
    deletedAt: raw.deleted_at != null ? new Date(raw.deleted_at).getTime() : null,
  }
}

/** 列表响应 → 领域数组（兼容 items 包裹 / 裸数组） */
export function toAccessTokenList(raw: AccessTokenListDto | AccessTokenItemDto[] | null): AccessToken[] {
  if (!raw) return []
  const items = Array.isArray(raw) ? raw : (raw.items ?? [])
  return items.map(toAccessToken)
}
