/**
 * 认证领域模型 —— camelCase
 * 对应后端 /auth/login（AuthService._issue_token，AUTH_MODE=dev 时可用）
 * 与 /auth/me（AuthService.get_current_user_info）
 *
 * 后端序列化输出为 snake_case，由 Infrastructure api 层负责字段名转换，
 * 本层零后端依赖。
 */

/** 用户信息（登录 /auth/me 统一 Domain 契约） */
export interface AuthUser {
  id: number
  username: string
  roleId: number | null
  roleName: string
  permissions: string[]
}

/** 登录成功结果（对应后端 /auth/login 响应） */
export interface AuthLoginResult {
  accessToken: string
  tokenType: string
  user: AuthUser
}

/** 当前登录用户信息（对应后端 /auth/me 响应；roleName 后端可能缺省） */
export interface CurrentUserInfo {
  userId: number | null
  username: string
  roleId: number | null
  roleName?: string
  permissions: string[]
}