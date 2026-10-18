/**
 * 全局算法选项（application 层，02_导航栏.md §3.4）。
 * GET /algorithm/options（algorithm:read 门槛）；无码（device_admin/guest）
 * 返回空表——切换器整钮隐藏（隐藏而非置灰）；数据 staleTime 5min。
 *
 * queryKey 用独立前缀 ['shell', ...]：评估域的「关联算法」facet 仍持
 * ['algorithm','options']（evaluation-api → {value,label}），两者契约不同，
 * React Query 按 key 共享缓存，共 key 会导致先填充的一方决定 data 形态、
 * 另一方字段读空白（代码审计 INT-607 P2 同源，INT-715 收敛同一口径）。
 */
import { useQuery } from '@tanstack/react-query'

import { hasPermission } from '@/domain/models/user'
import { fetchAlgorithmOptions } from '@/infrastructure/api/algorithmApi'
import { useAuthStore } from '@/infrastructure/stores/auth-store'

export function useAlgorithmOptions() {
  const user = useAuthStore((s) => s.user)
  const canRead = hasPermission(user, 'algorithm:read')

  const query = useQuery({
    queryKey: ['shell', 'algorithm', 'options'],
    queryFn: fetchAlgorithmOptions,
    staleTime: 5 * 60_000,
    enabled: canRead,
  })

  return {
    options: query.data ?? [],
    isLoading: query.isLoading && !query.data,
    isReadonly: !canRead,
  }
}
