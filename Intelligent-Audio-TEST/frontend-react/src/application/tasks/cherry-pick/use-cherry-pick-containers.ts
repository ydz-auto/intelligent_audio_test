/**
 * 统一合并容器列表 hook（application/tasks/cherry-pick，18_挑选合并交互重设计.md §7.2，INT-600）。
 * merged=true ∪ cherry_pick=true 双查询合并（§11-1 落地前客户端合并；mock 单源）。
 * 「挑选合并」页签计数 + 「合并方式」facet + 溯源数据源。
 *
 * §5.5.3 ③：列表批量已经拉过每个 picked 容器的 source（`fetchCherryPickContainers` 内），
 * 这里把它写进 `['task', id, 'cherry-pick-source']` 缓存，页签行首次展开复用同一 hook
 * （`useContainerComposition`）时只补 1 次 `GET /tasks/{id}` —— 列表首屏零新增请求。
 */
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect } from 'react'

import type { ContainerFilters } from '@/infrastructure/api/cherry-pick-api'
import { fetchCherryPickContainers } from '@/infrastructure/api/cherry-pick-api'

export function useCherryPickContainers(filters: ContainerFilters = {}) {
  const queryClient = useQueryClient()
  // 归一化：`undefined` / 'all' 与「无筛选」等价 → 页签计数处传 {} 与本页传 {mergeType:'all'}
  // 命中同一个 query key，列表首屏只发 1 次列表 + 1 次 source 批量（§5.5.3）
  const normalizedFilters: ContainerFilters = {
    search: filters.search?.trim() || undefined,
    mergeType:
      filters.mergeType && filters.mergeType !== 'all' ? filters.mergeType : undefined,
  }
  const queryKey = ['tasks', 'cherry-picks', normalizedFilters] as const
  const query = useQuery({
    queryKey,
    queryFn: () => fetchCherryPickContainers(normalizedFilters),
    staleTime: 15_000,
  })

  // 把列表已拉到的溯源落到行展开同一个 query key（已有缓存不覆盖，避免顶掉更新鲜的数据）
  const traces = query.data?.traces
  useEffect(() => {
    if (!traces || traces.size === 0) return
    for (const [taskId, trace] of traces) {
      const key = ['task', taskId, 'cherry-pick-source'] as const
      if (queryClient.getQueryData(key) === undefined) {
        queryClient.setQueryData(key, trace)
      }
    }
  }, [traces, queryClient])

  return query
}
