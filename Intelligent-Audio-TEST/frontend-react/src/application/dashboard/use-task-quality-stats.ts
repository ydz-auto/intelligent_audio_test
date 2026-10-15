/**
 * 质量统计 query（application 层）：通过率 / 平均得分卡数据源。
 * sparkline mock 序列经本 hook 透出（04_控制台.md §3.6 注记）——
 * feature 层不直触 infrastructure，接线时随 DTO 替换（红线④）。
 */
import { useQuery } from '@tanstack/react-query'

import { fetchTaskQualityStats } from '@/infrastructure/api/tasks-api'
import {
  MOCK_AVG_SCORE_TREND,
  MOCK_PASS_RATE_TREND,
} from '@/infrastructure/mock/dashboard-mock'

export function useTaskQualityStats() {
  const query = useQuery({
    queryKey: ['tasks', 'quality-stats'],
    queryFn: fetchTaskQualityStats,
    staleTime: 30_000,
  })

  return {
    ...query,
    passRateTrend: query.data ? MOCK_PASS_RATE_TREND : undefined,
    averageScoreTrend: query.data ? MOCK_AVG_SCORE_TREND : undefined,
  }
}
