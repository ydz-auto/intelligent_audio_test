import { useEffect, useState } from 'react'

import { fetchHomeStatsDetails } from '@/infrastructure/api/home'
import type { HomeStatsDetails } from '@/domain/models/home'
import { usePermissions } from '@/application/hooks/use-permissions'

/**
 * 首页统计 hook（application 层，03_首页.md §7 useHomeStats）。
 * 接线 INT-642：真实接口 GET /home/stats/details（home:read 权限）。
 * 未登录/无 home:read 时不发请求（公开门户页匿名态整条规模条由 stats-bar 替换为
 * 登录引导 §3.2 尾部——不发请求，避免 401 触发 client 会话过期跳转登录）；
 * 已登录后请求失败静默降级（stats 保持 null → 同匿名回退，不阻断整页）。
 */
export type HomeStatsState = {
  stats: HomeStatsDetails | null
}

export function useHomeStats(): HomeStatsState {
  const { user, hasPermission } = usePermissions()
  const canRead = user !== null && hasPermission('home:read')
  const [stats, setStats] = useState<HomeStatsDetails | null>(null)

  useEffect(() => {
    if (!canRead) {
      setStats(null)
      return
    }
    let cancelled = false
    fetchHomeStatsDetails()
      .then((data) => {
        if (!cancelled) setStats(data)
      })
      .catch(() => {
        if (!cancelled) setStats(null)
      })
    return () => {
      cancelled = true
    }
  }, [canRead])

  return { stats }
}
