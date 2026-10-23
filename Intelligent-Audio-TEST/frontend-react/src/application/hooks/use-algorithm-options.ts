import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'

import { hasPermission } from '@/domain/models/user'
import { fetchAlgorithmOptions } from '@/infrastructure/api/algorithm-api'
import { useAuthStore } from '@/infrastructure/stores/auth-store'

/**
 * 全局算法选项 query（application 层，壳 INT-607）。
 * 数据源 GET /algorithm/options（algorithm:read）；无权限（device_admin/guest）
 * 不发起请求（切换器整钮隐藏，此处仅返回空列表供权限判定用）。
 * staleTime 5min（02_导航栏.md §3.4 数据源契约）。
 *
 * queryKey 用独立前缀 ['shell', ...]：评估域的「关联算法」facet 仍持
 * ['algorithm','options']（evaluation-api mock → {value,label}），两者契约不同，
 * React Query 按 key 共享缓存，共 key 会导致先填充的一方决定 data 形态、另一方
 * 字段读空白（代码审计 INT-607 P2）。
 */
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
    isLoading: query.isLoading,
    isError: query.isError,
    refetch: query.refetch,
    canRead,
  }
}

/**
 * 算法类型码 → 中文名映射（value→name，取真实 GET /algorithm/options）。
 * 供用例域等无 query 依赖的同步渲染处查名（getAlgorithmLabel(type, labels)），
 * 未登录/无权限时为空表，查名回退原始类型码。
 */
export function useAlgorithmLabelMap(): Record<string, string> {
  const { options } = useAlgorithmOptions()
  return useMemo(
    () => Object.fromEntries(options.map((o) => [o.value, o.name])),
    [options]
  )
}
