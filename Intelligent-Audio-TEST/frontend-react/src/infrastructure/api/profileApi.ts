/**
 * 个人中心第三方绑定 API 桩（infrastructure 层，红线④：mock 常量）。
 * 契约对位 13_个人中心.md §2.0（oauth_bp.py 实测）：
 *  - 绑定列表 GET /auth/oauth/bindings（登录即可，端点内自验用户态）
 *  - 绑定 POST /auth/oauth/bindings body { bind_ticket }（幂等 no-op）
 *  - 解绑 DELETE /auth/oauth/bindings/{provider_id}（幂等，无绑定行也成功）
 *  - 提供方列表 GET /auth/oauth/providers（公开）→ 复用 authApi.listPublicOAuthProviders
 *  TODO(API 接线): 以上端点落真实实现；绑定授权跳转 authApi.beginOAuthAuthorize（slug,'bind'）。
 */
import type { OAuthBinding } from '@/domain/models/profile'
import { MOCK_OAUTH_BINDINGS } from '@/infrastructure/mock/profile-mock'

export const OAUTH_BINDINGS_QUERY_KEY = ['auth', 'oauth', 'bindings'] as const

/** 绑定列表桩。TODO(API 接线): GET /auth/oauth/bindings */
export async function listOAuthBindings(): Promise<OAuthBinding[]> {
  return [...MOCK_OAUTH_BINDINGS]
}

/**
 * 携票据落库（绑定回调回传 bind_ticket → 落库）。
 * TODO(API 接线): POST /auth/oauth/bindings { bind_ticket }；幂等重复绑定 no-op。
 */
export async function completeOAuthBinding(bindTicket: string): Promise<void> {
  if (!bindTicket.trim()) throw new Error('绑定票据为空')
  // mock：演示绑定成功（回调跳转未接线时不会被触发；预留落库路径）
  return Promise.resolve()
}

/** 解绑桩。TODO(API 接线): DELETE /auth/oauth/bindings/{provider_id} */
export async function unbindOAuthBinding(providerId: string): Promise<void> {
  const index = MOCK_OAUTH_BINDINGS.findIndex(
    (binding) => binding.providerId === providerId
  )
  if (index !== -1) MOCK_OAUTH_BINDINGS.splice(index, 1)
  return Promise.resolve()
}
