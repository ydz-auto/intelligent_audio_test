/**
 * Access Token Adapter —— AccessTokenDto(snake_case) ⇄ Domain accessToken (camelCase)
 *
 * 唯一允许出现 token_hint → tokenHint 这类键名转换的地方。
 * 显式逐字段映射，禁止 ...raw/...dto 透传（分层架构对齐 W1-A）。
 */
import type { AccessToken, AccessTokenCreated } from '../../domain/model/accessToken'
import type { AccessTokenItemDto, AccessTokenCreateResultDto } from '../dto/accessTokenDto'

/** 列表项 → Domain（expires_at: 0 或 null → null=永不过期） */
export function toAccessToken(raw: AccessTokenItemDto): AccessToken {
  return {
    id: raw.id,
    name: raw.name ?? '',
    tokenHint: raw.token_hint ?? '',
    scopes: raw.scopes ?? [],
    expiresAt: raw.expires_at === 0 || raw.expires_at == null ? null : String(raw.expires_at),
    status: raw.status ?? 'enabled',
    lastUsedAt: raw.last_used_at ?? null,
    createdAt: raw.created_at ?? '',
  }
}

/** 创建结果 → Domain（access_token 明文仅此一次，调用方只展示不落状态）。
 *  后端 data 为扁平条目 + 顶层 token（明文），无 item 包裹（INT-1148）。 */
export function toAccessTokenCreated(raw: AccessTokenCreateResultDto): AccessTokenCreated {
  return {
    accessToken: raw.token ?? '',
    token: toAccessToken(raw),
  }
}
