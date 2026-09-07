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