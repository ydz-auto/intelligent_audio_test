/**
 * 我的收藏用例 hook（application 层，13_个人中心.md §3.3/§7）：
 * GET /favorites 查询 → 三类计数映射（task/report/testcase，per-user）。
 * 收藏格登录即可见；明细行按实体 read 权限码过滤（permission-gate 消费）。
 */
import { useQuery } from '@tanstack/react-query'

import type { FavoriteCounts } from '@/domain/models/profile'
import { FAVORITES_QUERY_KEY, getFavorites } from '@/infrastructure/api/favoritesApi'

export function useFavorites() {
  const favoritesQuery = useQuery({
    queryKey: [...FAVORITES_QUERY_KEY],
    queryFn: getFavorites,
    staleTime: 30_000,
  })

  const counts: FavoriteCounts = favoritesQuery.data ?? {
    task: 0,
    report: 0,
    testcase: 0,
  }

  const total = counts.task + counts.report + counts.testcase

  return {
    counts,
    total,
    isLoading: favoritesQuery.isLoading || favoritesQuery.isPending,
  }
}
