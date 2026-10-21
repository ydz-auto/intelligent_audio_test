/**
 * Access Token 域模型 —— camelCase
 * 契约对位 INT-1140「Access Token + 智能音频测试 skill / MCP」：
 *  - POST   /api/v1/auth/access-tokens（创建，明文仅返回一次）
 *  - GET    /api/v1/auth/access-tokens（列表，token_hint 掩码末 4 位）
 *  - PATCH  /api/v1/auth/access-tokens/{id}（重命名 / 换 scopes / 改 expires / 启停）
 *  - DELETE /api/v1/auth/access-tokens/{id}
 * 数据模型对齐 new-api user_access_tokens（只存哈希、明文创建显示一次、scopes、expires_at）。
 * 本文件零后端依赖，snake_case 转换收敛在 infrastructure 层。
 */

/** Token 启用状态（枚举化，无魔法串） */
export type AccessTokenStatus = 'enabled' | 'disabled'

/** 列表项（掩码 hint 仅末 4 位，完整明文只在创建响应出现一次） */
export interface AccessToken {
  id: number
  /** 令牌名称（创建时必填，可重命名） */
  name: string
  /** 掩码末 4 位（token_hint；完整明文不二次存储/展示） */
  tokenHint: string
  /** 生效权限点列表（空 / null = 继承用户全部权限） */
  scopes: string[]
  /** 过期时间（null = 永不过期；ISO 字符串 = 到期时刻） */
  expiresAt: string | null
  status: AccessTokenStatus
  /** 最近使用时间（从未使用为 null） */
  lastUsedAt: string | null
  createdAt: string
}

/** 创建载荷（name 必填；scopes 空 = 继承用户全部；expiresAt null = 永不过期） */
export interface AccessTokenCreatePayload {
  name: string
  scopes: string[]
  expiresAt: string | null
}

/** 创建结果：明文 token 仅此一次返回 + 已落库记录 */
export interface AccessTokenCreated {
  /** 完整明文 token（at_ 前缀 + 32 hex，仅此一次展示） */
  accessToken: string
  token: AccessToken
}

/** 更新载荷（PATCH 语义：全字段可选 = 只更新给定字段） */
export interface AccessTokenUpdatePayload {
  name?: string
  scopes?: string[]
  expiresAt?: string | null
  status?: AccessTokenStatus
}
