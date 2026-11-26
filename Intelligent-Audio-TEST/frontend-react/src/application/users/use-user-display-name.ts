/**
 * 用户 ID → 显示名 query（application 层）。
 *
 * 列表/卡片接口只回 user_id、不回姓名（任务、用例等列表均如此），统一在此经
 * 真实用户详情接口 GET /auth/users/{id} 解析显示名（display_name 缺省兜底 username，
 * toPlatformUser 已处理）。口径（沿用 INT-2446）：
 * - 无 id / 未登录无 `user:read` 权限 → 不发请求，返回 null（调用方回退「用户#id」）；
 * - 查询失败（403 / 404 / 网络）→ retry 0 不重试，返回 null，不写死任何假名；
 * - queryKey 与用户管理抽屉的详情 query 同形（USERS_QUERY_KEY + 'detail' + id），
 *   共享 5 分钟缓存，同一用户多处展示不重复请求。
 */
import { useQuery } from '@tanstack/react-query'

import { usePermissions } from '@/application/hooks/use-permissions'
import { getUser, USERS_QUERY_KEY } from '@/infrastructure/api/userApi'

export function useUserDisplayName(
  userId: number | null | undefined
): string | null {
  const { hasPermission } = usePermissions()
  const id = userId != null ? String(userId) : null
  const { data } = useQuery({
    queryKey: [...USERS_QUERY_KEY, 'detail', id],
    queryFn: () => getUser(id as string),
    enabled: id != null && hasPermission('user:read'),
    staleTime: 5 * 60_000,
    retry: 0,
  })
  const name = data?.displayName?.trim() || data?.username?.trim()
  return name || null
}
