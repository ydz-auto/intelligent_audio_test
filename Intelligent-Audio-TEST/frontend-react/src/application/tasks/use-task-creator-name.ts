/**
 * 任务创建人显示名 query（application 层，INT-2446）。
 *
 * 任务详情接口（GET /tasks/{id}）只回 `created_by_user_id`、不回姓名，故由本 hook
 * 经真实用户详情接口 GET /auth/users/{id} 解析显示名（display_name 缺省兜底
 * username，toPlatformUser 已处理）。口径：
 * - 无 id / 未登录无 `user:read` 权限 → 不发请求，返回 null（页面回退「用户 #id」）；
 * - 查询失败（403 / 404 / 网络）→ retry 0 不重试，返回 null，页面同样回退 id 口径，
 *   不写死任何假名（devloop §3.2 无 mock 残留）。
 * - queryKey 与用户管理抽屉的详情 query 同形（USERS_QUERY_KEY + 'detail' + id），
 *   共享缓存，不重复请求同一用户。
 */
import { useQuery } from '@tanstack/react-query'

import { usePermissions } from '@/application/hooks/use-permissions'
import { getUser, USERS_QUERY_KEY } from '@/infrastructure/api/userApi'

export function useTaskCreatorName(
  createdByUserId: number | null | undefined
): string | null {
  const { hasPermission } = usePermissions()
  const userId = createdByUserId != null ? String(createdByUserId) : null
  const { data } = useQuery({
    queryKey: [...USERS_QUERY_KEY, 'detail', userId],
    queryFn: () => getUser(userId as string),
    enabled: userId != null && hasPermission('user:read'),
    staleTime: 5 * 60_000,
    retry: 0,
  })
  const name = data?.displayName?.trim() || data?.username?.trim()
  return name || null
}
