/**
 * Auth Adapter —— AuthDto(snake_case) ⇄ Domain auth (camelCase)
 *
 * 唯一允许出现 role_id → roleId 这类键名转换的地方。
 * 显式逐字段映射，禁止 ...raw/...dto 透传（分层架构对齐 W1-A）。
 */
import type { AuthLoginResult, AuthUser, CurrentUserInfo, OAuthProvider, OAuthProviderDetail } from '../../domain/model/auth'
import type { AuthLoginResultDto, AuthMeResultDto, AuthUserDto } from '../dto/authDto'
import type { OAuthProviderDto, OAuthProviderPublicDto } from '../dto/authDto'

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

// ===== 登录体系改造（INT-51）=====

/** 登录页公开提供方 → Domain（无凭证字段，透传） */
export function toOAuthProviderPublic(raw: OAuthProviderPublicDto): OAuthProvider {
  return {
    id: raw.id,
    name: raw.name ?? '',
    slug: raw.slug ?? '',
    icon: raw.icon ?? '',
  }
}

export function toOAuthProviderPublicList(raw: OAuthProviderPublicDto[]): OAuthProvider[] {
  return (raw ?? []).map(toOAuthProviderPublic)
}

/** 管理端提供方 → Domain（camelCase；client_secret 不存在于响应） */
export function toOAuthProvider(raw: OAuthProviderDto): OAuthProviderDetail {
  return {
    id: raw.id,
    name: raw.name ?? '',
    slug: raw.slug ?? '',
    icon: raw.icon ?? '',
    enabled: raw.enabled ?? false,
    clientId: raw.client_id ?? '',
    hasClientSecret: raw.has_client_secret ?? false,
    authorizeUrl: raw.authorize_url ?? '',
    tokenUrl: raw.token_url ?? '',
    userinfoUrl: raw.userinfo_url ?? '',
    scopes: raw.scopes ?? '',
    userIdField: raw.user_id_field ?? '',
    usernameField: raw.username_field ?? '',
    displayNameField: raw.display_name_field ?? '',
    emailField: raw.email_field ?? '',
    createdAt: raw.created_at ?? '',
    updatedAt: raw.updated_at ?? '',
  }
}

export function toOAuthProviderList(raw: OAuthProviderDto[]): OAuthProviderDetail[] {
  return (raw ?? []).map(toOAuthProvider)
}