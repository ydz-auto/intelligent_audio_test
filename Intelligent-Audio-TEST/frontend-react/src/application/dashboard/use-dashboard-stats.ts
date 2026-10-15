/**
 * 工作台统计 query（application 层）。
 * staleTime 30s：对齐 newAPI overview 快照缓存口径（04_控制台.md §3.3），
 * 路由往返不重复拉取；失败由调用方逐卡降级，不阻断整页。
 */
import { useQuery } from '@tanstack/react-query'

// details 复用基座桩（INT-377 infrastructure/api/home.ts），本卡不重复建桩
import { fetchHomeStatsDetails } from '@/infrastructure/api/home'

export function useDashboardStats() {
  return useQuery({
    queryKey: ['home', 'stats-details'],
    queryFn: fetchHomeStatsDetails,
    staleTime: 30_000,
  })
}
