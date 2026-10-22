/**
 * 认证 DTO（infrastructure/dto 层；snake_case ↔ camelCase 唯一转换层）。
 * 对照 api_gateway auth_bp.py / user_bp.py / oauth_bp.py 响应契约
 * （POST /auth/login → { access_token, token_type, user }；
 * GET /auth/me → { user_id, username, role_id, permissions }；
 * GET /auth/oauth/providers → { providers: [...] }）。
 */
import { ROLE_META, type RoleCode } from '@/domain/models/role'
import type { AuthUser } from '@/domain/models/user'
import type { OAuthProvider } from '@/domain/models/auth'

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

/** 自助注册响应（POST /auth/register；成功回包 user_id） */
export interface RegisterResultDto {
  user_id?: number
}

/** 已启用 OAuth 提供方（GET /auth/oauth/providers，公开端点无凭证字段） */
export interface OAuthProviderPublicDto {
  id: number
  name: string
  slug: string
  icon: string
}

export interface PublicOAuthProvidersResultDto {
  providers: OAuthProviderPublicDto[]
}

export interface PasswordEncryptionKeyDto {
  enabled: boolean
  kid?: string
  public_key?: string
  fallback?: { kid: string; public_key: string }
}

/** 角色码 → 中文名（系统角色照 ROLE_META，自定义角色沿用原码；复用 user.dto.ts 口径） */
function toRoleName(roleCode: string): string {
  return ROLE_META[roleCode as RoleCode]?.name ?? roleCode
}

/** 登录响应内嵌用户 → Domain AuthUser（displayName 后端无字段，兜底 username） */
export function toAuthUser(raw: AuthUserDto): AuthUser {
  return {
    id: String(raw.id),
    username: raw.username ?? '',
    displayName: raw.username ?? '',
    roleName: toRoleName(raw.role_name ?? ''),
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

/**
 * GET /auth/me 响应 → AuthUser（/auth/me 契约无 role_name——INT-1226 兜底口径：
 * roleName 由调用方传入会话缓存角色码，照 ROLE_META 映射中文名，不因缺字段清空；
 * displayName 兜底 username）。
 */
export function toAuthUserFromMe(
  raw: AuthMeResultDto,
  fallbackRoleName = ''
): AuthUser {
  return {
    id: raw.user_id != null ? String(raw.user_id) : '',
    username: raw.username ?? '',
    displayName: raw.username ?? '',
    roleName: toRoleName(fallbackRoleName),
    permissions: raw.permissions ?? [],
  }
}

/** GET /auth/oauth/providers 内嵌列表 → Domain OAuthProvider（id 数值转字符串） */
export function toOAuthProviderPublicList(
  raw: OAuthProviderPublicDto[]
): OAuthProvider[] {
  return (raw ?? []).map((provider) => ({
    id: String(provider.id),
    name: provider.name ?? '',
    slug: provider.slug ?? '',
    icon: provider.icon ?? '',
  }))
}
