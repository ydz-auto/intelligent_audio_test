import { useQuery } from '@tanstack/react-query'

import { fetchHomeStatsDetails } from '@/infrastructure/api/home'


/**
 * 首页统计 hook（application 层，03_首页.md §7 useHomeStats）。
 * 复用工作台 details query（['home','stats-details'] 同 key 共享缓存，避免门户页重复拉取）；
 * 未登录（home:read 403）时 query 进入 error 态，消费端按 usePermissions 降级 anonymous。
 */
export function useHomeStats() {
  return useQuery({
    queryKey: ['home', 'stats-details'],
    queryFn: fetchHomeStatsDetails,
    staleTime: 30_000,
  })
}
