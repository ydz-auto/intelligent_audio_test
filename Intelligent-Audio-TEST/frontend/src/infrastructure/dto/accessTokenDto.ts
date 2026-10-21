/**
 * Access Token DTO —— snake_case
 * 与后端 api_gateway /api/v1/auth/access-tokens 契约一一对应（INT-1140 数据模型：
 * id / user_id / name / token_hash / token_hint(末4位) / scopes / expires_at / status / last_used_* / created_at）。
 */

import type { AccessTokenStatus } from '../../domain/model/accessToken'

/** 列表项（GET /auth/access-tokens） */
export interface AccessTokenItemDto {
  id: number
  name: string
  /** 掩码末 4 位（完整明文不落库、不二次返回） */
  token_hint: string
  /** 权限点列表（空 / null = 继承用户全部） */
  scopes: string[] | null
  /** 0 = 永不过期；ISO 字符串 = 到期时刻 */
  expires_at: string | number | null
  status: AccessTokenStatus
  last_used_at: string | null
  created_at: string
}

/** 创建载荷（POST /auth/access-tokens） */
export interface AccessTokenCreatePayloadDto {
  name: string
  scopes: string[] | null
  /** 0 / null = 永不过期 */
  expires_at: string | number | null
}

/** 创建结果（明文仅此一次返回） */
export interface AccessTokenCreateResultDto {
  access_token: string
  token: AccessTokenItemDto
}

/** 更新载荷（PATCH /auth/access-tokens/{id}；键缺省 = 不修改） */
export interface AccessTokenUpdatePayloadDto {
  name?: string
  scopes?: string[] | null
  expires_at?: string | number | null
  status?: AccessTokenStatus
}
