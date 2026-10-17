import { useQuery } from '@tanstack/react-query'

import { hasPermission } from '@/domain/models/user'
import { fetchAlgorithmOptions } from '@/infrastructure/api/algorithm-api'
import { useAuthStore } from '@/infrastructure/stores/auth-store'

/**
 * 全局算法选项 query（application 层，壳 INT-607）。
 * 数据源 GET /algorithm/options（algorithm:read）；无权限（device_admin/guest）
 * 不发起请求（切换器整钮隐藏，此处仅返回空列表供权限判定用）。
 * staleTime 5min（02_导航栏.md §3.4 数据源契约）。
 */
export function useAlgorithmOptions() {
  const user = useAuthStore((s) => s.user)
  const canRead = hasPermission(user, 'algorithm:read')

  const query = useQuery({
    queryKey: ['algorithm', 'options'],
    queryFn: fetchAlgorithmOptions,
    staleTime: 5 * 60_000,
    enabled: canRead,
  })

  return {
    options: query.data ?? [],
    isLoading: query.isLoading,
    isError: query.isError,
    canRead,
  }
}
