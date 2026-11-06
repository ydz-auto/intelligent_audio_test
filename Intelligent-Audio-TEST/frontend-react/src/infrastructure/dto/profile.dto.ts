/**
 * 个人中心 DTO（infrastructure/dto 层；snake_case ↔ camelCase 唯一转换层）。
 * 对照 api_gateway oauth_bp.py / favorite_trash_bp.py 响应契约：
 *  - GET /auth/oauth/bindings → { bindings: [{ provider_id, provider_name,
 *    provider_slug, provider_icon, provider_user_id }] }（INT-147 实测）
 *  - POST /auth/oauth/bindings { bind_ticket } → 空 data（幂等 no-op）
 *  - DELETE /auth/oauth/bindings/{provider_id} → 空 data（幂等，无绑定行也成功）
 *  - GET /favorites → data: { task: [ids], report: [ids], testcase: [ids] }
 */
import type { FavoriteCounts, OAuthBinding } from '@/domain/models/profile'

/** 第三方账号绑定行（GET/POST /auth/oauth/bindings；provider_id 为提供方 DB id） */
export interface OAuthBindingDto {
  provider_id: number
  provider_name: string
  provider_slug: string
  provider_icon: string
  provider_user_id: string
}

/** GET /auth/oauth/bindings 信封内层 */
export interface OAuthBindingsResultDto {
  bindings: OAuthBindingDto[]
}

/** GET /favorites → data（三类实体 id 数组，计数取 length） */
export interface FavoriteIdsDto {
  task: string[]
  report: string[]
  testcase: string[]
}

/** 绑定行 → Domain OAuthBinding（providerId 数值转字符串，与 OAuthProvider.id 同口径） */
export function toOAuthBinding(raw: OAuthBindingDto): OAuthBinding {
  return {
    providerId: String(raw.provider_id),
    providerName: raw.provider_name ?? '',
    providerSlug: raw.provider_slug ?? '',
    providerIcon: raw.provider_icon ?? '',
    providerUserId: raw.provider_user_id ?? '',
  }
}

/** GET /auth/oauth/bindings 内嵌列表 → Domain OAuthBinding[] */
export function toOAuthBindingList(raw: OAuthBindingDto[]): OAuthBinding[] {
  return (raw ?? []).map(toOAuthBinding)
}

/** GET /favorites data → 三类计数（length；缺省数组兜底 0） */
export function toFavoriteCounts(raw: FavoriteIdsDto): FavoriteCounts {
  return {
    task: raw?.task?.length ?? 0,
    report: raw?.report?.length ?? 0,
    testcase: raw?.testcase?.length ?? 0,
  }
}
