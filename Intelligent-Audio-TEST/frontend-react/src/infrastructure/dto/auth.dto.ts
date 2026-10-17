/**
 * 认证 DTO（infrastructure/dto 层；snake_case ↔ camelCase 唯一转换层）。
 * 对照 api_gateway auth_bp.py / auth_service.py 响应契约
 * （POST /auth/login → { access_token, token_type, user }；
 * GET /auth/me → { user_id, username, role_id, permissions }）。
 */
import type { AuthUser } from '@/domain/models/user'

export interface AuthUserDto {
  id: number
  username: string
  role_id: number | null
  role_name: string
  permissions: string[]
}

export interface AuthLoginResultDto {
  access_token: string
  token_type: string
  user: AuthUserDto
}

export interface AuthMeResultDto {
  user_id: number | null
  username: string
  role_id: number | null
  permissions: string[]
}

export interface AuthModeResultDto {
  auth_mode: string
}

export interface PasswordEncryptionKeyDto {
  enabled: boolean
  kid?: string
  public_key?: string
  fallback?: { kid: string; public_key: string }
}

/** 登录响应内嵌用户 → Domain AuthUser（displayName 后端无字段，兜底 username） */
export function toAuthUser(raw: AuthUserDto): AuthUser {
  return {
    id: String(raw.id),
    username: raw.username ?? '',
    displayName: raw.username ?? '',
    roleName: raw.role_name ?? '',
    permissions: raw.permissions ?? [],
  }
}

/** POST /auth/login 响应 → { accessToken, user } */
export function toAuthLoginResult(
  raw: AuthLoginResultDto
): { accessToken: string; user: AuthUser } {
  return {
    accessToken: raw.access_token,
    user: toAuthUser(raw.user),
  }
}

/** GET /auth/me 响应 → AuthUser（roleName 后端缺省空串，displayName 兜底 username） */
export function toAuthUserFromMe(raw: AuthMeResultDto): AuthUser {
  return {
    id: raw.user_id != null ? String(raw.user_id) : '',
    username: raw.username ?? '',
    displayName: raw.username ?? '',
    roleName: '',
    permissions: raw.permissions ?? [],
  }
}
