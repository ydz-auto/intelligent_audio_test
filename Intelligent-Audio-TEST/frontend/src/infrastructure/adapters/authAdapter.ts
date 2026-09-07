/**
 * Auth Adapter —— AuthDto(snake_case) ⇄ Domain auth (camelCase)
 *
 * 唯一允许出现 role_id → roleId 这类键名转换的地方。
 * 显式逐字段映射，禁止 ...raw/...dto 透传（分层架构对齐 W1-A）。
 */
import type { AuthLoginResult, AuthUser, CurrentUserInfo } from '../../domain/model/auth'
import type { AuthLoginResultDto, AuthMeResultDto, AuthUserDto } from '../dto/authDto'

/** 登录响应内嵌用户 → AuthUser（Domain） */
export function toAuthUser(raw: AuthUserDto): AuthUser {
  return {
    id: raw.id,
    username: raw.username ?? '',
    roleId: raw.role_id ?? null,
    roleName: raw.role_name ?? '',
    permissions: raw.permissions ?? [],
  }
}

/** 登录响应 → Domain AuthLoginResult */
export function toAuthLoginResult(raw: AuthLoginResultDto): AuthLoginResult {
  return {
    accessToken: raw.access_token,
    tokenType: raw.token_type,
    user: toAuthUser(raw.user),
  }
}

/** /auth/me 响应 → Domain CurrentUserInfo（/auth/me 不含角色名，roleName 缺省由调用方兜底） */
export function toCurrentUserInfo(raw: AuthMeResultDto): CurrentUserInfo {
  return {
    userId: raw.user_id ?? null,
    username: raw.username ?? '',
    roleId: raw.role_id ?? null,
    roleName: undefined,
    permissions: raw.permissions ?? [],
  }
}