/**
 * 个人中心第三方绑定 API（infrastructure/api 层；接线 INT-650 切真实接口）。
 * 契约对位 13_个人中心.md §2.0（oauth_bp.py 实测）：
 *  - 绑定列表 GET /auth/oauth/bindings（登录即可，端点内自验用户态）
 *  - 绑定 POST /auth/oauth/bindings body { bind_ticket }（幂等 no-op）
 *  - 解绑 DELETE /auth/oauth/bindings/{provider_id}（幂等，无绑定行也成功）
 *  - 提供方列表 GET /auth/oauth/providers（公开）→ 复用 authApi.listPublicOAuthProviders
 * 绑定授权跳转 authApi.beginOAuthAuthorize（slug,'bind'）。
 */
import type { OAuthBinding } from '@/domain/models/profile'
import { request } from '@/infrastructure/api/client'
import type { OAuthBindingsResultDto } from '@/infrastructure/dto/profile.dto'
import { toOAuthBindingList } from '@/infrastructure/dto/profile.dto'

export const OAUTH_BINDINGS_QUERY_KEY = ['auth', 'oauth', 'bindings'] as const

/** 当前用户第三方绑定列表（GET /auth/oauth/bindings；JWT 由 client 拦截器注入） */
export async function listOAuthBindings(): Promise<OAuthBinding[]> {
  const dto = await request<OAuthBindingsResultDto>('GET', '/auth/oauth/bindings')
  return toOAuthBindingList(dto?.bindings ?? [])
}

/**
 * 携票据落库（POST /auth/oauth/bindings { bind_ticket }；幂等重复绑定 no-op；
 * 空票据后端 400 兜底，前端保留空值护栏防误提交）。
 */
export async function completeOAuthBinding(bindTicket: string): Promise<void> {
  if (!bindTicket.trim()) throw new Error('绑定票据为空')
  await request('POST', '/auth/oauth/bindings', { bind_ticket: bindTicket })
}

/**
 * 解绑（DELETE /auth/oauth/bindings/{provider_id}；providerId 域为字符串，
 * 路径拼数字 id 由 FastAPI int 路径参数解析；幂等，无绑定行也成功）。
 */
export async function unbindOAuthBinding(providerId: string): Promise<void> {
  await request('DELETE', `/auth/oauth/bindings/${encodeURIComponent(providerId)}`)
}
