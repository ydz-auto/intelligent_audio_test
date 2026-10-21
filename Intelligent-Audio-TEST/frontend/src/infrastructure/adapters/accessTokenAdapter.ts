/**
 * Access Token Adapter —— AccessTokenDto(snake_case) ⇄ Domain accessToken (camelCase)
 *
 * 唯一允许出现 token_hint → tokenHint 这类键名转换的地方。
 * 显式逐字段映射，禁止 ...raw/...dto 透传（分层架构对齐 W1-A）。
 */
import type { AccessToken, AccessTokenCreated, AccessTokenStatus } from '../../domain/model/accessToken'
import type { AccessTokenCreatedDto, AccessTokenDto } from '../dto/accessTokenDto'

/** 后端 status 值 → Domain 枚举（未知值收敛为 enabled，避免界面裸奔） */
function toStatus(raw: string): AccessTokenStatus {
  return raw === 'disabled' ? 'disabled' : 'enabled'
}

/** DTO → Domain（掩码 token，无明文） */
export function toAccessToken(raw: AccessTokenDto): AccessToken {
  return {
    id: raw.id,
    userId: raw.user_id,
    name: raw.name ?? '',
    tokenHint: raw.token_hint ?? '',
    scopes: raw.scopes ?? [],
    status: toStatus(raw.status),
    expiresAt: raw.expires_at ?? 0,
    lastUsedAt: raw.last_used_at ?? null,
    lastUsedIp: raw.last_used_ip ?? null,
    createdAt: raw.created_at ?? null,
  }
}

export function toAccessTokenList(raw: AccessTokenDto[]): AccessToken[] {
  return (raw ?? []).map(toAccessToken)
}

/** 创建响应 DTO → Domain（含明文，仅创建时一次） */
export function toAccessTokenCreated(raw: AccessTokenCreatedDto): AccessTokenCreated {
  return {
    ...toAccessToken(raw),
    token: raw.token ?? '',
  }
}
