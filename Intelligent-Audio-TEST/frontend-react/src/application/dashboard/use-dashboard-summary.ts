/**
 * 工作台摘要 query（application 层）：最近任务 / 用例分组排行（04_控制台.md §3.3）。
 */
import { useQuery } from '@tanstack/react-query'

import { fetchHomeStatsSummary } from '@/infrastructure/api/home-api'

export function useDashboardSummary() {
  return useQuery({
    queryKey: ['home', 'stats-summary'],
    queryFn: fetchHomeStatsSummary,
    staleTime: 30_000,
  })
}
