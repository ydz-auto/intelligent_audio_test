/**
 * 质量统计 query（application 层）：完成率卡 sparkline 数据源。
 * 完成率值取 home/stats/details tasks.completed/total（platform-summary 内计算），
 * 本 hook 仅透出完成率近 7 日 mock 趋势序列（04_控制台.md §3.6 注记）——
 * 序列沿用 task.py pass_rate 时序 mock（mock 阶段通过率≈完成率口径），
 * feature 层不直触 infrastructure，接线时随 DTO 替换（红线④）。
 */
import { useQuery } from '@tanstack/react-query'

import { fetchTaskQualityStats } from '@/infrastructure/api/tasks-api'
import { MOCK_PASS_RATE_TREND } from '@/infrastructure/mock/dashboard-mock'

export function useTaskQualityStats() {
  const query = useQuery({
    queryKey: ['tasks', 'quality-stats'],
    queryFn: fetchTaskQualityStats,
    staleTime: 30_000,
  })

  return {
    ...query,
    passRateTrend: query.data ? MOCK_PASS_RATE_TREND : undefined,
  }
}
