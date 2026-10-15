/**
 * 任务域统计 query（application 层）：图表区数据源 + 概览卡 sparkline 派生。
 * granularity 进 queryKey（04_控制台.md §3.7：粒度切换即重查）。
 */
import { useQuery } from '@tanstack/react-query'
import { useMemo } from 'react'

import type { TaskDomainStats, TrendPoint } from '@/domain/models/stats'
import { fetchTaskDomainStats } from '@/infrastructure/api/tasks-api'

export type TrendGranularity = TaskDomainStats['granularity']

const SPARKLINE_BUCKETS = 12

/**
 * trend 按时间均分 12 桶计数（buildSummarySparklines 等价平移，04_控制台.md §3.5）。
 */
export function buildSummarySparklines(trend: TrendPoint[]): number[] {
  const buckets = Array.from({ length: SPARKLINE_BUCKETS }, () => 0)
  for (const [index, point] of trend.entries()) {
    const bucket = Math.min(
      SPARKLINE_BUCKETS - 1,
      Math.floor((index / Math.max(trend.length, 1)) * SPARKLINE_BUCKETS)
    )
    buckets[bucket] += point.count
  }
  return buckets
}

export function useTaskDomainStats(granularity: TrendGranularity) {
  const query = useQuery({
    queryKey: ['tasks', 'domain-stats', granularity],
    queryFn: () => fetchTaskDomainStats(granularity),
    staleTime: 30_000,
  })

  const taskTrendSparkline = useMemo(
    () => buildSummarySparklines(query.data?.trend ?? []),
    [query.data?.trend]
  )

  return { ...query, taskTrendSparkline }
}
