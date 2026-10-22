/**
 * Access Token API module —— 真实接线（INT-1389）
 *
 * 端点（挂网关 /api/v1/auth 前缀，鉴权 = 当前登录用户本人）：
 *   POST   /auth/access-tokens            创建（明文仅返回一次）
 *   GET    /auth/access-tokens            列表（token_hint 掩码末 4 位）
 *   PATCH  /auth/access-tokens/{id}       重命名 / 换 scopes / 改 expires / 启停
 *   DELETE /auth/access-tokens/{id}       删除（软删）
 *
 * 响应契约（INT-1148 auth_service 接口层）：
 *   POST  → data 扁平条目 + 顶层 token（明文）；无 item 包裹；
 *   GET   → data: { total, items }；
 *   PATCH / DELETE → { success, message } 无 data。
 * 页面渲染层零 mock，本文件是唯一发真实请求的入口（无内存桩）。
 */
import { request, type RequestOptions } from '../http/client'
import type {
  AccessToken,
  AccessTokenCreatePayload,
  AccessTokenCreated,
  AccessTokenUpdatePayload,
} from '../../domain/model/accessToken'
import type {
  AccessTokenItemDto,
  AccessTokenCreateResultDto,
  AccessTokenUpdatePayloadDto,
} from '../dto/accessTokenDto'
import { toAccessToken, toAccessTokenCreated } from '../adapters/accessTokenAdapter'

/** 创建（POST /auth/access-tokens）——返回明文 token 仅此一次 */
export async function createAccessToken(
  payload: AccessTokenCreatePayload,
  options: RequestOptions = {},
): Promise<AccessTokenCreated> {
  const dto = await request<AccessTokenCreateResultDto>('POST', '/auth/access-tokens', {
    name: payload.name,
    scopes: payload.scopes.length > 0 ? payload.scopes : null,
    expires_at: payload.expiresAt ?? 0,
  }, options)
  return toAccessTokenCreated(dto)
}

/** 列表（GET /auth/access-tokens）——每行 token_hint 掩码末 4 位 */
export async function listAccessTokens(options: RequestOptions = {}): Promise<AccessToken[]> {
  const dto = await request<{ total: number; items: AccessTokenItemDto[] }>(
    'GET', '/auth/access-tokens', null, options,
  )
  return (dto?.items ?? []).map(toAccessToken)
}

/** 更新（PATCH /auth/access-tokens/{id}）——重命名 / 换 scopes / 改 expires / 启停。
 *  PATCH 成功响应无 data，回读详情供调用方（页面编辑弹窗 emit 的确认载荷需 AccessToken）。
 */
export async function updateAccessToken(
  id: number,
  payload: AccessTokenUpdatePayload,
  options: RequestOptions = {},
): Promise<AccessToken> {
  const body: AccessTokenUpdatePayloadDto = {}
  if (payload.name !== undefined) body.name = payload.name
  if (payload.scopes !== undefined) body.scopes = payload.scopes.length > 0 ? payload.scopes : null
  if (payload.expiresAt !== undefined) body.expires_at = payload.expiresAt ?? 0
  if (payload.status !== undefined) body.status = payload.status
  await request('PATCH', `/auth/access-tokens/${id}`, body, options)
  const dto = await request<AccessTokenItemDto>('GET', `/auth/access-tokens/${id}`, null, options)
  return toAccessToken(dto)
}

/** 删除（DELETE /auth/access-tokens/{id}；软删） */
export async function deleteAccessToken(id: number, options: RequestOptions = {}): Promise<void> {
  await request('DELETE', `/auth/access-tokens/${id}`, null, options)
}

/** 命名导出对象（供 api/index.ts 桶引用） */
export const accessTokenApi = {
  createAccessToken,
  listAccessTokens,
  updateAccessToken,
  deleteAccessToken,
}
