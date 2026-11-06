/**
 * 排行列表/表格双视图选择（localStorage iatp:rankings:v1:view，不入 URL；
 * 14_benchmark排行.md §5.3）。两视图共享同一组数据与筛选。
 */
import { useState } from 'react'

import type { RankingViewMode } from '@/features/rankings/components/metric-group-card'

const VIEW_STORAGE_KEY = 'iatp:rankings:v1:view'

export function useRankingView() {
  const [view, setViewState] = useState<RankingViewMode>(() => {
    if (typeof window === 'undefined') return 'list'
    return window.localStorage.getItem(VIEW_STORAGE_KEY) === 'table'
      ? 'table'
      : 'list'
  })

  const setView = (next: RankingViewMode) => {
    setViewState(next)
    if (typeof window !== 'undefined') {
      window.localStorage.setItem(VIEW_STORAGE_KEY, next)
    }
  }

  return { view, setView }
}
