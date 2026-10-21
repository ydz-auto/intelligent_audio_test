/**
 * Access Token + Agent skill 下载 API（infrastructure/api 层；INT-1153）。
 * 对照 INT-1148 后端实施契约（auth_service access_tokens 领域 + 网关 auth_bp 挂载）：
 *   POST   /api/v1/auth/access-tokens        创建（返回明文一次，只存哈希；data 扁平条目+token）
 *   GET    /api/v1/auth/access-tokens        列表（key 掩码 token_hint；data: {total, items}）
 *   PATCH  /api/v1/auth/access-tokens/{id}   重命名 / 换 scopes / 改 expires / 启停（成功无 data）
 *   DELETE /api/v1/auth/access-tokens/{id}   删除（软删；成功无 data）
 *   GET    /api/v1/agent/skill?base_url=...  下载 skill 包 ZIP（SKILL.md + MCP 模板）
 * 请求一律经 infrastructure/api/client.ts（统一信封解包 + 中文 ApiError），
 * 页面层只见 camelCase Domain 对象；snake_case↔camelCase 转换只发生在 dto 层。
 * expires_at 入参/出参均按后端契约：0=永不过期，否则 ISO 时间字符串。
 */
import type {
  AccessToken,
  AccessTokenStatus,
} from '@/domain/models/access-token'
import { apiClient } from '@/infrastructure/api/client'
import {
  toAccessToken,
  toAccessTokenList,
  type AccessTokenCreatedDto,
  type AccessTokenCreatePayload,
  type AccessTokenExpiryValue,
  type AccessTokenItemDto,
  type AccessTokenListDto,
  type AccessTokenUpdatePayload,
} from '@/infrastructure/dto/access-token.dto'

/** 创建 Access Token（返回明文仅一次；scopes 空数组 = 继承用户全部权限） */
export async function createAccessToken(input: {
  name: string
  scopes: string[]
  expiresAt: AccessTokenExpiryValue
}): Promise<{ token: string; item: AccessToken }> {
  const payload: AccessTokenCreatePayload = {
    name: input.name,
    scopes: input.scopes,
    expires_at: input.expiresAt,
  }
  // 后端创建响应 data 为扁平条目 + 顶层 token（明文），无 item 包裹
  const dto = await apiClient.post<AccessTokenCreatedDto | null>(
    '/auth/access-tokens',
    payload
  )
  if (!dto) return { token: '', item: toAccessToken(emptyItem()) }
  const { token, ...itemDto } = dto
  return {
    token: token ?? '',
    item: toAccessToken(itemDto as AccessTokenItemDto),
  }
}

function emptyItem(): AccessTokenItemDto {
  return {
    id: 0,
    name: '',
    token_hint: '',
    scopes: [],
    expires_at: 0,
    status: 'enabled',
    last_used_at: null,
    last_used_ip: null,
    created_at: null,
  }
}

/** 列表（token_hint 掩码） */
export async function listAccessTokens(): Promise<AccessToken[]> {
  const dto = await apiClient.get<AccessTokenListDto | AccessTokenItemDto[]>(
    '/auth/access-tokens'
  )
  return toAccessTokenList(dto as AccessTokenListDto)
}

/** 更新（重命名 / 换 scopes / 改 expires / 启停；只传要改的字段） */
export async function updateAccessToken(
  id: string,
  input: {
    name?: string
    scopes?: string[]
    expiresAt?: AccessTokenExpiryValue
    status?: AccessTokenStatus
  }
): Promise<void> {
  const payload: AccessTokenUpdatePayload = {
    name: input.name,
    scopes: input.scopes,
    expires_at: input.expiresAt,
    status: input.status,
  }
  // 显式过滤 undefined，避免把未改字段一并提交
  const body: AccessTokenUpdatePayload = Object.fromEntries(
    Object.entries(payload).filter(([, value]) => value !== undefined)
  ) as AccessTokenUpdatePayload
  // 后端 PATCH 成功响应为 { success, message } 无 data；仅确认成功，列表由 invalidate 刷新
  await apiClient.patch<null>(`/auth/access-tokens/${id}`, body)
}

/** 删除（软删；删除后 token 立即失效） */
export async function deleteAccessToken(id: string): Promise<void> {
  await apiClient.delete(`/auth/access-tokens/${id}`)
}

/** 下载 skill 包（GET /api/v1/agent/skill?base_url=…；ZIP 二进制流） */
export async function downloadSkill(baseUrl: string): Promise<Blob> {
  return apiClient.get<Blob>('/agent/skill', {
    params: { base_url: baseUrl },
    responseType: 'blob',
    unwrapResponse: false,
  })
}
