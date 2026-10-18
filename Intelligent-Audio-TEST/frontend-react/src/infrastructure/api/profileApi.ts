/**
 * 个人中心第三方绑定 API（infrastructure/api 层；INT-733 个人中心 mock 残留清除）。
 * 契约对位 13_个人中心.md §2.0（oauth_bp.py:114-149 实测）：
 *  - 绑定列表 GET /auth/oauth/bindings → data { bindings: [{ provider_id, provider_name,
 *    provider_slug, provider_icon, provider_user_id }] }（端点内自验用户态，登录即可）
 *  - 绑定 POST /auth/oauth/bindings body { bind_ticket }（幂等 no-op）
 *  - 解绑 DELETE /auth/oauth/bindings/{provider_id}（幂等，无绑定行也成功）
 *  - 提供方列表 GET /auth/oauth/providers（公开）→ 复用 authApi.listPublicOAuthProviders
 * snake_case↔camelCase 收敛在本文件（infrastructure 层）；绑定授权跳转 authApi.beginOAuthAuthorize（slug,'bind'）。
 */
import type { OAuthBinding } from '@/domain/models/profile'
import { apiClient } from '@/infrastructure/api/client'

export const OAUTH_BINDINGS_QUERY_KEY = ['auth', 'oauth', 'bindings'] as const

/** GET /auth/oauth/bindings 列表项 DTO（snake_case 唯一出现层） */
interface OAuthBindingDto {
  provider_id: string | number
  provider_name: string
  provider_slug: string
  provider_icon: string
  provider_user_id: string
}

/** DTO → Domain 适配：provider_id 归一为 string（对齐提供方列表 String(id) 口径） */
function toOAuthBinding(dto: OAuthBindingDto): OAuthBinding {
  return {
    providerId: String(dto.provider_id),
    providerName: dto.provider_name ?? '',
    providerSlug: dto.provider_slug ?? '',
    providerIcon: dto.provider_icon ?? '',
    providerUserId: dto.provider_user_id ?? '',
  }
}

/** 绑定列表（GET /auth/oauth/bindings；登录即可，端点内自验用户态） */
export async function listOAuthBindings(): Promise<OAuthBinding[]> {
  const dto = await apiClient.get<{ bindings?: OAuthBindingDto[] }>(
    '/auth/oauth/bindings'
  )
  return (dto?.bindings ?? []).map(toOAuthBinding)
}

/** 携票据落库（POST /auth/oauth/bindings { bind_ticket }；幂等重复绑定 no-op） */
export async function completeOAuthBinding(bindTicket: string): Promise<void> {
  if (!bindTicket.trim()) throw new Error('绑定票据为空')
  await apiClient.post('/auth/oauth/bindings', { bind_ticket: bindTicket })
}

/** 解绑（DELETE /auth/oauth/bindings/{provider_id}；幂等，无绑定行也成功） */
export async function unbindOAuthBinding(providerId: string): Promise<void> {
  await apiClient.delete(`/auth/oauth/bindings/${providerId}`)
}
