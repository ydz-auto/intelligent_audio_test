import { useQuery } from '@tanstack/react-query'

import { fetchHomeStatsDetails } from '@/infrastructure/api/home'
import { useAuthStore } from '@/infrastructure/stores/auth-store'


/**
 * 首页统计 hook（application 层，03_首页.md §7 useHomeStats）。
 * 复用工作台 details query（['home','stats-details'] 同 key 共享缓存，避免门户页重复拉取）；
 * 未登录（home:read 401/403）时 query 进入 error 态，消费端按 usePermissions 降级 anonymous。
 * INT-1225：enabled=登录态——匿名不拉取（401 无意义且落控制台 SEVERE），
 * 规模条按「未登录整条替换为登录引导」降级（03_首页.md §3.1/§5）。
 */
export function useHomeStats() {
  const user = useAuthStore((s) => s.user)
  return useQuery({
    queryKey: ['home', 'stats-details'],
    queryFn: fetchHomeStatsDetails,
    staleTime: 30_000,
    enabled: !!user,
  })
}
