/**
 * Auth DTO —— snake_case
 * 与后端 api_gateway 的 /auth/login、/auth/me 响应一一对应。
 */

/** 登录响应内嵌用户（AuthLoginResult.user） */
export interface AuthUserDto {
  id: number
  username: string
  role_id: number | null
  role_name: string
  permissions: string[]
}

/** 登录响应（POST /auth/login；to_response 透传后端结构） */
export interface AuthLoginResultDto {
  access_token: string
  token_type: string
  user: AuthUserDto
}

/** 当前用户响应（GET /auth/me；AuthService.get_current_user_info） */
export interface AuthMeResultDto {
  user_id: number | null
  username: string
  role_id: number | null
  permissions: string[]
}

// ===== 登录体系改造（INT-51）=====

/** 已启用 OAuth 提供方（GET /auth/oauth/providers，公开无凭证字段） */
export interface OAuthProviderPublicDto {
  id: number
  name: string
  slug: string
  icon: string
}

/** OAuth 提供方（管理端 GET/POST/PUT /auth/oauth-providers；掩去 client_secret） */
export interface OAuthProviderDto {
  id: number
  name: string
  slug: string
  icon: string
  enabled: boolean
  client_id: string
  has_client_secret: boolean
  authorize_url: string
  token_url: string
  userinfo_url: string
  scopes: string
  user_id_field: string
  username_field: string
  display_name_field: string
  email_field: string
  created_at: string
  updated_at: string
}

// ===== 登录密码加密传输 / 第三方账号绑定（INT-147）=====

/** 登录密码加密公钥（GET /auth/login/encryption-key） */
export interface PasswordEncryptionKeyDto {
  enabled: boolean
  kid?: string
  public_key?: string
}

/** 第三方账号绑定（GET/POST /auth/oauth/bindings） */
export interface OAuthBindingDto {
  provider_id: number
  provider_name: string
  provider_slug: string
  provider_icon: string
  provider_user_id: string
}

/** OIDC Discovery 拉取结果（POST /auth/oauth/admin/discovery；原文整体返回） */
export interface OAuthDiscoveryResultDto {
  well_known_url: string
  discovery: Record<string, unknown>
}

// ===== 认证模式启动自检（INT-180）=====

/** 当前生效认证模式（GET /auth/mode；仅回枚举 mode 值） */
export interface AuthModeResultDto {
  auth_mode?: string
}
