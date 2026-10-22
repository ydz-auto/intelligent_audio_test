/**
 * Access Token DTO —— snake_case
 * 与后端 auth_service /api/v1/auth/access-tokens 契约一一对应（INT-1148：
 * id / user_id / name / token_hash / token_hint(末4位) / scopes / expires_at /
 * status / last_used_* / created_at；掩码不落明文）。
 * 创建响应 data 为扁平条目 + 顶层 token（明文仅此一次），无 item 包裹
 * （对齐 React access-token.dto：AccessTokenCreatedDto extends AccessTokenItemDto）。
 */

import type { AccessTokenStatus } from '../../domain/model/accessToken'

/** 列表项（GET /auth/access-tokens；后端 _access_token_to_dict 输出） */
export interface AccessTokenItemDto {
  id: number
  user_id?: number
  name: string
  /** 掩码末 4 位（完整明文不落库、不二次返回） */
  token_hint: string
  /** 权限点列表（空 / null = 继承用户全部） */
  scopes: string[] | null
  /** 0 = 永不过期；ISO 字符串 = 到期时刻 */
  expires_at: string | number | null
  status: AccessTokenStatus
  last_used_at: string | null
  last_used_ip?: string | null
  created_at: string | null
}

/** 创建载荷（POST /auth/access-tokens） */
export interface AccessTokenCreatePayloadDto {
  name: string
  scopes: string[] | null
  /** 0 / null = 永不过期 */
  expires_at: string | number | null
}

/** 创建结果（明文仅此一次返回；data 为扁平条目 + 顶层 token 明文） */
export interface AccessTokenCreateResultDto extends AccessTokenItemDto {
  /** 明文 token（仅此一次返回，库中只存哈希） */
  token: string
}

/** 更新载荷（PATCH /auth/access-tokens/{id}；键缺省 = 不修改） */
export interface AccessTokenUpdatePayloadDto {
  name?: string
  scopes?: string[] | null
  expires_at?: string | number | null
  status?: AccessTokenStatus
}
