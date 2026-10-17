/**
 * 统一合并容器列表 hook（application/tasks/cherry-pick，18_挑选合并交互重设计.md §7.2，INT-600）。
 * merged=true ∪ cherry_pick=true 双查询合并（§11-1 落地前客户端合并；mock 单源）。
 * 「挑选合并」页签计数 + 「合并方式」facet + 溯源数据源。
 */
import { useQuery } from '@tanstack/react-query'

import type { ContainerFilters } from '@/infrastructure/api/cherry-pick-api'
import { fetchCherryPickContainers } from '@/infrastructure/api/cherry-pick-api'

export function useCherryPickContainers(filters: ContainerFilters = {}) {
  const queryKey = ['tasks', 'cherry-picks', filters] as const
  return useQuery({
    queryKey,
    queryFn: () => fetchCherryPickContainers(filters),
    staleTime: 15_000,
  })
}
