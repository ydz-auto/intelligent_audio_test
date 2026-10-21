/**
 * Access Token DTO —— snake_case
 * 对应后端 /api/v1/auth/access-tokens（auth_service，经网关转发）响应。
 */

/** 创建请求（POST /api/v1/auth/access-tokens） */
export interface CreateAccessTokenRequestDto {
  name: string
  scopes?: string[]
  expires_at?: number | string
}

/** 更新请求（PATCH /api/v1/auth/access-tokens/{id}；键缺省 = 不修改） */
export interface UpdateAccessTokenRequestDto {
  name?: string | null
  scopes?: string[] | null
  status?: string | null
  expires_at?: number | string | null
}

/** 列表/详情内的 token 项（掩码，无明文/哈希） */
export interface AccessTokenDto {
  id: number
  user_id: number
  name: string
  token_hint: string
  scopes: string[]
  status: string
  /** 0 = 永不过期，否则 ISO 字符串 */
  expires_at: number | string
  last_used_at: string | null
  last_used_ip: string | null
  created_at: string | null
}

/** 创建响应：在 AccessTokenDto 基础上附加明文（仅此一次） */
export interface AccessTokenCreatedDto extends AccessTokenDto {
  token: string
}

/** 列表响应 data（GET /api/v1/auth/access-tokens） */
export interface AccessTokenListResultDto {
  total: number
  items: AccessTokenDto[]
}
