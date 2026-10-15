import { useEffect, useState } from 'react'

import { fetchHomeStatsDetails } from '@/infrastructure/api/home'
import type { HomeStatsDetails } from '@/domain/models/home'

/**
 * 首页统计 hook（application 层，03_首页.md §7 useHomeStats）。
 * 红线④：mock 直返；未登录降级（anonymous 态）由消费端按 usePermissions 判定——
 * 真实接口 home:read 未登录为 403，规模条整条替换为登录引导（§3.2 尾部）。
 * TODO(API 接线): useQuery(['home','stats-details']) + 403 → anonymous。
 */

export type HomeStatsState = {
  stats: HomeStatsDetails | null
}

export function useHomeStats(): HomeStatsState {
  const [stats, setStats] = useState<HomeStatsDetails | null>(null)

  useEffect(() => {
    let cancelled = false
    // mock 同步返回，此处仍按异步约定消费，接线时换 useQuery 即可
    fetchHomeStatsDetails().then((data) => {
      if (!cancelled) setStats(data)
    })
    return () => {
      cancelled = true
    }
  }, [])

  return { stats }
}
